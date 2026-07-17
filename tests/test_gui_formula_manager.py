"""GUI Formula manager — categories, search, guidance pane, insert."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.gui._qtcompat import QApplication, QEvent  # noqa: E402
from abax.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def dlg(app):
    from abax.gui.dialogs.formula_browser import FormulaBrowser
    from abax.gui.main_window import MainWindow

    win = MainWindow(Settings())
    d = FormulaBrowser(win)
    yield d
    d.deleteLater()
    win.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _cat_row(dlg, label: str) -> int:
    for i in range(dlg._cats.count()):
        if dlg._cats.item(i).text() == label:
            return i
    raise AssertionError(f"category {label!r} not listed")


def test_categories_listed_and_all_selected(dlg):
    assert dlg.windowTitle() == "Formula manager"
    assert dlg._cats.item(0).text() == "All functions"
    labels = [dlg._cats.item(i).text() for i in range(dlg._cats.count())]
    assert "Math & trig" in labels and "Lookup & reference" in labels
    assert dlg._list.count() > 500          # the full registry under "All"


def test_category_filters_the_list(dlg):
    dlg._cats.setCurrentRow(_cat_row(dlg, "Database"))
    names = [dlg._list.item(i).text() for i in range(dlg._list.count())]
    assert "DSUM" in names
    assert all(n.startswith("D") for n in names)
    assert "SUM" not in names


def test_search_filters_within_category(dlg):
    dlg._cats.setCurrentRow(_cat_row(dlg, "Math & trig"))
    dlg._filter.setText("ROUND")
    names = [dlg._list.item(i).text() for i in range(dlg._list.count())]
    assert names and all("ROUND" in n for n in names)


def test_guidance_pane_shows_signature_description_category(dlg):
    dlg._filter.setText("XLOOKUP")
    text = dlg._info.text()
    assert "XLOOKUP(" in text               # signature
    assert "lookup" in text.lower()          # description ("modern lookup ...")
    assert "Lookup" in text                  # category label


def test_insert_appends_to_formula_bar(dlg):
    dlg._filter.setText("XLOOKUP")
    dlg._insert()
    assert dlg._win._formula_bar.text().endswith("XLOOKUP(")
