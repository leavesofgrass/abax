# qcell

A keyboard-first **statistics and data-science workstation** — an integrated
environment for data work, built on a fast, scriptable spreadsheet. Load a
dataset, explore it with ~150 formula functions (including statistical
distributions), run built-in analyses (regression, t-tests, ANOVA, correlation),
reshape it with pivot/group-by and recode, visualize with the grapher, hand a
selection off to pandas, and script the whole thing with Python macros — across
CSV, Excel, Parquet, SQLite, JSON, R, and more.

It runs as a Qt desktop GUI (the default), a vim-style terminal UI, or a headless
CLI. The core is pure-stdlib Python; every heavier capability is an optional
dependency with a graceful fallback. When a behaviour is ambiguous, qcell follows
**gnumeric**.

## Install

```sh
# core only (pure stdlib) — works immediately, no dependencies
python -m qcell --deps

# full dev install
pip install -e ".[dev,tui,gui,excel,fast-io]"
# pieces: .[gui] PyQt6 · .[excel] openpyxl · .[fast-io] msgspec+platformdirs · .[tui] textual
```

Every optional dependency degrades gracefully — `--deps` shows what's present
and what the fallback is. The whole test suite passes with zero optional
packages installed.

## Use

```sh
python -m qcell view sales.csv            # print as a table
python -m qcell get sales.csv D2          # compute one cell
python -m qcell convert sales.csv out.xlsx
python -m qcell tui budget.qcell          # curses TUI (vim keys)
python -m qcell gui budget.qcell          # Qt GUI (if PyQt6 installed)
python -m qcell macro run totals book.csv --macros macros/
```

## Formats

Open and save by file extension — convert between any of them:

| Format | Extensions | Notes |
|---|---|---|
| CSV / TSV | `.csv` `.tsv` `.tab` | comma and tab delimited |
| Excel | `.xlsx` `.xlsm` | via openpyxl; formulas preserved |
| XML Spreadsheet | `.xml` | Excel 2003 SpreadsheetML; formulas stored as R1C1 |
| Markdown | `.md` `.markdown` | first-class GFM tables (alignment, escaping) |
| Jupyter | `.ipynb` | markdown table + pandas DataFrame cell per sheet |
| R | `.R` `.RData` | `data.frame` export; best-effort import |
| SQLite | `.db` `.sqlite` | tables / `SELECT` queries ↔ sheets (one sheet per table) |
| JSON Lines | `.jsonl` `.ndjson` | flat-file record DB; one object per line |
| Fixed-width | `.fixed` | whitespace-aligned columns |
| Native / JSON | `.qcell` `.json` | lossless workbook; JSON is also the interchange format |

```sh
python -m qcell convert budget.csv budget.md      # → GitHub-flavored Markdown table
python -m qcell convert budget.csv budget.xml     # → XML Spreadsheet (R1C1 formulas)
python -m qcell convert budget.csv budget.ipynb   # → notebook (markdown + DataFrame)
python -m qcell convert budget.csv budget.R       # → R data.frame
```

**Foreign JSON.** Opening a `.json` file auto-detects what it is: a native qcell
workbook, the spec's interchange envelope (`{app, schema_version, data}`), a qrpn
calculator save (`{stack, registers}`), a list of records, or a dict of columns.

```sh
python -m qcell view qrpn-save.json --sheet stack   # read a qrpn calculator save
```

## Formulas

~150 functions across aggregate, conditional, math, lookup, logical, text, date,
statistics, and info families:

```
=SUM(A1:A10)                         =VLOOKUP("banana", A1:B9, 2, FALSE)
=IF(B2>0, "ok", "bad")               =INDEX(B1:B9, MATCH("kiwi", A1:A9, 0))
=SUMIF(A1:A9, ">100", B1:B9)         =IFS(s>=90,"A", s>=80,"B", TRUE,"F")
=ROUND(AVERAGE(C1:C5), 2)            =TEXT(0.1234, "0.00%")
=DATEDIF("2026-01-01", TODAY(), "M") =SWITCH(grade, 1,"one", 2,"two", "other")
=PERCENTILE(A1:A99, 0.9)             =CORREL(A1:A50, B1:B50)
```

Operators `+ - * / ^ % &` and comparisons; ranges (`A1:C3`); absolute refs
(`$A$1`); bare `TRUE`/`FALSE`. Errors are values (`#DIV/0!`, `#NAME?`, `#N/A`,
`#REF!`, `#CIRC!`, …) and propagate. Control-flow functions (`IF`, `IFERROR`,
`IFS`, `SWITCH`, `CHOOSE`) are lazily evaluated. Circular references surface as
`#CIRC!`, never a crash.

