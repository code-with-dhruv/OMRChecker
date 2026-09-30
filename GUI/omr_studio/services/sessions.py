"""Processing sessions: one folder per run holding staged input, output and metadata."""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from ..models import RunOptions, SessionInfo, SessionState, TemplateInfo
from .templates import META_FILE

SESSION_FILE = "session.json"


def _unique_name(folder: Path, name: str) -> str:
    candidate, counter, stem, suffix = name, 1, Path(name).stem, Path(name).suffix
    while (folder / candidate).exists():
        candidate, counter = f"{stem}_{counter}{suffix}", counter + 1
    return candidate


class SessionStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        root.mkdir(parents=True, exist_ok=True)

    # ---- lifecycle ------------------------------------------------------ #
    def create(self, template: TemplateInfo, sheets: Iterable[Path], options: RunOptions) -> SessionInfo:
        sheets = list(sheets)
        session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        folder = self._root / session_id
        suffix = 1
        while folder.exists():
            suffix += 1
            folder = self._root / f"{session_id}-{suffix}"
        input_dir = folder / "input"
        input_dir.mkdir(parents=True)

        for asset in template.path.iterdir():
            if asset.is_file() and asset.name != META_FILE:
                shutil.copy2(asset, input_dir / asset.name)
        for sheet in sheets:
            shutil.copy2(sheet, input_dir / _unique_name(input_dir, sheet.name))

        info = SessionInfo(
            id=folder.name, root=folder, template_id=template.id, template_name=template.name,
            created_at=datetime.now(), sheet_count=len(sheets), state=SessionState.RUNNING,
            graded=template.has_answer_key,
        )
        self._write(info, options=options.to_dict())
        return info

    def finish(self, info: SessionInfo, state: SessionState, duration: float, message: str = "") -> SessionInfo:
        updated = SessionInfo(**{**info.__dict__, "state": state, "duration_seconds": round(duration, 2)})
        self._write(updated, message=message)
        return updated

    # ---- queries -------------------------------------------------------- #
    def list(self) -> list[SessionInfo]:
        infos = [i for i in (self._read(p) for p in self._root.iterdir() if p.is_dir()) if i]
        return sorted(infos, key=lambda i: i.created_at, reverse=True)

    def get(self, session_id: str) -> Optional[SessionInfo]:
        return self._read(self._root / session_id)

    def delete(self, session_id: str) -> None:
        shutil.rmtree(self._root / session_id, ignore_errors=True)

    # ---- persistence ---------------------------------------------------- #
    @staticmethod
    def _write(info: SessionInfo, **extra) -> None:
        path = info.root / SESSION_FILE
        previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        payload = {
            **previous,
            "id": info.id,
            "template_id": info.template_id,
            "template_name": info.template_name,
            "created_at": info.created_at.isoformat(timespec="seconds"),
            "sheet_count": info.sheet_count,
            "state": info.state.value,
            "graded": info.graded,
            "duration_seconds": info.duration_seconds,
            **extra,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _read(folder: Path) -> Optional[SessionInfo]:
        path = folder / SESSION_FILE
        if not path.is_file():
            return None
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            return SessionInfo(
                id=d["id"], root=folder, template_id=d["template_id"], template_name=d["template_name"],
                created_at=datetime.fromisoformat(d["created_at"]), sheet_count=int(d["sheet_count"]),
                state=SessionState(d["state"]), graded=bool(d["graded"]),
                duration_seconds=float(d.get("duration_seconds", 0.0)),
            )
        except (KeyError, ValueError, json.JSONDecodeError):
            return None
