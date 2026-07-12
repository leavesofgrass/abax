"""Name a region as a Table, then write formulas against its column labels.

=SUM(Sales[Amount]) reads like English and keeps working when the table
moves — no more counting rows for A1 ranges.
"""

from abax.core.tables import detect_table
from abax.core.workbook import Workbook

wb = Workbook()
sheet = wb.sheet

rows = [
    ("Region", "Amount", "Qty"),
    ("West",   1200,     3),
    ("East",   950,      2),
    ("West",   400,      1),
    ("North",  2100,     5),
]
for r, row in enumerate(rows):
    for c, value in enumerate(row):
        sheet.set_cell(r, c, str(value))

# Rows 0-4, columns A-C, header row on top -> a Table named "Sales".
headers = [sheet.get_value(0, c) for c in range(3)]
table = detect_table(sheet.name, 0, 0, 4, 2, "Sales", headers)
wb.tables.add(table)

queries = [
    ("Total amount",  "=SUM(Sales[Amount])"),
    ("Average qty",   "=AVERAGE(Sales[Qty])"),
    ("Rows",          "=COUNTA(Sales[Region])"),
    ("West only",     '=SUMIF(Sales[Region], "West", Sales[Amount])'),
]
for r, (label, formula) in enumerate(queries, start=6):
    sheet.set_cell(r, 0, label)
    sheet.set_cell(r, 1, formula)
    print(f"{label:>13}: {sheet.get_value(r, 1)}")
