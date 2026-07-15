# Embedded charts: saved in the workbook, refreshed by recalc

Attach four chart objects to a sheet — line, box, histogram, and bar —
render them to SVG with zero dependencies, and save a `.abax` file that
carries the charts inside it.

**You'll need:** abax only. If matplotlib is installed
(`pip install "abax[charts]"`) the script also renders one PNG through
the optional backend; without it, that step skips with a hint.

## Run it

```sh
cd docs/examples/charts/embedded-charts
python run.py
```

## What you should see

```
edited B15: the line chart re-rendered 3,631 -> 3,639 bytes

wrote out/line.svg  (3,639 bytes)
wrote out/box.svg  (2,993 bytes)
wrote out/histogram.svg  (3,191 bytes)
wrote out/bar.svg  (2,561 bytes)
wrote out/line.png  (29,736 bytes, matplotlib backend)

saved out/charts.abax with 4 embedded charts
open it in the GUI and they are on the sheet, ready to refresh:
  abax out/charts.abax
```

Without matplotlib the `line.png` line becomes
`matplotlib not installed — skipped the PNG render (pip install "abax[charts]" adds it)`
and everything else is identical.

## How it works

- A `ChartObject` records *what* to draw (`kind`), *from where*
  (`source`, an A1 range — `"Summary!A1:B5"` reaches another sheet), and
  *where it sits* (`anchor` + pixel size). Appending it to
  `sheet.charts` is all it takes to embed it.
- Ranges resolve at **render time**, so the day-14 edit shows up in the
  very next `render_chart` call — no chart update step. The bar chart
  reads `=AVERAGE(...)` formulas, so it plots computed values.
- Column headers become series names (`sensor_a`, `sensor_b` in the
  legend); `options={"first_col_x": True}` makes the first column supply
  the x values; `bins` shapes the histogram.
- `render_chart` (pure stdlib) returns a complete `<svg>` string —
  writing it to a file is the export. `render_chart_mpl` draws the
  *same* chart data with matplotlib as PNG or SVG when it's installed.
- `wb.save_json(...)` writes envelope **schema v3**: the chart objects
  live in the file, so reopening the workbook brings them back —
  anchored, editable, and re-rendered from current cell values.

## Next steps

- [Charts guide](../../../charts.md) — all ten kinds, the data shape
  each expects, options, and both rendering backends.
- [Statistical charts](../statistical-charts/README.md) — one-off SVG
  files straight from lists, no workbook involved.
- [File formats](../../../file-formats.md) — how charts persist in the
  native envelope.
