"""Dynamic arrays: one formula spills its results across many cells.

=SORT(UNIQUE(...)), =FILTER(...), and =SEQUENCE(...) — the same
Excel-style behaviour you get typing them into the grid.
"""

from abax.core.workbook import Workbook

wb = Workbook()
sheet = wb.sheet

# Duplicate-laden sales figures in A1:A8.
for r, v in enumerate([70, 20, 70, 55, 20, 90, 55, 40]):
    sheet.set_cell(r, 0, str(v))

sheet.set_cell(0, 2, "=SORT(UNIQUE(A1:A8))")   # C1 spills downward
sheet.set_cell(0, 4, "=FILTER(A1:A8, A1:A8>50)")  # E1 keeps the big ones
sheet.set_cell(0, 6, "=SEQUENCE(3, 3)")        # G1 spills a 3x3 block


def column(col: int) -> list:
    """Read a spilled column until it runs out."""
    out, r = [], 0
    while (v := sheet.get_value(r, col)) is not None:
        out.append(v)
        r += 1
    return out


print("A1:A8            :", column(0))
print("SORT(UNIQUE(...)) :", column(2))
print("FILTER(... > 50)  :", column(4))
print("SEQUENCE(3, 3)    :")
for r in range(3):
    print("   ", [sheet.get_value(r, 6 + c) for c in range(3)])
