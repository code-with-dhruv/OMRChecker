"""Main application window: sidebar navigation + pages."""
from __future__ import annotations

import threading

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from .. import APP_NAME, __version__
from ..paths import Workspace
from ..services.engine import OMREngine
from ..services.exporter import ResultsExporter
from ..services.results import ResultsReader
from ..services.sessions import SessionStore
from ..services.templates import TemplateLibrary
from .icons import icon
from .pages.process_page import ProcessPage
from .pages.results_page import ResultsPage
from .pages.templates_page import TemplatesPage
from .widgets import open_path


def _prewarm_engine() -> None:
    """Import the heavy engine modules in the background so the first action is instant."""
    try:
        import src.entry  # noqa: F401
        import src.template  # noqa: F401
    except Exception:  # noqa: BLE001 - surfaced properly when the engine is actually used
        pass


class MainWindow(QMainWindow):
    def __init__(self, workspace: Workspace) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1360, 860)
        self.setMinimumSize(1100, 700)
        self._workspace = workspace
        self._settings = QSettings("OMRStudio", "OMRStudio")

        library = TemplateLibrary(workspace.templates)
        store = SessionStore(workspace.sessions)

        self._templates = TemplatesPage(library)
        self._process = ProcessPage(library, store, OMREngine(), self._settings)
        self._results = ResultsPage(store, ResultsReader(), ResultsExporter(), workspace, self._settings)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        self._stack = QStackedWidget()
        for page in (self._process, self._templates, self._results):
            self._stack.addWidget(page)
        layout.addWidget(self._stack, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage(f"Workspace: {workspace.root}")

        self._templates.templates_changed.connect(self._process.reload_templates)
        self._process.busy_changed.connect(self._on_busy)
        self._process.open_templates.connect(lambda: self._navigate(1))
        self._process.session_finished.connect(self._on_session_finished)
        self._results.navigate_process.connect(lambda: self._navigate(0))

        geometry = self._settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        self._navigate(0 if library.list() else 1)
        threading.Thread(target=_prewarm_engine, daemon=True).start()

    # ---- construction --------------------------------------------------- #
    def _build_sidebar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Sidebar")
        bar.setFixedWidth(232)
        layout = QVBoxLayout(bar)
        layout.setContentsMargins(16, 24, 16, 18)
        layout.setSpacing(6)
        brand = QLabel(APP_NAME)
        brand.setObjectName("Brand")
        sub = QLabel("Optical mark recognition")
        sub.setObjectName("BrandSub")
        layout.addWidget(brand)
        layout.addWidget(sub)
        layout.addSpacing(22)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._nav_buttons: list[QPushButton] = []
        for index, (label, icon_name) in enumerate((("Process Sheets", "process"), ("Templates", "templates"), ("Results", "results"))):
            button = QPushButton(label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setIcon(icon(icon_name, "#CBD5E1", 20))
            button.setIconSize(QSize(20, 20))
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, i=index: self._navigate(i))
            self._group.addButton(button)
            self._nav_buttons.append(button)
            layout.addWidget(button)
        layout.addStretch(1)
        folder = QPushButton("Workspace folder")
        folder.setObjectName("NavButton")
        folder.setIcon(icon("folder", "#94A3B8", 18))
        folder.clicked.connect(lambda: open_path(self._workspace.root))
        layout.addWidget(folder)
        version = QLabel(f"Version {__version__}")
        version.setObjectName("SidebarFoot")
        layout.addWidget(version)
        return bar

    # ---- behaviour --------------------------------------------------------- #
    def _navigate(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self._nav_buttons[index].setChecked(True)
        if index == 1:
            self._templates.refresh()

    def _on_busy(self, busy: bool) -> None:
        self._templates.set_locked(busy)
        self.statusBar().showMessage("Processing..." if busy else f"Workspace: {self._workspace.root}")

    def _on_session_finished(self, session) -> None:
        self._results.show_session(session)
        self._navigate(2)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._process.is_busy:
            answer = QMessageBox.question(self, "Processing in progress",
                                          "Sheets are still being processed. Cancel and exit?")
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self._process.shutdown()
        self._settings.setValue("window/geometry", self.saveGeometry())
        event.accept()
