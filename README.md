# abax

A keyboard-first **statistics and data-science workstation** — an integrated
environment for data work, built on a fast, scriptable spreadsheet. Load a
dataset, explore it with **642 formula functions** (statistics and
distributions, financial, engineering, database, and **RF/amateur-radio**),
run built-in analyses (regression, t-tests, ANOVA, correlation), reshape it
with pivot/group-by and recode, visualize it, hand a selection off to pandas,
and script the whole thing with Python macros — across CSV, Excel, Parquet,
SQLite, JSON, R, and more.

It runs as a Qt desktop GUI (the default), a vim-style terminal UI, or a
headless CLI. The core is pure-stdlib Python; every heavier capability is an
optional dependency with a graceful fallback. When a behaviour is ambiguous,
abax follows **gnumeric**.

## Quick start

One isolated install with every optional feature:

```sh
pipx install "abax[all]"      # or: pip install "abax[all]" in a venv
abax                          # the desktop GUI
abax tui                      # the vim-style terminal UI (SSH-friendly)
abax view data.csv            # headless: print any spreadsheet as a table
```

Prefer to start small? Plain `pip install abax` gives the stdlib-only core,
and on first launch the GUI shows a **chooser** where you pick optional
features à la carte — nothing installs without your say-so. **No Python?**
Every [GitHub Release](https://github.com/leavesofgrass/abax/releases) ships
ready-to-run downloads: a Linux AppImage, a self-contained Windows build, a
macOS app, and a tiny cross-platform `abax.pyz` zipapp. Full install details
(extras, sizes, the Qt binding) live in
[Getting started](https://leavesofgrass.github.io/abax/getting-started/).

**Your first minute in the GUI:**

- Arrow keys move (vim `h j k l` works too); just type into a cell and
  press `Enter`.
- Type `=SUM(A1:A5)` — anything starting with `=` computes, with
  autocomplete and argument hints as you go.
- `Ctrl+Shift+P` (or `:`) opens the command palette — every action lives
  there. `F1` lists the shortcuts.
- `Ctrl+S` saves — `.abax`, `.csv`, `.xlsx`, `.md`, whatever the
  extension says.

**Where next:** tested, copy-paste
**[examples for most of abax](docs/examples/README.md)** · the full
[online documentation](https://leavesofgrass.github.io/abax/).

## A taste of the formula engine

```
=SUM(A1:A10)                      =VLOOKUP("banana", A1:B9, 2, FALSE)
=PERCENTILE(A1:A99, 0.9)          =IFS(s>=90,"A", s>=80,"B", TRUE,"F")
=SORT(UNIQUE(B:B))                =FILTER(A1:A9, B1:B9>0)
```

Array results *spill* across neighbouring cells Excel-style; errors are
values (`#DIV/0!`, `#REF!`, `#CIRC!`, …), never crashes; `LET` and `LAMBDA`
work. The complete function list is in the
[formula reference](https://leavesofgrass.github.io/abax/formula-reference/).

## What's inside

Each guide below links to a tested, runnable example.

- **[Data & analysis](https://leavesofgrass.github.io/abax/data-analysis/)** —
  pivot/group-by, recode, column profiling, SQL over sheets, goal seek,
  conditional formatting, charts, and the pandas hand-off; the
  [deep numeric stack](https://leavesofgrass.github.io/abax/data-science/)
  adds hypothesis tests, regression, ML models, linear algebra, FFT/DSP, and
  ODE solvers — all with pure-stdlib fallbacks.
- **[File formats](https://leavesofgrass.github.io/abax/file-formats/)** —
  open and save by extension: CSV, Excel, Parquet, SQLite, JSON/JSONL,
  Markdown, R, ODS, Jupyter `.ipynb` (lossless round-trip), and more;
  `abax convert a.csv b.xlsx` converts between any pair.
- **[RF & antenna engineering](https://leavesofgrass.github.io/abax/rf-toolkit/)** —
  60+ RF functions, link budgets, a Smith chart, a thin-wire Method-of-Moments
  solver with NEC deck import/export, a satellite pass predictor, and
  POTA/SOTA activation logging.
- **[Macros & scripting](https://leavesofgrass.github.io/abax/macros-and-scripting/)** —
  Python command macros and formula UDFs, macro **recording**, a live
  [Python console](https://leavesofgrass.github.io/abax/python-console/), and a
  headless [automation API](https://leavesofgrass.github.io/abax/automation/);
  your code runs at a selectable isolation level, up to a strict OS sandbox.
- **[Jupyter](https://leavesofgrass.github.io/abax/jupyter/)** — abax as a
  Jupyter kernel, rich sheet display, and an editable notebook widget.
- **[Built-in tools](https://leavesofgrass.github.io/abax/calculators/)** —
  HP-style RPN and TI graphing calculators, a dual-pane
  [file manager](https://leavesofgrass.github.io/abax/file-manager/), a budget
  wizard, and a LaTeX equation editor.
- **[Approachable UI](https://leavesofgrass.github.io/abax/gui-guide/)** — a
  command palette, twelve themes, screen-reader labels with optional spoken
  cell readout, and an OpenDyslexic font fetched on demand.

## Develop

```sh
just install    # dev setup
just test       # tests (pass with zero optional deps)
just check      # lint + test + pyz + smoke
```

See [docs/architecture.md](docs/architecture.md) for the layered design and
its invariants. abax is free software, licensed **GPL-3.0-or-later**.
