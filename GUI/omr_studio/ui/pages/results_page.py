"""Results page: browse a session, inspect each sheet, export to Excel/CSV."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSettings, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImageReader
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QSplitter, QStackedWidget, QTableView, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ...models import RunResult, SessionInfo, SessionState, SheetResult, SheetStatus
from ...paths import Workspace
from ...services.exporter import ResultsExporter
from ...services.results import ResultsReader
from ...services.sessions import SessionStore
from .. import theme
from ..imaging import load_image
from ..widgets import Card, EmptyState, ImageViewer, PageHeader, StatCard, make_button, open_path

_STATUS_COLORS = {
    SheetStatus.PROCESSED: (theme.SUCCESS, "#F0FDF4"),
    SheetStatus.MULTI_MARKED: (theme.WARNING, "#FFFBEB"),
    SheetStatus.ERROR: (theme.DANGER, "#FEF2F2"),
}
_SORT_ROLE = Qt.UserRole + 1


class ResultsModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._result: Optional[RunResult] = None
        self._headers: list[str] = []
        self._graded = False
        self._bold = QFont()
        self._bold.setBold(True)

    def set_result(self, result: Optional[RunResult]) -> None:
        self.beginResetModel()
        self._result = result
        self._graded = bool(result and result.session.graded)
        self._headers = [] if not result else ["File", "Status"] + (["Score"] if self._graded else []) + result.columns
        self.endResetModel()

    def sheet(self, row: int) -> SheetResult:
        return self._result.sheets[row]

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() or not self._result else len(self._result.sheets)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._headers)

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self._headers[section]
        return None

    def _value(self, sheet: SheetResult, col: int):
        if col == 0:
            return sheet.file_id
        if col == 1:
            return sheet.status.value
        if self._graded and col == 2:
            return sheet.score
        return sheet.answers.get(self._headers[col], "")

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        sheet, col = self._result.sheets[index.row()], index.column()
        value = self._value(sheet, col)
        if role == Qt.DisplayRole:
            if value is None:
                return "-"
            return f"{value:g}" if isinstance(value, float) else value
        if role == _SORT_ROLE:
            return value if value is not None else float("-inf")
        if role == Qt.TextAlignmentRole and col >= 1:
            return int(Qt.AlignCenter)
        if role == Qt.ForegroundRole and col == 1:
            return QBrush(QColor(_STATUS_COLORS[sheet.status][0]))
        if role == Qt.BackgroundRole and sheet.status is not SheetStatus.PROCESSED:
            return QBrush(QColor(_STATUS_COLORS[sheet.status][1]))
        if role == Qt.FontRole and col == 1:
            return self._bold
        return None


class ResultsProxy(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSortRole(_SORT_ROLE)
        self._text = ""
        self._status = ""

    def set_filters(self, text: str, status: str) -> None:
        self._text, self._status = text.strip().lower(), status
        self.invalidateFilter()

    def filterAcceptsRow(self, row: int, parent: QModelIndex) -> bool:  # noqa: N802
        sheet = self.sourceModel().sheet(row)
        if self._status and sheet.status.value != self._status:
            return False
        if not self._text:
            return True
        return self._text in sheet.file_id.lower() or any(self._text in v.lower() for v in sheet.answers.values())


class ResultsPage(QWidget):
    navigate_process = Signal()

    def __init__(self, store: SessionStore, reader: ResultsReader, exporter: ResultsExporter,
                 workspace: Workspace, settings: QSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")
        self._store, self._reader, self._exporter, self._workspace = store, reader, exporter, workspace
        self._settings = settings
        self._result: Optional[RunResult] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(16)
        header = PageHeader("Results", "Review detected answers and scores, then export to Excel.")
        self._export_button = make_button("Export to Excel", "download", "primary")
        self._folder_button = make_button("Open output folder", "folder")
        header.actions.addWidget(self._folder_button)
        header.actions.addWidget(self._export_button)
        root.addWidget(header)

        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)
        empty = EmptyState("results", "No results yet", "Process a batch of OMR sheets and the results will show up here.")
        go = make_button("Go to Process Sheets", "process", "primary")
        go.clicked.connect(self.navigate_process)
        empty.actions.addWidget(go)
        self._stack.addWidget(empty)

        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(10)
        caption = QLabel("Run:")
        caption.setObjectName("Muted")
        self._history = QComboBox()
        self._history.setMinimumWidth(360)
        self._delete_button = make_button("Delete run", "trash", "danger")
        top.addWidget(caption)
        top.addWidget(self._history)
        top.addWidget(self._delete_button)
        top.addStretch(1)
        outer.addLayout(top)

        stats = QHBoxLayout()
        stats.setSpacing(12)
        self._stat_total = StatCard("Total sheets")
        self._stat_ok = StatCard("Processed", theme.SUCCESS)
        self._stat_multi = StatCard("Multi-marked", theme.WARNING)
        self._stat_error = StatCard("Errors", theme.DANGER)
        self._stat_avg = StatCard("Average score", theme.ACCENT)
        for card in (self._stat_total, self._stat_ok, self._stat_multi, self._stat_error, self._stat_avg):
            stats.addWidget(card)
        outer.addLayout(stats)

        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        filters = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search file name or answer...")
        self._search.setClearButtonEnabled(True)
        self._status_filter = QComboBox()
        self._status_filter.addItem("All statuses", "")
        for status in SheetStatus:
            self._status_filter.addItem(status.value, status.value)
        filters.addWidget(self._search, 1)
        filters.addWidget(self._status_filter)
        left_layout.addLayout(filters)
        self._model = ResultsModel(self)
        self._proxy = ResultsProxy(self)
        self._proxy.setSourceModel(self._model)
        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSortingEnabled(True)
        self._table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)  # default: processing order
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().hide()
        self._table.horizontalHeader().setDefaultSectionSize(70)
        self._table.horizontalHeader().setStretchLastSection(False)
        left_layout.addWidget(self._table, 1)
        split.addWidget(left)

        right = Card()
        self._tabs = QTabWidget()
        self._marked_view = ImageViewer("Select a sheet to see the detected bubbles")
        self._original_view = ImageViewer("Select a sheet to see the original scan")
        self._tabs.addTab(self._marked_view, "Detected (marked)")
        self._tabs.addTab(self._original_view, "Original scan")
        right.layout_.addWidget(self._tabs, 3)
        self._message = QLabel()
        self._message.setWordWrap(True)
        self._message.hide()
        right.layout_.addWidget(self._message)
        self._detail = QTableWidget(0, 2)
        self._detail.setHorizontalHeaderLabels(["Field", "Detected answer"])
        self._detail.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._detail.verticalHeader().hide()
        self._detail.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._detail.setAlternatingRowColors(True)
        right.layout_.addWidget(self._detail, 2)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        outer.addWidget(split, 1)
        self._stack.addWidget(content)

        self._history.currentIndexChanged.connect(self._on_history_changed)
        self._delete_button.clicked.connect(self._delete_session)
        self._search.textChanged.connect(self._apply_filters)
        self._status_filter.currentIndexChanged.connect(self._apply_filters)
        self._table.selectionModel().currentRowChanged.connect(self._on_row_changed)
        self._export_button.clicked.connect(self.export)
        self._folder_button.clicked.connect(lambda: self._result and open_path(self._result.output_dir))
        self.reload_history()

    # ---- history --------------------------------------------------------- #
    def reload_history(self, select_id: Optional[str] = None) -> None:
        sessions = self._store.list()
        keep = select_id or (self._result.session.id if self._result else None)
        self._history.blockSignals(True)
        self._history.clear()
        for s in sessions:
            suffix = "" if s.state is SessionState.COMPLETED else f"  [{s.state.value}]"
            self._history.addItem(s.label + suffix, s.id)
        index = next((i for i, s in enumerate(sessions) if s.id == keep), 0 if sessions else -1)
        self._history.setCurrentIndex(index)
        self._history.blockSignals(False)
        self._on_history_changed()

    def show_session(self, session: SessionInfo) -> None:
        self.reload_history(session.id)

    def _on_history_changed(self) -> None:
        session_id = self._history.currentData()
        info = self._store.get(session_id) if session_id else None
        if info is None:
            self._result = None
            self._model.set_result(None)
            self._stack.setCurrentIndex(0)
            self._set_actions(False)
            return
        self._result = self._reader.read(info)
        self._model.set_result(self._result)
        self._stack.setCurrentIndex(1)
        self._set_actions(True)
        self._update_stats()
        self._configure_columns()
        self._clear_detail()
        if self._proxy.rowCount():
            self._table.selectRow(0)

    def _set_actions(self, enabled: bool) -> None:
        for button in (self._export_button, self._folder_button, self._delete_button):
            button.setEnabled(enabled)

    def _delete_session(self) -> None:
        if not self._result:
            return
        answer = QMessageBox.question(self, "Delete run", "Permanently delete this run and its output files?\n"
                                                          "Exported Excel files are not affected.")
        if answer == QMessageBox.Yes:
            self._store.delete(self._result.session.id)
            self._result = None
            self.reload_history()

    # ---- table ------------------------------------------------------------ #
    def _update_stats(self) -> None:
        r = self._result
        self._stat_total.set_value(str(len(r.sheets)))
        self._stat_ok.set_value(str(r.count(SheetStatus.PROCESSED)))
        self._stat_multi.set_value(str(r.count(SheetStatus.MULTI_MARKED)))
        self._stat_error.set_value(str(r.count(SheetStatus.ERROR)))
        average = r.average_score
        self._stat_avg.set_value(f"{average:.2f}" if (r.session.graded and average is not None) else "-")

    def _configure_columns(self) -> None:
        head = self._table.horizontalHeader()
        self._table.setColumnWidth(0, 230)
        if self._model.columnCount() > 1:
            self._table.setColumnWidth(1, 120)
        if self._result.session.graded and self._model.columnCount() > 2:
            self._table.setColumnWidth(2, 80)

    def _apply_filters(self) -> None:
        self._proxy.set_filters(self._search.text(), self._status_filter.currentData() or "")

    # ---- detail ----------------------------------------------------------- #
    def _clear_detail(self) -> None:
        self._marked_view.set_image(None)
        self._original_view.set_image(None)
        self._detail.setRowCount(0)
        self._message.hide()

    def _on_row_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        if not current.isValid() or not self._result:
            self._clear_detail()
            return
        sheet = self._model.sheet(self._proxy.mapToSource(current).row())
        self._marked_view.set_image(
            QImageReader(str(sheet.marked_path)).read() if sheet.marked_path else None,
            "No marked image available for this sheet")
        original = load_image(sheet.source_path, sheet.file_id) if sheet.source_path else None
        self._original_view.set_image(original, "Original scan not available")
        self._detail.setRowCount(len(sheet.answers))
        for row, (field, answer) in enumerate(sheet.answers.items()):
            self._detail.setItem(row, 0, QTableWidgetItem(field))
            self._detail.setItem(row, 1, QTableWidgetItem(answer or "(blank)"))
        color = _STATUS_COLORS[sheet.status][0]
        if sheet.message:
            self._message.setText(f"<b style='color:{color}'>{sheet.status.value}:</b> {sheet.message}")
            self._message.show()
        else:
            self._message.hide()

    # ---- export ------------------------------------------------------------ #
    def export(self) -> None:
        if not self._result:
            return
        stamp = self._result.session.created_at.strftime("%Y%m%d-%H%M")
        safe = "".join(c if c.isalnum() else "-" for c in self._result.session.template_name).strip("-")
        default = str(self._workspace.exports / f"{safe}-{stamp}.xlsx")
        path, chosen = QFileDialog.getSaveFileName(self, "Export results", default,
                                                   "Excel workbook (*.xlsx);;CSV file (*.csv)")
        if not path:
            return
        try:
            if chosen.startswith("CSV") or path.lower().endswith(".csv"):
                target = self._exporter.export_csv(self._result, Path(path))
            else:
                target = self._exporter.export_excel(self._result, Path(path))
        except PermissionError:
            QMessageBox.warning(self, "Export failed", "The file could not be written. If it is open in Excel, close it and try again.")
            return
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        box = QMessageBox(QMessageBox.Information, "Export complete", f"Saved to:\n{target}", QMessageBox.NoButton, self)
        open_file = box.addButton("Open file", QMessageBox.AcceptRole)
        box.addButton("Show folder", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Close)
        box.exec()
        clicked = box.clickedButton()
        if clicked is open_file:
            open_path(target)
        elif clicked and clicked.text() == "Show folder":
            open_path(target.parent)
