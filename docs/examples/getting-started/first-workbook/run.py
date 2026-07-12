"""Build your first abax workbook from Python and save it to out/.

Everything here is the pure-stdlib core — no optional packages needed.
"""

from pathlib import Path

from abax.core.workbook import Workbook

wb = Workbook()
sheet = wb.sheet
sheet.name = "Groceries"

# A header row, three items, and formulas that multiply Qty x Price.
rows = [
    ("Item",   "Qty", "Price", "Total"),
    ("Apples", 4,     0.60,    "=B2*C2"),
    ("Bread",  2,     2.10,    "=B3*C3"),
    ("Coffee", 1,     8.75,    "=B4*C4"),
]
for r, row in enumerate(rows):
    for c, value in enumerate(row):
        sheet.set_cell(r, c, str(value))
sheet.set_cell(4, 0, "TOTAL")
sheet.set_cell(4, 3, "=SUM(D2:D4)")

# Formulas compute on read — print the grid the way the GUI would show it.
for r in range(5):
    cells = [sheet.get_value(r, c) for c in range(4)]
    print("  ".join(f"{'' if v is None else v!s:>7}" for v in cells))

out = Path("out")
out.mkdir(exist_ok=True)
wb.save_json(out / "first-workbook.abax")
print("\nSaved out/first-workbook.abax — open it in the GUI with:")
print("  abax out/first-workbook.abax")
