"""Personal budgeting model + a live budget-worksheet builder (pure stdlib).

A small envelope-budgeting model (income, budgeted categories, logged expenses)
with the usual rollups, plus :func:`budget_cells`, which lays the model out as a
**live spreadsheet**: a Category / Budgeted / Spent / Remaining table where *Spent*
is a ``SUMIF`` over an Expenses log the user fills in, and *Remaining* is
``Budgeted - Spent``. So once the wizard drops the sheet in, logging an expense
updates the budget automatically — abax's own formula engine does the work.

The 50/30/20 helper seeds sensible needs / wants / savings categories from a
monthly income. Everything is plain data and arithmetic — no GUI, fully tested.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .reference import to_a1


@dataclass
class Category:
    name: str
    budgeted: float
    group: str = ""          # "needs" / "wants" / "savings" (50/30/20), optional


@dataclass
class Expense:
    date: str
    category: str
    amount: float
    note: str = ""


@dataclass
class Budget:
    income: float = 0.0
    categories: list[Category] = field(default_factory=list)
    expenses: list[Expense] = field(default_factory=list)

    def spent(self, category: str) -> float:
        return sum(e.amount for e in self.expenses if e.category == category)

    def remaining(self, category: str) -> float:
        budgeted = next((c.budgeted for c in self.categories if c.name == category), 0.0)
        return budgeted - self.spent(category)

    def total_budgeted(self) -> float:
        return sum(c.budgeted for c in self.categories)

    def total_spent(self) -> float:
        return sum(e.amount for e in self.expenses)

    def unallocated(self) -> float:
        """Income not yet assigned to a category (negative = over-allocated)."""
        return self.income - self.total_budgeted()

    def by_category(self) -> list[dict]:
        return [{"name": c.name, "group": c.group, "budgeted": c.budgeted,
                 "spent": self.spent(c.name),
                 "remaining": c.budgeted - self.spent(c.name)}
                for c in self.categories]

    def over_budget(self) -> list[str]:
        return [c.name for c in self.categories if self.spent(c.name) > c.budgeted]


# 50/30/20: fractions of monthly income, grouped. Each group sums to its share.
_TEMPLATE = (
    ("needs", (("Housing / rent", 0.25), ("Utilities", 0.05), ("Groceries", 0.10),
               ("Transport", 0.07), ("Insurance", 0.03))),
    ("wants", (("Dining out", 0.10), ("Entertainment", 0.07), ("Shopping", 0.08),
               ("Subscriptions", 0.05))),
    ("savings", (("Emergency fund", 0.10), ("Retirement", 0.07), ("Debt payoff", 0.03))),
)


def fifty_thirty_twenty(income: float) -> list[Category]:
    """Seed categories from the 50/30/20 rule (needs / wants / savings)."""
    out: list[Category] = []
    for group, items in _TEMPLATE:
        for name, frac in items:
            out.append(Category(name, round(income * frac, 2), group))
    return out


def suggested_categories() -> list[str]:
    """A flat list of common category names (for a blank/custom budget)."""
    return [name for _g, items in _TEMPLATE for name, _f in items]


_HEADERS = ("Category", "Budgeted", "Spent", "Remaining")
_EXP_HEADERS = ("Date", "Category", "Amount", "Note")
_EXP_COL = 5             # column F: the expenses log starts here (F,G,H,I)
_DATA_ROW = 5            # 0-indexed row 5 (spreadsheet row 6): first data row
_LOG_ROWS = 1000         # SUMIF scans this many expense rows


def budget_cells(budget: Budget) -> list[tuple[int, int, str]]:
    """Lay ``budget`` out as ``(row, col, raw)`` cells for a live budget sheet.

    Layout (0-indexed): a title and income/unallocated summary, a budget table at
    columns A-D with ``SUMIF``-driven Spent and ``Budgeted - Spent`` Remaining, a
    totals row, and an Expenses log at columns F-I (seeded with any existing
    expenses) that the Spent column sums over.
    """
    cells: list[tuple[int, int, str]] = []
    cat_col, bud_col, spent_col, rem_col = 0, 1, 2, 3
    exp_date, exp_cat, exp_amt, exp_note = (_EXP_COL, _EXP_COL + 1,
                                            _EXP_COL + 2, _EXP_COL + 3)
    n = len(budget.categories)
    last_data = _DATA_ROW + n - 1            # 0-indexed last category row
    total_row = _DATA_ROW + n                # 0-indexed totals row

    # A1 column letters for formulas
    spent_range_lo = to_a1(_DATA_ROW, exp_cat)
    spent_range_hi = to_a1(_DATA_ROW + _LOG_ROWS - 1, exp_cat)
    amt_range_lo = to_a1(_DATA_ROW, exp_amt)
    amt_range_hi = to_a1(_DATA_ROW + _LOG_ROWS - 1, exp_amt)

    cells.append((0, 0, "Monthly Budget"))
    cells.append((1, 0, "Income"))
    cells.append((1, 1, _fmt(budget.income)))
    cells.append((2, 0, "Unallocated"))
    if n:
        b_lo, b_hi = to_a1(_DATA_ROW, bud_col), to_a1(last_data, bud_col)
        cells.append((2, 1, f"={to_a1(1, 1)}-SUM({b_lo}:{b_hi})"))
    else:
        cells.append((2, 1, f"={to_a1(1, 1)}"))

    # budget table header (row index 4)
    for c, label in enumerate(_HEADERS):
        cells.append((_DATA_ROW - 1, c, label))
    # expenses log header (same header row, columns F-I)
    for i, label in enumerate(_EXP_HEADERS):
        cells.append((_DATA_ROW - 1, _EXP_COL + i, label))

    for i, cat in enumerate(budget.categories):
        r = _DATA_ROW + i
        name_ref = to_a1(r, cat_col)
        bud_ref = to_a1(r, bud_col)
        spent_ref = to_a1(r, spent_col)
        cells.append((r, cat_col, cat.name))
        cells.append((r, bud_col, _fmt(cat.budgeted)))
        cells.append((r, spent_col,
                      f"=SUMIF({spent_range_lo}:{spent_range_hi},{name_ref},"
                      f"{amt_range_lo}:{amt_range_hi})"))
        cells.append((r, rem_col, f"={bud_ref}-{spent_ref}"))

    if n:
        cells.append((total_row, cat_col, "Total"))
        for c in (bud_col, spent_col, rem_col):
            lo, hi = to_a1(_DATA_ROW, c), to_a1(last_data, c)
            cells.append((total_row, c, f"=SUM({lo}:{hi})"))

    # seed the expenses log with any existing expenses
    for i, e in enumerate(budget.expenses):
        r = _DATA_ROW + i
        cells.append((r, exp_date, e.date))
        cells.append((r, exp_cat, e.category))
        cells.append((r, exp_amt, _fmt(e.amount)))
        if e.note:
            cells.append((r, exp_note, e.note))
    return cells


def _fmt(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}"
