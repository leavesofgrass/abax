# Command-line interface

The `abax` command is the single entry point for every interface: the desktop GUI, the terminal UI, and a set of headless subcommands for viewing, converting, and querying spreadsheets without opening a window. This page documents every subcommand and flag, with example invocations and the output you can expect. Everything below works equally as `abax …` (the installed script) or `python -m abax …`.

See also: [getting started](getting-started.md) · [examples catalog](examples/README.md) ·
[headless CLI example](examples/scripting-and-cli/headless-cli/README.md) (a tested script
you can run).

## Synopsis

```
abax [--version] [--deps] [--macros PATH ...] [COMMAND] [ARGS]
```

With **no command**, abax opens the GUI when a Qt binding is installed; if Qt is missing it opens the TUI when standard output is a terminal, and otherwise prints help. See [getting-started.md](getting-started.md) for installation and the choice of Qt binding.

## Global flags

These are parsed before any command and the first two are *fast paths* — they answer instantly and never import the GUI/TUI stacks or create an environment.

| Flag | Effect |
|------|--------|
| `--version` | Print `abax <version>` and exit. |
| `--deps` | Print the optional-dependency status report (with the **auto-install** state and how many optional packages are present) and the config/data/cache/log directories, then exit. |
| `--macros PATH` | Load a macro file or directory. Repeatable. Adds its `@macro` commands and `@register_function` UDFs to every command (`view`, `get`, `gui`, `tui`, `macro`). |

### `--version`

```bash
$ abax --version
abax 0.1.13
```

### `--deps`

Reports each optional package as available or missing (with the fallback that kicks in when it is absent), plus external tools like pandoc, and prints the runtime directories.

```bash
$ abax --deps
optional dependencies:
  [OK ] msgspec       available
  [-- ] openpyxl      missing  (fallback: ...)
  [OK ] PySide6       available
  ...
  [-- ] pandoc        missing  (fallback: built-in subset MathML)

  config: C:\Users\you\AppData\Roaming\abax
  data:   C:\Users\you\AppData\Local\abax
  cache:  C:\Users\you\AppData\Local\abax\Cache
  log:    C:\Users\you\AppData\Local\abax\Logs
```

(The exact list and paths depend on your platform and what is installed.) See [configuration.md](configuration.md) for what each directory holds.

### `--macros PATH`

```bash
# Load one macro file and one directory, then open the TUI with them available
abax --macros ./my_macros.py --macros ~/.config/abax/macros tui data.csv
```

Macros from `CONFIG_DIR/macros/*.py` are always discovered automatically; `--macros` adds more on top.

## Commands

### `gui [file]` — desktop GUI

Launch the Qt GUI, optionally opening a file. This is also what runs when you give no command at all.

```bash
abax gui                # empty workbook
abax gui report.abax   # open a file
abax gui data.csv
```

| Argument | Description |
|----------|-------------|
| `file` | Optional spreadsheet to open (`.csv`, `.tsv`, `.xlsx`, `.abax`, `.json`, and more). |

Requires a Qt binding (`gui` or `gui-pyqt` extra). See [gui-guide.md](gui-guide.md).

### `tui [file]` — terminal UI

Launch the curses/Textual TUI, optionally opening a file.

```bash
abax tui                # empty workbook
abax tui data.csv       # open a file
```

| Argument | Description |
|----------|-------------|
| `file` | Optional spreadsheet to open. |

The TUI is modal and vi-flavoured. Navigate with `h`/`j`/`k`/`l` **or the arrow
keys**. Key features:

| Key / command | Action |
|---|---|
| `Enter` / `i` / `a` | Edit the current cell. `Enter` also works Excel-style (from navigation it starts editing; while editing it commits and steps down a row). `Esc` cancels an edit (keeps the old value); `Backspace` deletes (works over SSH too). |
| `PageUp` / `PageDown` / `Home` / `End` | Page the viewport up/down; jump to the first / last used column of the row |
| `u` / `Ctrl-R` | Undo / redo (also `:undo` / `:redo`) — destructive actions checkpoint first |
| `:q` / `:q!` | Quit (`:q` refuses on unsaved edits; `:q!`/`:Q!` force-quit) |
| `:w [path]` | Write; with no path an untitled sheet saves to `./untitled_workbook.abax` |
| `:trace [deps] [N]` | Show the current cell's precedents (or `deps` = dependents) as a scrollable ASCII dependency tree, up to depth `N` |
| `v` / `V` | Visual selection (cell range / whole rows); movement extends it, and the status line shows a live **sum / count / average** |
| `y` · `d` / `x` | In visual mode: yank the range · delete it (under an undo checkpoint) |
| `?` | Help overlay — a scrollable list of every key and command (also `:help`) |
| `:plot A1:A50 [B1:B50]` | Plot a sheet range as a braille chart (or `:plot sin(x) -3 3` for an expression) |
| `:pivot rng idx col val [agg]` | Pivot / group-by a table into a new area of the sheet (`:pt` alias); e.g. `:pivot A1:C99 A B sum` |
| `:describe A1:A50` | Descriptive stats (count / mean / median / stdev / min / max) in the status line; `:describe full A1:A50` opens a scrollable overlay |
| `:!cmd` | Run a shell command; the current cell is exported as `$ABAX_ACTIVE_CELL` / `$ABAX_SELECTION_RANGE` / `$ABAX_SELECTION_JSON` / `$ABAX_SELECTION_TSV` |
| `:live [on\|off]` | Toggle network live data (`=REST`/`=WEBSOCKET` formulas); off by default |
| `:extern [on\|off]` | Toggle closed-workbook external references (`=[Book.abax]Sheet1!A1`); off by default |
| `:table [NAME]` | Name the current region as a structured table (top row = headers) so formulas can use `NAME[Column]`; no args lists tables |
| `:auth HOST HEADER VALUE` | Set a **session-only** live-data request header for HOST (e.g. `:auth api.x Authorization Bearer tok`); `:auth` lists hosts, `:noauth [HOST]` clears. Never persisted |
| `:` commands | `:w` `:q` write/quit, `:find`, `:rpn`, `:fmt`, `:py`, `:!cmd`, `:func`, `:sheet`, `:pivot`, `:describe`, `:trace`, `:live`, `:extern`, … |

