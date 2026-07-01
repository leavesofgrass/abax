# Command-line interface

The `qcell` command is the single entry point for every interface: the desktop GUI, the terminal UI, and a set of headless subcommands for viewing, converting, and querying spreadsheets without opening a window. This page documents every subcommand and flag, with example invocations and the output you can expect. Everything below works equally as `qcell …` (the installed script) or `python -m qcell …`.

## Synopsis

```
qcell [--version] [--deps] [--macros PATH ...] [COMMAND] [ARGS]
```

With **no command**, qcell opens the GUI when a Qt binding is installed; if Qt is missing it opens the TUI when standard output is a terminal, and otherwise prints help. See [getting-started.md](getting-started.md) for installation and the choice of Qt binding.

## Global flags

These are parsed before any command and the first two are *fast paths* — they answer instantly and never import the GUI/TUI stacks or create an environment.

| Flag | Effect |
|------|--------|
| `--version` | Print `qcell <version>` and exit. |
| `--deps` | Print the optional-dependency status report (with the **auto-install** state and how many optional packages are present) and the config/data/cache/log directories, then exit. |
| `--macros PATH` | Load a macro file or directory. Repeatable. Adds its `@macro` commands and `@register_function` UDFs to every command (`view`, `get`, `gui`, `tui`, `macro`). |

### `--version`

```bash
$ qcell --version
qcell 0.1.1
```

### `--deps`

Reports each optional package as available or missing (with the fallback that kicks in when it is absent), plus external tools like pandoc, and prints the runtime directories.

```bash
$ qcell --deps
optional dependencies:
  [OK ] msgspec       available
  [-- ] openpyxl      missing  (fallback: ...)
  [OK ] PySide6       available
  ...
  [-- ] pandoc        missing  (fallback: built-in subset MathML)

  config: C:\Users\you\AppData\Roaming\qcell
  data:   C:\Users\you\AppData\Local\qcell
  cache:  C:\Users\you\AppData\Local\qcell\Cache
  log:    C:\Users\you\AppData\Local\qcell\Logs
```

(The exact list and paths depend on your platform and what is installed.) See [configuration.md](configuration.md) for what each directory holds.

### `--macros PATH`

```bash
# Load one macro file and one directory, then open the TUI with them available
qcell --macros ./my_macros.py --macros ~/.config/qcell/macros tui data.csv
```

Macros from `CONFIG_DIR/macros/*.py` are always discovered automatically; `--macros` adds more on top.

## Commands

### `gui [file]` — desktop GUI

Launch the Qt GUI, optionally opening a file. This is also what runs when you give no command at all.

```bash
qcell gui                # empty workbook
qcell gui report.qcell   # open a file
qcell gui data.csv
```

| Argument | Description |
|----------|-------------|
| `file` | Optional spreadsheet to open (`.csv`, `.tsv`, `.xlsx`, `.qcell`, `.json`, and more). |

Requires a Qt binding (`gui` or `gui-pyqt` extra). See [gui-guide.md](gui-guide.md).

### `tui [file]` — terminal UI

Launch the curses/Textual TUI, optionally opening a file.

```bash
qcell tui                # empty workbook
qcell tui data.csv       # open a file
```

| Argument | Description |
|----------|-------------|
| `file` | Optional spreadsheet to open. |

### `view file [--sheet NAME]` — print a sheet

Render a spreadsheet as a plain-text table on standard output. Computed values are shown (formulas are evaluated), and columns are aligned with `A, B, C …` headers and `1, 2, 3 …` row labels.

```bash
$ qcell view data.csv
  | A        | B
--------------------
1 | Item     | Price
2 | Apples   | 3
3 | Pears    | 4
4 | Cherries | 5
```

| Argument / flag | Description |
|-----------------|-------------|
| `file` | Spreadsheet to open (`.csv`/`.xlsx`/`.json`/`.qcell`/…). |
| `--sheet NAME` | Which sheet to print. Defaults to the workbook's active sheet. |

If the named sheet does not exist, qcell prints `no such sheet: NAME` to standard error and exits with status `2`. An empty sheet prints `(empty)`.

