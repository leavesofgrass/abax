# Examples

Every example is a folder with a `README.md` and (usually) a `run.py`.
They all work the same way:

```sh
cd docs/examples/<category>/<example>
python run.py
```

Each README shows the exact output you should get. The scripts need only
an installed abax (`pipx install "abax[all]"` — see the
[getting-started guide](../getting-started.md)); none of them need
optional packages, a network connection, or a display.

> **Running from a source checkout without installing?** Put the repo
> root on the import path first: `pip install -e .` once, or prefix runs
> with `PYTHONPATH=/path/to/abax`.

## Getting started

| I want to… | Go to | Runs? |
|---|---|---|
| Build and save my first workbook from Python | [first-workbook](getting-started/first-workbook/README.md) | `run.py` |
| Learn the GUI in a minute (keys, palette, themes) | [sixty-second-tour](getting-started/sixty-second-tour/README.md) | walkthrough |
| Install abax / pick extras / binary downloads | [getting-started guide](../getting-started.md) | guide |

## Formulas

| I want to… | Go to | Runs? |
|---|---|---|
| Summarize data — mean, spread, percentiles, correlation | [descriptive-statistics](formulas/descriptive-statistics/README.md) | `run.py` |
| Use spilling formulas — SORT, UNIQUE, FILTER, SEQUENCE | [dynamic-arrays](formulas/dynamic-arrays/README.md) | `run.py` |
| Schedule work in business days, skipping holidays | [business-days](formulas/business-days/README.md) | `run.py` |
| Look up any of the 642 functions | [formula reference](../formula-reference.md) | guide |

## Data: import, clean, export

| I want to… | Go to | Runs? |
|---|---|---|
| Clean a messy CSV and export the fixed values | [csv-clean-and-export](data/csv-clean-and-export/README.md) | `run.py` |
| Query a region by column name — `=SUM(Sales[Amount])` | [structured-tables](data/structured-tables/README.md) | `run.py` |
| See every format abax reads and writes | [file formats](../file-formats.md) | guide |
| Import Excel / Parquet / SQLite / Stata / R | [file formats](../file-formats.md) | guide |

## Analysis

| I want to… | Go to | Runs? |
|---|---|---|
| Solve backwards — "what input gives this output?" | [goal-seek](analysis/goal-seek/README.md) | `run.py` |
| Colour cells by value, regex, rank, or CSS | [conditional-formatting](analysis/conditional-formatting/README.md) | `run.py` |
| Run regression, t-tests, ANOVA, pivot, group-by | [data & analysis tools](../data-analysis.md) | guide |
| Hand a selection to pandas / run SQL across sheets | [Python console](../python-console.md) | guide |
| Compare scenarios (what-if) | [data & analysis tools](../data-analysis.md) | guide |

## Charts

| I want to… | Go to | Runs? |
|---|---|---|
| Save histogram / bar / scatter charts as SVG files | [statistical-charts](charts/statistical-charts/README.md) | `run.py` |
| Plot interactively, sparklines in cells | [data & analysis tools](../data-analysis.md) | guide |

## Scripting & CLI

| I want to… | Go to | Runs? |
|---|---|---|
| Use abax headlessly — view, get, convert, profile | [headless-cli](scripting-and-cli/headless-cli/README.md) | `run.py` |
| Write macros and custom formula functions (UDFs) | [macros & scripting](../macros-and-scripting.md) | guide |
| Script the live workbook from the built-in REPL | [Python console](../python-console.md) | guide |
| Run shell commands on the current selection | [terminal](../terminal.md) | guide |
| Drive abax from other programs | [automation API](../automation.md) | guide |
| Round-trip notebooks / run abax as a Jupyter kernel | [Jupyter](../jupyter.md) | guide |

## Radio & RF

| I want to… | Go to | Runs? |
|---|---|---|
| Score a contest log — dupes, points, totals | [contest-log-scoring](radio/contest-log-scoring/README.md) | `run.py` |
| Link budgets, VSWR, Smith chart, antenna modeling | [RF toolkit](../rf-toolkit.md) | guide |

## Everything else

| I want to… | Go to |
|---|---|
| The dual-pane file manager | [file manager](../file-manager.md) |
| The budget wizard | [budgeting](../budgeting.md) |
| RPN / graphing / algebraic calculators | [calculators](../calculators.md) |
| Themes, fonts, settings, environment variables | [configuration](../configuration.md) |
| The vim-style terminal UI | [getting-started guide](../getting-started.md) |
| Accessibility (high contrast, spoken cells) | [GUI guide](../gui-guide.md) |
| How abax is put together | [architecture](../architecture.md) |
