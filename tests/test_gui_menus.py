"""Menu organization after the reorg: a dedicated Radio menu, Scientific holds
only the general-math tools, and the workbook/report actions moved to File/Data."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("qcell.gui._qtcompat")

from qcell.gui._qtcompat import QApplication  # noqa: E402
from qcell.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    from qcell.gui.main_window import MainWindow

    return MainWindow(Settings())


def _menu_titles(win):
    return [a.text().replace("&", "") for a in win.menuBar().actions()]


def _items(win, title):
    """Flat list of leaf + submenu labels under a top-level menu (recurses one
    level into submenus)."""
    for a in win.menuBar().actions():
        if a.text().replace("&", "") == title:
            out = []
            for x in a.menu().actions():
                if not x.text():
                    continue
                out.append(x.text().replace("&", ""))
                if x.menu() is not None:
                    out += [y.text().replace("&", "") for y in x.menu().actions() if y.text()]
            return out
    return None


def test_radio_menu_exists(win):
    assert "Radio" in _menu_titles(win)
    radio = _items(win, "Radio")
    for label in ("RF toolkit...", "Smith chart...", "Antenna pattern...",
                  "RF reference (bands / CTCSS)...", "I/Q constellation -> SVG",
                  "Solve NEC deck (PyNEC)..."):
        assert label in radio, label


def test_scientific_is_general_math_only(win):
    tools = _items(win, "Tools")
    # The RF tools left Scientific for the Radio menu.
    for label in ("Matrix tool...", "Numerical solver...", "ML tool (PCA / k-means / regression)..."):
        assert label in tools, label
    for gone in ("RF toolkit...", "Smith chart...", "Antenna pattern..."):
        assert gone not in tools, gone


def test_about_covers_current_features(win, monkeypatch):
    from qcell.gui import _qtcompat

    captured = {}
    monkeypatch.setattr(_qtcompat.QMessageBox, "about",
                        staticmethod(lambda parent, title, text: captured.update(text=text)))
    win.show_about()
    text = captured["text"]
    # The About box should reflect the breadth of the app, not just "spreadsheet".
    for keyword in ("RF", "signal processing", "antenna modeling", "Jupyter kernel",
                    "machine learning", "Smith chart", "XLOOKUP"):
        assert keyword in text, keyword


def test_report_and_compare_moved(win):
    file_items = _items(win, "File")
    data_items = _items(win, "Data")
    insert_items = _items(win, "Insert")
    assert "Export as HTML report..." in file_items
    assert "Compare workbook..." in data_items
    assert "Export chart as SVG..." in insert_items
    # Analyze keeps the data-science tools + goal seek.
    assert "Statistics / analysis..." in data_items
    assert "Goal seek..." in data_items