### `view file [--sheet NAME]` — print a sheet

Render a spreadsheet as a plain-text table on standard output. Computed values are shown (formulas are evaluated), and columns are aligned with `A, B, C …` headers and `1, 2, 3 …` row labels.

```bash
$ abax view data.csv
  | A        | B
--------------------
1 | Item     | Price
2 | Apples   | 3
3 | Pears    | 4
4 | Cherries | 5
```

| Argument / flag | Description |
|-----------------|-------------|
| `file` | Spreadsheet to open (`.csv`/`.xlsx`/`.json`/`.abax`/…). |
| `--sheet NAME` | Which sheet to print. Defaults to the workbook's active sheet. |

If the named sheet does not exist, abax prints `no such sheet: NAME` to standard error and exits with status `2`. An empty sheet prints `(empty)`.

```bash
abax view book.xlsx --sheet Summary
```

### `convert src dst [--values]` — convert between formats

Open `src` and save it to `dst`. The format is chosen entirely by the **destination file extension** (`.csv`, `.tsv`, `.tab`, `.xlsx`, `.json`, `.abax`, and the other formats abax supports).

```bash
$ abax convert data.csv data.xlsx
converted data.csv -> data.xlsx

$ abax convert book.xlsx out.csv
converted book.xlsx -> out.csv
```

| Argument / flag | Description |
|-----------------|-------------|
| `src` | Source file to read. |
| `dst` | Destination file to write; its extension picks the output format. |
| `--values` | Write computed values instead of formulas. |

If the conversion cannot be performed — for example saving to `.xlsx` without the `excel` extra installed — abax prints the error to standard error and exits with status `3`.

### `get file ref` — one cell's value

Print the computed value of a single cell from the workbook's active sheet, formatted the way abax would display it.

```bash
$ abax get data.csv B7
42

$ abax get budget.abax C10
1,250.00
```

| Argument | Description |
|----------|-------------|
| `file` | Spreadsheet to open. |
| `ref` | An A1-style reference, e.g. `B7`. |

### `diff old new` — cell-level workbook diff

Compare two `.abax`/JSON workbooks and print the per-sheet cell differences —
added (`+`), removed (`-`), and changed (`~ old -> new`). Output is coloured when
stdout is a terminal. Exit codes follow `diff(1)`: **0** = identical, **1** =
differences found, **2** = error.

```bash
$ abax diff before.abax after.abax
Sheet1
  ~B2: 100 -> 125
  +D2: =B2*C2
  -E9: draft
```

### `pipe target file` — stream stdin into cells

Read piped text and lay it into a workbook starting at `target` (an anchor cell
or the top-left of a range, optionally sheet-qualified `Sheet1!A1`), then save
`file`. Columns are auto-detected (tab, else comma, else one cell per line);
force with `--tsv` / `--csv`.

```bash
$ printf 'a,b\n1,2\n' | abax pipe Sheet1!A1 book.abax
wrote 4 cell(s) across 2 row(s) at Sheet1!A1
```

### `profile file [--sheet NAME] [--repeat N] [--limit N]` — slowest formula cells

Time every populated formula cell in a workbook and print them slowest-first —
the headless twin of the GUI formula profiler (same `core.profile` engine). Use
it to find which formulas dominate a slow recalc. `--sheet` restricts to one
sheet (default: all); `--repeat N` averages N passes for a steadier estimate on
sub-millisecond timings; `--limit N` caps the rows (default 20, `0` = all). Exit
codes: **0** = report printed, **2** = file can't be opened or the sheet is
unknown.

```bash
$ abax profile model.abax --limit 3
  #  Cell         Time (ms)  Formula
------------------------------------
  1  Sheet1!D200     1.9420  =SUMPRODUCT(A2:A200,B2:B200)
  2  Sheet1!C2       0.4110  =VLOOKUP(A2,Rates!A:B,2,0)
  3  Sheet1!E2       0.0900  =C2*(1+tax)
```

### `deps` — install optional dependencies

