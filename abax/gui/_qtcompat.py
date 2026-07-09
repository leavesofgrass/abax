"""The ONLY place binding-specific (PySide6 / PyQt6) code lives.

Prefers **PySide6** (LGPL) and falls back to PyQt6, re-exporting a normalized
surface so the rest of the GUI never branches on the binding. ``pyqtSignal`` is
aliased to PySide's ``Signal`` under PySide6. Set ``ABAX_QT_BINDING=PyQt6`` to
force PyQt6 (e.g. for testing); the default order is PySide6 then PyQt6.

Every Qt name any GUI module needs is imported here and re-exported — no other
module may ``import PySide6``/``PyQt6`` directly, so the app runs unchanged on
either binding.
"""

from __future__ import annotations

import os

BINDING: str

_FORCE = os.environ.get("ABAX_QT_BINDING", "")

try:
    if _FORCE == "PyQt6":
        raise ImportError("ABAX_QT_BINDING=PyQt6")
    from PySide6.QtCore import (
        QAbstractTableModel,
        QEvent,
        QItemSelection,
        QItemSelectionModel,
        QModelIndex,
        QObject,
        QPoint,
        QPointF,
        QRect,
        QRectF,
        QSize,
        QStringListModel,
        Qt,
        QThread,
        QTimer,
    )
    from PySide6.QtCore import Signal as pyqtSignal  # type: ignore
    from PySide6.QtGui import (
        QAction,
        QBrush,
        QColor,
        QFont,
        QFontDatabase,
        QFontMetricsF,
        QIcon,
        QImage,
        QKeyEvent,
        QKeySequence,
        QLinearGradient,
        QPageSize,
        QPainter,
        QPainterPath,
        QPdfWriter,
        QPen,
        QPixmap,
        QTextDocument,
    )
    from PySide6.QtPrintSupport import QPrintDialog, QPrinter
    from PySide6.QtWidgets import (
        QAbstractItemDelegate,
        QAbstractItemView,
        QApplication,
        QCheckBox,
        QColorDialog,
        QComboBox,
        QCompleter,
        QDialog,
        QDialogButtonBox,
        QDockWidget,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QLineEdit,
        QListWidget,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QRadioButton,
        QSpinBox,
        QSplitter,
        QStatusBar,
        QStyledItemDelegate,
        QTabBar,
        QTableView,
        QTableWidget,
        QTableWidgetItem,
        QTableWidgetSelectionRange,
        QTabWidget,
        QToolTip,
        QVBoxLayout,
        QWidget,
    )

    BINDING = "PySide6"
except ImportError:  # pragma: no cover - depends on which binding is installed
    from PyQt6.QtCore import (
        QAbstractTableModel,
        QEvent,
        QItemSelection,
        QItemSelectionModel,
        QModelIndex,
        QObject,
        QPoint,
        QPointF,
        QRect,
        QRectF,
        QSize,
        QStringListModel,
        Qt,
        QThread,
        QTimer,
        pyqtSignal,  # type: ignore
    )
    from PyQt6.QtGui import (
        QAction,
        QBrush,
        QColor,
        QFont,
        QFontDatabase,
        QFontMetricsF,
        QIcon,
        QImage,
        QKeyEvent,
        QKeySequence,
        QLinearGradient,
        QPageSize,
        QPainter,
        QPainterPath,
        QPdfWriter,
        QPen,
        QPixmap,
        QTextDocument,
    )
    from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
    from PyQt6.QtWidgets import (
        QAbstractItemDelegate,
        QAbstractItemView,
        QApplication,
        QCheckBox,
        QColorDialog,
        QComboBox,
        QCompleter,
        QDialog,
        QDialogButtonBox,
        QDockWidget,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QInputDialog,
        QLabel,
        QLineEdit,
        QListWidget,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QRadioButton,
        QSpinBox,
        QSplitter,
        QStatusBar,
        QStyledItemDelegate,
        QTabBar,
        QTableView,
        QTableWidget,
        QTableWidgetItem,
        QTableWidgetSelectionRange,
        QTabWidget,
        QToolTip,
        QVBoxLayout,
        QWidget,
    )

    BINDING = "PyQt6"

# QtSvgWidgets is optional (shipped in PySide6-Essentials / PyQt6, but a thin or
# unusual build may lack it). A live SVG preview degrades to export-only when
# ``QSvgWidget`` is None, so callers must treat it as possibly-absent.
try:
    if BINDING == "PySide6":
        from PySide6.QtSvgWidgets import QSvgWidget
    else:
        from PyQt6.QtSvgWidgets import QSvgWidget
except Exception:  # noqa: BLE001 — optional widget; absence is handled by callers
    QSvgWidget = None  # type: ignore

# QDesktopServices/QUrl (opening a folder/URL in the OS handler) are always
# present in a normal binding, but keep the import defensive so a stripped build
# can't break module load — callers fall back to os.startfile.
try:
    if BINDING == "PySide6":
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
    else:
        from PyQt6.QtCore import QUrl
        from PyQt6.QtGui import QDesktopServices
except Exception:  # noqa: BLE001
    QUrl = None  # type: ignore
    QDesktopServices = None  # type: ignore

__all__ = [
    "BINDING",
    "QSvgWidget",
    "QDesktopServices",
    "QUrl",
    "QAbstractTableModel",
    "QEvent",
    "QItemSelection",
    "QItemSelectionModel",
    "QModelIndex",
    "QObject",
    "QPoint",
    "QPointF",
    "QRect",
    "QRectF",
    "QSize",
    "Qt",
    "QStringListModel",
    "QThread",
    "QTimer",
    "pyqtSignal",
    "QAction",
    "QBrush",
    "QColor",
    "QFont",
    "QFontDatabase",
    "QFontMetricsF",
    "QIcon",
    "QImage",
    "QKeyEvent",
    "QKeySequence",
    "QLinearGradient",
    "QPageSize",
    "QPainter",
    "QPainterPath",
    "QPdfWriter",
    "QPen",
    "QPixmap",
    "QPrintDialog",
    "QPrinter",
    "QTextDocument",
    "QAbstractItemDelegate",
    "QAbstractItemView",
    "QSplitter",
    "QApplication",
    "QCheckBox",
    "QColorDialog",
    "QComboBox",
    "QCompleter",
    "QDialog",
    "QDialogButtonBox",
    "QDockWidget",
    "QDoubleSpinBox",
    "QFileDialog",
    "QFormLayout",
    "QGridLayout",
    "QGroupBox",
    "QHBoxLayout",
    "QInputDialog",
    "QLabel",
    "QLineEdit",
    "QListWidget",
    "QMainWindow",
    "QMenu",
    "QMessageBox",
    "QPlainTextEdit",
    "QProgressBar",
    "QPushButton",
    "QRadioButton",
    "QSpinBox",
    "QStatusBar",
    "QStyledItemDelegate",
    "QTabBar",
    "QTableView",
    "QTableWidget",
    "QTableWidgetItem",
    "QTableWidgetSelectionRange",
    "QTabWidget",
    "QToolTip",
    "QVBoxLayout",
    "QWidget",
]
