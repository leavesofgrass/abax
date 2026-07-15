"""Embed charts in a workbook: anchored, range-driven, saved in the file.

Builds a 28-day two-sensor log plus a formula-driven weekly summary,
attaches four chart objects to the sheet, renders each with the
pure-stdlib SVG backend, and saves the workbook — charts included — to
out/charts.abax. If matplotlib is installed, the same objects also
render to PNG through the optional engine backend.
"""

import random
from pathlib import Path

from abax.core.chartobj import ChartObject, new_chart_id, render_chart
from abax.core.workbook import Workbook
from abax.engine.chartmpl import HAS_MATPLOTLIB, render_chart_mpl

random.seed(7)

out = Path("out")
out.mkdir(exist_ok=True)

# --- a 28-day, two-sensor log ------------------------------------------
wb = Workbook()
data = wb.sheet
data.name = "Data"
for c, header in enumerate(("day", "sensor_a", "sensor_b")):
    data.set_cell(0, c, header)
for day in range(1, 29):
    data.set_cell(day, 0, str(day))
    data.set_cell(day, 1, f"{20 + 0.15 * day + random.gauss(0, 0.8):.2f}")
    data.set_cell(day, 2, f"{24 + random.gauss(0, 1.6):.2f}")

# A second sheet summarises each week with formulas. Charts read the
# *computed* values, so the bar chart below plots live AVERAGE() results.
summary = wb.add_sheet("Summary")
summary.set("A1", "week")
summary.set("B1", "mean_a")
for w in range(4):
    summary.set(f"A{w + 2}", f"W{w + 1}")
    summary.set(f"B{w + 2}", f"=AVERAGE(Data!B{2 + w * 7}:B{8 + w * 7})")


# --- four chart objects, anchored to the Data sheet ---------------------
def add_chart(**kw):
    chart = ChartObject(id=new_chart_id(data.charts), **kw)
    data.charts.append(chart)
    return chart


add_chart(kind="line", source="A1:C29", title="Sensor readings by day",
          anchor=(1, 4), options={"first_col_x": True})
add_chart(kind="box", source="B1:C29", title="Spread per sensor",
          anchor=(18, 4))
add_chart(kind="histogram", source="B1:B29", title="sensor_a distribution",
          anchor=(35, 4), options={"bins": 8})
add_chart(kind="bar", source="Summary!A1:B5", title="Weekly mean (sensor_a)",
          anchor=(52, 4))

# Ranges resolve at render time, so an edit refreshes the picture: the
# next render of the same object picks up the new value (a day-14 glitch).
before = len(render_chart(wb, "Data", data.charts[0]))
data.set("B15", "35")
after = len(render_chart(wb, "Data", data.charts[0]))
print(f"edited B15: the line chart re-rendered {before:,} -> {after:,} bytes\n")

# --- render: the stdlib SVG backend always works -------------------------
for ch in data.charts:
    path = out / f"{ch.kind}.svg"
    path.write_text(render_chart(wb, "Data", ch), encoding="utf-8",
                    newline="\n")
    print(f"wrote out/{path.name}  ({path.stat().st_size:,} bytes)")

# --- optional: the matplotlib backend renders the same objects to PNG ----
if HAS_MATPLOTLIB:
    png = render_chart_mpl(wb, "Data", data.charts[0], fmt="png")
    (out / "line.png").write_bytes(png)
    print(f"wrote out/line.png  ({len(png):,} bytes, matplotlib backend)")
else:
    print('matplotlib not installed — skipped the PNG render'
          ' (pip install "abax[charts]" adds it)')

# --- save: the chart objects travel inside the .abax file ----------------
wb.save_json(out / "charts.abax")
print(f"\nsaved out/charts.abax with {len(data.charts)} embedded charts")
print("open it in the GUI and they are on the sheet, ready to refresh:")
print("  abax out/charts.abax")
