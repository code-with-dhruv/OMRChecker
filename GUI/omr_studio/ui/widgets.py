"""Reusable UI building blocks."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, QSize, Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFrame, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView,
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from ..paths import collect_sheets
from . import theme
from .icons import icon
from .workers import ThumbnailTask, _ThumbSignals


def make_button(text: str, icon_name: Optional[str] = None, variant: str = "", tooltip: str = "") -> QPushButton:
    button = QPushButton(text)
    if icon_name:
        color = "#FFFFFF" if variant == "primary" else (theme.DANGER if variant == "danger" else "#334155")
        button.setIcon(icon(icon_name, color))
        button.setIconSize(QSize(16, 16))
    if variant:
        button.setProperty("variant", variant)
    if tooltip:
        button.setToolTip(tooltip)
    button.setCursor(Qt.PointingHandCursor)
    return button


class Card(QFrame):
    def __init__(self, title: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(18, 16, 18, 16)
        self.layout_.setSpacing(12)
        if title:
            label = QLabel(title)
            label.setObjectName("CardTitle")
            self.layout_.addWidget(label)


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        text = QVBoxLayout()
        text.setSpacing(2)
        head = QLabel(title)
        head.setObjectName("PageTitle")
        sub = QLabel(subtitle)
        sub.setObjectName("PageSubtitle")
        sub.setWordWrap(True)
        text.addWidget(head)
        text.addWidget(sub)
        outer.addLayout(text, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        outer.addLayout(self.actions)


class StatCard(QFrame):
    def __init__(self, label: str, accent: str = theme.TEXT, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(0)
        self._value = QLabel("-")
        self._value.setObjectName("StatValue")
        self._value.setStyleSheet(f"color: {accent};")
        caption = QLabel(label)
        caption.setObjectName("StatLabel")
        layout.addWidget(self._value)
        layout.addWidget(caption)

    def set_value(self, text: str) -> None:
        self._value.setText(text)


class EmptyState(QWidget):
    def __init__(self, icon_name: str, title: str, message: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)
        glyph = QLabel()
        glyph.setPixmap(icon(icon_name, "#94A3B8", 56).pixmap(56, 56))
        glyph.setAlignment(Qt.AlignCenter)
        head = QLabel(title)
        head.setObjectName("EmptyTitle")
        head.setAlignment(Qt.AlignCenter)
        body = QLabel(message)
        body.setObjectName("Muted")
        body.setAlignment(Qt.AlignCenter)
        body.setWordWrap(True)
        body.setMaximumWidth(420)
        layout.addWidget(glyph)
        layout.addWidget(head)
        layout.addWidget(body, 0, Qt.AlignHCenter)
        self.actions = QHBoxLayout()
        self.actions.setAlignment(Qt.AlignCenter)
        layout.addSpacing(6)
        layout.addLayout(self.actions)


class ImageViewer(QGraphicsView):
    """Zoomable / pannable image surface (wheel = zoom, drag = pan)."""

    def __init__(self, placeholder: str = "No image", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._item: Optional[QGraphicsPixmapItem] = None
        self._placeholder = placeholder
        self._fit = True
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setFrameShape(QFrame.NoFrame)
        self.set_image(None)

    def set_image(self, image: Optional[QImage], placeholder: Optional[str] = None) -> None:
        self._scene.clear()
        self._item = None
        if image is None or image.isNull():
            text = self._scene.addText(placeholder or self._placeholder)
            text.setDefaultTextColor(QColor(theme.MUTED))
            self._scene.setSceneRect(text.boundingRect())
            self.resetTransform()
            self.centerOn(text)
            return
        self._item = self._scene.addPixmap(QPixmap.fromImage(image))
        self._item.setTransformationMode(Qt.SmoothTransformation)
        self._scene.setSceneRect(self._item.boundingRect())
        self.fit()

    def fit(self) -> None:
        if self._item:
            self._fit = True
            self.fitInView(self._item, Qt.KeepAspectRatio)

    def zoom(self, factor: float) -> None:
        if self._item:
            self._fit = False
            self.scale(factor, factor)

    def wheelEvent(self, event) -> None:  # noqa: N802
        self.zoom(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._fit:
            self.fit()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.fit()


class ImageDialog(QDialog):
    """Large preview window with zoom controls and optional multi-image selector."""

    def __init__(self, title: str, images: list[tuple[str, QImage]], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1000, 780)
        self._images = images
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self._selector = QComboBox()
        for name, _ in images:
            self._selector.addItem(name)
        self._selector.setVisible(len(images) > 1)
        bar.addWidget(self._selector)
        bar.addStretch(1)
        self.viewer = ImageViewer()
        for name, tip, action in (("zoom-in", "Zoom in", lambda: self.viewer.zoom(1.25)),
                                  ("zoom-out", "Zoom out", lambda: self.viewer.zoom(0.8)),
                                  ("maximize", "Fit to window", self.viewer.fit)):
            button = make_button("", name, tooltip=tip)
            button.clicked.connect(action)
            bar.addWidget(button)
        layout.addLayout(bar)
        layout.addWidget(self.viewer, 1)
        self._selector.currentIndexChanged.connect(self._show)
        self._show(0)

    def _show(self, index: int) -> None:
        if self._images:
            self.viewer.set_image(self._images[index][1])


class ThumbnailList(QListWidget):
    """Sheet gallery with drag & drop and background thumbnail loading."""

    paths_dropped = Signal(list)
    preview_requested = Signal(object)
    THUMB = 128

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setViewMode(QListWidget.IconMode)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setIconSize(QSize(self.THUMB, self.THUMB))
        self.setGridSize(QSize(self.THUMB + 28, self.THUMB + 48))
        self.setWordWrap(True)
        self.setUniformItemSizes(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self._items: dict[str, QListWidgetItem] = {}
        self._pool = QThreadPool.globalInstance()
        self._signals = _ThumbSignals()
        self._signals.ready.connect(self._apply_thumbnail)
        self._placeholder = icon("image", "#CBD5E1", self.THUMB)
        self.itemDoubleClicked.connect(lambda item: self.preview_requested.emit(Path(item.data(Qt.UserRole))))

    # ---- model ---------------------------------------------------------- #
    def add_paths(self, paths: list[Path]) -> int:
        added = 0
        for path in paths:
            key = str(path)
            if key in self._items:
                continue
            item = QListWidgetItem(self._placeholder, path.name)
            item.setData(Qt.UserRole, key)
            item.setToolTip(key)
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
            self.addItem(item)
            self._items[key] = item
            self._pool.start(ThumbnailTask(path, self.THUMB, self._signals))
            added += 1
        self.viewport().update()
        return added

    def all_paths(self) -> list[Path]:
        return [Path(self.item(i).data(Qt.UserRole)) for i in range(self.count())]

    def selected_paths(self) -> list[Path]:
        return [Path(i.data(Qt.UserRole)) for i in self.selectedItems()]

    def remove_selected(self) -> None:
        for item in self.selectedItems():
            self._items.pop(item.data(Qt.UserRole), None)
            self.takeItem(self.row(item))
        self.viewport().update()

    def clear_all(self) -> None:
        self._items.clear()
        self.clear()
        self.viewport().update()

    def _apply_thumbnail(self, key: str, image: QImage) -> None:
        item = self._items.get(key)
        if item is not None and not image.isNull():
            item.setIcon(QPixmap.fromImage(image))

    # ---- drag & drop ---------------------------------------------------- #
    def _dropped(self, event) -> list[Path]:
        return [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        event.acceptProposedAction() if event.mimeData().hasUrls() else event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        event.acceptProposedAction() if event.mimeData().hasUrls() else event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = self._dropped(event)
        if paths:
            self.paths_dropped.emit(collect_sheets(paths))
            event.acceptProposedAction()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self.count() == 0:
            painter = QPainter(self.viewport())
            painter.setPen(QColor(theme.MUTED))
            rect = self.viewport().rect()
            painter.drawPixmap(QPointF(rect.center().x() - 24, rect.center().y() - 64),
                               icon("upload", "#94A3B8", 48).pixmap(48, 48))
            painter.drawText(rect.adjusted(0, 30, 0, 0), Qt.AlignCenter,
                             "Drag & drop OMR sheets or folders here\n(PNG, JPG, PDF)")
            painter.end()


def open_path(path: Path) -> None:
    from PySide6.QtGui import QDesktopServices

    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
