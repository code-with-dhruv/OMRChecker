"""Template library: import, validate, list and remove OMR templates.

A template is stored as a *flat* folder (template.json, optional config.json /
evaluation.json and the assets they reference). Flattening keeps the engine from
treating nested asset folders as extra batches of OMR sheets.
"""
from __future__ import annotations

import filecmp
import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..models import TemplateInfo
from ..paths import CONFIG_FILE, EVALUATION_FILE, TEMPLATE_FILE

META_FILE = "template_meta.json"
_TEMPLATE_ASSET_KEYS = ("relativePath", "reference")
_EVALUATION_ASSET_KEYS = ("answer_key_csv_path", "answer_key_image_path")
_DEFAULT_MARKER = "omr_marker.jpg"


class TemplateError(Exception):
    """A template could not be imported or validated (message is user-facing)."""


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise TemplateError(f"File not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise TemplateError(
            f"'{path.name}' is not valid JSON (line {exc.lineno}, column {exc.colno}): {exc.msg}"
        ) from None
    if not isinstance(data, dict):
        raise TemplateError(f"'{path.name}' must contain a JSON object.")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return slug or "template"


def _copy_flat(src: Path, dest_dir: Path) -> str:
    """Copy *src* into *dest_dir* (no sub-folders); return the stored file name."""
    name, candidate, counter = src.name, dest_dir / src.name, 1
    while candidate.exists() and not filecmp.cmp(src, candidate, shallow=False):
        candidate = dest_dir / f"{src.stem}_{counter}{src.suffix}"
        name, counter = candidate.name, counter + 1
    if not candidate.exists():
        shutil.copy2(src, candidate)
    return name


def _require_file(base: Path, relative: str, owner: str) -> Path:
    path = (base / relative).resolve()
    if not path.is_file():
        raise TemplateError(
            f"{owner} refers to '{relative}', but that file was not found next to it."
        )
    return path


def _flatten_template_assets(template: dict, source_dir: Path, dest_dir: Path) -> None:
    for step in template.get("preProcessors", []) or []:
        options = step.get("options")
        if not isinstance(options, dict):
            continue
        if step.get("name") == "CropOnMarkers" and "relativePath" not in options:
            _copy_flat(_require_file(source_dir, _DEFAULT_MARKER, "Marker detection"), dest_dir)
            continue
        for key in _TEMPLATE_ASSET_KEYS:
            if options.get(key):
                src = _require_file(source_dir, options[key], f"Pre-processor '{step.get('name')}'")
                options[key] = _copy_flat(src, dest_dir)


def _flatten_evaluation_assets(evaluation: dict, source_dir: Path, dest_dir: Path) -> None:
    options = evaluation.get("options")
    if not isinstance(options, dict):
        return
    for key in _EVALUATION_ASSET_KEYS:
        if not options.get(key):
            continue
        candidate = source_dir / options[key]
        if not candidate.is_file():
            # The engine tolerates a missing CSV when an answer-key image exists.
            if key == "answer_key_csv_path" and options.get("answer_key_image_path"):
                continue
            raise TemplateError(f"The answer key file '{options[key]}' was not found.")
        options[key] = _copy_flat(candidate, dest_dir)


def _summarise(staged: Path) -> dict[str, Any]:
    """Validate a staged template with the real engine and return display metadata."""
    from src.defaults import CONFIG_DEFAULTS
    from src.evaluation import EvaluationConfig
    from src.template import Template
    from src.utils.parsing import open_config_with_defaults

    try:
        config_path = staged / CONFIG_FILE
        tuning = open_config_with_defaults(config_path) if config_path.exists() else CONFIG_DEFAULTS
        template = Template(staged / TEMPLATE_FILE, tuning)
    except (Exception, SystemExit) as exc:  # engine may call exit()
        raise TemplateError(f"The template is not valid: {exc or 'see the log for details'}") from exc

    summary: dict[str, Any] = {
        "page_dimensions": list(template.page_dimensions),
        "field_count": len(template.output_columns),
        "preprocessors": [p.__class__.__name__ for p in template.pre_processors],
        "has_answer_key": False,
        "question_count": None,
    }
    evaluation_path = staged / EVALUATION_FILE
    if evaluation_path.exists():
        try:
            evaluation = EvaluationConfig(staged, evaluation_path, template, tuning)
        except (Exception, SystemExit) as exc:
            raise TemplateError(f"The answer key is not valid: {exc or 'see the log for details'}") from exc
        summary["has_answer_key"] = True
        questions = getattr(evaluation, "questions_in_order", None)
        summary["question_count"] = len(questions) if questions else None
    return summary


