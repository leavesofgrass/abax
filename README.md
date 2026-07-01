# abax

A keyboard-first **statistics and data-science workstation** — an integrated
environment for data work, built on a fast, scriptable spreadsheet. Load a
dataset, explore it with **600+ formula functions** (statistics and distributions,
financial, engineering, database, and **RF/ham-radio**), run built-in analyses
(regression, t-tests, ANOVA, correlation),
reshape it with pivot/group-by and recode, visualize with the grapher, hand a
selection off to pandas, and script the whole thing with Python macros — across
CSV, Excel, Parquet, SQLite, JSON, R, and more.

It also carries purpose-built tools: **RF & antenna engineering** (link budgets,
Smith charts, a thin-wire Method-of-Moments solver with NEC `.nec` import/export),
**Jupyter integration** (a lossless `.ipynb` round-trip, rich display, and
abax-as-a-Jupyter-kernel), a **dual-pane file manager** with configurable command
buttons and one-click archiving, and a **budget wizard**.

It runs as a Qt desktop GUI (the default), a vim-style terminal UI, or a headless
CLI. The core is pure-stdlib Python; every heavier capability is an optional
dependency with a graceful fallback. When a behaviour is ambiguous, abax follows
**gnumeric**.

## Install

```sh
pip install abax[gui]         # the Qt GUI (PySide6) — the usual choice
python -m abax                # launch it
```

abax installs *full-fat by default*: on first launch it **auto-installs the
remaining optional dependencies in the background** (the data-science stack,
Excel/Parquet I/O, the PTY terminal, Jupyter integration) so everything just
works. It's best-effort and non-blocking — abax keeps using its pure-Python
fallbacks meanwhile — and attempted only once per machine.

```sh
python -m abax deps           # install every optional dependency now (blocking)
python -m abax --deps         # show what's present + the auto-install status
ABAX_NO_AUTOINSTALL=1 …        # opt out (or set auto_install=false in settings)

pip install -e ".[dev]"        # a development checkout
# extras: .[gui] PySide6 · .[gui-pyqt] PyQt6 · .[tui] textual · .[excel] openpyxl
#         .[parquet] pyarrow · .[science] numpy/pandas/scipy/… · .[bayes] pymc (heavy)
#         .[jupyter] nbformat/ipykernel/anywidget · .[all] everything (default full-fat)
#         .[thin] GUI + light conveniences, no heavy science
```

The core is pure stdlib — the whole test suite passes with **zero** optional
packages installed, and every optional dependency degrades gracefully.

## Use

```sh
python -m abax view sales.csv            # print as a table
python -m abax get sales.csv D2          # compute one cell
python -m abax convert sales.csv out.xlsx
python -m abax tui budget.abax          # curses TUI (vim keys)
python -m abax gui budget.abax          # Qt GUI (PySide6/PyQt6)
python -m abax macro run totals book.csv --macros macros/
python -m abax deps                      # fetch all optional dependencies
```

## Formats

Open and save by file extension — convert between any of them:

| Format | Extensions | Notes |
|---|---|---|
| CSV / TSV | `.csv` `.tsv` `.tab` | comma and tab delimited |
| Excel | `.xlsx` `.xlsm` | via openpyxl; formulas preserved |
| XML Spreadsheet | `.xml` | Excel 2003 SpreadsheetML; formulas stored as R1C1 |
| Markdown | `.md` `.markdown` | first-class GFM tables (alignment, escaping) |
| Jupyter | `.ipynb` | valid nbformat 4.5; **round-trips the whole workbook losslessly** (markdown-table fallback for foreign notebooks) |
| R | `.R` `.RData` | `data.frame` export; best-effort import |
| SQLite | `.db` `.sqlite` | tables / `SELECT` queries ↔ sheets (one sheet per table) |
| JSON Lines | `.jsonl` `.ndjson` | flat-file record DB; one object per line |
| Fixed-width | `.fixed` | whitespace-aligned columns |
| Native / JSON | `.abax` `.json` | lossless workbook; JSON is also the interchange format |

```sh
python -m abax convert budget.csv budget.md      # → GitHub-flavored Markdown table
python -m abax convert budget.csv budget.xml     # → XML Spreadsheet (R1C1 formulas)
python -m abax convert budget.csv budget.ipynb   # → notebook (markdown + DataFrame)
python -m abax convert budget.csv budget.R       # → R data.frame
```

**Foreign JSON.** Opening a `.json` file auto-detects what it is: a native abax
workbook, the spec's interchange envelope (`{app, schema_version, data}`), a qrpn
calculator save (`{stack, registers}`), a list of records, or a dict of columns.

```sh
python -m abax view qrpn-save.json --sheet stack   # read a qrpn calculator save
```

## Formulas

600+ functions across aggregate, conditional, math, lookup, logical, text, date,
statistics, financial (incl. bonds), engineering, **RF/ham-radio & antenna**,
info, and the LET/LAMBDA functional families:

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
`#REF!`, `#SPILL!`, `#CALC!`, `#CIRC!`, …) and propagate. Control-flow functions
(`IF`, `IFERROR`, `IFS`, `SWITCH`, `CHOOSE`) are lazily evaluated. Circular
references surface as `#CIRC!`, never a crash.

