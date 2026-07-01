# Data & analysis tools

Beyond formulas, abax ships a set of point-and-click tools for statistics,
reshaping, cleaning, plotting, and light machine learning. They all operate on a
**selected range** in the grid (first row usually read as column names) and write
their results **back into the sheet**, so output is just more cells you can keep
working with.

Most of these live under **Data → Analyze** in the Qt GUI; the scientific tools
live under **Tools → Scientific**. Almost everything is also reachable from the
command palette (`Ctrl+Shift+P`, or `:` on the grid). Engines that can use
optional packages **degrade gracefully** — they fall back to abax's own
pure-Python implementations or tell you exactly which package to install.

See also: [index](index.md) · [formula reference](formula-reference.md) ·
[file formats](file-formats.md) · [command-line interface](cli.md).

## Where to find each tool

| Tool | Menu | Backed by |
| --- | --- | --- |
| Statistics / analysis | Data → Analyze → Statistics / analysis… | [`engine/analysis.py`](../abax/engine/analysis.py), [`core/science/stats.py`](../abax/core/science/stats.py) |
| Open selection in pandas | Data → Analyze → Open selection in pandas… | [`gui/dialogs/dataframe_dialog.py`](../abax/gui/dialogs/dataframe_dialog.py) |
| Recode / clean column | Data → Analyze → Recode / clean column… | [`core/recode.py`](../abax/core/recode.py) |
| Pivot / group-by | Data → Analyze → Pivot / group-by… (palette) | [`core/pivot.py`](../abax/core/pivot.py) |
| Graph / chart | Data → Analyze → Graph / chart… | [`core/graphing.py`](../abax/core/graphing.py), [`core/science/signal.py`](../abax/core/science/signal.py) |
| ML tool | Tools → Scientific → ML tool… | [`core/science/ml.py`](../abax/core/science/ml.py), [`core/science/cluster.py`](../abax/core/science/cluster.py), [`core/science/metrics.py`](../abax/core/science/metrics.py) |
| Matrix tool | Tools → Scientific → Matrix tool… | [`core/science/matrix.py`](../abax/core/science/matrix.py), [`core/science/eigen.py`](../abax/core/science/eigen.py) |

## Statistics / analysis

The headline analysis tool. Select a numeric range (a non-numeric first row is
read as column names), pick an analysis, choose where to write the output, and
run. The dialog shows a **summary** — statistic, p-value, an effect size, and a
one-line plain-English interpretation — and writes a result **table** back into
the grid. Backed by [`abax/engine/analysis.py`](../abax/engine/analysis.py).

| Analysis | Needs | What it reports |
| --- | --- | --- |
| Descriptive statistics | — (stdlib) | per column: n, mean, stdev, min, Q1, median, Q3, max |
| t-test (two columns) | `scipy` | independent (Welch) or paired t, df, p, Cohen's d |
| One-way ANOVA | `scipy` | F, df, p, eta-squared effect size |
| Correlation matrix | `scipy` | Pearson or Spearman r matrix with p-values |
| Linear regression (OLS) | — (fallbacks) | coefficients, std err, t, p, R², adjusted R² |
| Normality (Shapiro–Wilk) | `scipy` | W, p, pass/fail at α = 0.05 |
| Kaplan–Meier survival | `lifelines` | time / at-risk / survival rows + median survival |

Graceful degradation is the rule:

- **Descriptive statistics** uses only the stdlib `statistics` module — it always
  runs.
- **Linear regression** prefers `statsmodels`, then falls back to a `numpy`
  least-squares solve, then to a pure-Python normal-equations solve — so it also
  always runs.
- The **t-test** uses `pingouin` when present (tidy output with the effect size),
  otherwise `scipy.stats` with a hand-computed Cohen's d.
- Analyses whose package is missing report a clear "… requires <pkg>" message
  rather than failing.

abax also has a dependency-free statistics engine in
[`abax/core/science/stats.py`](../abax/core/science/stats.py) (descriptive stats,
normal/Student-t/F distributions, t-tests, ANOVA, chi-square, confidence
intervals) that underpins the formula-level statistical functions.

## Pivot / group-by

Reshape and summarise a table, powered by
[`abax/core/pivot.py`](../abax/core/pivot.py). Select a range (first row =
column names) and choose a mode:

- **Group by** — group rows by one or more columns and aggregate a value column.
- **Pivot table** — index column down the left, distinct values of a second
  column across the top, each cell the aggregate of a value column.
- **Cross-tab** — a frequency cross-tabulation (counts of co-occurrences).

Aggregations include `sum`, `mean`, `min`, `max`, `median`, `std` (sample),
`count`, `nunique`, and `first`. Numeric aggregations skip blank/non-numeric
cells rather than erroring; keys are sorted naturally (numerically when all keys
are numbers, else lexicographically). The result block is written back into the
sheet.

## Recode / clean column

Column-at-a-time cleaning, powered by
[`abax/core/recode.py`](../abax/core/recode.py). Each operation transforms every
column in the selected range (raw text in, recoded text out) and writes the
result back in place. A single *Options* field is interpreted per operation, with
a live hint.