# --------------------------------------------------------------------------- #
# library
# --------------------------------------------------------------------------- #
class TemplateLibrary:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._staging = root / ".staging"
        root.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(self._staging, ignore_errors=True)  # leftovers from a crash

    # ---- queries -------------------------------------------------------- #
    def list(self) -> list[TemplateInfo]:
        infos = []
        for folder in sorted(p for p in self._root.iterdir() if p.is_dir() and not p.name.startswith(".")):
            info = self._load_info(folder)
            if info:
                infos.append(info)
        return sorted(infos, key=lambda t: t.name.lower())

    def get(self, template_id: str) -> TemplateInfo:
        info = self._load_info(self._root / template_id)
        if info is None:
            raise TemplateError("That template no longer exists.")
        return info

    # ---- commands ------------------------------------------------------- #
    def import_template(self, template_json: Path, name: Optional[str] = None,
                        evaluation_json: Optional[Path] = None) -> TemplateInfo:
        """Import ``template.json`` (plus sibling config/evaluation/assets)."""
        template_json = Path(template_json)
        if template_json.is_dir():
            template_json = template_json / TEMPLATE_FILE
        source_dir = template_json.parent
        template = _read_json(template_json)

        stage = self._new_stage()
        try:
            _flatten_template_assets(template, source_dir, stage)
            _write_json(stage / TEMPLATE_FILE, template)

            sibling_config = source_dir / CONFIG_FILE
            if sibling_config.is_file():
                _write_json(stage / CONFIG_FILE, _read_json(sibling_config))

            evaluation_src = Path(evaluation_json) if evaluation_json else source_dir / EVALUATION_FILE
            if evaluation_src.is_file():
                self._stage_evaluation(stage, evaluation_src)

            summary = _summarise(stage)
            display_name = (name or source_dir.name or "Template").strip()
            template_id = self._unique_id(_slugify(display_name))
            self._write_meta(stage, display_name, summary)
            stage.replace(self._root / template_id)
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        return self.get(template_id)

    def set_answer_key(self, template_id: str, evaluation_json: Path) -> TemplateInfo:
        current = self._root / template_id
        if not current.is_dir():
            raise TemplateError("That template no longer exists.")
        stage = self._new_stage()
        try:
            shutil.copytree(current, stage, dirs_exist_ok=True)
            (stage / EVALUATION_FILE).unlink(missing_ok=True)
            self._stage_evaluation(stage, Path(evaluation_json))
            summary = _summarise(stage)
            meta = json.loads((current / META_FILE).read_text(encoding="utf-8"))
            self._write_meta(stage, meta["name"], summary, created_at=meta["created_at"])
            self._swap(current, stage)
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        return self.get(template_id)

    def remove_answer_key(self, template_id: str) -> TemplateInfo:
        current = self._root / template_id
        evaluation = current / EVALUATION_FILE
        if evaluation.exists():
            evaluation.unlink()
            meta_path = current / META_FILE
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta.update(has_answer_key=False, question_count=None)
            _write_json(meta_path, meta)
        return self.get(template_id)

    def remove(self, template_id: str) -> None:
        target = self._root / template_id
        if target.is_dir():
            shutil.rmtree(target)

    # ---- internals ------------------------------------------------------ #
    def _new_stage(self) -> Path:
        stage = self._staging / uuid.uuid4().hex
        stage.mkdir(parents=True)
        return stage

    def _unique_id(self, base: str) -> str:
        candidate, n = base, 2
        while (self._root / candidate).exists():
            candidate, n = f"{base}-{n}", n + 1
        return candidate

    def _stage_evaluation(self, stage: Path, evaluation_src: Path) -> None:
        evaluation = _read_json(evaluation_src)
        _flatten_evaluation_assets(evaluation, evaluation_src.parent, stage)
        _write_json(stage / EVALUATION_FILE, evaluation)

    def _swap(self, current: Path, stage: Path) -> None:
        retired = self._staging / f"old-{uuid.uuid4().hex}"
        current.replace(retired)
        try:
            stage.replace(current)
        except BaseException:
            retired.replace(current)  # roll back
            raise
        shutil.rmtree(retired, ignore_errors=True)

    @staticmethod
    def _write_meta(folder: Path, name: str, summary: dict, created_at: Optional[str] = None) -> None:
        _write_json(folder / META_FILE, {
            "name": name,
            "created_at": created_at or datetime.now().isoformat(timespec="seconds"),
            **summary,
        })

    @staticmethod
    def _load_info(folder: Path) -> Optional[TemplateInfo]:
        meta_path = folder / META_FILE
        if not meta_path.is_file() or not (folder / TEMPLATE_FILE).is_file():
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return TemplateInfo(
                id=folder.name,
                name=meta["name"],
                path=folder,
                created_at=datetime.fromisoformat(meta["created_at"]),
                page_dimensions=tuple(meta["page_dimensions"]),
                field_count=int(meta["field_count"]),
                preprocessors=tuple(meta["preprocessors"]),
                has_answer_key=bool(meta["has_answer_key"]),
                question_count=meta.get("question_count"),
            )
        except (KeyError, ValueError, json.JSONDecodeError):
            return None
