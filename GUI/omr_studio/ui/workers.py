"""Background execution so the UI never blocks."""
from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QObject, QRunnable, QThread, Signal

from ..models import RunOptions, SessionInfo, SessionState, TemplateInfo
from ..services.engine import EngineError, EngineHooks, OMREngine, RunCancelled
from ..services.sessions import SessionStore


class ProcessingWorker(QThread):
    """Stages a session, runs the engine, and reports progress/logs."""

    progress = Signal(int, int)        # done, total
    log = Signal(str, str)             # level, message
    stage = Signal(str)                # human readable phase
    finished_ok = Signal(object)       # SessionInfo
    failed = Signal(str, str, object)  # message, details, SessionInfo | None
    cancelled = Signal(object)         # SessionInfo | None

    def __init__(self, store: SessionStore, engine: OMREngine, template: TemplateInfo,
                 sheets: Sequence[Path], options: RunOptions, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._store, self._engine = store, engine
        self._template, self._sheets, self._options = template, list(sheets), options
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:  # noqa: D401 - QThread entry point
        started, session = time.monotonic(), None
        try:
            self.stage.emit("Preparing files...")
            session = self._store.create(self._template, self._sheets, self._options)
            self.stage.emit("Reading sheets...")
            hooks = EngineHooks(
                on_log=self.log.emit,
                on_progress=self.progress.emit,
                is_cancelled=self._cancel.is_set,
            )
            self._engine.execute(session, self._options, hooks)
            session = self._store.finish(session, SessionState.COMPLETED, time.monotonic() - started)
            self.finished_ok.emit(session)
        except RunCancelled:
            if session:
                session = self._store.finish(session, SessionState.CANCELLED, time.monotonic() - started)
            self.cancelled.emit(session)
        except EngineError as exc:
            self._fail(session, started, str(exc), traceback.format_exc())
        except Exception as exc:  # noqa: BLE001 - last line of defence for the thread
            self._fail(session, started, f"Unexpected error: {exc}", traceback.format_exc())

    def _fail(self, session: SessionInfo | None, started: float, message: str, details: str) -> None:
        if session:
            session = self._store.finish(session, SessionState.FAILED, time.monotonic() - started, message)
        self.failed.emit(message, details, session)


class _ThumbSignals(QObject):
    ready = Signal(str, object)  # path, QImage


class ThumbnailTask(QRunnable):
    """Loads a scaled thumbnail off the UI thread."""

    def __init__(self, path: Path, size: int, signals: _ThumbSignals) -> None:
        super().__init__()
        self._path, self._size, self._signals = path, size, signals

    def run(self) -> None:
        from .imaging import load_thumbnail

        image = load_thumbnail(self._path, self._size)
        self._signals.ready.emit(str(self._path), image)


class FunctionWorker(QThread):
    """Runs a single callable off the UI thread (short one-off jobs)."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, func, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._func = func

    def run(self) -> None:
        try:
            self.succeeded.emit(self._func())
        except EngineError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"Unexpected error: {exc}")
