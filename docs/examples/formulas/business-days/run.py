"""Schedule work in business days with WORKDAY.INTL and NETWORKDAYS.INTL.

Each task starts the working day after the previous one finishes;
weekends and two holidays are skipped automatically.
"""

from abax.core.workbook import Workbook

wb = Workbook()
sheet = wb.sheet

# Two holidays in D1:D2 (ISO dates, like everywhere in abax).
sheet.set_cell(0, 3, "2026-09-07")   # Labor Day
sheet.set_cell(1, 3, "2026-11-26")   # Thanksgiving

tasks = [("Design", 5), ("Build", 10), ("Test", 4), ("Ship", 1)]
sheet.set_cell(0, 0, "Task")
sheet.set_cell(0, 1, "Days")
sheet.set_cell(0, 2, "Finishes")

start = "2026-09-01"
for r, (name, days) in enumerate(tasks, start=1):
    sheet.set_cell(r, 0, name)
    sheet.set_cell(r, 1, str(days))
    prev = f"C{r}" if r > 1 else f'"{start}"'
    # weekend spec 1 = Saturday+Sunday; D1:D2 are the holidays.
    sheet.set_cell(r, 2, f"=WORKDAY.INTL({prev}, B{r + 1}, 1, D1:D2)")

for r, (name, days) in enumerate(tasks, start=1):
    print(f"{name:>7} ({days:>2}d) finishes {sheet.get_value(r, 2)}")

sheet.set_cell(6, 2, f'=NETWORKDAYS.INTL("{start}", C5, 1, D1:D2)')
print(f"\nWhole project: {sheet.get_value(6, 2)} working days")
