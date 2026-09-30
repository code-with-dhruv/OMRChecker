"""OMR Studio - launch with:  python GUI/main.py"""
from __future__ import annotations

import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Make ``omr_studio`` and the engine (repo root) importable from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from PySide6.QtWidgets import QApplication, QMessageBox
except ImportError:  # pragma: no cover
    sys.exit("PySide6 is required.  Install with:  pip install -r GUI/requirements.txt")

from omr_studio import APP_NAME  # noqa: E402
from omr_studio.paths import Workspace  # noqa: E402
from omr_studio.ui.main_window import MainWindow  # noqa: E402
from omr_studio.ui.theme import apply_theme  # noqa: E402


def _configure_logging(workspace: Workspace) -> logging.Logger:
    log = logging.getLogger("omr_studio")
    log.setLevel(logging.INFO)
    handler = RotatingFileHandler(workspace.logs / "omr_studio.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    return log


def main() -> int:
    workspace = Workspace.default()
    log = _configure_logging(workspace)

    def excepthook(exc_type, exc, tb) -> None:
        details = "".join(traceback.format_exception(exc_type, exc, tb))
        log.error("Unhandled exception:\n%s", details)
        box = QMessageBox(QMessageBox.Critical, APP_NAME, f"An unexpected error occurred:\n{exc}")
        box.setDetailedText(details)
        box.exec()

    sys.excepthook = excepthook

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("OMRStudio")
    apply_theme(app)
    window = MainWindow(workspace)
    window.show()
    log.info("Started (workspace %s)", workspace.root)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
