"""Conditional formatting from a script: regex rules, CSS styling, top-N.

The same CondRule objects the GUI dialog creates, driven headlessly.
style_at() reports the merged style for any cell — here we print which
cells each rule lit up. Rules persist with the workbook.
"""

from pathlib import Path

from abax.core.format.condformat import CondRule, scale_context, style_at
from abax.core.workbook import Workbook

wb = Workbook()
sheet = wb.sheet

rows = [
    ("Task",            "Status",      "Score"),
    ("Import wizard",   "done",        88),
    ("Chart export",    "BLOCKED",     35),
    ("Undo history",    "in progress", 72),
    ("Login flow",      "blocked",     41),
    ("Search index",    "done",        95),
    ("Dark theme",      "in progress", 60),
]
for r, row in enumerate(rows):
    for c, value in enumerate(row):
        sheet.set_cell(r, c, str(value))

sheet.cond_rules = [
    # Any status containing "blocked", any case — white-on-red, bold.
    CondRule(range="B2:B7", kind="regex", value="(?i)blocked",
             css="color: #ffffff; background: #c62828; font-weight: bold"),
    # The three best scores get a green fill.
    CondRule(range="C2:C7", kind="top_n", value=3, color="#2e7d32"),
    # Below-average scores are flagged amber.
    CondRule(range="C2:C7", kind="below_avg", color="#ff8f00"),
]

# One range scan for the range-aware rules (top_n / below_avg), reused
# for every cell — the same trick the GUI grid uses per repaint.
ctx = scale_context(sheet, sheet.cond_rules)

for r in range(1, 7):
    for c in (1, 2):
        style = style_at(sheet, sheet.cond_rules, r, c, ctx)
        if style is not None:
            cell = f"{'BC'[c - 1]}{r + 1}"
            parts = [p for p in (
                f"fill {style.fill}" if style.fill else "",
                f"text {style.text}" if style.text else "",
                "bold" if style.bold else "",
            ) if p]
            print(f"{cell}  {sheet.get_value(r, c)!s:<12} -> {', '.join(parts)}")

out = Path("out")
out.mkdir(exist_ok=True)
wb.save_json(out / "formatted.abax")
print("\nSaved out/formatted.abax — open it to see the colours:")
print("  abax out/formatted.abax")
