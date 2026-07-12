"""Clean a messy CSV with spreadsheet formulas, then export the result.

Names get TRIM + PROPER; dollar amounts lose their "$" and thousands
comma and become real numbers. The cleaned table is written to
out/cleaned.csv.
"""

import csv
from pathlib import Path

from abax.core.workbook import Workbook

here = Path(__file__).parent
wb = Workbook()
sheet = wb.sheet

# Load the raw CSV into columns A-B (row 0 is the header).
with open(here / "messy.csv", newline="", encoding="utf-8") as f:
    for r, row in enumerate(csv.reader(f)):
        for c, value in enumerate(row):
            sheet.set_cell(r, c, value)

# Cleaning formulas in columns C-D.
sheet.set_cell(0, 2, "name")
sheet.set_cell(0, 3, "amount")
for r in range(1, 5):
    sheet.set_cell(r, 2, f"=PROPER(TRIM(A{r + 1}))")
    sheet.set_cell(
        r, 3, f'=VALUE(SUBSTITUTE(SUBSTITUTE(B{r + 1}, "$", ""), ",", ""))'
    )

print(f"{'raw name':<18} {'raw amount':>11}   ->  {'clean':<15} {'amount':>8}")
for r in range(1, 5):
    print(
        f"{sheet.get_value(r, 0)!r:<18} {sheet.get_value(r, 1):>11}"
        f"   ->  {sheet.get_value(r, 2):<15} {sheet.get_value(r, 3):>8}"
    )

# Export the computed values (columns C-D only).
out = Path("out")
out.mkdir(exist_ok=True)
with open(out / "cleaned.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    for r in range(5):
        writer.writerow([sheet.get_value(r, 2), sheet.get_value(r, 3)])

total = sum(sheet.get_value(r, 3) for r in range(1, 5))
print(f"\nWrote out/cleaned.csv — 4 rows, total {total:.2f}")
