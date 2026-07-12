# abax documentation

abax is a keyboard-first **statistics and data-science workstation** — an
integrated environment for data work, built on a fast, scriptable spreadsheet.
Import a dataset, explore it with **642 formula functions** (statistics and
distributions, financial, engineering, database, and RF/amateur-radio), run built-in
analyses, reshape and visualize it, hand a
selection to pandas, and script everything with Python — over CSV, Excel, Parquet,
SQLite, JSON, R, and more. It runs as a Qt desktop GUI (the default), a vim-style
terminal UI, or a headless CLI. The core is dependency-free; optional features are
opt-in from a first-run chooser (nothing is installed until you choose it).

- License: **GPL-3.0-or-later** — see [LICENSE](https://github.com/leavesofgrass/abax/blob/main/LICENSE) and
  [licensing.md](licensing.md).
- Default Qt binding: **PySide6** (LGPL); PyQt6 is also supported.

> **This documentation is published online** at
> <https://leavesofgrass.github.io/abax/> — that's where the app's *Help →
> Documentation (online)* link goes. Its source lives in the repository under
> `docs/`, so a source checkout has it locally; a binary install does not, and
> reads it here. The application itself runs fully offline — only the docs site
> and a few opt-in features (live-data formulas, optional-dependency install,
> pandoc-based document conversion) use the network.

## Data science with abax

- [Data science overview](data-science.md) — the end-to-end workflow: import →
  explore → analyze → reshape → visualize → script → export.
- [Data & analysis tools](data-analysis.md) — descriptive statistics, regression,
  t-tests, ANOVA, correlation, pivot/group-by, recode, the pandas hand-off,
  graphing, and the ML tools.
- [Conditional formatting](conditional-formatting.md) — colour cells by value:
  comparisons, text/regex matches, duplicates, ranking, colour scales, and CSS
  styling, with worked examples.
- [Formula reference](formula-reference.md) — every built-in function, including
  the statistical distributions (normal, t, F, chi-square) and regression helpers.
- [Calculators](calculators.md) — RPN, graphing, and algebraic calculators with
  a two-way cell value bridge.
- [RF toolkit & antenna modeling](rf-toolkit.md) — RF engineering functions (link
  budget, transmission line & matching, Maidenhead grid, band plan / CTCSS), the
  Smith chart, dipole impedance, and a thin-wire **Method-of-Moments** solver with
  wire junctions, a ground-reflection take-off model, and NEC `.nec` import/export.
  Amateur-radio logging adds contest/POTA/SOTA dupe-checking and QSO-scoring
  functions (`ISDUPE`, `QSOPOINTS`) and an activation-log dialog; satellite pass
  prediction from a TLE is available with the optional `satellite` extra.
- [Jupyter integration](jupyter.md) — lossless `.ipynb` round-trip, rich display,
  abax as a Jupyter kernel, and the editable-sheet widget.

## Working in abax

- [Getting started](getting-started.md) — install, launch, and a 5-minute walkthrough.
- [Examples](examples/README.md) — tested, copy-paste examples: each is a folder
  with a `run.py` and the exact output you should see, covering formulas, data
  cleaning, tables, goal seek, conditional formatting, charts, the CLI, and
  contest logging.
- [GUI guide](gui-guide.md) — the grid, Excel-style keyboard navigation, selection
  statistics, formatting, cell borders and merged cells, freeze panes, find/replace,
  themes, and accessibility options (high-contrast mode, spoken active-cell readout).
- [File manager](file-manager.md) — the dual-pane browser, archiving, search, and
  configurable command buttons.
- [Budgeting](budgeting.md) — the budget wizard and the live `SUMIF`-driven budget
  sheet.
- [File formats](file-formats.md) — CSV, Excel, ODS, Parquet, XML, Markdown,
  Jupyter, R, SQLite, JSON Lines, ADIF logbooks, and the native `.abax` envelope.
- [Command-line interface](cli.md) — headless `view`/`convert`/`get`/`macro`/`deps`
  plus the GUI/TUI launchers.
- [Configuration](configuration.md) — settings, auto-install, environment
  variables, themes, fonts, runtime paths, iterative (circular-reference)
  calculation, and third-party plugin consent (off by default).

## Extend & contribute

- [Macros & scripting](macros-and-scripting.md) — command macros, UDFs, recording,
  and the extension model.
- [Python console](python-console.md) — the REPL wired to the live workbook: read
  and write cells, the pandas hand-off, SQL across sheets, and loading files.
- [Terminal](terminal.md) — the in-app system shell, with the current selection
  exported to commands as `$ABAX_*` environment variables.
- [Architecture](architecture.md) — the three-layer seam, invariants, the Qt
  binding shim, the virtualized grid, and the build.
- [Licensing & notices](licensing.md) — GPL, third-party components, trademarks,
  and attribution.