| Operation | Options | Effect |
| --- | --- | --- |
| Re-type column | `int \| float \| bool \| date \| text` | coerce + re-render canonically |
| Fill missing | `value:0 \| mean \| median \| ffill \| bfill \| zero` | fill blank cells |
| Strip whitespace | — | trim leading/trailing whitespace |
| Change case | `upper \| lower \| title` | recase each cell |
| Standardize dates | output format (default `%Y-%m-%d`) | parse common date forms, re-emit |
| Map / replace values | `old=new, old2=new2` | exact-match lookup; unmapped → default |
| Normalize | `minmax \| zscore` | numeric rescale to [0,1] or z-score |
| Clip / clamp | `low,high` (blank side = unbounded) | clamp numeric cells |

Blanks are preserved by every operation except *Fill missing*. Numeric
operations raise on non-numeric data (except *Clip*, which passes non-numeric
cells through unchanged).

## Open selection in pandas

A DataFrame viewer ([`gui/dialogs/dataframe_dialog.py`](../abax/gui/dialogs/dataframe_dialog.py))
that loads the selected range as a **typed** pandas DataFrame — each column is
coerced to its inferred type (int / float / bool / date / text) via
`abax.core.typeinfer`. It displays the shape, dtypes, `describe()`, and a head
preview, and can write `describe()` back into the sheet. Requires `pandas`
(auto-installs on first GUI run); reports cleanly if it isn't ready yet. Use this
when you want a quick, read-only pandas-eye view of a block without leaving the
app.

## Graph / chart

A no-matplotlib grapher painted with QPainter
([`gui/dialogs/graph_dialog.py`](../abax/gui/dialogs/graph_dialog.py), backed by
[`core/graphing.py`](../abax/core/graphing.py)). It can:

- **Plot** a math expression of `x` over a range (sandboxed evaluator, `^`→`**`).
- **Plot selection** — the selected column as a series.
- **Histogram** of a column; **Scatter** of two columns (a third colours the
  points); **Regression** scatter with the least-squares fit line.
- **Spectrum (FFT)** and **Spectrogram** of the selected column (via
  [`core/science/signal.py`](../abax/core/science/signal.py)).
- **PCA scatter** and **k-means cluster scatter** of the selected matrix, and an
  **ROC curve** from a true-label column plus a score column.

In the curses TUI, `:plot <expr> [xmin xmax]` renders a braille
plot of an expression or the selected column.

## ML tool

Light machine learning over a numeric samples × features matrix
([`gui/dialogs/ml_dialog.py`](../abax/gui/dialogs/ml_dialog.py)), backed by the pure-Python
[`core/science/ml.py`](../abax/core/science/ml.py) and [`core/science/cluster.py`](../abax/core/science/cluster.py)
(no numpy/sklearn required). Pick an operation and a parameter; the result
(scores, labels, coefficients) is written back to the grid:

- **PCA** (param = number of components)
- **K-means** clustering (param = k) and **GMM** clustering
- **Linear regression** (last column is `y`)
- **Standardize** (z-score)
- **Decision tree**, **Random forest**, and **Naive Bayes** classification
  (last column is the label `y`)

Model evaluation helpers — train/test split, k-fold cross-validation, confusion
matrix, accuracy/precision/recall/F1, and ROC/AUC — live in
[`core/science/metrics.py`](../abax/core/science/metrics.py), also dependency-free and seedable
for reproducible splits.

## Matrix tool

Linear-algebra over grid ranges ([`gui/dialogs/matrix_dialog.py`](../abax/gui/dialogs/matrix_dialog.py),
backed by [`core/science/matrix.py`](../abax/core/science/matrix.py) and
[`core/science/eigen.py`](../abax/core/science/eigen.py)). Reads numeric ranges and computes:
transpose, inverse, determinant, multiply (A·B), solve (A·x = b), eigenvalues,
Cholesky factor, QR (Q and R), and condition number. Matrix results are written
back starting at a target cell; scalar results (determinant, condition number)
are reported in the status line.

## Optional dependencies

The analysis engine never hard-requires a third-party package; it imports them
lazily and degrades. Check what's installed with:

```bash
python -m abax --deps
```

| Package | Used for | Fallback when absent |
| --- | --- | --- |
| `scipy` | t-test, ANOVA, correlation, Shapiro–Wilk | abax core stats engines |
| `statsmodels` | richest OLS output | numpy lstsq, then pure-Python OLS |
| `pingouin` | tidy t-test with effect size | `scipy.stats` |
| `lifelines` | Kaplan–Meier survival | survival analysis unavailable |
| `pandas` | DataFrame viewer | (DataFrame view needs pandas) |
| `numpy` | faster OLS fallback | pure-Python normal equations |
| `scikit-learn` | — (not required) | abax core ML / trees / cluster engines |

The descriptive statistics, pivot/group-by, recode, graphing, matrix, ML, and
model-metrics engines all run with **zero** optional packages installed.
