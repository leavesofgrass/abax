"""Menu organization: Radio and the general-math Scientific tools are Tools
submenus, code-isolation is a checkable Tools submenu, and the workbook/report
actions moved to File/Data."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.gui._qtcompat import QApplication  # noqa: E402
from abax.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    from abax.gui.main_window import MainWindow

    _win = MainWindow(Settings())
    yield _win
    # Dispose the window so it doesn't accumulate across a long test process
    # (many live MainWindows segfault Qt when a later test restyles them).
    from abax.gui._qtcompat import QEvent as _QEvent
    _win.deleteLater()
    app.sendPostedEvents(None, _QEvent.Type.DeferredDelete)
    app.processEvents()


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


def _submenu_items(win, top, sub):
    """Leaf labels directly under the submenu named ``sub`` of top-level ``top``."""
    for a in win.menuBar().actions():
        if a.text().replace("&", "") == top:
            for x in a.menu().actions():
                if x.menu() is not None and x.text().replace("&", "") == sub:
                    return [y.text().replace("&", "") for y in x.menu().actions() if y.text()]
    return None


def test_radio_is_a_tools_submenu(win):
    # Radio moved from a top-level menu into Tools.
    assert "Radio" not in _menu_titles(win)
    radio = _submenu_items(win, "Tools", "Radio")
    assert radio is not None, "Radio submenu missing from Tools"
    for label in ("RF toolkit...", "Smith chart...", "Antenna pattern...",
                  "RF reference (bands / CTCSS)...", "I/Q constellation -> SVG",
                  "Solve NEC deck (PyNEC)..."):
        assert label in radio, label


def test_scientific_is_general_math_only(win):
    # The RF tools live under Radio, not Scientific.
    sci = _submenu_items(win, "Tools", "Scientific")
    assert sci is not None
    for label in ("Matrix tool...", "Numerical solver...",
                  "ML tool (PCA / k-means / regression)..."):
        assert label in sci, label
    for gone in ("RF toolkit...", "Smith chart...", "Antenna pattern..."):
        assert gone not in sci, gone


def test_code_isolation_submenu(win):
    # A checkable Tools submenu offers the isolation levels, with the current
    # setting (default 'isolated') checked.
    iso = _submenu_items(win, "Tools", "Code isolation (sandbox)")
    assert iso is not None, "Code isolation submenu missing from Tools"
    assert len(iso) == 4
    acts = win._isolation_actions
    assert set(acts) == {"off", "restricted", "isolated", "strict"}
    assert all(a.isCheckable() for a in acts.values())
    assert acts["isolated"].isChecked()
    assert not acts["off"].isChecked()
    # Selecting a level updates the setting and the checkmarks.
    win.set_code_isolation("off")
    assert win._settings.code_isolation == "off"
    assert acts["off"].isChecked() and not acts["isolated"].isChecked()
    win.set_code_isolation("isolated")  # restore


def test_about_is_concise_and_current(win, monkeypatch):
    from abax.gui import _qtcompat

    captured = {}
    monkeypatch.setattr(_qtcompat.QMessageBox, "about",
                        staticmethod(lambda parent, title, text: captured.update(text=text)))
    win.show_about()
    text = captured["text"]
    # Concise but still names the headline capabilities.
    for keyword in ("RF", "machine learning", "Jupyter kernel", "dynamic arrays",
                    "spill"):
        assert keyword in text, keyword
    # Concise: the old multi-paragraph blurb is gone.
    assert text.count("<br><br>") <= 3
    # The function count must reflect the live registries exactly (no stale figure).
    from abax.core.functions import CONTEXT_FUNCTIONS, FUNCTIONS, LAZY_FUNCTIONS
    n = len(set(FUNCTIONS) | set(LAZY_FUNCTIONS) | set(CONTEXT_FUNCTIONS))
    assert f"{n} formula functions" in text


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
