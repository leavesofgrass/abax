# Desktop GUI guide

abax's Qt desktop app is keyboard-first: you can drive almost everything from
the grid, the formula bar, and the command palette without reaching for the
mouse. This guide covers day-to-day use of the window — navigation, editing,
formatting, sheets, dynamic arrays, the docks, and the full menu bar.

Launch it with:

    python -m abax gui data.csv

The default Qt binding is **PySide6** (PyQt6 also works; bindings are isolated
in one place — `abax/gui/_qtcompat.py` — so the rest of the app is unchanged).

New to abax? Start with [Getting started](getting-started.md). For the formula
language, see the [Formula reference](formula-reference.md). For paths, themes,
and persisted options, see [Configuration](configuration.md). For the built-in
calculators, see [Calculators](calculators.md). For the analysis dialogs, see
[Data analysis](data-analysis.md) and [Data science](data-science.md); for the
RF suite, see the [RF toolkit](rf-toolkit.md). The docs index is
[here](index.md).

## Launching the GUI

The GUI is one of several front-ends (there's also a curses TUI and a headless
CLI). A few ways to reach it:

- `abax gui` — open to an empty workbook.
- `abax gui data.csv` — open straight into a file.
- `abax data.csv` — a **bare file path with no subcommand** is treated as
  `abax gui data.csv`, so double-clicking a spreadsheet (or `abax myfile.xlsx`)
  lands in the GUI (`abax/app.py`, `_normalize_argv`).
- `abax` with nothing else — prefers the GUI when Qt is available, otherwise
  falls back to the TUI, then to `--help`.

Pass `--macros PATH` (repeatable) to load extra macro/UDF files at startup; they
show up in *Tools → Macros* and the command palette.

On the **first launch** abax pops the optional-feature chooser (Thin / All /
custom — see *Tools → Install optional features now* below). The Python console,
terminal, and calculator are **not** auto-opened: the window starts on a clean
grid, and those panels appear on demand (their code-execution consent prompt
only fires when you actually open the console or terminal).

If Qt isn't installed, `abax gui` prints an install hint
(`pip install abax[gui]`) and suggests `abax tui` instead.

## The window at a glance

From top to bottom:

- **Menu bar** — File, Edit, View, Insert, Format, Data, Sheet, Tools, Radio,
  Help.
- **Toolbar** — icon shortcuts for the common actions (toggle with
  *View → Show toolbar*; the state is remembered in settings).
- **Formula bar** — shows and edits the active cell's raw value or formula.
- **Grid** — the virtualized cell grid.
- **Sheet tabs** — one coloured tab per sheet, with a `+` button to add one.
- **Status bar** — the active cell's address or selection aggregates, an I/O
  progress bar, and a right-hand cluster showing vim/insert mode, the current
  theme, and the saved/unsaved state.

Docks (calculator, Python console, terminal) attach around the grid on demand
and can be floated or moved to any edge. Window geometry, the active sheet, and
the cursor cell are saved on close and restored next session.

## The virtualized grid

The grid renders only the cells currently in view, so even very large files
scroll smoothly — no widget is created per cell. It's a `QTableView` over a
custom `AbaxTableModel` (`abax/gui/grid/grid_model.py`); the model reports a
generous extent (the used range plus headroom — 200 margin rows, 8 margin
columns, a 200×26 minimum) and **grows on demand**: scroll to the bottom or
right edge and more rows/columns appear automatically. You can also add space
deliberately with *Insert → Rows / columns → Append row (end)* /
*Append column (end)*.

A cell shows its **computed value** (`DisplayRole` = `Sheet.display`); when you
start editing, the editor seeds with the **raw text** (`EditRole` =
`Sheet.get_raw`) — the formula, not the result. Alternating row colours are on.

Visual attributes are served lazily through the model's `data()` roles, so they
cost nothing until a cell is painted:

- **BackgroundRole / ForegroundRole** — conditional-format fills and per-cell
  fill/text colours (an explicit cell style overrides a conditional fill).