**Dynamic arrays.** A formula that yields an array *spills* across neighbouring
cells (Excel-style): `=SORT(A1:A9)`, `=UNIQUE(B:B)`, `=SEQUENCE(3,3)`,
`=FILTER(A1:A9, B1:B9>0)`, and the reshaping family (`TRANSPOSE`, `VSTACK`,
`TAKE`, `MMULT`, …). Operators **broadcast** over ranges (`=A1:A3*2`), array
constants (`={1,2;3,4}`) and array `IF` work, `A1#` references a spill range, and
`@` takes a single value. See [docs/formula-reference.md](docs/formula-reference.md).

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
| **Tools** | Calculator `Ctrl+K`, Python console `Ctrl+Shift+Y`, Clipboard `Ctrl+Shift+V`, **File manager `Ctrl+Shift+F`**, **Budget wizard**, **Scientific** (Matrix / Signal / ODE / ML / **RF toolkit / Smith chart / Antenna pattern**), Install optional features, Macros, recording |
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

## RF, antenna & signal engineering

For hams and RF engineers (the *Radio* menu), plus **60+ RF formula functions**:

- **RF math** — `DBM2W`, `W2DBM`, `VSWR`, `FSPL`, `FRIIS`, `EIRP`, `WAVELENGTH`,
  `XL`/`XC`, `RESFREQ`, `Z0COAX`, `SKINDEPTH`, the **Maidenhead grid locator**
  (`GRIDSQUARE`, `GRIDDIST`, `GRIDBEARING`), the **US band plan** (`HAMBAND`) and
  **CTCSS** tones — with an **RF toolkit** dialog (link budget / coax / antenna
  dimensions / L-network matching) and a **Smith chart**.
- **Antenna modeling** — analytic dipole/array patterns with a polar viewer;
  dipole input impedance (`DIPOLER`/`DIPOLEX`/`RESONANTLEN`); and a real thin-wire
  **Method of Moments** solver generalised to arbitrary 3-D wire structures (Yagis,
  bent wires) with **NEC `.nec`** deck import/export. The Antenna pattern viewer
  exports **SVG** and **NEC** decks.
- **Signal/DSP** — no-numpy FFT/STFT/spectrogram, Welch PSD (real + complex I/Q),
  interpolation, Butterworth/FIR filters, and ODE solvers via the *Signal / data*
  and *ODE solver* tools. See [docs/rf-toolkit.md](docs/rf-toolkit.md).

## File manager & budgeting

- **Dual-pane file manager** (*Tools → File manager*, `Ctrl+Shift+F`) — a
  Worker / Directory Opus-style browser: two panes where operations act on the
  active pane's selection with the other pane as target. Copy / move / delete /
  rename, one-click **`.zip` and `.tar.gz`** creation and safe extraction,
  recursive **find** by name and file contents, and **configurable command
  buttons** whose shell commands expand `{dir}`/`{path}`/`{sel}`/`{dest}`
  placeholders (Python, not Lua — persisted per user).
- **Budget wizard** (*Tools → Budget wizard*) — set up income and 50/30/20
  categories and drop in a **live budget sheet** where *Spent* is a `SUMIF` over an
  expenses log; logging an expense updates the budget through the formula engine.

## Jupyter integration

`.ipynb` export is valid **nbformat 4.5** and round-trips the whole workbook
losslessly. A `Sheet` renders as an HTML/Markdown table via the IPython
rich-display protocol. abax can run **as a Jupyter kernel** (`python -m
abax.kernel`, after `pip install abax[jupyter]`) and expose an **editable sheet
widget** (anywidget). See [docs/jupyter.md](docs/jupyter.md).

## The TUI

`python -m abax tui` — a vim-first curses interface that degrades to ASCII +
8-color over SSH. Normal/insert/command modes, the eight themes (live `:theme`),
`Tab` autocomplete with argument hints, an RPN REPL (`:rpn`), a Python one-liner
(`:py`), and the same editing/find/macro commands as the GUI via `:`.

## Macros

Extend abax with plain Python files — command macros that drive a workbook, and
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
abax --macros macros/ macro list           # discover macros + UDFs
abax --macros macros/ macro run totals book.csv
abax --macros macros/ view sheet.csv        # UDFs available everywhere
```

Reachable from the TUI (`:macro <name>`), the GUI *Tools → Macros* menu, and the
command palette. Macros run trusted Python (not a sandbox) — only load files you
trust. Auto-discovered from `CONFIG_DIR/macros/*.py`.

### Recording

Record your edits and abax writes the macro for you:

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
abax --macros macros/ macro run rowcalc data.csv --at B4   # replay relative to C-col B4
```

### Autocomplete & argument hints

While typing a formula, abax completes function names — built-ins **and** your
UDFs. In the TUI, `Tab` completes (single → `NAME(`, multiple → common prefix);
once inside a call it shows the signature with the **current argument** marked —
`VLOOKUP(lookup, table, »col_index«, [approximate])`. In the GUI, the formula bar
shows a completion popup and a floating signature tooltip that tracks your cursor.

## Build

```sh
just install    # dev setup
just test       # tests (pass with zero optional deps)
just pyz        # abax.pyz — one-file, optimize=2, compressed, stripped
just wheel      # wheel (docstrings kept)
just check      # lint + test + pyz + smoke
```

## Layout

```
abax/
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
