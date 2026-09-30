"""Application-wide look & feel (Fusion style + QSS)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from .icons import icon

NAVY = "#0F172A"
NAVY_HOVER = "#1E293B"
ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"
BG = "#F1F5F9"
CARD = "#FFFFFF"
BORDER = "#E2E8F0"
TEXT = "#0F172A"
MUTED = "#64748B"
SUCCESS, WARNING, DANGER = "#16A34A", "#D97706", "#DC2626"

def build_stylesheet(check_url: str) -> str:
    return f"""
* {{ font-family: "Segoe UI", "Inter", "SF Pro Text", "Helvetica Neue", Arial, sans-serif; font-size: 13px; color: {TEXT}; }}
QMainWindow, QWidget#Page {{ background: {BG}; }}
QToolTip {{ background: {NAVY}; color: white; border: none; padding: 5px 8px; }}

/* sidebar */
QFrame#Sidebar {{ background: {NAVY}; }}
QLabel#Brand {{ color: white; font-size: 17px; font-weight: 700; padding-left: 4px; }}
QLabel#BrandSub {{ color: #94A3B8; font-size: 11px; padding-left: 4px; }}
QPushButton#NavButton {{ color: #CBD5E1; background: transparent; border: none; border-radius: 8px;
    text-align: left; padding: 11px 14px; font-size: 14px; font-weight: 600; }}
QPushButton#NavButton:hover {{ background: {NAVY_HOVER}; color: white; }}
QPushButton#NavButton:checked {{ background: {ACCENT}; color: white; }}
QLabel#SidebarFoot {{ color: #64748B; font-size: 11px; }}

/* typography */
QLabel#PageTitle {{ font-size: 24px; font-weight: 700; }}
QLabel#PageSubtitle {{ color: {MUTED}; font-size: 13px; }}
QLabel#CardTitle {{ font-size: 14px; font-weight: 700; }}
QLabel#Muted {{ color: {MUTED}; }}
QLabel#EmptyTitle {{ font-size: 16px; font-weight: 700; }}

/* cards */
QFrame#Card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#StatCard {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
QLabel#StatValue {{ font-size: 24px; font-weight: 700; }}
QLabel#StatLabel {{ color: {MUTED}; font-size: 12px; }}

/* buttons */
QPushButton {{ background: {CARD}; border: 1px solid #CBD5E1; border-radius: 8px; padding: 8px 14px; font-weight: 600; }}
QPushButton:hover {{ background: #F8FAFC; border-color: #94A3B8; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: #94A3B8; background: #F1F5F9; border-color: {BORDER}; }}
QPushButton[variant="primary"] {{ background: {ACCENT}; border: 1px solid {ACCENT}; color: white; }}
QPushButton[variant="primary"]:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton[variant="primary"]:disabled {{ background: #93C5FD; border-color: #93C5FD; color: white; }}
QPushButton[variant="danger"] {{ color: {DANGER}; }}
QPushButton[variant="danger"]:hover {{ background: #FEF2F2; border-color: #FCA5A5; }}
QPushButton[variant="danger"]:disabled {{ color: #FCA5A5; }}
QPushButton[variant="ghost"] {{ border: none; background: transparent; color: {MUTED}; }}
QPushButton[variant="ghost"]:hover {{ background: {BORDER}; color: {TEXT}; }}

/* inputs */
QLineEdit, QComboBox {{ background: white; border: 1px solid #CBD5E1; border-radius: 8px; padding: 7px 10px; min-height: 18px; }}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: white; border: 1px solid {BORDER}; selection-background-color: #DBEAFE; selection-color: {TEXT}; outline: 0; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid #94A3B8; border-radius: 4px; background: white; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url({check_url}); }}

/* tables & lists */
QTableView, QTableWidget, QListWidget {{ background: white; border: 1px solid {BORDER}; border-radius: 10px;
    gridline-color: #F1F5F9; alternate-background-color: #F8FAFC; selection-background-color: #DBEAFE; selection-color: {TEXT}; outline: 0; }}
QTableView::item {{ padding: 4px 8px; }}
QListWidget::item {{ border-radius: 8px; padding: 6px; }}
QListWidget::item:selected {{ background: #DBEAFE; color: {TEXT}; }}
QListWidget::item:hover {{ background: #F1F5F9; }}
QHeaderView::section {{ background: #F8FAFC; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
    padding: 9px 10px; font-weight: 700; font-size: 12px; }}
QTableCornerButton::section {{ background: #F8FAFC; border: none; }}

/* progress, scrollbars, misc */
QProgressBar {{ border: none; background: {BORDER}; border-radius: 5px; height: 10px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #CBD5E1; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #94A3B8; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #CBD5E1; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QPlainTextEdit {{ background: {NAVY}; color: #E2E8F0; border-radius: 10px; padding: 8px; font-family: Consolas, "SF Mono", Menlo, monospace; font-size: 12px; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 10px; background: white; top: -1px; }}
QTabBar::tab {{ background: transparent; padding: 8px 16px; color: {MUTED}; font-weight: 600; border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; }}
QSplitter::handle {{ background: transparent; }}
QStatusBar {{ background: white; border-top: 1px solid {BORDER}; color: {MUTED}; }}
QGraphicsView {{ border: none; background: #E2E8F0; border-radius: 10px; }}
QMessageBox {{ background: white; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(BG))
    palette.setColor(QPalette.WindowText, QColor(TEXT))
    palette.setColor(QPalette.Base, QColor("white"))
    palette.setColor(QPalette.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.HighlightedText, QColor("white"))
    app.setPalette(palette)
    app.setFont(QFont("Segoe UI", 10))
    check = Path(tempfile.gettempdir()) / "omr_studio_check.png"
    icon("check", "#FFFFFF", 14).pixmap(14, 14).save(str(check), "PNG")
    app.setStyleSheet(build_stylesheet(check.as_posix()))
