"""Reads the CSV/JSON artefacts the engine wrote for a session."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import pandas as pd

from ..models import RunResult, SessionInfo, SheetResult, SheetStatus
from .engine import OUTCOMES_FILE

_FIXED_COLUMNS = 4  # file_id, input_path, output_path, score


def _read_csv(path: Optional[Path]) -> pd.DataFrame:
    if path is None or not path.is_file():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _parse_score(raw: str) -> Optional[float]:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


class ResultsReader:
    def read(self, info: SessionInfo) -> RunResult:
        out = info.root / "output"
        outcomes_path = out / OUTCOMES_FILE
        outcomes: dict[str, dict[str, str]] = (
            json.loads(outcomes_path.read_text(encoding="utf-8")) if outcomes_path.is_file() else {}
        )
        result_files = sorted((out / "Results").glob("Results_*.csv"), key=lambda p: p.stat().st_mtime)
        frames = {
            "ok": _read_csv(result_files[-1] if result_files else None),
            "multi": _read_csv(out / "Manual" / "MultiMarkedFiles.csv"),
            "error": _read_csv(out / "Manual" / "ErrorFiles.csv"),
        }
        columns: list[str] = []
        for frame in frames.values():
            if len(frame.columns) > _FIXED_COLUMNS:
                columns = list(frame.columns[_FIXED_COLUMNS:])
                break

        sheets: list[SheetResult] = []
        for kind, frame in frames.items():
            for row in frame.to_dict("records"):
                file_id = row["file_id"]
                outcome = outcomes.get(file_id, {})
                if kind == "error":
                    status = SheetStatus.ERROR
                elif kind == "multi" or outcome.get("status") == "multi":
                    status = SheetStatus.MULTI_MARKED
                else:
                    status = SheetStatus.PROCESSED
                marked = out / "CheckedOMRs" / file_id
                source = Path(row.get("input_path", ""))
                sheets.append(SheetResult(
                    file_id=file_id,
                    status=status,
                    score=_parse_score(row.get("score", "")) if info.graded and kind == "ok" else None,
                    answers={c: row.get(c, "") for c in columns},
                    source_path=source if source.is_file() else None,
                    marked_path=marked if marked.is_file() else None,
                    message=outcome.get("message", ""),
                ))

        order = {name: i for i, name in enumerate(outcomes)}
        sheets.sort(key=lambda s: order.get(s.file_id, len(order)))
        return RunResult(session=info, columns=columns, sheets=sheets)