## Editing: copy / paste / fill / sort

Gnumeric-style grid editing. **Fill series** autodetects progressions —
`1, 2, …`, `Mon, Tue, …`, `Jan, Feb, …`, ISO dates, and `Item 1, Item 2, …`.
Pasting shifts relative references (`$`-anchored refs stay fixed).

- **GUI:** `Ctrl+C` / `Ctrl+V` (relative paste; values go to the system clipboard
  as TSV for other apps), `Ctrl+D` / `Ctrl+R` fill down/right, `Del` to clear;
  *Data* menu for Sort and Fill series; *Tools → Copy selection as Markdown*.
- **TUI:** `y`/`p` yank/paste, `:copy A1:B3`, `:paste C1`, `:fill down A1:A20`,
  `:fill series A1:A12`, `:sort A1:C10 B desc`.

## The GUI

A complete menu bar with logical shortcuts, plus a command palette reachable two
ways: `Ctrl+Shift+P` **or** pressing `:` on the grid (vim/gnumeric feel). The
palette lists every action — including any loaded macros.

| Menu | Highlights |
|---|---|
| **File** | New `Ctrl+N`, Open `Ctrl+O`, Save `Ctrl+S`, Save As `Ctrl+Shift+S`, Quit `Ctrl+Q` |
| **Edit** | Copy `Ctrl+C`, Paste `Ctrl+V`, Clear `Del`, Fill `Ctrl+D`/`Ctrl+R`, Find/Replace `Ctrl+F`, Palette `Ctrl+Shift+P` |
| **Insert** | Sheet `Shift+F11`, Function `Shift+F3` |
| **Format** | Theme `Ctrl+T`, OpenDyslexic font, conditional formatting, vim mode |
| **Data** | Sort, Fill series, Recalculate `F9` |
| **Sheet** | Next `Ctrl+PgDn`, Previous `Ctrl+PgUp`, Rename (or use the **tabs**) |
| **Tools** | RPN calculator `Ctrl+K`, Python console `Ctrl+Shift+Y`, Clipboard `Ctrl+Shift+V`, Macros, recording |
| **Help** | Keyboard shortcuts `F1`, About |

Vim navigation works in the grid too (`j/k/h/l`, `g`/`G`, `/`). **Sheet tabs** sit
at the bottom (click to switch, double-click to rename). The formula bar
autocompletes function names and shows a live argument-hint tooltip. **Eight
themes** ship — Obsidian, Dark One, Nord, Solarized, CRT green/amber, Light, and
High-contrast (≥7:1) — matching the star/qv palettes; an **OpenDyslexic** font can
be fetched on demand. Widgets are screen-reader labelled.

## Find, format, calculate, script

- **Find / Replace** (`Ctrl+F`) — regex with backreferences, scoped, in-formulas
  or values; TUI `:find`/`n`/`N`, `:s/pat/repl/`.
- **Conditional formatting** — value→color rules (comparisons, between, contains,
  color scale) rendered in the GUI **and** the TUI; persists with the workbook.
- **Function browser** (`Shift+F3`) — searchable list of every function (incl. UDFs)
  with signatures; TUI `:func`.
- **RPN calculator** (`Ctrl+K`) — an HP-style scientific RPN keypad with an X/Y/Z/T
  stack, rolled in from the qv project. **← Cell** pulls the active cell onto the
  stack; **→ Cell** writes X back. TUI `:rpn` is a REPL (`<` pull / `>` store).
  Its save format is qv-compatible (`{stack, registers}`).
- **Python console** (`Ctrl+Shift+Y`) — a REPL wired to the live workbook
  (`doc`, `wb`, `cell(ref)`, `put(ref, val)`, `rpn`, `refresh()`). TUI `:py <code>`.
- **Clipboard manager** (`Ctrl+Shift+V`) — copy history with pinning; TUI
  `:clips`/`:clip`. Runs trusted Python for macros/console — not a sandbox.
- **Graphing** (*Data → Graph*) — plot a function of `x` or a selected column;
  `QPainter` in the GUI, HP-48-style **braille** in the TUI (`:plot sin(x) -6 6`).
- **Equation editor** (*Insert → Equation*) — type LaTeX, get a live Unicode
  preview and **MathML** (via pandoc when present, pure-Python fallback otherwise);
  insert into a cell. TUI `:eq \frac{a}{b}`.
