# Statistical charts as SVG files

Save a histogram, a bar chart, and a scatter plot as standalone `.svg`
files — no GUI, no matplotlib, no dependencies at all.

**You'll need:** abax only.

## Run it

```sh
cd docs/examples/charts/statistical-charts
python run.py
```

## What you should see

```
wrote out/histogram.svg  (3,670 bytes)
wrote out/bars.svg  (2,583 bytes)
wrote out/scatter.svg  (6,822 bytes)

Open them in any browser or image viewer.
```

## How it works

- Every chart function returns a complete `<svg>…</svg>` string —
  writing it to a file *is* the export.
- `histogram_svg(values, bins=12, title=…)` bins the data itself;
  `bar_svg(categories, values)` and `scatter_svg([(x, y), …])` take
  plain Python lists.
- Because the output is text, charts drop cleanly into web pages,
  Markdown docs, and version control.
- The same engine powers box, violin, Q-Q, ECDF, heatmap, waterfall,
  sunburst, treemap, and sparkline charts — same call shape.

## Next steps

- In the GUI, *Data → Graph* plots a selected column interactively, and
  `=SPARKLINE(A1:A20)` draws a tiny chart inside a cell.
- [Data & analysis tools](../../../data-analysis.md) covers the plot
  dialogs; the RF side has polar antenna patterns and Smith charts
  ([RF toolkit](../../../rf-toolkit.md)).
