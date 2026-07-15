# Embedded charts

A chart in abax can be more than an exported picture: an **embedded chart
object** lives *on the sheet*. It is **anchored** (it floats over a cell, with
a pixel size), **range-driven** (it records an A1 source range, not a copy of
the data), it **refreshes on recalc** (ranges resolve at render time, so
re-rendering after an edit is the whole update story), and it **survives in
the file** (chart objects round-trip through the native `.abax` envelope,
[schema v3](file-formats.md#embedded-charts-schema-v3)). The model lives in
[`abax/core/chartobj.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/chartobj.py)
— pure stdlib, like everything in the core.

This page covers the chart model, the ten kinds and the data shape each one
expects, the two rendering backends, and how to script all of it. For
inserting and arranging charts interactively, see the
[GUI guide](gui-guide.md); for one-off plots and exported SVG files that
*don't* live in the workbook, see
[Graph / chart](data-analysis.md#graph--chart) in the data & analysis tools.

## The chart object

Every chart is a `ChartObject` with a handful of plain fields:

| Field | Meaning | Default |
| --- | --- | --- |
| `id` | unique per sheet — `new_chart_id(sheet.charts)` hands out `chart1`, `chart2`, … | — |
| `kind` | one of the ten kinds below | — |
| `source` | the data range, e.g. `"A1:C10"` — or sheet-qualified, `"Data!A1:C10"` | — |
| `title` | drawn above the plot | `""` |
| `labels` | optional category/label range (bar, waterfall, heatmap) | `""` |
| `anchor` | `(row, col)` the top-left corner floats over (0-based) | `(0, 0)` |
| `width`, `height` | pixel size | `480 × 320` |
| `options` | kind-specific extras (below) | `{}` |

The objects live in the `sheet.charts` list. On save they become a per-sheet
`charts` key in the envelope — omitted when the list is empty, so a plain
grid's file is unchanged, and older v1/v2 files simply load with no charts.
Only the native format carries chart objects: exporting to `.xlsx`, CSV, or
any other format writes the *data*, not the charts.

Three options are recognised (anything else is ignored, so an option written
by a newer abax never breaks an older one):

| Option | Kind | Effect |
| --- | --- | --- |
| `first_col_x` | line | the first column supplies shared x values for the other columns |
| `bins` | histogram | number of equal-width bins (default 10) |
| `total` | waterfall | append a running-total bar (default true) |

## The ten kinds and the data each expects

`CHART_KINDS` is `line`, `bar`, `scatter`, `histogram`, `box`, `violin`,
`qq`, `ecdf`, `heatmap`, `waterfall`. All of them read their source range
through the same shaping pass (`chart_data`), with three shared rules:

- **Headers are detected, not declared.** When the range has at least two
  rows and its first row contains text but no numbers, that row names the
  columns — series pick up the header names in the legend. Columns without a
  header fall back to their column letter.
- **Non-numeric cells are skipped, not errors.** Text, blanks, and booleans
  drop out of numeric series; numeric-looking text (including `"1,234"`)
  counts as a number.
- **Formulas feed charts their computed values**, through the normal
  evaluation path — a chart over `=AVERAGE(...)` cells plots the averages.

| Kind | Feed it | Shaping rules |
| --- | --- | --- |
| `line` | columns of numbers | one series per column, points at x = 1…n; with `first_col_x`, the first column becomes the shared x axis |
| `bar` | a text column + a value column, or bare numbers | when every data row starts with text, the first column is the categories and the **second** column the values; otherwise every numeric cell is a value, with categories from the `labels` range (else 1…n) |
| `scatter` | two columns | first column x, second y; a row missing either number is skipped |
| `histogram` | any numeric block | every numeric cell pooled into one sample; `bins` controls the bin count |
| `box` / `violin` / `ecdf` | columns of numbers | one named series per column — side-by-side boxes, violins, or ECDF step curves |
| `qq` | any numeric block | pooled values against theoretical normal quantiles (a straight line ⇒ plausibly normal) |
| `heatmap` | a numeric matrix | text cells inside the matrix count as 0, rows with no numbers are dropped, ragged rows are padded; a `labels` range supplies one label per row — ideal for a correlation matrix |
| `waterfall` | categories + signed deltas | category rules as for `bar`; the values are increments, and a running-total bar is appended unless `total` is false |

(Sunburst, treemap, and sparkline charts exist in the
[SVG chart engine](data-analysis.md#graph--chart) but need hierarchical input
or live in a cell formula, so they are not embeddable kinds.)

## Two rendering backends

**Built-in SVG — always works.** `render_chart(workbook, sheet_name, chart)`
resolves the ranges against current cell values and returns a complete,
self-contained `<svg>…</svg>` string, rendered by the pure-stdlib
[`core/science/chartsvg.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/science/chartsvg.py)
engine. It is pure and uncached: call it again after a recalc and you have
the refreshed picture. Because the output is text, writing it to a file *is*
the export.

**Matplotlib — optional.**
[`abax/engine/chartmpl.py`](https://github.com/leavesofgrass/abax/blob/main/abax/engine/chartmpl.py)
renders the *same* chart objects with matplotlib:
`render_chart_mpl(workbook, sheet_name, chart, fmt="png")` returns PNG bytes
(or SVG text with `fmt="svg"`). Install it with the `charts` extra —
`pip install "abax[charts]"` — or pick it in the first-run chooser; `abax
--deps` and `abax doctor` report whether it's present. Without matplotlib the
function raises a `RuntimeError` that says exactly that, and nothing else in
abax misses it: **the built-in SVG renderer is always the fallback.** Both
backends draw from one shared shaping pass, so they always show identical
data; the matplotlib path uses the object-oriented `Figure` API on an Agg
canvas (no `pyplot`, no global state), so it is safe off the GUI thread.

## Scripting: build, render, save

Everything above is scriptable with the pure-stdlib core (this snippet is
tested — it runs as written):

```python
from pathlib import Path

from abax.core.chartobj import ChartObject, new_chart_id, render_chart
from abax.core.workbook import Workbook

wb = Workbook()
s = wb.sheet
s.set("A1", "north")
s.set("B1", "south")
for i in range(2, 14):
    s.set(f"A{i}", str(40 + 3 * i))
    s.set(f"B{i}", str(90 - 2 * i))

chart = ChartObject(id=new_chart_id(s.charts), kind="line",
                    source="A1:B13", title="Monthly totals",
                    anchor=(1, 3), width=520, height=300)
s.charts.append(chart)

svg = render_chart(wb, s.name, chart)        # a complete "<svg>…</svg>" string
Path("totals.svg").write_text(svg, encoding="utf-8")

wb.save_json("book.abax")                    # the chart travels in the file
print(Workbook.load_json("book.abax").sheet.charts[0].kind)   # -> line
```

With matplotlib installed, the same object renders to PNG:

```python
from abax.engine.chartmpl import render_chart_mpl

png = render_chart_mpl(wb, s.name, chart)                  # PNG bytes
Path("totals.png").write_bytes(png)
svg_text = render_chart_mpl(wb, s.name, chart, fmt="svg")  # or SVG text
```

The runnable [embedded-charts example](examples/charts/embedded-charts/README.md)
builds a four-chart workbook this way — line, box, histogram, and a bar chart
fed by cross-sheet `AVERAGE()` formulas — and shows the exact output.

## Charts track your edits

Chart references are live parts of the workbook, so structural edits keep
them honest:

- **Inserting or deleting rows/columns** shifts anchors and source/label
  ranges the same way cell references shift — a chart over `A1:B9` reads
  `A3:B11` after two rows are inserted above it.
- The tracking is **workbook-wide**: a chart whose source points at another
  sheet (`Data!A1:C10`) follows edits made *on that sheet*.
- **Deleting the anchored row or column** clamps the anchor to the edit point
  — the chart itself survives.
- **Deleting the entire source range** blanks it out. The chart then reports
  a dead range instead of silently drawing shifted neighbours.

When a chart cannot render — an unknown kind, a source sheet that no longer
exists, an invalid or deleted range — the renderers raise `ChartError` with a
plain-English message. Surfaces that must never fail (a paint loop) catch it
and draw a placeholder instead.

## See also

- [Data & analysis tools](data-analysis.md#graph--chart) — the interactive
  grapher and the exportable one-off SVG charts.
- [Data science](data-science.md#distribution--diagnostic-charts) — the
  statistical background for box / violin / Q-Q / ECDF / heatmap.
- [File formats](file-formats.md#embedded-charts-schema-v3) — how charts
  persist in the envelope.
- [Embedded-charts example](examples/charts/embedded-charts/README.md) —
  tested, copy-paste, with the exact output.
- [Getting started](getting-started.md) — the extras table (`charts` is the
  matplotlib backend).
