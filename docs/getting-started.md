# Getting started

qcell is a keyboard-first statistics and data-science workstation built on a
scriptable spreadsheet. It reads and writes CSV, TSV, Excel `.xlsx`, the native
`.qcell`/`.json` format, and many more (see [file formats](file-formats.md)), and
runs three ways: a Qt desktop GUI (the default), a curses/Textual terminal UI
(TUI), and a headless command-line interface (CLI). This guide covers installing
qcell, the ways to launch it, and a five-minute walkthrough from an empty grid to a
saved spreadsheet with a working formula. For the end-to-end data workflow, see the
[data science overview](data-science.md).

## Installing

qcell is pure Python and works with no optional packages at all — the core spreadsheet engine is stdlib-only. The graphical interfaces and the data/format features are pulled in through *extras*, each with a graceful stdlib fallback. Install only what you need.

Clone or download the project, then install from the project root:

```bash
# Core CLI/TUI only (no third-party packages) — runs everywhere, tiny
pip install .

# Desktop GUI (Qt) — pulls in PySide6-Essentials (LGPL-3.0)
pip install ".[gui]"

# Lean desktop: GUI + every lightweight convenience, no heavy data libraries
pip install ".[thin]"

# Everything qcell can use, including the data-science stack
pip install ".[all]"

# Full developer setup
pip install ".[dev,thin]"
```

If you have `just` installed, `just install` runs the full developer setup for you.

### Available extras

| Extra | Pulls in | Gives you |
|-------|----------|-----------|
| `gui` | `PySide6-Essentials` (LGPL-3.0) | The Qt desktop GUI — recommended default binding (no QtWebEngine) |
| `gui-pyqt` | `PyQt6` (GPL/commercial) | An alternative Qt binding; the GUI runs unchanged on either |
| `tui` | `textual`, `rich` | Richer terminal UI support |
| `excel` | `openpyxl` | Reading and writing `.xlsx` workbooks |
| `fast-io` | `msgspec`, `platformdirs` | Faster JSON and OS-correct config/data paths |
| `terminal` | `pyte` | A true PTY terminal panel (with `pywinpty` on Windows) |
| `parquet` | `pyarrow` | Parquet / Feather I/O |
| `science` | numpy, pandas, scipy, scikit-learn, statsmodels, lifelines, pingouin, scikit-survival, pymc | The data-science / (bio)statistics stack behind the analysis, ML, and graphing tools |
| `jupyter` | `nbformat`, `ipykernel`, `anywidget` | Notebook validation, the qcell Jupyter kernel, and the editable-sheet widget ([jupyter.md](jupyter.md)) |
| **`thin`** | `gui` + `tui` + `excel` + `fast-io` + `terminal` | A lean desktop install — every lightweight convenience, none of the heavy data libraries |
| **`all`** | `thin` + `parquet` + `science` + `jupyter` | One-shot install of everything qcell can use |

