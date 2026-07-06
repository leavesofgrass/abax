# Getting started

abax is a keyboard-first statistics and data-science workstation built on a
scriptable spreadsheet. It reads and writes CSV, TSV, Excel `.xlsx`, the native
`.abax`/`.json` format, and many more (see [file formats](file-formats.md)), and
runs three ways: a Qt desktop GUI (the default), a curses/Textual terminal UI
(TUI), and a headless command-line interface (CLI). This guide covers installing
abax, the ways to launch it, and a five-minute walkthrough from an empty grid to a
saved spreadsheet with a working formula. For the end-to-end data workflow, see the
[data science overview](data-science.md).

## Installing

abax is pure Python and works with no optional packages at all — the core spreadsheet engine is stdlib-only. The graphical interfaces and the data/format features are pulled in through *extras*, each with a graceful stdlib fallback. Install only what you need.

> **Don't want to install Python?** Every [GitHub Release](https://github.com/leavesofgrass/abax/releases)
> ships ready-to-run downloads: a portable **Linux AppImage** of the full
> `abax[all]` (download, `chmod +x`, run), a self-contained **Windows build**
> (unzip; double-click `abaxw.exe` for the GUI, or `abax.exe` for the full CLI),
> and the tiny cross-platform `abax.pyz` zipapp (`python abax.pyz`, needs only a
> Python 3.13 interpreter).

Clone or download the project, then install from the project root:

```bash
# Core CLI/TUI only (no third-party packages) — runs everywhere, tiny
pip install .

# Desktop GUI (Qt) — pulls in PySide6-Essentials (LGPL-3.0)
pip install ".[gui]"

# Lean desktop: GUI + every lightweight convenience, no heavy data libraries
pip install ".[thin]"

# Everything abax can use, including the data-science stack
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
| `science` | numpy, pandas, scipy, scikit-learn, statsmodels, lifelines, pingouin, scikit-survival | The data-science / (bio)statistics stack behind the analysis, ML, and graphing tools |
| `bayes` | pymc | Bayesian / probabilistic programming — split out because it's heavy (pytensor + arviz + numba/llvmlite, ~150 MB) |
| `jupyter` | `nbformat`, `ipykernel`, `anywidget` | Notebook validation, the abax Jupyter kernel, and the editable-sheet widget ([jupyter.md](jupyter.md)) |
| `sevenzip` | `py7zr` | Create / extract `.7z` archives in the file manager |
| `stats-io` | `pyreadstat` | Reading Stata `.dta` / SPSS `.sav` files |
| `hdf5` | `h5py` | Reading HDF5 `.h5` / `.hdf5` files |
| `nec` | `PyNEC` | Reference NEC-2 antenna solver (cross-checks the built-in MoM) |
| **`thin`** | `gui` + `tui` + `excel` + `fast-io` + `terminal` + `sevenzip` | A lean desktop install — every lightweight convenience, none of the heavy data libraries |
| **`all`** | `thin` + `parquet` + `science` + `jupyter` + `bayes` + `stats-io` + `hdf5` + `nec` | One-shot install of everything abax can use (the full-fat set) |

> **You choose on first launch.** You don't have to pick extras at install time:
> install just `gui`, and the first time you open abax it shows a short **chooser**
> that explains each optional feature and offers two presets — **Thin** (lean
> everyday conveniences, ~25 MB) and **All** (everything, recommended) — plus a
> checkbox per feature so you can pick your own mix. Your choice is fetched in the
> background (best-effort, non-blocking) and remembered. Re-open it any time from
> *Tools → Install optional features*. In the TUI/headless, `abax deps` installs
> everything, or `pip install abax[science]` (etc.) picks specific extras. Opt out
> of prompting/auto-install entirely with `auto_install: false` or
> `ABAX_NO_AUTOINSTALL=1`. See [Configuration → Auto-install](configuration.md#auto-install).

### Install profiles & footprint

Approximate **installed** sizes (excluding the Python interpreter) — within ~10 %
across Windows, Linux, and macOS, since the heavy pieces are comparable binary
wheels on each:

| Profile | Command | Size |
|---------|---------|-----:|
| Core / headless | `pip install .` | **< 2 MB** |
| Desktop GUI | `pip install ".[gui]"` | **~0.22 GB** |
| Lean desktop | `pip install ".[thin]"` | **~0.23 GB** |
| Everything without Bayesian | `pip install ".[thin,parquet,science,jupyter]"` | **~0.69 GB** |
| Everything | `pip install ".[all]"` | **~0.84 GB** |

Dropping the `bayes` extra (pymc → pytensor + arviz + numba/llvmlite) saves
~0.15 GB with no loss to the spreadsheet, RF/antenna, DSP, or ML tools.

The GUI tiers are dominated by Qt (~0.2 GB). `all` adds the scientific stack — roughly +0.7 GB of numpy/scipy/pandas/scikit-learn/pyarrow/… The core and curses TUI need nothing beyond the standard library.

> abax is licensed **GPL-3.0-or-later**. The default GUI binding is **PySide6**, which is LGPL-3.0. If you prefer PyQt6, install the `gui-pyqt` extra instead — the GUI code never branches on the binding, so it behaves identically on either.

### Choosing the Qt binding

When both bindings are installed, abax prefers PySide6. To force PyQt6 (handy for testing), set the `ABAX_QT_BINDING` environment variable:

```bash
ABAX_QT_BINDING=PyQt6 abax gui
```

See [configuration.md](configuration.md) for more on environment variables.

### Checking your install

Run the dependency report to see which optional packages are present and which fall back to a built-in alternative. This is a fast path — it never imports the heavy Qt or terminal stacks:

```bash
abax --deps
```

It also prints where abax keeps its config, data, cache, and log directories.

## Launching abax

abax can be run as the `abax` script (installed by the extras above) or as a module with `python -m abax`. The two are equivalent.

### The GUI is the default

Running abax with **no subcommand** opens the Qt GUI:

```bash
abax                 # opens the GUI on an empty workbook
abax data.csv        # the bare-file form is not a subcommand — use `gui`
abax gui             # explicitly open the GUI, empty
abax gui data.csv    # open the GUI on a file
```

If Qt is not installed, abax falls back automatically: it opens the TUI when standard output is a terminal, and otherwise prints help. To open the GUI on a specific file, use the `gui` subcommand with a path.

### The terminal UI

```bash
abax tui             # curses/Textual TUI on an empty workbook
abax tui data.csv    # open a file in the TUI
```

The TUI is keyboard-driven with vim-style bindings on by default — move around the sheet with `h`/`j`/`k`/`l` **or the arrow keys** — and a `:command` line for everything else (find, fill, sort, macros, the RPN calculator, and more).

### Headless CLI

For scripting and quick lookups, abax never opens a window:

```bash
abax view data.csv               # print the sheet as a text table
abax get data.csv B7             # print one computed cell value
abax convert data.csv out.xlsx   # convert between formats by extension
```

The full command and flag reference lives in [cli.md](cli.md).

## Your first spreadsheet in five minutes

This walkthrough uses the GUI, but the same concepts (typing into cells, writing a formula, saving) apply in the TUI.

### 1. Open abax

```bash
abax gui
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