```bash
qcell view book.xlsx --sheet Summary
```

### `convert src dst [--values]` — convert between formats

Open `src` and save it to `dst`. The format is chosen entirely by the **destination file extension** (`.csv`, `.tsv`, `.tab`, `.xlsx`, `.json`, `.qcell`, and the other formats qcell supports).

```bash
$ qcell convert data.csv data.xlsx
converted data.csv -> data.xlsx

$ qcell convert book.xlsx out.csv
converted book.xlsx -> out.csv
```

| Argument / flag | Description |
|-----------------|-------------|
| `src` | Source file to read. |
| `dst` | Destination file to write; its extension picks the output format. |
| `--values` | Write computed values instead of formulas. |

If the conversion cannot be performed — for example saving to `.xlsx` without the `excel` extra installed — qcell prints the error to standard error and exits with status `3`.

### `get file ref` — one cell's value

Print the computed value of a single cell from the workbook's active sheet, formatted the way qcell would display it.

```bash
$ qcell get data.csv B7
42

$ qcell get budget.qcell C10
1,250.00
```

| Argument | Description |
|----------|-------------|
| `file` | Spreadsheet to open. |
| `ref` | An A1-style reference, e.g. `B7`. |

### `deps` — install optional dependencies

Install every optional dependency (the "full-fat" set: the data-science stack,
Excel/Parquet I/O, the PTY terminal, and Jupyter integration), blocking with
progress. Useful for headless setups where you want everything up front instead of
waiting for the background auto-installer.

```bash
$ qcell deps
Attempted 5 package(s): msgspec, textual, nbformat, anywidget, pyte
Optional dependencies present: 20/20
```

qcell already auto-installs these in the background on first GUI/TUI launch (see
[configuration.md](configuration.md#auto-install)); `qcell deps` just does it now
and synchronously. The Qt GUI binding is *not* installed this way — you choose it
with `pip install qcell[gui]`. Set `QCELL_NO_AUTOINSTALL=1` (or `auto_install:
false` in settings) to disable automatic installation entirely.

### `macro list` — list macros and UDFs

List the macros and user-defined functions that were discovered (from `CONFIG_DIR/macros` plus any `--macros` paths).

```bash
$ qcell macro list
macros:
  totals
  uppercase_headers
user functions:
  TAXED()
  REVERSE()
```

If nothing was found:

```bash
$ qcell macro list
no macros found (drop .py files in CONFIG_DIR/macros or pass --macros PATH)
```

### `macro run NAME FILE [-o OUT] [--at A1]` — run a macro

Open `FILE`, run the macro called `NAME` against its workbook, print any messages the macro logged, then save. By default it overwrites the input file; use `-o`/`--output` to save elsewhere.

```bash
# Run the 'totals' macro and overwrite the file
$ qcell macro run totals report.qcell
... any messages the macro logged ...
ran macro 'totals'; saved report.qcell

# Save the result to a new file instead
$ qcell macro run totals report.qcell -o report_with_totals.qcell

# Run a relative-recording macro anchored at cell C5
$ qcell macro run my_recording data.csv --at C5
```

| Argument / flag | Description |
|-----------------|-------------|
| `NAME` | The macro to run (as shown by `macro list`). |
| `FILE` | Spreadsheet to open and operate on. |
| `-o`, `--output OUT` | Save path. Defaults to overwriting the input `FILE`. |
| `--at A1` | Anchor cell for **relative** macros (e.g. `C5`). Relative recordings offset every target and relative reference from this anchor; absolute (`$`) references stay put. |

If the macro is not found or fails, qcell prints the error to standard error and exits with status `4`.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success. |
| `2` | `view`: the requested `--sheet` does not exist. |
| `3` | `convert`: the conversion failed (e.g. a missing optional dependency). |
| `4` | `macro run`: the macro was not found or raised an error. |

## See also

- [getting-started.md](getting-started.md) — install and first-run walkthrough.
- [configuration.md](configuration.md) — settings, directories, and environment variables.
- [gui-guide.md](gui-guide.md) — the GUI menus, palette, and shortcuts.
- [index.md](index.md) — documentation home.
