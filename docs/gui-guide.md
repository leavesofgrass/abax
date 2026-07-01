# Desktop GUI guide

abax's Qt desktop app is keyboard-first: you can drive almost everything from
the grid, the formula bar, and the command palette without reaching for the
mouse. This guide covers day-to-day use of the window — navigation, editing,
formatting, sheets, and the menu bar.

Launch it with:

    python -m abax gui data.csv

The default Qt binding is **PySide6** (PyQt6 also works; bindings are isolated
in one place so the rest of the app is unchanged).

New to abax? Start with [Getting started](getting-started.md). For the formula
language, see the [Formula reference](formula-reference.md). For paths, themes,
and persisted options, see [Configuration](configuration.md). For the built-in
calculators, see [Calculators](calculators.md). The docs index is
[here](index.md).

## The window at a glance

From top to bottom:

- **Menu bar** — File, Edit, View, Insert, Format, Data, Sheet, Tools, Help.
- **Toolbar** — icon shortcuts for the common actions (toggle with
  *View → Show toolbar*).
- **Formula bar** — shows and edits the active cell's raw value or formula.
- **Grid** — the virtualized cell grid.
- **Sheet tabs** — one coloured tab per sheet, with a `+` button to add one.
- **Status bar** — the active cell's address, selection aggregates, and a
  progress bar during file I/O.

## The virtualized grid

The grid renders only the cells currently in view, so even very large files
scroll smoothly — no widget is created per cell. The grid starts with a
generous extent (a 200×26 minimum plus headroom past your data) and **grows on
demand**: scroll to the bottom or right edge and more rows/columns appear
automatically. You can also add space deliberately with *Insert → Rows /
columns → Append row (end)* / *Append column (end)*.

A cell shows its **computed value**; when you start editing, the editor seeds
with the **raw text** (the formula), not the result.

## Keyboard navigation (Excel-style)

The grid uses the navigation muscle-memory you already have from Excel:

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

Double-clicking a cell also opens the in-place editor, and you can pick the
allowed value from a dropdown when the cell has list-style data validation.

`Ctrl+Arrow` is the classic "jump to the edge of the data block" move: from
inside a filled region it lands on the last non-blank cell before a gap; from a
blank cell it jumps to the next filled one.

## Vim navigation (on by default)

Vim-style movement is enabled out of the box (`settings.vim_mode = True`). When
you are **not** editing a cell:

| Key | Action |
| --- | --- |
| `j` / `k` | Move down / up |
| `h` / `l` | Move left / right |
| `g` / `G` | Jump to the top / bottom row |
| `/` | Focus the formula bar (search/entry) |
| `Esc` | Return focus to the grid |

Vim keys work alongside the arrow keys and the mouse — they never replace them.
Turn the mode off any time with *View → Toggle vim mode* (or the command
palette). When vim mode is off, those letters type into the cell as usual.

## The formula bar

Click into the formula bar (or press `/` in vim mode) to edit the active cell's
contents. Type a literal value or a formula beginning with `=`, then press
`Enter` to commit. As in Excel, **Enter in the formula bar commits and advances
the selection one row down** — even if you didn't change the value — so you can
key down a column quickly.

While you type a formula, an **argument hint** tooltip appears under the bar,
showing the current function's signature with the active parameter in bold, plus
a function-name autocomplete.

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
- Selecting an enormous range (e.g. a whole column) shows the cell count
  instead of scanning every cell, so the readout never stalls.

## Find and replace

Open with `Ctrl+F` (*Edit → Find / Replace*). The dialog supports regular
expressions and find/replace-all over the sheet. The grid also has a quick
*Go to* jump (`Ctrl+G`) that accepts a cell or range like `B12` or `A1:C9`.

## Conditional formatting

*Format → Conditional format…* opens a dialog where you define rules that colour
cell backgrounds based on their values. Rules are stored **per sheet** and saved
in the workbook, so they travel with the file. The grid applies the fills lazily
as cells paint (so even large rule ranges are cheap). Clear them with *Format →
Clear conditional formats*.

## Cell styles and number formats

Select cells, then apply styles from the **Format** menu or the toolbar:

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

**Number formats** live under *Format → Number* (a list of presets). Choosing
"General" clears the per-cell format. Formats are stored per cell and applied
when the value is displayed, so the underlying number is never changed.

## Freeze panes

*View → Freeze panes* keeps header rows or columns pinned while you scroll:

- **Freeze panes (at cursor)** — freeze every row above and column left of the
  active cell.
- **Freeze top row**.
- **Freeze first column**.
- **Unfreeze**.

Frozen panes are drawn as scroll-synced overlays on top of the grid, so they
virtualize exactly like the main view.

## Sheet tabs

Each sheet gets a coloured tab at the bottom of the window:

- **Add** — click the `+` button, or *Sheet → New sheet* (`Shift+F11`).
- **Rename** — double-click a tab, or *Sheet → Rename sheet…*.
- **Reorder** — drag a tab; the workbook's sheet order follows.
- **Duplicate / delete** — right-click a tab, or use the *Sheet* menu.

Right-clicking a tab opens a menu with New / Rename / Duplicate / Delete. Move
between sheets with `Ctrl+PgDown` (next) and `Ctrl+PgUp` (previous). The active
sheet's name appears in the window title when a workbook has more than one
sheet. Deleting a sheet is confirmed and a workbook always keeps at least one
sheet.

## Themes

abax ships several built-in themes under *Format → Theme*: Obsidian, Dark One,
Nord, Solarized, CRT green, CRT amber, Light, and High contrast. Pick one
directly from the submenu, or open the chooser with `Ctrl+T` (*Format → Choose
theme…*). Your choice is remembered in settings. There's also an optional
**OpenDyslexic** font toggle (*View → Toggle OpenDyslexic font*), fetched and
cached on first use (it degrades gracefully when offline).

