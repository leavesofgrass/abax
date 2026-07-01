# Budgeting

abax includes a small budgeting workflow that turns your budget into a **live
spreadsheet** — because tracking a budget is exactly what a spreadsheet is good
at. Open it from *Tools → Budget wizard* (or the command palette).

## The wizard

1. **Enter your monthly income.**
2. **Seed categories.** Choose the **50/30/20 rule** to pre-fill needs / wants /
   savings categories (50 % needs, 30 % wants, 20 % savings) sized from your
   income, or **Blank** to start from a plain list. Edit the category table freely
   — add rows, rename, change amounts. A running summary shows how much you've
   allocated and what's left unallocated.
3. **Create budget sheet.** abax adds a new **Budget** sheet to your workbook and
   switches to it.

## The live budget sheet

The generated sheet has two parts side by side:

- A **budget table** — `Category | Budgeted | Spent | Remaining`, with an income
  and unallocated summary above it. **Spent** is a `SUMIF` over the expenses log,
  and **Remaining** is `Budgeted − Spent`. A totals row sums each column.
- An **expenses log** (`Date | Category | Amount | Note`) that you fill in as you
  spend.

Because *Spent* is a formula, **logging an expense updates the whole budget
automatically** — type a row in the expenses log (matching a category name) and
the Spent, Remaining, and totals recompute through abax's formula engine. No
special code path: it's an ordinary spreadsheet you can edit, chart, or export
like any other.

The model and worksheet builder live in `core/budget.py` (pure stdlib), so you can
also build a budget from the Python console:

```python
from abax.core import budget as B
b = B.Budget(income=4000, categories=B.fifty_thirty_twenty(4000))
for r, c, raw in B.budget_cells(b):
    sheet.set_cell(r, c, raw)
```
