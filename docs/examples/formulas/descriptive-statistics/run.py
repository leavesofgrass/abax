"""Summarize a column of data with abax's statistics functions.

Reaction times (ms) from a small experiment go in column A, treatment
scores in column B, and the summary is ordinary spreadsheet formulas.
"""

from abax.core.workbook import Workbook

times = [312, 279, 301, 288, 344, 297, 315, 290, 322, 305, 281, 330]
scores = [58, 61, 55, 63, 49, 60, 52, 62, 50, 57, 64, 48]

wb = Workbook()
sheet = wb.sheet
for r, (t, s) in enumerate(zip(times, scores)):
    sheet.set_cell(r, 0, str(t))       # column A
    sheet.set_cell(r, 1, str(s))       # column B

summary = [
    ("Mean",        "=AVERAGE(A1:A12)"),
    ("Median",      "=MEDIAN(A1:A12)"),
    ("Std dev",     "=STDEV.S(A1:A12)"),
    ("Min / Max",   '=MIN(A1:A12)&" / "&MAX(A1:A12)'),
    ("90th pctile", "=PERCENTILE(A1:A12, 0.9)"),
    ("IQR",         "=QUARTILE(A1:A12, 3) - QUARTILE(A1:A12, 1)"),
    ("r (A vs B)",  "=CORREL(A1:A12, B1:B12)"),
]
for r, (label, formula) in enumerate(summary):
    sheet.set_cell(r, 3, label)        # column D
    sheet.set_cell(r, 4, formula)      # column E

for r, (label, _f) in enumerate(summary):
    v = sheet.get_value(r, 4)
    v = round(v, 3) if isinstance(v, float) else v
    print(f"{label:>12}: {v}")