- **FontRole** — bold / italic / underline, plus the OpenDyslexic family when
  that font is active (a per-cell font is needed because the delegate's painter
  doesn't honour a stylesheet font family).
- **TextAlignmentRole** — the per-cell horizontal alignment (left/center/right),
  always vertically centred.

Number formats are applied when the value is displayed, so the underlying number
is never changed.

## Keyboard navigation (Excel-style)

Navigation lives in one place — `CellTableView` in
`abax/gui/grid/grid_view.py` — and uses the muscle-memory you already have:

| Key | Action |
| --- | --- |
| `Enter` | Commit and move **down** one row |
| `Shift+Enter` | Commit and move **up** one row |
| `Tab` | Commit and move **right** one column |
| `Shift+Tab` | Commit and move **left** one column |
| `F2` | Edit the active cell in place |
| Any printable key | Start a **replace-mode** edit (overwrites the cell) |
| `Ctrl+Arrow` | Jump to the next data edge in that direction |
| `Home` | Jump to column A in the current row |
| `Ctrl+Home` | Jump to `A1` |
| `Ctrl+End` | Jump to the last used cell |
| `Del` | Clear the selected cells |

Enter/Tab (and their Shift reverses) also commit **from inside the in-cell
editor**: the delegate stashes the pending move, lets Qt write the value back,
then advances the cursor — so the value always lands before the selection moves.

Double-clicking a cell also opens the in-place editor, and you can pick the
allowed value from a dropdown when the cell has list-style data validation.

`Ctrl+Arrow` is the classic "jump to the edge of the data block" move: from
inside a filled region it lands on the last non-blank cell before a gap; from a
blank cell it jumps to the next filled one. It uses a cached set of populated
cells (rebuilt after any edit), so it never rescans the whole sheet per keypress.

Copy/cut/paste (`Ctrl+C/X/V`) are also handled directly by the grid view, not
just via the menu shortcut, so they work reliably even when a focused editor or
an ambiguous window shortcut would otherwise swallow them.

## Vim navigation (on by default)

Vim-style movement is enabled out of the box (`settings.vim_mode = True`;
`abax/gui/mixin_navigation.py`). When you are **not** editing a cell:

| Key | Action |
| --- | --- |
| `j` / `k` | Move down / up |
| `h` / `l` | Move left / right |
| `g` / `G` | Jump to the top / bottom row |
| `/` | Focus the formula bar (search/entry) |
| `Esc` | Return focus to the grid |

Vim keys work alongside the arrow keys and the mouse — they never replace them.
Turn the mode off any time with *View → Toggle vim mode* (or the command
palette). When vim mode is off, those letters type into the cell as usual. The
status-bar cluster shows `VIM` or `INS` so you always know which mode you're in.

## The formula bar

Click into the formula bar (or press `/` in vim mode) to edit the active cell's
contents. Type a literal value or a formula beginning with `=`, then press
`Enter` to commit. As in Excel, **Enter in the formula bar commits and advances
the selection one row down** — even if you didn't change the value — so you can
key down a column quickly.

While you type a formula, an **argument hint** tooltip appears under the bar,
showing the current function's signature with the active parameter in bold, and
a function-name **autocomplete** (`FormulaCompleter`) offers function names plus
the workbook's defined names and sheet names. The **in-cell editor** gets the
same completer, so autocomplete follows you whether you edit in the bar or in
the cell.

## Status-bar selection aggregates

Select a range and the status bar shows live aggregates over it, mirroring
Excel:

```
Sum 1,240   Avg 124   Min 12   Max 305   Count 10
```

- Aggregates (Sum/Avg/Min/Max) are computed over **numeric** cells only.
  Booleans and error values are not counted as numbers.
- **Count** is the number of non-blank cells in the selection.
- If no numbers are present, only `Count` is shown.
- A single-cell selection shows just the cell's `A1` address.
- Selecting an enormous range (over ~200,000 cells, e.g. a whole column) shows
  the cell count instead of scanning every cell, so the readout never stalls.

## Find, replace, and go-to

Open Find/Replace with `Ctrl+F` (*Edit → Find / Replace*). The dialog is
regex-capable and can find/replace-all across the sheet or restrict to the
current selection. It's kept alive between opens and re-focuses its search box.
The grid also has a quick *Go to* jump (`Ctrl+G`) that accepts a cell or range
like `B12` or `A1:C9` and selects it.

## Dynamic-array spill

abax has real Excel-style dynamic arrays: functions like `SEQUENCE`, `UNIQUE`,
`SORT`, `FILTER`, and `XLOOKUP` return a whole block from a single formula. The
grid shows this the way Excel does:

- The **anchor** cell holds the formula; the surrounding **spilled** cells show
  the array's other values but stay read-only (they belong to the anchor).
- A **dashed blue border** (colour `#3b82f6`) outlines the whole spill range.
  It's drawn by `GridDelegate.paint`, which asks the sheet
  (`Sheet.spill_edges`) which region borders pass through each painted cell and
  strokes only those edges — so the outline virtualizes with the grid.
- If you try to **edit into a spilled cell**, or something already occupies the
  target region, the anchor renders `#SPILL!` (the array can't lay itself out).

See the [Formula reference](formula-reference.md) for the dynamic-array
functions and the `A1#` spilled-range reference syntax.

## Conditional formatting

*Format → Conditional format…* opens a dialog where you define rules that colour
cell backgrounds based on their values (including colour-scale rules). Rules are
stored **per sheet** and saved in the workbook, so they travel with the file.
The grid evaluates them **lazily, per painted cell, and caches the result** for
the current refresh — so even a rule spanning tens of thousands of cells is
cheap, because only the cells actually on screen are ever coloured. Only a
colour-scale rule triggers a range scan (to find its min/max). Text on a
conditional fill is drawn dark for readability. Clear them with *Format → Clear
conditional formats*.

## Cell styles and number formats

Select cells, then apply styles from the **Format** menu, the toolbar, or the
right-click menu:

| Action | Shortcut |
| --- | --- |
| Bold | `Ctrl+B` |
| Italic | `Ctrl+I` |
| Underline | `Ctrl+U` |
| Align left / center / right | *Format → Align* |
| Text colour | *Format → Text colour…* |
| Fill colour | *Format → Fill colour…* |
| Clear cell styles | *Format → Clear cell styles* |

Toggling a boolean style (bold/italic/underline) turns it **on** for the whole
selection if any cell lacks it, otherwise **off** — so the toggle is
predictable across a mixed selection.

**Number formats** live under *Format → Number* (a list of presets — General,
Integer, Currency, Percent, Scientific, and more, from
`core.format.cellformat.FORMATS`). Choosing "General" clears the per-cell
format. Formats are stored per cell and applied only when the value is
displayed, so the underlying number is never changed.

## Freeze panes

*View → Freeze panes* keeps header rows or columns pinned while you scroll:

- **Freeze panes (at cursor)** — freeze every row above and column left of the
  active cell.
- **Freeze top row**.
- **Freeze first column**.
- **Unfreeze**.

Frozen panes are drawn as scroll-synced mirror overlays that **share the main
grid's model and selection** (`abax/gui/grid/frozen_panes.py`), so they
virtualize exactly like the main view — no per-cell widgets, and the selection
shows through the frozen strips.

## Sheet tabs

Each sheet gets a coloured tab at the bottom of the window:

- **Add** — click the `+` button, or *Sheet → New sheet* (`Shift+F11`).
- **Rename** — double-click a tab, or *Sheet → Rename sheet…*.
- **Reorder** — drag a tab; the workbook's sheet order follows.
- **Duplicate / delete** — right-click a tab, or use the *Sheet* menu.

Right-clicking a tab opens a menu with New / Rename / Duplicate / Delete. Move
between sheets with `Ctrl+PgDown` (next) and `Ctrl+PgUp` (previous). The active
sheet's name appears in the window title when a workbook has more than one
sheet. Deleting a sheet is confirmed, and a workbook always keeps at least one
sheet.

## Themes, zoom, and fonts

abax ships several built-in themes under *Format → Theme*: Obsidian, Dark One,
Nord, Solarized, CRT green, CRT amber, Light, and High contrast. Pick one
directly from the submenu, or open the chooser (with a live preview) via `Ctrl+T`
(*Format → Choose theme…*). Your choice is remembered in settings.

**Zoom** scales the whole UI font under the *View* menu:

| Action | Shortcut |
| --- | --- |
| Zoom in | `Ctrl+=` |
| Zoom out | `Ctrl+-` |
| Reset zoom | `Ctrl+0` |

Zoom is clamped to 0.5×–3.0× and persisted; it's applied as a stylesheet layer
over the theme so it survives theme changes.

There's also an optional **OpenDyslexic** font toggle (*View → Toggle
OpenDyslexic font*), fetched and cached on first use (it degrades gracefully
when offline). When on, the family is pushed across menus, dialogs, lists, the
console/terminal, and the cells (via the model's FontRole) — deliberately not
the QPainter calculator faceplates, so the LCD/keypad keep their display fonts.

## Formula precedents

With a formula cell active, press `Ctrl+[` (*View → Show formula precedents*) to
highlight every cell the formula reads from. It's a quick way to trace where a
result comes from. If the cell isn't a formula with references, the status bar
says so.

## Recalculation

Recalculation is **automatic**. Cell values are computed on demand and memoized,
and any edit clears the value cache so every dependent recomputes — including
dependents that live on other sheets (cross-sheet refs invalidate every sheet's
cache). You never have to trigger a recompute after typing a value or a formula.

When you want to force a full pass anyway — for example after loading data, or to
re-roll volatile functions like `RAND` / `NOW` — *Data → Recalculate* (`F9`)
recomputes every formula in the workbook and refreshes the grid, and the status
bar confirms with `recalculated`.

## Undo / redo

| Action | Shortcut |
| --- | --- |
| Undo | `Ctrl+Z` |
| Redo | `Ctrl+Y` |
| Undo history… | `Ctrl+Shift+Z` |

Edits, fills, pastes, sorts, styling, validation, name definitions, and
calculator writes are all undoable, and edits coalesce sensibly (rapid typing
into one cell collapses to one checkpoint). The **Undo history** dialog shows the
timeline of checkpoints so you can jump back several steps at once. (Note:
deleting a sheet is *not* reversible with `Ctrl+Z`, and is confirmed before it
happens.)

## Copy / paste / fill / sort

| Action | Shortcut |
| --- | --- |
| Cut | `Ctrl+X` |
| Copy | `Ctrl+C` |
| Paste | `Ctrl+V` |
| Fill down | `Ctrl+D` |
| Fill right | `Ctrl+R` |
| Fill series | *Edit → Fill series* |

- **Copy** puts the values on the system clipboard as TSV (so you can paste into
  other apps) and keeps a richer internal clip for in-app paste.
- **Paste** of an internal clip shifts relative references by default
  (formula-aware); pasting plain text from another app is verbatim.
- **Fill series** continues numeric, date, weekday, and month-name progressions
  (gnumeric-style autofill).
- **Sort** is available from *Data → Sort…* (a multi-column dialog), the quick
  *Sort ascending / descending* items, and by right-clicking a column header.
  Sorting carries each row's per-cell styles and number formats along with its
  values. A single-cell selection auto-expands to the surrounding data region
  before sorting.
- *Tools → Copy selection as Markdown* (also in the right-click menu) copies the
  selection as a GFM table onto the clipboard and into the copy history.

## Right-click context menu

Right-click any cell (or selection) for a context menu wired to the same actions
as the menu bar — built for quick, keyboard-light editing. Right-clicking a cell
*outside* the current selection first moves to it (so Paste / Clear / Format
target where you clicked); right-clicking *inside* a multi-cell selection keeps
it. The menu offers:

- **Clipboard** — Cut / Copy / Paste, and *Copy as Markdown*.
- **Insert / Delete** — rows above/below, columns left/right, delete
  row(s)/column(s).
- **Clear contents**.
- **Format** — Bold / Italic / Underline, text & fill colour, clear styles.
- **Number format** — the full General / Integer / Currency / Percent /
  Scientific / … list.
- **Conditional format…**
- **Data** — Sort ascending/descending, Fill series, *Recode / clean…*, and
  *Open selection in pandas…*.

The row- and column-header right-click menus add header-specific actions: insert
above/below (rows) or left/right (columns), delete, and — on a column header —
sort ascending/descending by that column and open the filter dialog.

## Clipboard history

`Ctrl+Shift+V` (also *View → Clipboard history*) opens the copy history as a
searchable `rofi`/`dmenu`-style palette: type to fuzzy-filter past copies, press
`Enter` to paste the chosen fragment at the cursor (pinned entries are listed
first, marked 📌). To pin, remove, clear, or copy an entry back to the system
clipboard, use *View → Manage clipboard…*.

## Data validation and named ranges

*Data → Data validation…* attaches a validation rule to the selected cells.
List-type rules turn the in-cell editor into a dropdown of the allowed values
(you can still type a value, which is checked on commit). Invalid entries are
rejected with a warning and the edit is discarded.

Manage names from *Data → Name range…* (names the current cell or selection —
`Ctrl+N`-style prompt) and *Data → Name manager…* (list defined names, jump to
them, or delete them). Defined names are offered by formula autocomplete.

## Async open / save and the progress bar

Opening and saving run on a **background thread** so a large file never freezes
the window. While I/O is in flight:

- the grid and formula bar are disabled,
- the cursor shows the busy/wait shape, and
- a compact **progress bar** appears at the right of the status bar.

Save takes an independent snapshot of the workbook (rebuilt from its raw-text
envelope) so the saver thread never races the UI thread's compute caches. The UI
is restored automatically when the operation finishes, and errors are reported in
a dialog. Only one open/save runs at a time. Settings are also autosaved every 30
seconds, and window state is flushed on close (and on any uncaught error).

Import paths:

- *File → Import large CSV…* streams a huge CSV with type inference; if it sniffs
  more than ~50,000 rows it offers an optional row cap.
- *File → Import from URL…* downloads a data file (CSV, JSON, Excel, Parquet, …)
  off the UI thread and opens it, guessing the format from the URL / content type.

Supported formats include CSV/TSV, Excel `.xlsx`, LibreOffice `.ods`,
Parquet/Feather, XML Spreadsheet, Markdown, Jupyter `.ipynb`, R, SQLite, ADIF
amateur-radio logbooks (`.adi`/`.adif`), and native `.abax`/JSON. *File → Export
as HTML report…* writes the whole workbook to a standalone HTML page. (Some
formats require optional dependencies — run `python -m abax --deps` to see what's
installed.) The full list of what each format keeps is in
[File formats](file-formats.md).

## Command palette

Press `Ctrl+Shift+P` — or just type `:` on the grid (gnumeric/vim feel) — to
open the command palette: a floating, `rofi`/`dmenu`-style panel with a search
box above a live-filtered list of **every** action — file operations,
formatting, sheet management, the calculators, analysis tools, macros, and more.
Loaded macros appear as `Macro: <name>` entries.

Start typing to fuzzy-match (characters match in order, so `pgb` finds
"Pivot / group-by"); the best matches rise to the top. It's fully keyboard-driven:
**↑/↓** (and **PageUp/PageDown**) move the highlight while your cursor stays in
the search box, **Enter** runs the highlighted command, and **Esc** closes the
palette. A double-click also runs a command. (The chosen command runs after the
palette closes, so any dialog it opens doesn't fight the palette for focus.)

The **keyboard-shortcuts palette** (`F1`, *Help → Keyboard shortcuts*) reuses
the same UI but lists only actions that have a shortcut, generated live from the
menus — so it's always accurate to your build. Type to filter by action name or
key, and Enter runs the highlighted action.

## The docks: calculator, Python console, terminal

Three panels dock around the grid (movable, floatable, closable). None open on
launch.

- **Calculator** (`Ctrl+K`, *View → Calculator*) — a floating window hosting the
  RPN / scientific / financial / graphing / algebraic calculators. It exchanges
  values with the grid: *Get cell value → calculator* (`Ctrl+Shift+G`) loads the
  active numeric cell, and *Send calculator value → cell* (`Ctrl+Shift+H`) writes
  the calculator's current value into every selected cell (undoable). Its
  faceplate art folder is set under *Tools → Calculator faceplates → Set image
  folder…*. See [Calculators](calculators.md) for the key-by-key details.
- **Python console** (`Ctrl+Shift+Y`, *View → Python console*) — an embedded REPL.
  By default (the `isolated` level) its user code runs **out-of-process** (a
  subprocess on a background thread), so a crash, hang, or runaway there never
  freezes the GUI, and a runaway can be interrupted (which kills the worker; the
  next command respawns it). The live workbook is shipped to the worker and back
  as a JSON envelope each command. Its namespace includes `doc`, `wb`, `sheet()`,
  `cell(ref)`, `put(ref, val)`, `refresh()`, `rpn`, and the engineering /
  data-science toolkits when installed; Tab-completes those plus Python keywords
  and builtins. The console's title bar shows the active **code-isolation level**
  (in-process / isolated / strict) — cycle it from the command palette.
- **Terminal** (`` Ctrl+` ``, *View → Terminal*) — a dockable shell. It prefers a
  **true PTY** terminal (ConPTY on Windows, `pty` on POSIX) that renders a real
  `pyte` screen with full colour/SGR styling — interactive full-screen programs
  (vim, top, less) work — and falls back to a line-oriented terminal when a PTY
  backend isn't available.

The console and terminal both run **arbitrary code with your full privileges**,
so the first time you open either one abax shows a one-time **consent gate**
("Run untrusted code?"). Approving is remembered in settings. How isolated that
code is depends on the **code-isolation level** (command palette → *Cycle code
isolation*): `off` runs it in-process (no isolation), `isolated` (default) uses
the out-of-process, resource-limited worker (crash/resource isolation, not a
security boundary), and `strict` OS-confines the worker (no network, writes to a
scratch dir only) and refuses to run if that confinement can't be established.
For untrusted code, use `strict` or a throwaway VM/container. See
[Macros & scripting](macros-and-scripting.md) for the full description.

*View → Open default workspace* lays out the everyday arrangement in one click:
the spreadsheet upper-left, a floating calculator, and the Python console
(bottom-left) beside the terminal (bottom-right), split 50/50.

## Menu bar reference

The full menu bar, organised the standard desktop way (labels are exactly as in
`abax/gui/main_window.py`):

- **File** — New (`Ctrl+N`), Open (`Ctrl+O`), Import large CSV, Import from URL,
  Save (`Ctrl+S`), Save As (`Ctrl+Shift+S`), Export as HTML report, Quit
  (`Ctrl+Q`).
- **Edit** — Undo (`Ctrl+Z`), Redo (`Ctrl+Y`), Undo history (`Ctrl+Shift+Z`),
  Cut (`Ctrl+X`), Copy (`Ctrl+C`), Paste (`Ctrl+V`), Clear (Del), Fill Down
  (`Ctrl+D`), Fill Right (`Ctrl+R`), Fill series, Find / Replace (`Ctrl+F`), Go
  to (`Ctrl+G`), Command Palette (`Ctrl+Shift+P`).
- **View** — Freeze panes (at cursor / top row / first column / unfreeze),
  Calculator (`Ctrl+K`), Get/Send calculator value (`Ctrl+Shift+G` /
  `Ctrl+Shift+H`), Terminal (`` Ctrl+` ``), Python console (`Ctrl+Shift+Y`),
  Clipboard history (`Ctrl+Shift+V`), Manage clipboard, Open default workspace,
  Show toolbar, Show formula precedents (`Ctrl+[`), Toggle vim mode, Toggle
  OpenDyslexic font, Zoom in (`Ctrl+=`), Zoom out (`Ctrl+-`), Reset zoom
  (`Ctrl+0`).
- **Insert** — Rows / columns (row above `Ctrl++`, row below, column left, column
  right, append row/column, delete row(s) `Ctrl+-`, delete column(s)), Function
  (`Shift+F3`), Equation, Chart / graph, Export chart as SVG.
- **Format** — Bold (`Ctrl+B`), Italic (`Ctrl+I`), Underline (`Ctrl+U`), Align
  (left/center/right), Text colour, Fill colour, Clear cell styles, Number
  (preset list), Conditional format, Clear conditional formats, Theme (submenu),
  Choose theme (`Ctrl+T`).
- **Data** — Sort, Sort ascending, Sort descending, Filter, Clear filter, Name
  range, Name manager, Data validation, Compare workbook, Recalculate (`F9`),
  Analyze → (Statistics / analysis, SQL query, Profile columns, Open selection in
  pandas, Recode / clean column, Pivot / group-by, Goal seek).
- **Sheet** — New sheet (`Shift+F11`), Duplicate sheet, Rename sheet, Delete
  sheet, Next sheet (`Ctrl+PgDown`), Previous sheet (`Ctrl+PgUp`).
- **Tools** — Scientific → (Matrix tool, Numerical solver, Signal / data tool,
  ODE solver, ML tool), Install optional features now, Budget wizard, File
  manager (`Ctrl+Shift+F`), Macros (submenu), Recording (start/stop, relative,
  save, replay), Load macro / UDF file, Run Python script, **Code isolation
  (sandbox)** → (Off / Isolated / Strict), **Radio** → (RF toolkit, Smith chart,
  Antenna pattern, RF reference (bands / CTCSS), I/Q constellation → SVG, Solve
  NEC deck (PyNEC)), Calculator faceplates, Copy selection as Markdown.
- **Help** — Keyboard shortcuts (`F1`), About abax.

Press `F1` any time for the full, live shortcut list (it's generated from the
menus, so it's always accurate to your build).

## Dialog reference

Every dialog listed here is confirmed against `abax/gui/dialogs/` and the menu
that opens it. The heavy analysis dialogs are covered in depth in the sibling
docs — this is the one-line "what it does" index.

**Data / analysis** (see [Data analysis](data-analysis.md) and
[Data science](data-science.md)):

- **Statistics / analysis** (*Data → Analyze*) — run a statistical test over
  selected columns and show the results.
- **SQL over sheets** (*Data → Analyze → SQL query*) — run SQL against the
  workbook's sheets and view the result set.
- **Profile columns** (*Data → Analyze*) — write a per-column profile (dtype,
  count, missing, unique, min/max/mean/median/std) to a new *Profile* sheet.
- **DataFrame viewer (pandas)** (*Data → Analyze → Open selection in pandas*) —
  open the selected range as a typed pandas DataFrame.
- **Recode / clean column** (*Data → Analyze*) — retype, fill blanks, normalize,
  map, clip, and similar column-cleaning transforms.
- **Pivot / group-by** (*Data → Analyze*) — summarise a table with
  `abax.core.pivot`.
- **Goal Seek** (*Data → Analyze*) — find the input-cell value that makes a
  target cell equal a chosen value.
- **Sort** and **Filter** (*Data*) — multi-column sort; multi-condition column
  filter that hides rows failing *all* conditions.
- **Name manager** and **Data validation** (*Data*) — as described above.

**Insert / objects:**

- **Function browser** (*Insert → Function*, `Shift+F3`) — searchable list of all
  functions (built-ins + UDFs).
- **Equation editor** (*Insert → Equation*) — LaTeX in, live Unicode preview,
  MathML out.
- **Graph** (*Insert → Chart / graph*) — an HP-48-flavored function grapher,
  painted with QPainter (line/scatter/histogram, regression overlay); *Export
  chart as SVG* writes the current selection to an SVG file.

**Scientific** (*Tools → Scientific*):

- **Matrix tool** — apply a matrix operation over grid ranges.
- **Numerical solver** — root-find / integrate / differentiate an expression
  `f(x)`.
- **Signal / data tool** — apply a DSP operation over a column of samples.
- **ODE solver** — integrate `dy/dt = f(t, y)` and write `t, y` columns.
- **ML tool** — PCA, k-means clustering, and regression over a data matrix.

**Radio / RF** (*Radio*; see [RF toolkit](rf-toolkit.md)):

- **RF toolkit** — link budget, coax line, antenna dimensions, and L-network
  matching.
- **Smith chart** — plot a load impedance, its reflection coefficient, and a
  matching path.
- **Antenna pattern** — a QPainter polar plot of the analytic patterns.
- **RF reference (bands & CTCSS)** — the US amateur band plan and standard CTCSS
  tones; non-modal, so it can send values into the grid (double-click / Send)
  while you keep working, like the calculator.
- **I/Q constellation → SVG** — read a two-column (I, Q) selection and export the
  constellation as SVG.
- **Solve NEC deck (PyNEC)** — solve a NEC deck with PyNEC when installed (the
  built-in method-of-moments solver works without it).

**Tools / utilities:**

- **Install optional features** (*Tools → Install optional features now*; also the
  first-run chooser) — pick Thin / All / custom optional dependencies.
- **Budget setup wizard** (*Tools → Budget wizard*) — collect income and
  categories, then drop in a live budget sheet (see [Budgeting](budgeting.md)).
- **File manager** (*Tools → File manager*, `Ctrl+Shift+F`) — a dual-pane,
  Directory-Opus/Worker-style browser with F-key command buttons (see
  [File manager](file-manager.md)).
- **Optional-feature chooser**, **Clipboard history manager**, **Undo history**,
  and **Theme** — as described in their sections above.

Workbook diff lives at *Data → Compare workbook*: it diffs the current workbook
against another file and writes the changes into a new *Diff* sheet.

---

License: GPL-3.0-or-later.