> **Full-fat by default.** You don't have to pick extras: install just `gui` and,
> on first launch, qcell **auto-installs the rest in the background** (the science
> stack, Excel/Parquet, terminal, Jupyter). It's best-effort and non-blocking; opt
> out with `auto_install: false` or `QCELL_NO_AUTOINSTALL=1`, or force it now with
> `qcell deps`. See [Configuration → Auto-install](configuration.md#auto-install).

### Install profiles & footprint

Approximate **installed** sizes — similar on Windows and Linux, since the heavy pieces are comparable binary wheels on both:

| Profile | Command | Size |
|---------|---------|-----:|
| Core / headless | `pip install .` | **< 1 MB** (+ the Python interpreter) |
| Desktop GUI | `pip install ".[gui]"` | **~0.22 GB** |
| Lean desktop | `pip install ".[thin]"` | **~0.22 GB** |
| Everything | `pip install ".[all]"` | **~0.9 GB** |

The GUI tiers are dominated by Qt (~0.2 GB). `all` adds the scientific stack — roughly +0.7 GB of numpy/scipy/pandas/scikit-learn/pyarrow/… The core and curses TUI need nothing beyond the standard library.

> qcell is licensed **GPL-3.0-or-later**. The default GUI binding is **PySide6**, which is LGPL-3.0. If you prefer PyQt6, install the `gui-pyqt` extra instead — the GUI code never branches on the binding, so it behaves identically on either.

### Choosing the Qt binding

When both bindings are installed, qcell prefers PySide6. To force PyQt6 (handy for testing), set the `QCELL_QT_BINDING` environment variable:

```bash
QCELL_QT_BINDING=PyQt6 qcell gui
```

See [configuration.md](configuration.md) for more on environment variables.

### Checking your install

Run the dependency report to see which optional packages are present and which fall back to a built-in alternative. This is a fast path — it never imports the heavy Qt or terminal stacks:

```bash
qcell --deps
```

It also prints where qcell keeps its config, data, cache, and log directories.

## Launching qcell

qcell can be run as the `qcell` script (installed by the extras above) or as a module with `python -m qcell`. The two are equivalent.

### The GUI is the default

Running qcell with **no subcommand** opens the Qt GUI:

```bash
qcell                 # opens the GUI on an empty workbook
qcell data.csv        # the bare-file form is not a subcommand — use `gui`
qcell gui             # explicitly open the GUI, empty
qcell gui data.csv    # open the GUI on a file
```

If Qt is not installed, qcell falls back automatically: it opens the TUI when standard output is a terminal, and otherwise prints help. To open the GUI on a specific file, use the `gui` subcommand with a path.

### The terminal UI

```bash
qcell tui             # curses/Textual TUI on an empty workbook
qcell tui data.csv    # open a file in the TUI
```

The TUI is keyboard-driven with vim-style bindings on by default and a `:command` line for everything else (find, fill, sort, macros, the RPN calculator, and more).

### Headless CLI

For scripting and quick lookups, qcell never opens a window:

```bash
qcell view data.csv               # print the sheet as a text table
qcell get data.csv B7             # print one computed cell value
qcell convert data.csv out.xlsx   # convert between formats by extension
```

The full command and flag reference lives in [cli.md](cli.md).

## Your first spreadsheet in five minutes

This walkthrough uses the GUI, but the same concepts (typing into cells, writing a formula, saving) apply in the TUI.

### 1. Open qcell

```bash
qcell gui
```

You get an empty grid with rows numbered `1, 2, 3, …` and columns labelled `A, B, C, …`, just like any spreadsheet.

### 2. Enter some data

Click cell **A1** (or move to it with the arrow keys) and type a label, then press `Enter` to commit and move down. Build a tiny table:

| | A | B |
|---|-------|-------|
| **1** | Item | Price |
| **2** | Apples | 3 |
| **3** | Pears | 4 |
| **4** | Cherries | 5 |

Type the text and numbers cell by cell. Numbers are stored as numbers; everything else is text.

### 3. Add a formula

Move to cell **B5** and type a formula. Formulas start with `=`:

```
=SUM(B2:B4)
```

Press `Enter`. The cell shows the computed total, `12`. qcell ships with around 200 functions — `SUM`, `AVERAGE`, `IF`, `VLOOKUP`, `CONCAT`, date functions, and more. As you type a function name the GUI offers autocomplete and an argument hint showing the current parameter. See [formula-reference.md](formula-reference.md) for the full function list.

A few things worth knowing right away:

- References look like `A1`, ranges like `B2:B4`. A `$` (as in `$A$1`) anchors a reference so it does not shift when copied.
- Errors are *values*, not crashes: a bad formula shows something like `#DIV/0!`, `#NAME?`, or `#REF!`.
- Editing a cell that others depend on recomputes them automatically.

### 4. Save your work

Save with `Ctrl+S` and pick a filename. The extension chooses the format:

- `myfile.qcell` or `myfile.json` — qcell's native JSON format (keeps formulas, multiple sheets, formatting, and conditional rules).
- `myfile.csv` / `.tsv` — plain delimited text.
- `myfile.xlsx` — Excel (requires the `excel` extra).

All of qcell's own persistence is JSON, so `.qcell`/`.json` round-trips everything losslessly. CSV and Excel keep what those formats can represent.

### 5. Reopen or inspect from the CLI

Once saved, you can re-open the file in any interface, or peek at it without launching a window:

```bash
qcell view myfile.qcell      # see the whole sheet as a table
qcell get myfile.qcell B5    # prints: 12
```

## Where to go next

- [cli.md](cli.md) — every command-line subcommand and flag, with examples.
- [configuration.md](configuration.md) — settings, runtime directories, environment variables, themes, fonts, and pandoc.
- [gui-guide.md](gui-guide.md) — the menus, command palette, and keyboard shortcuts.
- [formula-reference.md](formula-reference.md) — the function library.
- [index.md](index.md) — documentation home.