- **Number formats** (*Format → Number*) — General/Integer/Currency/Percent/
  Scientific/Thousands per cell, persisted with the workbook; TUI `:fmt percent A1:A9`.
- A **toolbar** with the common actions, for mouse-first usability.

## The TUI

`python -m qcell tui` — a vim-first curses interface that degrades to ASCII +
8-color over SSH. Normal/insert/command modes, the eight themes (live `:theme`),
`Tab` autocomplete with argument hints, an RPN REPL (`:rpn`), a Python one-liner
(`:py`), and the same editing/find/macro commands as the GUI via `:`.

## Macros

Extend qcell with plain Python files — command macros that drive a workbook, and
user-defined functions callable inside formulas:

```python
# macros/sample.py
@macro("totals")
def totals(ctx):
    n_rows, n_cols = ctx.sheet.used_bounds()
    for c in range(n_cols):
        col = chr(ord("A") + c)
        ctx.set(f"{col}{n_rows+1}", f"=SUM({col}1:{col}{n_rows})")
    ctx.recalc()

@register_function("TAXED")          # now usable as =TAXED(A1, 0.08)
def taxed(args):
    return numbers([args[0]])[0] * (1 + (as_number(args[1]) if len(args) > 1 else 0.08))
```

```sh
qcell --macros macros/ macro list           # discover macros + UDFs
qcell --macros macros/ macro run totals book.csv
qcell --macros macros/ view sheet.csv        # UDFs available everywhere
```

Reachable from the TUI (`:macro <name>`), the GUI *Tools → Macros* menu, and the
command palette. Macros run trusted Python (not a sandbox) — only load files you
trust. Auto-discovered from `CONFIG_DIR/macros/*.py`.

### Recording

Record your edits and qcell writes the macro for you:

- **GUI:** *Tools* menu → *Start recording* / *Start relative recording* /
  *Save recorded macro…* / *Replay recording*. A `● REC` / `● REL` indicator
  shows in the title bar.
- **TUI:** `:rec` start/stop, `:rec rel` for a *relative* recording, `:rec save
  mymacro.py`, `:rec replay`.

A recording is a list of actions, so it round-trips through JSON and emits clean
`@macro` Python you can hand-edit. **Relative recording** generalizes a pattern:
record `=A1*2` at B1, replay at B4, and it writes `=A4*2` — cells and relative
refs shift by the same offset.

```sh
qcell --macros macros/ macro run rowcalc data.csv --at B4   # replay relative to C-col B4
```

### Autocomplete & argument hints

While typing a formula, qcell completes function names — built-ins **and** your
UDFs. In the TUI, `Tab` completes (single → `NAME(`, multiple → common prefix);
once inside a call it shows the signature with the **current argument** marked —
`VLOOKUP(lookup, table, »col_index«, [approximate])`. In the GUI, the formula bar
shows a completion popup and a floating signature tooltip that tracks your cursor.

## Build

```sh
just install    # dev setup
just test       # tests (pass with zero optional deps)
just pyz        # qcell.pyz — one-file, optimize=2, compressed, stripped
just wheel      # wheel (docstrings kept)
just check      # lint + test + pyz + smoke
```

## Layout

```
qcell/
  core/      stdlib-only engine at the root: references, tokenizer, parser,
             evaluator, functions, sheet, workbook; fill/series; translate
             (ref-shift), r1c1, completion. Pluggable libraries in subpackages:
    core/io/        csv/markdown/notebook/r/xml/exchange/sqlite/flatfile I/O
    core/calc/      RPN (12C/15C/16C), algebraic, TI calculator engines
    core/science/   linear algebra, calculus/ODE, signal, stats, ML, finance
    core/format/    number formats, cell styles, conditional formatting, palettes
  engine/    adapters: excel_io/ods_io/parquet_io, document façade (dispatch)
  gui/       Qt front-end: MainWindow + mixins (view/palette/calc/console/
             macros/tools), menus, dual-surface theming, _qtcompat. Widgets in
             gui/grid/, gui/dialogs/, gui/calc/, gui/console/
  tui/       curses TUI (vim-first, SSH-safe): capabilities/themes/commands/
             editor/keys/render/app
  macros.py  macro engine + UDF registration
  recorder.py  macro recording (absolute & relative)
  app.py     CLI entry (lazy imports, --help/--version/--deps fast paths)
tests/       pytest suite
```

See [docs/architecture.md](docs/architecture.md) for the architecture and
invariants, and [docs/formula-reference.md](docs/formula-reference.md) for the
complete function list.
