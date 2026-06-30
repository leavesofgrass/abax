# qcell documentation

qcell is a keyboard-first **statistics and data-science workstation** — an
integrated environment for data work, built on a fast, scriptable spreadsheet.
Import a dataset, explore it with ~150 formula functions (including statistical
distributions), run built-in analyses, reshape and visualize it, hand a selection
to pandas, and script everything with Python — over CSV, Excel, Parquet, SQLite,
JSON, R, and more. It runs as a Qt desktop GUI (the default), a vim-style terminal
UI, or a headless CLI.

- License: **GPL-3.0-or-later** — see [LICENSE](../LICENSE) and
  [licensing.md](licensing.md).
- Default Qt binding: **PySide6** (LGPL); PyQt6 is also supported.

## Data science with qcell

- [Data science overview](data-science.md) — the end-to-end workflow: import →
  explore → analyze → reshape → visualize → script → export.
- [Data & analysis tools](data-analysis.md) — descriptive statistics, regression,
  t-tests, ANOVA, correlation, pivot/group-by, recode, the pandas hand-off,
  graphing, and the ML tools.
- [Formula reference](formula-reference.md) — every built-in function, including
  the statistical distributions (normal, t, F, chi-square) and regression helpers.
- [Calculators](calculators.md) — RPN, graphing, and algebraic calculators with
  a two-way cell value bridge.
- [RF toolkit](rf-toolkit.md) — radio-frequency engineering functions: link budget,
  transmission line & matching, antenna math, and the Maidenhead grid locator.

## Working in qcell

- [Getting started](getting-started.md) — install, launch, and a 5-minute walkthrough.
- [GUI guide](gui-guide.md) — the grid, Excel-style keyboard navigation, selection
  statistics, formatting, freeze panes, find/replace, themes.
- [File formats](file-formats.md) — CSV, Excel, ODS, Parquet, XML, Markdown,
  Jupyter, R, SQLite, JSON Lines, and the native `.qcell` envelope.
- [Command-line interface](cli.md) — headless `view`/`convert`/`get`/`macro` plus
  the GUI/TUI launchers.
- [Configuration](configuration.md) — settings, environment variables, themes,
  fonts, and runtime paths.

## Extend & contribute

- [Macros & scripting](macros-and-scripting.md) — command macros, UDFs, recording,
  and the embedded Python console.
- [Architecture](architecture.md) — the three-layer seam, invariants, the Qt
  binding shim, the virtualized grid, and the build.
- [Licensing & notices](licensing.md) — GPL, third-party components, trademarks,
  and attribution.
