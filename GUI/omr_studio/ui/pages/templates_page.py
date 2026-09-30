"""Template management: add, inspect, attach answer keys and remove templates."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QMenu,
    QMessageBox, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...models import TemplateInfo
from ...paths import SAMPLES_DIR, TEMPLATE_FILE
from ...services.templates import TemplateError, TemplateLibrary
from ..widgets import Card, EmptyState, PageHeader, make_button, open_path


class TemplatesPage(QWidget):
    templates_changed = Signal()

    def __init__(self, library: TemplateLibrary, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")
        self._library = library
        self._templates: list[TemplateInfo] = []
        self._locked = False

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(18)

        header = PageHeader("Templates", "A template describes one OMR sheet design. Add it once, reuse it for every batch.")
        self._add_button = make_button("Add Template", "plus", "primary")
        menu = QMenu(self)
        menu.addAction("From a folder...", self._add_from_folder)
        menu.addAction("From a template.json file...", self._add_from_file)
        menu.addSeparator()
        menu.addAction("Add bundled sample templates", self._add_samples)
        self._add_button.setMenu(menu)
        header.actions.addWidget(self._add_button)
        root.addWidget(header)

        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        empty = EmptyState("templates", "No templates yet",
                           "Add a template folder (template.json with its marker image), "
                           "or start with the bundled samples to try the app.")
        sample_button = make_button("Add sample templates", "layers", "primary")
        sample_button.clicked.connect(self._add_samples)
        folder_button = make_button("Add from folder", "folder")
        folder_button.clicked.connect(self._add_from_folder)
        empty.actions.addWidget(sample_button)
        empty.actions.addWidget(folder_button)
        self._stack.addWidget(empty)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Name", "Fields", "Answer key", "Added"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.verticalHeader().hide()
        head = self._table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in (1, 2, 3):
            head.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self._table.itemSelectionChanged.connect(self._show_details)
        splitter.addWidget(self._table)

        self._details = Card("Template details")
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        self._fields = {key: QLabel("-") for key in ("Name", "Page size", "Detected fields", "Pre-processing", "Answer key", "Stored at")}
        for key, label in self._fields.items():
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            caption = QLabel(key)
            caption.setObjectName("Muted")
            form.addRow(caption, label)
        self._details.layout_.addLayout(form)
        self._details.layout_.addStretch(1)

        row = QHBoxLayout()
        self._key_button = make_button("Attach answer key...", "key", tooltip="Add an evaluation.json so sheets are graded")
        self._key_button.clicked.connect(self._attach_key)
        self._unkey_button = make_button("Remove key", "x")
        self._unkey_button.clicked.connect(self._remove_key)
        row.addWidget(self._key_button)
        row.addWidget(self._unkey_button)
        self._details.layout_.addLayout(row)
        row2 = QHBoxLayout()
        self._open_button = make_button("Open folder", "folder")
        self._open_button.clicked.connect(lambda: self._selected() and open_path(self._selected().path))
        self._remove_button = make_button("Delete template", "trash", "danger")
        self._remove_button.clicked.connect(self._remove)
        row2.addWidget(self._open_button)
        row2.addWidget(self._remove_button)
        self._details.layout_.addLayout(row2)
        splitter.addWidget(self._details)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self._stack.addWidget(splitter)

        self.refresh()

    # ---- state ---------------------------------------------------------- #
    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        self._add_button.setEnabled(not locked)
        self._show_details()

    def refresh(self, select_id: Optional[str] = None) -> None:
        self._templates = self._library.list()
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._templates))
        for row, t in enumerate(self._templates):
            cells = [t.name, str(t.field_count),
                     f"Yes ({t.question_count} questions)" if t.has_answer_key and t.question_count else ("Yes" if t.has_answer_key else "No"),
                     t.created_at.strftime("%d %b %Y")]
            for col, text in enumerate(cells):
                self._table.setItem(row, col, QTableWidgetItem(text))
        self._table.blockSignals(False)
        self._stack.setCurrentIndex(1 if self._templates else 0)
        if self._templates:
            row = next((i for i, t in enumerate(self._templates) if t.id == select_id), 0)
            self._table.selectRow(row)
        self._show_details()

    def _selected(self) -> Optional[TemplateInfo]:
        rows = self._table.selectionModel().selectedRows() if self._table.selectionModel() else []
        return self._templates[rows[0].row()] if rows else None

    def _show_details(self) -> None:
        t = self._selected()
        values = ["-"] * 6
        if t:
            key = "Yes - sheets will be graded" if t.has_answer_key else "None - answers are read but not graded"
            values = [t.name, f"{t.page_dimensions[0]} x {t.page_dimensions[1]} px", f"{t.field_count} output columns",
                      ", ".join(t.preprocessors) or "None", key, str(t.path)]
        for label, value in zip(self._fields.values(), values):
            label.setText(value)
        editable = t is not None and not self._locked
        self._key_button.setEnabled(editable)
        self._unkey_button.setEnabled(editable and bool(t and t.has_answer_key))
        self._remove_button.setEnabled(editable)
        self._open_button.setEnabled(t is not None)

    # ---- actions -------------------------------------------------------- #
    def _run(self, action, success_message: Optional[str] = None):
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            return action()
        except TemplateError as exc:
            QGuiApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Template not accepted", str(exc))
        except OSError as exc:
            QGuiApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "File error", f"Could not access the files: {exc}")
        finally:
            while QGuiApplication.overrideCursor():
                QGuiApplication.restoreOverrideCursor()
        return None

    def _ask_name(self, default: str) -> Optional[str]:
        name, ok = QInputDialog.getText(self, "Template name", "Give this template a name:", text=default)
        return name.strip() if ok and name.strip() else None

    def _import(self, source: Path, default_name: str) -> None:
        name = self._ask_name(default_name)
        if not name:
            return
        info = self._run(lambda: self._library.import_template(source, name))
        if info:
            self.refresh(info.id)
            self.templates_changed.emit()

    def _add_from_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select the template folder (contains template.json)")
        if not folder:
            return
        if not (Path(folder) / TEMPLATE_FILE).is_file():
            QMessageBox.warning(self, "No template found", f"'{TEMPLATE_FILE}' was not found in that folder.")
            return
        self._import(Path(folder), Path(folder).name)

    def _add_from_file(self) -> None:
        file, _ = QFileDialog.getOpenFileName(self, "Select template.json", "", "Template (*.json)")
        if file:
            self._import(Path(file), Path(file).parent.name)

    def _add_samples(self) -> None:
        existing = {t.name for t in self._library.list()}
        candidates = sorted(p for p in SAMPLES_DIR.glob("sample*") if (p / TEMPLATE_FILE).is_file())
        added, failed = [], []
        for folder in candidates:
            name = f"Sample - {folder.name}"
            if name in existing:
                continue
            info = self._run(lambda f=folder, n=name: self._library.import_template(f, n))
            (added if info else failed).append(folder.name)
        if not candidates:
            QMessageBox.information(self, "Samples", "No bundled samples were found in this installation.")
        self.refresh()
        if added:
            self.templates_changed.emit()

    def _attach_key(self) -> None:
        t = self._selected()
        if not t:
            return
        file, _ = QFileDialog.getOpenFileName(self, "Select evaluation.json (answer key)", "", "Answer key (*.json)")
        if file:
            info = self._run(lambda: self._library.set_answer_key(t.id, Path(file)))
            if info:
                self.refresh(info.id)
                self.templates_changed.emit()

    def _remove_key(self) -> None:
        t = self._selected()
        if t and QMessageBox.question(self, "Remove answer key", f"Stop grading sheets with '{t.name}'?") == QMessageBox.Yes:
            info = self._run(lambda: self._library.remove_answer_key(t.id))
            if info:
                self.refresh(info.id)
                self.templates_changed.emit()

    def _remove(self) -> None:
        t = self._selected()
        if not t:
            return
        answer = QMessageBox.question(self, "Delete template",
                                      f"Delete '{t.name}'?\nPast results that used it are kept.")
        if answer == QMessageBox.Yes:
            self._run(lambda: self._library.remove(t.id))
            self.refresh()
            self.templates_changed.emit()