Press `Enter`. The cell shows the computed total, `12`. abax ships with 620+ functions — `SUM`, `AVERAGE`, `IF`, `VLOOKUP`, `CONCAT`, date functions, and more — and array formulas like `=SORT(A1:A9)` **spill** across neighbouring cells. As you type a function name the GUI offers autocomplete and an argument hint showing the current parameter. See [formula-reference.md](formula-reference.md) for the full function list.

A few things worth knowing right away:

- References look like `A1`, ranges like `B2:B4`. A `$` (as in `$A$1`) anchors a reference so it does not shift when copied.
- Errors are *values*, not crashes: a bad formula shows something like `#DIV/0!`, `#NAME?`, or `#REF!`.
- Editing a cell that others depend on recomputes them automatically.

### 4. Save your work

Save with `Ctrl+S` and pick a filename. The extension chooses the format:

- `myfile.abax` or `myfile.json` — abax's native JSON format (keeps formulas, multiple sheets, formatting, and conditional rules).
- `myfile.csv` / `.tsv` — plain delimited text.
- `myfile.xlsx` — Excel (requires the `excel` extra).

All of abax's own persistence is JSON, so `.abax`/`.json` round-trips everything losslessly. CSV and Excel keep what those formats can represent.

### 5. Reopen or inspect from the CLI

Once saved, you can re-open the file in any interface, or peek at it without launching a window:

```bash
abax view myfile.abax      # see the whole sheet as a table
abax get myfile.abax B5    # prints: 12
```

## Where to go next

- [cli.md](cli.md) — every command-line subcommand and flag, with examples.
- [configuration.md](configuration.md) — settings, runtime directories, environment variables, themes, fonts, and pandoc.
- [gui-guide.md](gui-guide.md) — the menus, command palette, and keyboard shortcuts.
- [formula-reference.md](formula-reference.md) — the function library.
- [index.md](index.md) — documentation home.
