"""Plain data objects shared between services and the UI."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class SheetStatus(str, Enum):
    PROCESSED = "Processed"
    MULTI_MARKED = "Multi-marked"
    ERROR = "Error"


class SessionState(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class TemplateInfo:
    id: str
    name: str
    path: Path
    created_at: datetime
    page_dimensions: tuple[int, int]
    field_count: int
    preprocessors: tuple[str, ...]
    has_answer_key: bool
    question_count: Optional[int] = None


@dataclass(frozen=True)
class RunOptions:
    auto_align: bool = False
    hold_multi_marked: bool = True
    verbose: bool = False

    def to_dict(self) -> dict:
        return {
            "auto_align": self.auto_align,
            "hold_multi_marked": self.hold_multi_marked,
            "verbose": self.verbose,
        }


@dataclass(frozen=True)
class SessionInfo:
    id: str
    root: Path
    template_id: str
    template_name: str
    created_at: datetime
    sheet_count: int
    state: SessionState
    graded: bool
    duration_seconds: float = 0.0

    @property
    def label(self) -> str:
        stamp = self.created_at.strftime("%d %b %Y, %H:%M")
        return f"{stamp}  -  {self.template_name}  ({self.sheet_count} sheets)"


@dataclass
class SheetResult:
    file_id: str
    status: SheetStatus
    score: Optional[float]
    answers: dict[str, str]
    source_path: Optional[Path] = None
    marked_path: Optional[Path] = None
    message: str = ""


@dataclass
class RunResult:
    session: SessionInfo
    columns: list[str]
    sheets: list[SheetResult] = field(default_factory=list)

    def count(self, status: SheetStatus) -> int:
        return sum(1 for s in self.sheets if s.status is status)

    @property
    def scores(self) -> list[float]:
        return [s.score for s in self.sheets if s.score is not None]

    @property
    def average_score(self) -> Optional[float]:
        scores = self.scores
        return sum(scores) / len(scores) if scores else None

    @property
    def output_dir(self) -> Path:
        return self.session.root / "output"