## Formula precedents

With a formula cell active, press `Ctrl+[` (*View → Show formula precedents*) to
highlight every cell the formula reads from. It's a quick way to trace where a
result comes from. If the cell isn't a formula with references, the status bar
says so.

## Undo / redo

| Action | Shortcut |
| --- | --- |
| Undo | `Ctrl+Z` |
| Redo | `Ctrl+Y` |
| Undo history… | `Ctrl+Shift+Z` |

Edits, fills, pastes, sorts, styling, validation, and calculator writes are all
undoable. The **Undo history** dialog lists the checkpoints so you can jump back
several steps at once. (Note: deleting a sheet is *not* reversible with
`Ctrl+Z`, and is confirmed before it happens.)

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
- **Sort** is available from *Data → Sort…*, the quick *Sort ascending /
  descending* items, and by right-clicking a column header. *Tools → Copy
  selection as Markdown* copies the selection as a GFM table.

## Right-click context menu

Right-click any cell (or selection) for a context menu wired to the same actions
as the menu bar — built for quick, keyboard-light editing:

- **Clipboard** — Cut / Copy / Paste, and *Copy as Markdown*.
- **Insert / Delete** — rows above/below, columns left/right, delete row(s)/column(s).
- **Clear contents**.
- **Format** — Bold / Italic / Underline, text & fill colour, clear styles.
- **Number format** — the full General / Integer / Currency / Percent / Scientific / … list.
- **Conditional format…**
- **Data** — Sort ascending/descending, Fill series, *Recode / clean…*, and
  *Open selection in pandas…*.

## Clipboard history

`Ctrl+Shift+V` (also *View → Clipboard history*) opens the copy history as a
searchable `rofi`/`dmenu`-style palette: type to fuzzy-filter past copies, press
`Enter` to paste the chosen fragment at the cursor (pinned entries are listed
first). To pin, remove, or clear entries, use *View → Manage clipboard…*.

## Data validation

*Data → Data validation…* attaches a validation rule to the selected cells.
List-type rules turn the in-cell editor into a dropdown of the allowed values
(you can still type a value, which is checked on commit). Invalid entries are
rejected with a warning and the edit is discarded. Manage named ranges from
*Data → Name range…* and *Data → Name manager…*.

## Async open / save and the progress bar

Opening and saving run on a **background thread** so a large file never freezes
the window. While I/O is in flight:

- the grid and formula bar are disabled,
- the cursor shows the busy/wait shape, and
- a compact **progress bar** appears at the right of the status bar.

The UI is restored automatically when the operation finishes, and errors are
reported in a dialog. Only one open/save runs at a time. Settings are also
autosaved every 30 seconds. *File → Import large CSV…* streams a huge CSV with
type inference and an optional row cap.

Supported formats include CSV/TSV, Excel `.xlsx`, LibreOffice `.ods`,
Parquet/Feather, XML Spreadsheet, Markdown, Jupyter `.ipynb`, R, and native
`.abax`/JSON. (Some formats require optional dependencies — run
`python -m abax --deps` to see what's installed.)

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
palette. A double-click also runs a command.

## Menu bar reference

The full menu bar, organised the standard desktop way:

- **File** — New (`Ctrl+N`), Open (`Ctrl+O`), Import large CSV, Save
  (`Ctrl+S`), Save As (`Ctrl+Shift+S`), Quit (`Ctrl+Q`).
- **Edit** — Undo/Redo, Undo history, Cut/Copy/Paste, Clear, Fill
  Down/Right/series, Find/Replace (`Ctrl+F`), Go to (`Ctrl+G`), Command palette
  (`Ctrl+Shift+P`).
- **View** — Freeze panes, Calculator (`Ctrl+K`), get/send calculator value
  (`Ctrl+Shift+G` / `Ctrl+Shift+H`), Terminal (`` Ctrl+` ``), Python console
  (`Ctrl+Shift+Y`), Clipboard history (`Ctrl+Shift+V`), Show toolbar, Show
  formula precedents (`Ctrl+[`), Toggle vim mode, Toggle OpenDyslexic font.
- **Insert** — Rows/columns (insert/append/delete; `Ctrl++`, `Ctrl+-`),
  Function (`Shift+F3`), Equation, Chart/graph.
- **Format** — Bold/Italic/Underline, Align, Text/Fill colour, Clear styles,
  Number formats, Conditional format, Theme, Choose theme (`Ctrl+T`).
- **Data** — Sort, Sort ascending/descending, Filter, Name range, Name manager,
  Data validation, Recalculate (`F9`), Analyze (statistics, pandas, recode,
  pivot, graph).
- **Sheet** — New (`Shift+F11`), Duplicate, Rename, Delete, Next
  (`Ctrl+PgDown`), Previous (`Ctrl+PgUp`).
- **Tools** — Scientific (matrix, solver, signal, ODE, ML, and the **RF toolkit /
  Smith chart / Antenna pattern** — see [rf-toolkit.md](rf-toolkit.md)), **File
  manager** (`Ctrl+Shift+F`, see [file-manager.md](file-manager.md)), **Budget
  wizard** (see [budgeting.md](budgeting.md)), **Install optional features now**,
  Macros, Recording, Load macro/UDF file, Run Python script, Calculator faceplates,
  Copy selection as Markdown.
- **Help** — Keyboard shortcuts (`F1`), About abax.

Press `F1` any time for the full, live shortcut list (it's generated from the
menus, so it's always accurate to your build).

---

License: GPL-3.0-or-later.
