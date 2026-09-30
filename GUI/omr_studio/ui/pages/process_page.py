"""Process page: choose a template, add sheets, run, watch progress."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QProgressBar,
    QSplitter, QVBoxLayout, QWidget,
)

from ...models import RunOptions, SessionInfo, TemplateInfo
from ...paths import SUPPORTED_EXTENSIONS, collect_sheets
from ...services.engine import OMREngine
from ...services.sessions import SessionStore
from ...services.templates import TemplateLibrary
from ..imaging import array_to_qimage, load_image
from ..widgets import Card, ImageDialog, PageHeader, ThumbnailList, make_button
from ..workers import FunctionWorker, ProcessingWorker


class ProcessPage(QWidget):
    session_finished = Signal(object)   # SessionInfo
    busy_changed = Signal(bool)
    open_templates = Signal()

    def __init__(self, library: TemplateLibrary, store: SessionStore, engine: OMREngine,
                 settings: QSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")
        self._library, self._store, self._engine, self._settings = library, store, engine, settings
        self._worker: Optional[ProcessingWorker] = None
        self._preview_worker: Optional[FunctionWorker] = None
        self._templates: list[TemplateInfo] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(18)
        root.addWidget(PageHeader("Process Sheets", "Add scanned OMR sheets, pick a template and press Run. "
                                                    "Results appear automatically."))

        body = QSplitter(Qt.Horizontal)
        body.setChildrenCollapsible(False)
        root.addWidget(body, 1)

        # ---- sheets card ------------------------------------------------ #
        sheets_card = Card("OMR sheets")
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self._add_files = make_button("Add files", "file", tooltip="Select images or PDFs")
        self._add_folder = make_button("Add folder", "folder", tooltip="Add every sheet inside a folder (including sub-folders)")
        self._remove = make_button("Remove selected", "x")
        self._clear = make_button("Clear all", "trash", "danger")
        self._count = QLabel("0 sheets")
        self._count.setObjectName("Muted")
        for w in (self._add_files, self._add_folder, self._remove, self._clear):
            bar.addWidget(w)
        bar.addStretch(1)
        bar.addWidget(self._count)
        sheets_card.layout_.addLayout(bar)
        self._gallery = ThumbnailList()
        sheets_card.layout_.addWidget(self._gallery, 1)
        hint = QLabel("Double-click a sheet to enlarge it.")
        hint.setObjectName("Muted")
        sheets_card.layout_.addWidget(hint)
        body.addWidget(sheets_card)

        # ---- settings card ---------------------------------------------- #
        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(14)

        template_card = Card("Template")
        self._template_combo = QComboBox()
        self._template_info = QLabel()
        self._template_info.setObjectName("Muted")
        self._template_info.setWordWrap(True)
        self._manage = make_button("Manage templates", "templates")
        template_card.layout_.addWidget(self._template_combo)
        template_card.layout_.addWidget(self._template_info)
        template_card.layout_.addWidget(self._manage)
        side_layout.addWidget(template_card)

        options_card = Card("Options")
        self._auto_align = QCheckBox("Auto-align slightly shifted scans")
        self._auto_align.setToolTip("Experimental. Use when scans are misaligned by a few pixels.")
        self._hold_multi = QCheckBox("Hold multi-marked sheets for review")
        self._hold_multi.setToolTip("Sheets where a question has several bubbles marked are listed separately instead of scored.")
        self._verbose = QCheckBox("Verbose activity log")
        for cb in (self._auto_align, self._hold_multi, self._verbose):
            options_card.layout_.addWidget(cb)
        self._preview = make_button("Preview template layout", "eye",
                                    tooltip="Overlay the template on the selected sheet to check bubble positions")
        options_card.layout_.addWidget(self._preview)
        side_layout.addWidget(options_card)

        run_card = Card("Run")
        self._progress = QProgressBar()
        self._progress.setRange(0, 1)
        self._status = QLabel("Ready")
        self._status.setObjectName("Muted")
        self._status.setWordWrap(True)
        self._run_button = make_button("Process sheets", "play", "primary")
        self._run_button.setMinimumHeight(38)
        self._cancel_button = make_button("Cancel", "x")
        self._cancel_button.hide()
        self._log_toggle = make_button("Show activity log", variant="ghost")
        run_card.layout_.addWidget(self._progress)
        run_card.layout_.addWidget(self._status)
        run_card.layout_.addWidget(self._run_button)
        run_card.layout_.addWidget(self._cancel_button)
        run_card.layout_.addWidget(self._log_toggle)
        side_layout.addWidget(run_card)
        side_layout.addStretch(1)
        side.setMinimumWidth(320)
        side.setMaximumWidth(380)
        body.addWidget(side)
        body.setStretchFactor(0, 1)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(5000)
        self._log.setMinimumHeight(140)
        self._log.hide()
        root.addWidget(self._log)

        # ---- wiring ------------------------------------------------------ #
        self._add_files.clicked.connect(self._pick_files)
        self._add_folder.clicked.connect(self._pick_folder)
        self._remove.clicked.connect(self._remove_selected)
        self._clear.clicked.connect(self._clear_all)
        self._gallery.paths_dropped.connect(self._add_paths)
        self._gallery.preview_requested.connect(self._open_sheet)
        self._gallery.itemSelectionChanged.connect(self._refresh_state)
        self._template_combo.currentIndexChanged.connect(self._on_template_changed)
        self._manage.clicked.connect(self.open_templates)
        self._preview.clicked.connect(self._preview_layout)
        self._run_button.clicked.connect(self._start)
        self._cancel_button.clicked.connect(self._cancel)
        self._log_toggle.clicked.connect(self._toggle_log)

        self._auto_align.setChecked(settings.value("run/auto_align", False, bool))
        self._hold_multi.setChecked(settings.value("run/hold_multi", True, bool))
        self._verbose.setChecked(settings.value("run/verbose", False, bool))
        self.reload_templates()

    # ---- public --------------------------------------------------------- #
    @property
    def is_busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def shutdown(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(15000)

    def reload_templates(self) -> None:
        wanted = self._current_template().id if self._current_template() else self._settings.value("run/template", "", str)
        self._templates = self._library.list()
        self._template_combo.blockSignals(True)
        self._template_combo.clear()
        for t in self._templates:
            self._template_combo.addItem(t.name, t.id)
        index = next((i for i, t in enumerate(self._templates) if t.id == wanted), 0 if self._templates else -1)
        self._template_combo.setCurrentIndex(index)
        self._template_combo.blockSignals(False)
        self._on_template_changed()

    # ---- state ---------------------------------------------------------- #
    def _current_template(self) -> Optional[TemplateInfo]:
        index = self._template_combo.currentIndex()
        return self._templates[index] if 0 <= index < len(self._templates) else None

    def _on_template_changed(self) -> None:
        t = self._current_template()
        if t is None:
            self._template_info.setText("No templates available. Add one on the Templates page first.")
        else:
            grading = "Graded against its answer key." if t.has_answer_key else "Answers are read but not graded (no answer key)."
            self._template_info.setText(f"{t.field_count} fields. {grading}")
            self._settings.setValue("run/template", t.id)
        self._refresh_state()

    def _refresh_state(self) -> None:
        busy = self.is_busy
        count = self._gallery.count()
        self._count.setText(f"{count} sheet{'s' if count != 1 else ''}")
        ready = self._current_template() is not None and count > 0 and not busy
        self._run_button.setEnabled(ready)
        self._preview.setEnabled(self._current_template() is not None and count > 0 and not busy and self._preview_worker is None)
        for w in (self._add_files, self._add_folder, self._remove, self._clear, self._template_combo,
                  self._auto_align, self._hold_multi, self._verbose, self._manage):
            w.setEnabled(not busy)
        self._gallery.setEnabled(not busy)

    # ---- sheet management ----------------------------------------------- #
    def _add_paths(self, paths: list[Path]) -> None:
        added = self._gallery.add_paths(paths)
        self._status.setText(f"Added {added} sheet(s)." if paths else "No supported files found (PNG, JPG, PDF).")
        self._refresh_state()

    def _pick_files(self) -> None:
        patterns = " ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS))
        files, _ = QFileDialog.getOpenFileNames(self, "Select OMR sheets", "", f"OMR sheets ({patterns})")
        if files:
            self._add_paths(collect_sheets([Path(f) for f in files]))

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select a folder of OMR sheets")
        if folder:
            self._add_paths(collect_sheets([Path(folder)]))

    def _remove_selected(self) -> None:
        self._gallery.remove_selected()
        self._refresh_state()

    def _clear_all(self) -> None:
        if self._gallery.count() and QMessageBox.question(self, "Clear sheets", "Remove all sheets from the list?") == QMessageBox.Yes:
            self._gallery.clear_all()
            self._refresh_state()

    def _open_sheet(self, path: Path) -> None:
        image = load_image(path)
        if image.isNull():
            QMessageBox.warning(self, "Cannot open", f"'{path.name}' could not be displayed.")
            return
        ImageDialog(path.name, [(path.name, image)], self).exec()

    # ---- layout preview -------------------------------------------------- #
    def _options(self) -> RunOptions:
        return RunOptions(self._auto_align.isChecked(), self._hold_multi.isChecked(), self._verbose.isChecked())

    def _preview_layout(self) -> None:
        template = self._current_template()
        selected = self._gallery.selected_paths() or self._gallery.all_paths()[:1]
        if not template or not selected:
            return
        sheet, options = selected[0], self._options()
        self._status.setText(f"Building layout preview for {sheet.name}...")
        self._preview_worker = FunctionWorker(lambda: self._engine.preview_layout(template, sheet, options), self)
        self._preview_worker.succeeded.connect(self._show_preview)
        self._preview_worker.failed.connect(self._preview_failed)
        self._preview_worker.finished.connect(self._preview_done)
        self._preview_worker.start()
        self._refresh_state()

    def _show_preview(self, previews) -> None:
        images = [(name, array_to_qimage(array)) for name, array in previews]
        self._status.setText("Ready")
        ImageDialog("Template layout preview", images, self).exec()

    def _preview_failed(self, message: str) -> None:
        self._status.setText("Ready")
        QMessageBox.warning(self, "Layout preview", message)

    def _preview_done(self) -> None:
        self._preview_worker = None
        self._refresh_state()

    # ---- processing ------------------------------------------------------ #
    def _start(self) -> None:
        template, sheets, options = self._current_template(), self._gallery.all_paths(), self._options()
        if not template or not sheets:
            return
        for key, value in (("auto_align", options.auto_align), ("hold_multi", options.hold_multi_marked), ("verbose", options.verbose)):
            self._settings.setValue(f"run/{key}", value)
        self._log.clear()
        self._progress.setRange(0, len(sheets))
        self._progress.setValue(0)
        self._worker = ProcessingWorker(self._store, self._engine, template, sheets, options, self)
        self._worker.stage.connect(self._status.setText)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._append_log)
        self._worker.finished_ok.connect(self._on_success)
        self._worker.failed.connect(self._on_failure)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.finished.connect(self._on_thread_finished)
        self._run_button.hide()
        self._cancel_button.show()
        self._cancel_button.setEnabled(True)
        self._worker.start()
        self._refresh_state()
        self.busy_changed.emit(True)

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self._cancel_button.setEnabled(False)
            self._status.setText("Cancelling after the current sheet...")

    def _on_progress(self, done: int, total: int) -> None:
        self._progress.setRange(0, max(total, 1))
        self._progress.setValue(done)
        self._status.setText(f"Processed {done} of {total} sheets")

    def _append_log(self, level: str, message: str) -> None:
        if level in ("WARNING", "ERROR", "CRITICAL") or self._verbose.isChecked() or self._log.isVisible():
            self._log.appendPlainText(f"{level:<8} {message}")

    def _toggle_log(self) -> None:
        visible = not self._log.isVisible()
        self._log.setVisible(visible)
        self._log_toggle.setText("Hide activity log" if visible else "Show activity log")

    def _on_success(self, session: SessionInfo) -> None:
        self._status.setText(f"Finished {session.sheet_count} sheet(s) in {session.duration_seconds:.1f}s")
        self._progress.setValue(self._progress.maximum())
        self.session_finished.emit(session)

    def _on_failure(self, message: str, details: str, session: Optional[SessionInfo]) -> None:
        self._status.setText("Processing failed")
        self._log.appendPlainText(details)
        box = QMessageBox(QMessageBox.Critical, "Processing failed", message, QMessageBox.Ok, self)
        box.setDetailedText(details)
        box.exec()

    def _on_cancelled(self, session: Optional[SessionInfo]) -> None:
        self._status.setText("Cancelled. Partial results were saved in History.")
        if session:
            self.session_finished.emit(session)

    def _on_thread_finished(self) -> None:
        self._worker = None
        self._cancel_button.hide()
        self._run_button.show()
        self._refresh_state()
        self.busy_changed.emit(False)