Install every optional dependency (the "full-fat" set: the data-science stack,
Excel/Parquet I/O, the PTY terminal, and Jupyter integration), blocking with
progress. Useful for headless setups where you want everything up front instead of
picking features in the first-run chooser.

```bash
$ abax deps
Attempted 5 package(s): msgspec, textual, nbformat, anywidget, pyte
Optional dependencies present: 24/24
```

On first GUI launch abax offers these through a feature chooser — **nothing is
installed unless you choose it** (see
[configuration.md](configuration.md#auto-install)); `abax deps` installs the whole
set at once and synchronously. The Qt GUI binding is *not* installed this way — you choose it
with `pip install abax[gui]`. Set `ABAX_NO_AUTOINSTALL=1` (or `auto_install:
false` in settings) to disable automatic installation entirely.

### `macro list` — list macros and UDFs

List the macros and user-defined functions that were discovered (from `CONFIG_DIR/macros` plus any `--macros` paths).

```bash
$ abax macro list
macros:
  totals
  uppercase_headers
user functions:
  TAXED()
  REVERSE()
```

If nothing was found:

```bash
$ abax macro list
no macros found (drop .py files in CONFIG_DIR/macros or pass --macros PATH)
```

### `macro run NAME FILE [-o OUT] [--at A1]` — run a macro

Open `FILE`, run the macro called `NAME` against its workbook, print any messages the macro logged, then save. By default it overwrites the input file; use `-o`/`--output` to save elsewhere.

```bash
# Run the 'totals' macro and overwrite the file
$ abax macro run totals report.abax
... any messages the macro logged ...
ran macro 'totals'; saved report.abax

# Save the result to a new file instead
$ abax macro run totals report.abax -o report_with_totals.abax

# Run a relative-recording macro anchored at cell C5
$ abax macro run my_recording data.csv --at C5
```

| Argument / flag | Description |
|-----------------|-------------|
| `NAME` | The macro to run (as shown by `macro list`). |
| `FILE` | Spreadsheet to open and operate on. |
| `-o`, `--output OUT` | Save path. Defaults to overwriting the input `FILE`. |
| `--at A1` | Anchor cell for **relative** macros (e.g. `C5`). Relative recordings offset every target and relative reference from this anchor; absolute (`$`) references stay put. |

If the macro is not found or fails, abax prints the error to standard error and exits with status `4`.

### `doctor` — environment health report

Prints a self-diagnostic: Python version and platform, the optional-dependency
matrix (what's installed vs. available), the active **code-isolation** level and
which sandbox confinement is selected/available, the runtime directories
(config / data / cache / log) and whether each is writable, and whether
`settings.json` parses. It never installs anything and never crashes when a
confinement or directory is unavailable — a quick first stop when a feature seems
missing.

```console
$ abax doctor
abax doctor — environment health report
=======================================
Python & platform
  python      : 3.13.0 (CPython)
  ...
Optional dependencies
  [OK] openpyxl            available
  [--] PyNEC               missing (fallback: built-in method-of-moments solver)
  ...
```

### `report file [-o OUT]` — export a PM report

Generates a project-management report (HTML or Markdown) for every project
defined in the workbook.  The report includes per-project status tables, task
summaries, and milestone listings — the same content as **Project → Export
report** in the GUI.

```console
$ abax report portfolio.abax -o status.html
report written to status.html

$ abax report portfolio.abax -o status.md
report written to status.md
```

The output format is chosen by the file extension: `.md` produces Markdown,
anything else produces HTML. If `-o` is omitted the report is written to
`report.html` in the current directory. Exit code **2** when the file cannot
be opened or the workbook defines no projects.

### `notebook run FILE [-o OUT]` — execute a notebook headlessly

Runs a Jupyter `.ipynb` end to end **without** `nbclient`: each code cell is
executed in order against abax's own shell (so `doc`, `wb`, `cell`, `put`, … are
bound, exactly as in the embedded console), and the computed outputs are written
back into the notebook. With no `-o` the notebook is executed **in place**.

```console
# Execute in place (overwrites the file with results)
$ abax notebook run analysis.ipynb
executed 12 cell(s); wrote analysis.ipynb

# Write the executed copy elsewhere
$ abax notebook run analysis.ipynb -o analysis-run.ipynb
```

| Argument / flag | Description |
|-----------------|-------------|
| `FILE` | The `.ipynb` notebook to execute. |
| `-o`, `--output OUT` | Write the executed notebook here (default: overwrite `FILE`). |

A cell that raises does not stop the run; its error rides back into the notebook's
outputs and the summary line notes how many cells raised. See
[jupyter.md](jupyter.md) for the kernel and rich-display integration.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success. |
| `2` | `view`: the requested `--sheet` does not exist. |
| `3` | `convert`: the conversion failed (e.g. a missing optional dependency). |
| `4` | `macro run` / `notebook run`: the macro/notebook was not found or failed. |

## See also

- [getting-started.md](getting-started.md) — install and first-run walkthrough.
- [configuration.md](configuration.md) — settings, directories, and environment variables.
- [gui-guide.md](gui-guide.md) — the GUI menus, palette, and shortcuts.
- [index.md](index.md) — documentation home.
