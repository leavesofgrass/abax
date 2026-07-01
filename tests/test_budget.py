"""Budget model + the live SUMIF-driven budget worksheet."""

from __future__ import annotations

import pytest

from abax.core import budget as B
from abax.core.sheet import Sheet


def test_model_rollups():
    b = B.Budget(income=3000, categories=[
        B.Category("Groceries", 400), B.Category("Transport", 200)])
    b.expenses = [B.Expense("2026-06-01", "Groceries", 150),
                  B.Expense("2026-06-05", "Groceries", 100),
                  B.Expense("2026-06-03", "Transport", 60)]
    assert b.spent("Groceries") == 250
    assert b.remaining("Groceries") == 150
    assert b.total_budgeted() == 600
    assert b.total_spent() == 310
    assert b.unallocated() == 2400
    assert b.over_budget() == []


def test_over_budget_detection():
    b = B.Budget(categories=[B.Category("Dining", 100)],
                 expenses=[B.Expense("x", "Dining", 130)])
    assert b.over_budget() == ["Dining"]


def test_fifty_thirty_twenty_splits_income():
    cats = B.fifty_thirty_twenty(4000)
    by_group = {}
    for c in cats:
        by_group.setdefault(c.group, 0.0)
        by_group[c.group] += c.budgeted
    assert by_group["needs"] == pytest.approx(2000, abs=1)     # 50%
    assert by_group["wants"] == pytest.approx(1200, abs=1)     # 30%
    assert by_group["savings"] == pytest.approx(800, abs=1)    # 20%
    assert sum(by_group.values()) == pytest.approx(4000, abs=1)


def test_budget_cells_layout():
    b = B.Budget(income=2000, categories=[B.Category("Rent", 800)])
    cells = dict(((r, c), v) for r, c, v in B.budget_cells(b))
    assert cells[(0, 0)] == "Monthly Budget"
    assert cells[(1, 1)] == "2000"
    assert cells[(4, 0)] == "Category" and cells[(4, 1)] == "Budgeted"
    assert cells[(4, 5)] == "Date"                 # expenses log header at col F
    assert cells[(5, 0)] == "Rent"
    assert cells[(5, 2)].startswith("=SUMIF(")     # Spent is a live SUMIF
    assert cells[(5, 3)] == "=B6-C6"               # Remaining = Budgeted - Spent


def test_live_worksheet_recomputes_from_logged_expenses():
    b = B.Budget(income=3000, categories=[
        B.Category("Groceries", 400), B.Category("Transport", 200)])
    sheet = Sheet()
    for r, c, raw in B.budget_cells(b):
        sheet.set_cell(r, c, raw)

    # log two grocery expenses + one transport in the expenses table (cols G/H)
    sheet.set_cell(5, 6, "Groceries")
    sheet.set_cell(5, 7, "150")
    sheet.set_cell(6, 6, "Groceries")
    sheet.set_cell(6, 7, "100")
    sheet.set_cell(7, 6, "Transport")
    sheet.set_cell(7, 7, "60")
    sheet.recalculate()

    assert sheet.get_value(5, 2) == 250            # Groceries Spent (SUMIF)
    assert sheet.get_value(5, 3) == 150            # Groceries Remaining = 400-250
    assert sheet.get_value(6, 2) == 60             # Transport Spent
    # totals row (after 2 categories -> row index 7, but that row also holds a
    # logged expense in cols F-I; the budget totals live in cols A-D)
    total_row = 5 + len(b.categories)
    assert sheet.get_value(total_row, 1) == 600    # total budgeted
    assert sheet.get_value(total_row, 2) == 310    # total spent


def test_unallocated_formula():
    b = B.Budget(income=3000, categories=[B.Category("Rent", 1000)])
    sheet = Sheet()
    for r, c, raw in B.budget_cells(b):
        sheet.set_cell(r, c, raw)
    sheet.recalculate()
    assert sheet.get_value(2, 1) == 2000           # 3000 income - 1000 budgeted
