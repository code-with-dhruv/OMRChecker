import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")


def test_window_builds_and_switches_pages(workspace):
    from PySide6.QtWidgets import QApplication

    from omr_studio.ui.main_window import MainWindow
    from omr_studio.ui.theme import apply_theme

    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    window = MainWindow(workspace)
    for index in range(3):
        window._navigate(index)
        assert window._stack.currentIndex() == index
    window.close()
