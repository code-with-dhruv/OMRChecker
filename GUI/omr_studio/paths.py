"""Filesystem layout and shared constants."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = ENGINE_ROOT / "samples"

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg"})
PDF_EXTENSIONS = frozenset({".pdf"})
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | PDF_EXTENSIONS

TEMPLATE_FILE = "template.json"
EVALUATION_FILE = "evaluation.json"
CONFIG_FILE = "config.json"


@dataclass(frozen=True)
class Workspace:
    """All user data lives below a single root (override with OMR_STUDIO_HOME)."""

    root: Path

    @classmethod
    def default(cls) -> "Workspace":
        override = os.environ.get("OMR_STUDIO_HOME")
        return cls(Path(override) if override else Path.home() / "OMRStudio").ensure()

    @property
    def templates(self) -> Path:
        return self.root / "templates"

    @property
    def sessions(self) -> Path:
        return self.root / "sessions"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    def ensure(self) -> "Workspace":
        for folder in (self.templates, self.sessions, self.exports, self.logs):
            folder.mkdir(parents=True, exist_ok=True)
        return self


def is_supported_sheet(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS


def collect_sheets(paths: "list[Path]") -> "list[Path]":
    """Expand files/folders (recursively) into a sorted, de-duplicated sheet list."""
    found: dict[Path, None] = {}
    for raw in paths:
        p = Path(raw)
        candidates = sorted(p.rglob("*")) if p.is_dir() else [p]
        for candidate in candidates:
            if is_supported_sheet(candidate):
                found[candidate.resolve()] = None
    return list(found)
