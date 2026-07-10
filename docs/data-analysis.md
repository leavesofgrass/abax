# Data & analysis tools

Beyond formulas, abax ships a set of point-and-click tools for reshaping,
cleaning, summarising, querying, and plotting a table. They all operate on a
**selected range** in the grid (first row usually read as column names) and write
their results **back into the sheet** (or into a brand-new sheet), so output is
just more cells you can keep working with.

This page covers the everyday **analysis, reshaping, and reporting** side of
abax: importing, pivots/group-by, cleaning, column profiling, SQL over sheets,
goal seek, workbook compare, HTML export, charts, and the pandas hand-off. The
deeper numeric/statistics/ML/signal stack — hypothesis tests, regression, the ML
models, linear algebra, DSP, and ODE solvers — lives in its companion page,
[data science](data-science.md).

Most of these live under **Data → Analyze** in the Qt GUI; the scientific tools
live under **Tools → Scientific**; the HTML export is under **File**; workbook
compare is under **Data**. Almost everything is also reachable from the command
palette (`Ctrl+Shift+P`, or `:` on the grid) and, for scripting, from the
[embedded Python console](#the-console-namespace). Engines that can use optional
packages **degrade gracefully** — they fall back to abax's own pure-Python
implementations or tell you exactly which package to install.

See also: [index](index.md) · [data science](data-science.md) ·
[formula reference](formula-reference.md) · [gui guide](gui-guide.md) ·
[file formats](file-formats.md) · [command-line interface](cli.md).

## Where to find each tool

| Tool | Menu | Backed by |
| --- | --- | --- |
| Descriptive Statistics | Data → Analyze → Descriptive Statistics… | [`gui/dialogs/describe_dialog.py`](../abax/gui/dialogs/describe_dialog.py), [`core/science/descriptive.py`](../abax/core/science/descriptive.py) |
| Statistics / analysis | Data → Analyze → Statistics / analysis… | [`engine/analysis.py`](../abax/engine/analysis.py), [`core/science/stats.py`](../abax/core/science/stats.py) |
| SQL query | Data → Analyze → SQL query… | [`core/sqlsheets.py`](../abax/core/sqlsheets.py) |
| Profile columns | Data → Analyze → Profile columns | [`core/profile.py`](../abax/core/profile.py) |
| Open selection in pandas | Data → Analyze → Open selection in pandas… | [`gui/dialogs/dataframe_dialog.py`](../abax/gui/dialogs/dataframe_dialog.py) |
| Recode / clean column | Data → Analyze → Recode / clean column… | [`core/recode.py`](../abax/core/recode.py) |
| Pivot / group-by | Data → Analyze → Pivot / group-by… | [`core/pivot.py`](../abax/core/pivot.py) |
| PivotTable fields (drag-drop) | Data → Analyze → PivotTable fields (drag-drop)… | [`core/pivotspec.py`](../abax/core/pivotspec.py) |
| Curve fit | Data → Analyze → Curve fit… | [`gui/dialogs/curvefit_dialog.py`](../abax/gui/dialogs/curvefit_dialog.py), [`core/science/curvefit.py`](../abax/core/science/curvefit.py) |
| Goal seek | Data → Analyze → Goal seek… | [`gui/dialogs/goalseek_dialog.py`](../abax/gui/dialogs/goalseek_dialog.py), [`core/goalseek.py`](../abax/core/goalseek.py) |
| What-if analysis | Data → Analyze → What-if analysis… | [`gui/dialogs/whatif_dialog.py`](../abax/gui/dialogs/whatif_dialog.py), [`core/whatif.py`](../abax/core/whatif.py) |
| Formula profiler | Data → Analyze → Formula profiler… | [`gui/dialogs/profile_dialog.py`](../abax/gui/dialogs/profile_dialog.py), [`core/profile.py`](../abax/core/profile.py) |
| Compare workbook | Data → Compare workbook… | [`core/wbdiff.py`](../abax/core/wbdiff.py) |
| Export as HTML report | File → Export as HTML report… | [`core/io/html_report.py`](../abax/core/io/html_report.py) |
| Graph / chart | Data → Analyze → Graph / chart… (also Insert) | [`core/graphing.py`](../abax/core/graphing.py), [`core/science/chartsvg.py`](../abax/core/science/chartsvg.py) |
| ML tool | Tools → Scientific → ML tool… | see [data science](data-science.md) |
| Matrix / solver / signal / ODE tools | Tools → Scientific → … | see [data science](data-science.md) |

Every path above is also on the palette. A few tools write to a **new sheet**
rather than into the current selection: *Compare workbook* (a `Diff` sheet),
*Profile columns* (a `Profile` sheet), and *Descriptive Statistics* (a `Describe`
sheet, on demand).

## Importing data

abax opens or imports almost any tabular format — CSV/TSV, Excel `.xlsx`,
LibreOffice `.ods`, Parquet/Feather, SQLite, JSON / JSON Lines, R `data.frame`,
Jupyter notebooks, Markdown tables, and the native `.abax` workbook. Large CSVs
stream in with type inference and an optional row cap. From the shell,
`abax data.csv` opens it straight in the GUI; `abax convert in.csv out.parquet`
converts headlessly. See [file formats](file-formats.md) and the
[CLI](cli.md) for the full matrix of readers/writers and options.

Once a range is on the grid, the tools below take over. Most read the **first
row as column names** and the rest as data; blank cells are treated as missing.

## Descriptive Statistics

A one-click summary of a range (**Data → Analyze → Descriptive Statistics…**),
backed by [`gui/dialogs/describe_dialog.py`](../abax/gui/dialogs/describe_dialog.py)
and the pure-stdlib [`core/science/descriptive.py`](../abax/core/science/descriptive.py).
It reads the selected range (any shape — cells are pooled row-major), drops blank
and non-numeric cells, and fills a read-only two-column *statistic / value* table
with the full spread of measures: **count, sum, mean, median, mode, min, Q1, Q3,
max, range, sample & population variance/stdev, skewness, and kurtosis** (sixteen
in all). The summary recomputes live when you edit the range and press *Compute*,
and **Write summary to new sheet** drops the same table into a fresh `Describe`
sheet. Statistics that are undefined for the sample size degrade to a blank rather
than erroring — sample variance/stdev need n ≥ 2, skewness n ≥ 3, kurtosis n ≥ 4.
This is the fastest first look at a single column or block; for a per-column
*describe* of the whole sheet use [Profile columns](#profile-columns), and for
inferential tests use [Statistics / analysis](#statistics--analysis) below.

## Statistics / analysis

The headline analysis tool (**Data → Analyze → Statistics / analysis…**). Select
a numeric range (a non-numeric first row is read as column names), pick an
analysis, choose where to write the output, and run. The dialog shows a
**summary** — statistic, p-value, an effect size, and a one-line plain-English
interpretation — and writes a result **table** back into the grid. Backed by
[`abax/engine/analysis.py`](../abax/engine/analysis.py).

The registry (`analysis.ANALYSES`) drives the menu: descriptive statistics,
two-column t-test, one-way ANOVA, correlation matrix, OLS linear regression, a
Shapiro–Wilk normality check, and Kaplan–Meier survival. Descriptive statistics
and OLS regression always run (stdlib / graceful fallbacks); the others report a
clear "… requires *pkg*" message when their optional dependency is absent.

Because these overlap the statistical stack, the **full test-by-test table,
effect sizes, engines, and worked examples live in the
[data science](data-science.md#the-statistics-analysis-tool) page.** Use this
page for the reshaping/cleaning/reporting tools around it.

## Pivot / group-by

Reshape and summarise a table (**Data → Analyze → Pivot / group-by…**), powered
by [`abax/core/pivot.py`](../abax/core/pivot.py). Select a range (first row =
column names) and choose a mode:

- **Group by** (`pivot.group_by`) — group rows by one or more columns and
  aggregate a value column. The header becomes `[*group_cols, "agg(value_col)"]`.
- **Pivot table** (`pivot.pivot_table`) — an index column down the left,
  distinct values of a second column across the top, each cell the aggregate of
  a value column (blank where a combination has no data).
- **Cross-tab** (`pivot.crosstab`) — a frequency cross-tabulation (counts of
  co-occurrences); the same shape as a pivot table with `count`.

The *Pivot table* mode adds two extras in the dialog. **Show grand totals
(margins)** appends a grand-total row and column (labelled `Total`) recomputed
from the pooled raw cells — so a `mean`/`median` total is the true aggregate of
all rows, not an average of the cell aggregates. **Display as** re-expresses each
body cell as a **percent of the grand total, of its row, or of its column**
(`pct_of="grand"|"row"|"col"`); combined with margins, the margin cells show
`100`. The core [`pivot.pivot_table`](../abax/core/pivot.py) also supports
**multiple value fields** at once (`value_cols=` with an optional matching `aggs=`
list — one sub-column per value field per column key); this is scriptable from
the console today rather than exposed in the dialog.

Aggregations (`pivot.AGGREGATIONS`) are `sum`, `mean`, `count`, `min`, `max`,
`median`, `std` (**sample**, n−1), `nunique` (distinct count), and `first`.
Numeric aggregations *skip* blank/non-numeric cells rather than erroring, so a
group with no numeric values aggregates to blank; `count`/`nunique`/`first`
operate on the raw non-blank cells. Keys are sorted **naturally** — numerically
when every key parses as a number, else lexicographically — and floats render
compactly (`5.0` → `5`). Columns are addressed by **name**; an unknown column or
aggregation raises `PivotError`. Rows shorter than the header are treated as
blank-padded (ragged-tolerant). The result block is written back into the sheet.

### PivotTable Fields (drag-drop)

**Data → Analyze → PivotTable fields (drag-drop)…** opens a dockable pane like
Excel's PivotTable Fields, over the same [`core/pivot.py`](../abax/core/pivot.py)
engine (routing in [`core/pivotspec.py`](../abax/core/pivotspec.py)). Set a data
range, then drag columns — or use the `→` buttons — into four areas:

- **Rows** — one or more group fields. With a Columns field also set, two or
  more Row fields become **nested rows**: one leading column per field (e.g.
  `Region` then `Product`), not a single joined label;
- **Columns** — an optional pivot field across the top (omit it for a plain
  multi-field group-by);
- **Values** — one or more measures; select a Values item and pick its
  aggregation from **Summarize**;
- **Filters** — restrict the data to a field's value before pivoting. Select a
  Filters field and choose a **keep-value** from the picker; it defaults to
  `(All)` (no restriction).

**Grand totals** and **% of** (grand/row/col) mirror the classic dialog. A live
preview updates on every change; **Insert into sheet** writes the full result at
the anchor cell. Multiple Values fields are supported here (each becomes its own
sub-column), which the classic dialog does not expose.

Example — sales by region, then a region × quarter pivot:

```
Region  Quarter  Amount
West    Q1       120
West    Q2       80
East    Q1       200
```

*Group by* `Region`, value `Amount`, agg `sum` → `West 200`, `East 200`.
*Pivot table* index `Region`, columns `Quarter`, value `Amount`, agg `sum` →
a `Region | Q1 | Q2` grid.

## Recode / clean column

Column-at-a-time cleaning (**Data → Analyze → Recode / clean column…**), powered
by [`abax/core/recode.py`](../abax/core/recode.py). Each operation transforms
every column in the selected range (raw text in, recoded text out) and writes the
result back in place. A single *Options* field is interpreted per operation, with
a live hint. The operations come from `recode.OPERATIONS`:

| Operation | Options | Effect |
| --- | --- | --- |
| Re-type column (`retype`) | `int \| float \| bool \| date \| text` | coerce + re-render canonically (`1.0`→`1`, dates→ISO) |
| Fill missing (`fill_missing`) | `value:… \| zero \| mean \| median \| ffill \| bfill` | fill blank cells only |
| Strip whitespace (`strip_whitespace`) | — | trim leading/trailing whitespace |
| Change case (`to_case`) | `upper \| lower \| title` | recase each cell |
| Standardize dates (`standardize_dates`) | output format (default `%Y-%m-%d`) | parse common date forms, re-emit |
| Map / replace values (`map_values`) | `old=new, old2=new2` | exact-match lookup; unmapped → default (or unchanged) |
| Normalize (`normalize`) | `minmax \| zscore` | numeric rescale to [0,1] or z-score (sample std) |
| Clip / clamp (`clip`) | `low,high` (blank side = unbounded) | clamp numeric cells |

Blanks are preserved by every operation except *Fill missing* (whose whole job is
to fill them). Numeric operations (`normalize`, mean/median fill) **raise** on
non-numeric data so text is never silently mangled — *Clip* is the exception: it
passes blanks and non-numeric cells through unchanged, so it is safe on a mixed
column. `standardize_dates` accepts a dozen common forms (ISO, US `m/d/y`,
`02-Jan-2020`, `January 02, 2020`, …); an unrecognised cell is left as-is.

## Profile columns

**Data → Analyze → Profile columns** writes a per-column *describe* of the active
sheet to a fresh **`Profile`** sheet, powered by
[`abax/core/profile.py`](../abax/core/profile.py). For every used column it
infers a dtype (`bool` → `int` → `float`, else `text`, or `empty`) and reports
`count` (non-missing), `missing`, and `unique`. Numeric columns add
`min / max / mean / median / std` (population std) plus quartiles; text columns
add `max_len` and the five most-common values. `None` and `""` are missing; a
column is numeric only when *every* non-missing value parses. Great as a
first-look sanity check before analysis. (Programmatically: `describe()` in the
console returns the same list of stat dicts.)

## SQL query

**Data → Analyze → SQL query…** runs SQL over the workbook's sheets, powered by
[`abax/core/sqlsheets.py`](../abax/core/sqlsheets.py) and the stdlib `sqlite3`.
Each sheet is loaded into an in-memory SQLite table named after the sheet (the
first used row supplies column names). Column affinity is inferred per column
(`INTEGER` / `REAL` / `TEXT`), so numeric columns **aggregate as numbers**, not
concatenated text. Sheet and column names are sanitised to valid SQL identifiers
(non-alphanumerics → `_`, leading digits prefixed) and de-duplicated. The result
`(columns, rows)` is written back to the grid.

```sql
SELECT Region, SUM(Amount) AS total
FROM Sales
GROUP BY Region
ORDER BY total DESC;
```

Any SQLite error — including a reference to an unknown table — surfaces as a
clear `SqlError` message rather than a crash. In the console, `sql("…")` returns
`(columns, rows)` directly.

## Curve fit

Fit a model to XY data (**Data → Analyze → Curve fit…**), powered by
[`gui/dialogs/curvefit_dialog.py`](../abax/gui/dialogs/curvefit_dialog.py) and the
pure-stdlib [`core/science/curvefit.py`](../abax/core/science/curvefit.py). Point
it at an **X range** and a **Y range** (the dialog guesses the first two selected
columns) and pick one of four models:

- **Linear** — `y = a + b·x`.
- **Polynomial** (degree n) — least-squares fit of the chosen degree.
- **Exponential** — `y = a·e^(b·x)` (log-linear fit on `ln(y)`; needs `y > 0`).
- **Power** — `y = a·x^b` (log-log fit; needs `x > 0` and `y > 0`).

It reports the fitted equation and the **R²** (always computed on the original
`y` values, so it is comparable across models) and — with *Write fitted-values
column next to Y* ticked — writes the model's fitted `ŷ` down a column from the
cell you name. Bad input (mismatched X/Y counts, a non-positive value for the log
models, a degree ≥ the number of points) is reported rather than crashing. For
the underlying `polyfit`/`expfit`/`powerfit` and the closed-form linear helpers,
see [data science](data-science.md#regression-forecasting--curve-fitting-pure-stdlib).

## Goal seek

**Data → Analyze → Goal seek…** answers "what input makes this cell hit this
target?", powered by [`gui/dialogs/goalseek_dialog.py`](../abax/gui/dialogs/goalseek_dialog.py)
and [`core/goalseek.py`](../abax/core/goalseek.py). You name a **Set cell** (a
formula cell), a **To value** target, and a **By changing cell** to vary; the
solver finds the input that drives the target to the goal. It hands the problem
to the self-bracketing hybrid secant/bisection root-finder in
[`core/science/numeric.py`](../abax/core/science/numeric.py) (`solve_root`), so it
is robust on awkward or poorly-seeded problems. On success the changing cell keeps
the solution and the sheet recomputes; on failure — no bracketable root, no
convergence, or a target cell that never evaluates to a number — the changing cell
is **restored to its original text** (the sheet is left untouched) and
`GoalSeekError` is raised. In the console,
`goalseek.goal_seek(sheet, target_ref, target_value, changing_ref)` runs the same
solver over A1 cell references.

## What-if analysis

**Data → Analyze → What-if analysis…** (dialog
[`gui/dialogs/whatif_dialog.py`](../abax/gui/dialogs/whatif_dialog.py), core
[`core/whatif.py`](../abax/core/whatif.py)) bundles two classic what-if tools:

- **Data tables** — sweep values through an input cell and tabulate what a
  formula produces. A **one-variable** table takes a column (or row) of inputs,
  an input cell, and a formula cell, and writes the input→result pairs; a
  **two-variable** table sweeps a row of inputs against a column of inputs
  through two input cells and fills the grid with one formula's result. Inputs
  are always **restored** afterward, even if a formula errors mid-sweep.
- **Scenario manager** — capture a named **scenario**: a set of input cells and
  the values they should hold. Apply one to write those values (recomputing the
  sheet), switch between them to compare outcomes, and undo to roll back.
  Scenarios attach to the workbook (`workbook.scenarios`) and round-trip through
  save/load.

The dialog also exposes a headless programmatic API (`run_one_var` /
`run_two_var`) that the tests drive directly.

## Formula profiler

**Data → Analyze → Formula profiler…** (dialog
[`gui/dialogs/profile_dialog.py`](../abax/gui/dialogs/profile_dialog.py), core
[`core/profile.py`](../abax/core/profile.py)) finds what makes a recalc slow.
**Profile now** times every formula cell — all sheets, or just one — and ranks
them slowest-first in a monospace report (rank, cell, ms, formula); set
**Repeat** > 1 to average several passes for a steadier estimate on
sub-millisecond timings. Pick a cell and **Draw graph** to render its
**precedent** (what feeds it) or **dependent** (what it feeds) dependency graph
as a layered SVG, with an optional **Save SVG…**. The measurement functions
(`profile.profile_recalc`, `slowest`, `format_report`, `dependency_svg`) are
plain stdlib and callable from the console.

## Compare workbook

**Data → Compare workbook…** diffs the current workbook against another file,
powered by [`abax/core/wbdiff.py`](../abax/core/wbdiff.py). It compares the
**raw text you typed** (not computed values) cell-by-cell over the union of used
bounds, classifying each change as `added` (empty→non-empty), `removed`
(non-empty→empty), or `changed`. Results land in a new **`Diff`** sheet: a
one-line summary (`"3 changed, 1 added, 0 removed across 2 sheet(s)…"`) plus a
table of `sheet, row, col, kind, this, other`. Sheets present in only one
workbook are listed by name. In the console, `wbdiff.diff_workbooks(a, b)` and
`wbdiff.summary(diff)` expose the same engine.

## Export as HTML report

**File → Export as HTML report…** writes a standalone `<!DOCTYPE html>` document
— one bordered `<table>` per sheet, with column-letter headers, row numbers, and
each cell's *displayed* value (all escaped) — powered by
[`abax/core/io/html_report.py`](../abax/core/io/html_report.py). Pure stdlib
(`html` only), no external template engine. Large sheets are bounded (default
1000 rows × 100 columns) with a note recording what was omitted. In the console,
`html_report.workbook_to_html(wb)` and `html_report.sheet_to_html(sheet)` return
the HTML string.

## Graph / chart

abax has **two** complementary charting paths, both **without matplotlib**:

**1. The interactive grapher** (**Data → Analyze → Graph / chart…**, also under
Insert) — a live plot painted with QPainter
([`gui/dialogs/graph_dialog.py`](../abax/gui/dialogs/graph_dialog.py), backed by
[`core/graphing.py`](../abax/core/graphing.py)). It can:

- **Plot** a math expression of `x` over a range. The evaluator is sandboxed
  (empty `__builtins__`, only safe math names in scope, `^`→`**`), so a stray
  name errors instead of executing.
- **Plot selection** — the selected column as a series.
- **Histogram** of a column; **Scatter** of two columns (a third colours the
  points); **Regression** scatter with the least-squares fit line.
- **Spectrum (FFT)** and **Spectrogram** of the selected column, and **PCA
  scatter**, **k-means cluster scatter**, and an **ROC curve** — these hand off
  to the science stack (see [data science](data-science.md)).

In the curses TUI, `:plot <expr> [xmin xmax]` renders a **braille** plot
(`graphing.braille_plot`) of an expression or the selected column right in the
terminal.

**2. Exportable SVG charts** — [`core/science/chartsvg.py`](../abax/core/science/chartsvg.py)
is a pure-stdlib generator of complete, self-contained `<svg>…</svg>` strings
(bordered plot area, axes with numeric tick labels, optional title and legend).
Reach it from the [console](#the-console-namespace) as `chartsvg`:

- `chartsvg.line_svg(series, title=…)` — overlaid named line series
  (`[(name, [(x, y), …]), …]`), each in a distinct palette colour with a legend.
- `chartsvg.bar_svg(categories, values, title=…)` — vertical bars.
- `chartsvg.scatter_svg(points, title=…)` — points as circles.
- `chartsvg.histogram_svg(values, bins=10, title=…)` — equal-width bins.

It also renders a family of **distribution / diagnostic charts** over named
series `[(name, values), …]` — box-and-whisker (`box_svg`), violin
(`violin_svg`, a stdlib Gaussian-KDE silhouette), empirical-CDF step curves
(`ecdf_svg`), a normal **Q-Q** plot (`qq_svg`), and a value **heatmap**
(`heatmap_svg`, viridis colormap, ideal for a labelled correlation matrix). These
are documented with the statistical detail in
[data science](data-science.md#distribution--diagnostic-charts).

Because the output is a plain SVG string you can drop it into an HTML report,
save it to a file, or embed it anywhere — no rendering backend required.

## Open selection in pandas

A DataFrame viewer (**Data → Analyze → Open selection in pandas…**,
[`gui/dialogs/dataframe_dialog.py`](../abax/gui/dialogs/dataframe_dialog.py))
that loads the selected range as a **typed** pandas DataFrame — each column is
coerced to its inferred type (int / float / bool / date / text) via
`abax.core.typeinfer`. It displays the shape, dtypes, `describe()`, and a head
preview, and can write `describe()` back into the sheet. Requires `pandas`
(from the *Data science* feature — pick it in the first-run chooser or **Tools →
Install optional features**); reports cleanly if it isn't ready yet. Use this when you want a quick, read-only
pandas-eye view of a block without leaving the app — and the
[console](#the-console-namespace) when you want the full library.

## The console namespace

The embedded Python console (and the console worker, however isolated) is wired
to the live workbook via [`abax/core/console_ns.py`](../abax/core/console_ns.py). Every
engine on this page is exposed by name, so anything a dialog does you can script:

| Name(s) | What it gives you |
| --- | --- |
| `sql("…")` | run SQL over the sheets → `(columns, rows)` |
| `describe()` | per-column profile of the active sheet |
| `profile` | the profiling module (`profile_column`, `profile_sheet`) |
| `wbdiff` | workbook/sheet diff (`diff_workbooks`, `summary`) |
| `goalseek` | `goal_seek(sheet, target_ref, target_value, changing_ref)` |
| `html_report` | `sheet_to_html`, `workbook_to_html` |
| `chartsvg` | `line_svg` / `bar_svg` / `scatter_svg` / `histogram_svg` |
| `urlfetch` | fetch remote data |
| `cell(ref)` / `put(ref, v)` | read/write a single cell |
| `read_matrix("A1:C9")` / `write_matrix("E1", mat)` | range ↔ list-of-lists of floats |
| `sheet_to_df("A1:C9")` / `df_to_sheet(df, "E1")` | range ↔ pandas DataFrame |
| `np` / `pd` / `scipy` / `sm` / `sklearn` / `pingouin` | the optional packages, or `None` if absent |

The science engines (`stats`, `nonparam`, `ml`, `cluster`, `trees`, `bayes`,
`metrics`, `gmm`, `matrix`, `eigen`, `numeric`, `units`, `fft`, `signal`,
`spectral`, `filters`, `ode`, `interp`, …) are also all in scope — including the
rank/nonparametric tests and the `chartsvg` distribution charts — see
[data science](data-science.md). *(The console runs untrusted code; only run
scripts you trust — see [macros & scripting](macros-and-scripting.md).)*

## Optional dependencies

The analysis engines never hard-require a third-party package; they import them
lazily and degrade. Check what's installed with:

```bash
python -m abax --deps
```

| Package | Used for | Fallback when absent |
| --- | --- | --- |
| `scipy` | t-test, ANOVA, correlation, Shapiro–Wilk (the stats tool) | abax core stats engines |
| `statsmodels` | richest OLS output | numpy lstsq, then pure-Python OLS |
| `pingouin` | tidy t-test with effect size | `scipy.stats` |
| `lifelines` | Kaplan–Meier survival | survival analysis unavailable |
| `pandas` | DataFrame viewer / hand-off, Parquet | (those features need pandas) |
| `numpy` | faster OLS fallback, accelerated big reductions | pure-Python paths |

The **reshaping, cleaning, profiling, SQL, goal-seek, compare, HTML-report, and
SVG-chart** engines all run with **zero** optional packages installed — they are
stdlib-only by design. This is the same "pure-stdlib core with graceful
optional-dependency upgrades" philosophy that runs through the whole
[data-science stack](data-science.md).
