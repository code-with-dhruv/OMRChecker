"""Adapter around the OMRChecker engine.

Re-uses the engine's own building blocks (template, evaluation, per-sheet
processing) but drives the loop itself so the GUI gets progress reporting,
cancellation and per-sheet error isolation - one bad scan never aborts a batch.
"""
from __future__ import annotations

import json
import logging
import tempfile
from csv import QUOTE_NONNUMERIC
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from ..models import RunOptions, SessionInfo, TemplateInfo
from ..paths import CONFIG_FILE, EVALUATION_FILE, TEMPLATE_FILE, is_supported_sheet

OUTCOMES_FILE = "outcomes.json"


class EngineError(Exception):
    """Failure with a user-facing message."""


class RunCancelled(Exception):
    """Raised when the user cancels a running batch."""


@dataclass
class EngineHooks:
    on_log: Callable[[str, str], None] = lambda level, message: None
    on_progress: Callable[[int, int], None] = lambda done, total: None
    is_cancelled: Callable[[], bool] = lambda: False


@dataclass
class _Outcomes:
    items: dict[str, dict[str, str]] = field(default_factory=dict)

    def add(self, file_id: str, status: str, message: str = "") -> None:
        self.items[file_id] = {"status": status, "message": message}

    def save(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / OUTCOMES_FILE).write_text(json.dumps(self.items, indent=2), encoding="utf-8")


class _LogRelay(logging.Handler):
    def __init__(self, hooks: EngineHooks, level: int) -> None:
        super().__init__(level)
        self._hooks = hooks

    def emit(self, record: logging.LogRecord) -> None:
        self._hooks.on_log(record.levelname, record.getMessage())


def _deep_update(base: dict, overrides: dict) -> dict:
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def build_config(base_config: Optional[Path], options: RunOptions) -> dict[str, Any]:
    config: dict[str, Any] = {}
    if base_config and base_config.is_file():
        config = json.loads(base_config.read_text(encoding="utf-8-sig"))
    overrides: dict[str, Any] = {
        # GUI must never open OpenCV windows; results are shown in-app instead.
        "outputs": {
            "show_image_level": 0,
            "save_detections": True,
            "filter_out_multimarked_files": options.hold_multi_marked,
        }
    }
    if options.auto_align:
        overrides["alignment_params"] = {"auto_align": True}
    return _deep_update(config, overrides)


class OMREngine:
    # ------------------------------------------------------------------ #
    def execute(self, session: SessionInfo, options: RunOptions, hooks: EngineHooks) -> None:
        """Process every sheet staged in ``session.root / 'input'``."""
        import pandas as pd

        from src import entry
        from src.evaluation import EvaluationConfig
        from src.logger import logger
        from src.template import Template
        from src.utils.file import Paths, setup_dirs_for_paths, setup_outputs_for_template
        from src.utils.image import ImageUtils
        from src.utils.parsing import open_config_with_defaults

        input_dir = (session.root / "input").resolve()
        output_dir = session.root / "output"
        config_path = input_dir / CONFIG_FILE
        config_path.write_text(json.dumps(build_config(config_path, options), indent=2), encoding="utf-8")

        relay = _LogRelay(hooks, logging.DEBUG if options.verbose else logging.INFO)
        logger.log.addHandler(relay)
        outcomes = _Outcomes()
        try:
            try:
                tuning = open_config_with_defaults(config_path)
                template = Template(input_dir / TEMPLATE_FILE, tuning)
                evaluation = None
                if (input_dir / EVALUATION_FILE).exists():
                    evaluation = EvaluationConfig(input_dir, input_dir / EVALUATION_FILE, template, tuning)
            except (Exception, SystemExit) as exc:
                raise EngineError(f"Template configuration failed: {exc or 'see log'}") from exc

            excluded = {Path(p).resolve() for step in template.pre_processors for p in step.exclude_files()}
            if evaluation:
                excluded |= {Path(p).resolve() for p in evaluation.get_exclude_files()}
            sheets = sorted(f for f in input_dir.iterdir() if is_supported_sheet(f) and f.resolve() not in excluded)
            if not sheets:
                raise EngineError("There are no OMR sheets to process.")

            paths = Paths(output_dir)
            setup_dirs_for_paths(paths)
            ns = setup_outputs_for_template(paths, template)
            entry.STATS.files_not_moved = 0

            def record_error(name: str, source: Path, message: str, write_row: bool = True) -> None:
                outcomes.add(name, "error", message)
                if write_row:
                    row = [name, str(source), "NA", "NA"] + ns.empty_resp
                    pd.DataFrame(row, dtype=str).T.to_csv(
                        ns.files_obj["Errors"], mode="a", quoting=QUOTE_NONNUMERIC, header=False, index=False)

            counter = 0
            for done, sheet in enumerate(sheets):
                if hooks.is_cancelled():
                    raise RunCancelled()
                hooks.on_progress(done, len(sheets))
                try:
                    images = ImageUtils.load_omr_image(sheet, tuning)
                except Exception as exc:  # noqa: BLE001 - isolate corrupt files
                    record_error(sheet.name, sheet, f"File could not be read: {exc}")
                    continue
                if not images:
                    record_error(sheet.name, sheet, "File could not be read.")
                    continue
                for name, image in images:
                    counter += 1
                    if image is None:
                        record_error(name, sheet, "Image could not be decoded.")
                        continue
                    try:
                        multi = entry._process_single_image(  # noqa: SLF001
                            sheet, name, image, template, tuning, evaluation, ns, counter)
                    except Exception as exc:  # noqa: BLE001
                        logger.error(f"Failed to process '{name}': {exc}")
                        record_error(name, sheet, f"Processing failed: {exc}")
                        continue
                    if multi is None:
                        record_error(name, sheet, "Page or alignment markers could not be detected.", write_row=False)
                    else:
                        outcomes.add(name, "multi" if multi else "ok", "Multiple bubbles marked in a question." if multi else "")
            hooks.on_progress(len(sheets), len(sheets))
        finally:
            logger.log.removeHandler(relay)
            outcomes.save(output_dir)

    # ------------------------------------------------------------------ #
    def preview_layout(self, template: TemplateInfo, sheet: Path, options: RunOptions):
        """Draw the template's bubble layout over a sheet (replacement for ``--setLayout``)."""
        from src.template import Template
        from src.utils.image import ImageUtils
        from src.utils.parsing import open_config_with_defaults

        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / CONFIG_FILE
            cfg_path.write_text(json.dumps(build_config(template.path / CONFIG_FILE, options)), encoding="utf-8")
            try:
                tuning = open_config_with_defaults(cfg_path)
                tpl = Template(template.path / TEMPLATE_FILE, tuning)
            except (Exception, SystemExit) as exc:
                raise EngineError(f"Template could not be loaded: {exc or 'see log'}") from exc

        previews = []
        for name, image in ImageUtils.load_omr_image(sheet, tuning):
            if image is None:
                raise EngineError("The selected file could not be decoded as an image.")
            prepared = tpl.image_instance_ops.apply_preprocessors(str(sheet), image, tpl)
            if prepared is None:
                raise EngineError("Page or alignment markers could not be detected on this sheet.")
            previews.append((name, tpl.image_instance_ops.draw_template_layout(prepared, tpl, shifted=False, border=2)))
        if not previews:
            raise EngineError("Nothing to preview - the file could not be read.")
        return previews
