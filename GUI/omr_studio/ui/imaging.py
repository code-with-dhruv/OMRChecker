"""Image loading helpers shared by the UI (Qt images from files, arrays, PDFs)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QImageReader

from ..paths import PDF_EXTENSIONS


def array_to_qimage(array: np.ndarray) -> QImage:
    array = np.ascontiguousarray(array)
    height, width = array.shape[:2]
    if array.ndim == 2:
        image = QImage(array.data, width, height, width, QImage.Format_Grayscale8)
    else:
        rgb = np.ascontiguousarray(array[:, :, ::-1])  # BGR -> RGB
        image = QImage(rgb.data, width, height, 3 * width, QImage.Format_RGB888)
    return image.copy()  # detach from the numpy buffer


def render_pdf_page(path: Path, page: int = 0, max_side: int = 0) -> QImage:
    import fitz

    with fitz.open(str(path)) as doc:
        page = min(max(page, 0), len(doc) - 1)
        rect = doc[page].rect
        zoom = (max_side / max(rect.width, rect.height)) if max_side else 150 / 72
        pix = doc[page].get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB)
        return QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()


def load_image(path: Path, file_id: Optional[str] = None) -> QImage:
    """Load a full-size image; PDFs render the page encoded in *file_id* (``name_p3.png``)."""
    if path.suffix.lower() in PDF_EXTENSIONS:
        match = re.search(r"_p(\d+)\.png$", file_id or "")
        return render_pdf_page(path, int(match.group(1)) - 1 if match else 0)
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    return reader.read()


def load_thumbnail(path: Path, size: int) -> QImage:
    try:
        if path.suffix.lower() in PDF_EXTENSIONS:
            return render_pdf_page(path, 0, max_side=size * 2).scaled(
                size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        native = reader.size()
        if native.isValid():
            native.scale(QSize(size * 2, size * 2), Qt.KeepAspectRatio)  # cheap decode-time downscale
            reader.setScaledSize(native)
        image = reader.read()
        return image.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation) if not image.isNull() else QImage()
    except Exception:  # noqa: BLE001 - a bad file must never break the gallery
        return QImage()
