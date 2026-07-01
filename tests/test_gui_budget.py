"""Budget setup wizard: seeding, editing, and creating a live budget sheet."""

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

    return MainWindow(Settings())


def test_seed_50_30_20(win):
    from abax.gui.dialogs.budget_dialog import BudgetWizard

    dlg = BudgetWizard(win)
    dlg._income.setText("4000")
    dlg._seed()
    cats = dlg.categories()
    assert cats and sum(c.budgeted for c in cats) == pytest.approx(4000, abs=2)
    assert any(c.name.startswith("Housing") for c in cats)


def test_blank_template(win):
    from abax.gui.dialogs.budget_dialog import BudgetWizard

    dlg = BudgetWizard(win)
    dlg._template.setCurrentText("Blank")
    dlg._seed()
    assert all(c.budgeted == 0.0 for c in dlg.categories())


def test_create_budget_sheet_is_live(win):
    from abax.gui.dialogs.budget_dialog import BudgetWizard

    dlg = BudgetWizard(win)
    dlg._income.setText("3000")
    dlg._seed()
    name = dlg.create_budget()
    assert name == "Budget"
    wb = win._doc.workbook
    sheet = wb.get_sheet(name)
    assert sheet is not None and wb.sheet is sheet     # switched to it

    # the Spent column is a live SUMIF: log an expense and watch it update
    # first category row is row index 5 (A6/B6/C6...)
    assert sheet.get_raw(5, 2).startswith("=SUMIF(")
    cat_name = sheet.get_raw(5, 0)
    sheet.set_cell(5, 6, cat_name)                      # expenses log: category (G)
    sheet.set_cell(5, 7, "123")                        # amount (H)
    sheet.recalculate()
    assert sheet.get_value(5, 2) == 123                # Spent updated


def test_create_twice_gets_unique_name(win):
    from abax.gui.dialogs.budget_dialog import BudgetWizard

    BudgetWizard(win).create_budget()
    second = BudgetWizard(win).create_budget()
    assert second == "Budget 2"


def test_wired_into_window(win):
    assert callable(win.show_budget_wizard)
    assert "Budget wizard..." in win._palette_actions()
