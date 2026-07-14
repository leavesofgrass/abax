# File formats

abax is JSON-first but reads and writes many tabular formats. Every open and
save is dispatched purely by **file extension** in
[`abax/engine/document.py`](https://github.com/leavesofgrass/abax/blob/main/abax/engine/document.py) — the single façade the
GUI, TUI, and CLI all call. This page lists every supported format, what import
and export actually do, and which formats need an optional dependency.

See also: [index](index.md) · [formula reference](formula-reference.md) ·
[command-line interface](cli.md) ·
[CSV clean & export example](examples/data/csv-clean-and-export/README.md).

## At a glance

| Format | Extensions | Read | Write | Optional dep | Fallback when absent |
| --- | --- | :---: | :---: | --- | --- |
| Native workbook | `.json` `.abax` | yes | yes | — (stdlib `json`) | always available |
| ADIF logbook | `.adi` `.adif` | yes | yes | — | always available |
| CSV | `.csv` | yes | yes | — | always available |
| Excel | `.xlsx` `.xlsm` | yes | yes | `openpyxl` | error with install hint |
| Feather | `.feather` `.ft` | yes | yes | `pandas` + `pyarrow`/`fastparquet` | error with install hint |
| Fixed-width | `.fixed` | yes | yes | — | always available |
| HDF5 | `.h5` `.hdf5` | yes | no | `h5py` (`abax[hdf5]`) | error with install hint |
| JSON Lines | `.jsonl` `.ndjson` | yes | yes | — | always available |
| Jupyter notebook | `.ipynb` | yes | yes | — (no `nbformat` needed) | always available |
| Markdown (GFM) | `.md` `.markdown` | yes | yes | — | always available |
| OpenDocument | `.ods` | yes | yes | — (stdlib `zipfile`+`xml`) | always available |
| Parquet | `.parquet` `.pq` | yes | yes | `pandas` + `pyarrow`/`fastparquet` | error with install hint |
| R data.frame | `.r` `.rdata` | yes | yes | — | always available |
| SQLite | `.db` `.sqlite` `.sqlite3` | yes | yes | — (stdlib `sqlite3`) | always available |
| Stata / SPSS | `.dta` `.sav` `.zsav` `.por` | yes | no | `pyreadstat` (`abax[stats-io]`) | error with install hint |
| TSV / tab | `.tsv` `.tab` | yes | yes | — | always available |
| XML Spreadsheet | `.xml` | yes | yes | — | always available |
| 7-Zip archive | `.7z` | yes | yes | `py7zr` (`abax[sevenzip]`) | `.zip`/`.tar` still work; 7z shows a hint |

**Excel**, **Parquet/Feather**, **Stata/SPSS**, **HDF5**, and **7-Zip** each need
an optional package (see the table's *Optional dep* column); everything else is
pure standard library and works in a zero-optional-dependency install.
Run `python -m abax --deps` to see what is installed on your machine.

## A shared data model

Whatever the source format, importing produces the same in-memory model: a
`Workbook` of one or more `Sheet`s, where each cell holds **raw text**. A field
that begins with `=` becomes a formula and is re-evaluated by abax's own engine
(see the [formula reference](formula-reference.md)); everything else is a literal
value. Single-sheet formats (CSV, Markdown, JSON Lines, fixed-width, Parquet)
load into a one-sheet workbook; multi-sheet formats (native JSON, Excel, XML,
notebooks, R, SQLite) preserve every sheet/table.

On export, most formats write **computed values** by default (what you see in the
grid), while a few write **raw text** so formulas survive a round-trip — see each
format below.

## Converting files

Beyond opening and saving, abax has a **batch file-conversion tool** for turning
files from one format into another — including **non-tabular documents**. It has
two backends, chosen automatically by extension:

- **Tabular data** (CSV/TSV, Excel, ODS, Parquet, JSON, Markdown tables) is
  converted by abax's own workbook engine — no extra software needed.
- **Documents** (Markdown ↔ **Word `.docx`**, **HTML**, **reStructuredText**,
  **LaTeX**, **EPUB**, **RTF**, **plain text**, and **PDF**) go through
  [**pandoc**](https://pandoc.org/), an optional dependency. If pandoc isn't
  installed, a document conversion reports a clear message; install it from
  *Tools → Install optional features* (or `pip install pypandoc_binary`). PDF
  output additionally needs a LaTeX engine on your system.

**Two ways in:**

- **Tools → Convert files…** opens the dialog directly. Click *Add files…* to
  choose one or many inputs, pick a **Convert to** format, set an **Output
  folder** (defaults to the inputs' folder), and click **Convert**. Each file's
  result — success or the reason it failed — is listed, and one bad file never
  stops the rest.
- **File manager → Convert** ([File manager](file-manager.md)) opens the same
  dialog **pre-filled with the files you've selected**, so you can convert
  straight from the browser.

Examples: turn a folder of `.csv` exports into `.xlsx`; convert a `.md` report to
`.docx` or `.html`; flatten `.docx` notes to plain Markdown; or produce a `.pdf`
from Markdown (with a LaTeX engine installed).

## Native workbook (`.json` / `.abax`)

abax's own format is a self-describing JSON **envelope** produced by
`Workbook.to_envelope` ([`abax/core/workbook.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/workbook.py)):

```json
{
  "app": "abax",
  "schema_version": 2,
  "written_at": "2026-06-29T12:00:00+00:00",
  "data": {
    "active": 0,
    "names": { },
    "sheets": [
      {
        "name": "Sheet1",
        "cells": { "A1": "Item", "B1": "Price", "B2": "=A2*1.1" },
        "cond_rules": [],
        "formats": {},
        "styles": {},
        "comments": {},
        "validations": []
      }
    ]
  }
}
```

This is fully lossless: cell text and formulas, multiple sheets, the active
sheet, named ranges, conditional-formatting rules, per-cell number formats,
styles, comments, and data validations are all preserved. `schema_version` lets
older files migrate forward on load.

### View fidelity (schema v2)

The envelope is now **schema v2** and additionally preserves a sheet's **view
fidelity** — the layout you set up, not just its data. Each sheet may carry:

- `col_widths` / `row_heights` — non-default column and row sizes (sparse, keyed
  by index).
- `frozen` — `[rows, cols]`, the frozen top rows and left columns.
- `borders` — per-cell borders, keyed by A1, as `{edge: style}` maps.
- `merges` — merged regions as a list of `"A1:B2"` ranges.

These keys are **omitted whenever they are empty**, so a plain grid's file is
byte-for-byte what abax wrote before — the new keys appear only once you actually
set a width, freeze a pane, draw a border, or merge cells. They also survive
row/column insert and delete: sizes shift along their axis, borders relocate like
any per-cell attribute, and merged regions move like a range (dropped if wholly
deleted or collapsed to a single cell).

The change is **backward-compatible in both directions**. Older (schema v1) files
have none of these keys and load unchanged: `from_envelope` reads each with a
default, so a v1 file simply comes back with no custom widths, freezes, borders,
or merges. The migration is a bare version-label bump — no data transform — so
nothing in an older file is rewritten or lost.

### `.json` auto-detects native vs foreign

A `.json` (or `.abax`) file is opened through
[`abax/core/io/exchange_io.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/io/exchange_io.py), which inspects the
payload shape and does the right thing:

- **abax workbook envelope** (`data.sheets` present) → loaded losslessly.
- **qrpn calculator save** (`{stack, registers}`) → a `stack` sheet plus a
  `registers` key/value sheet.
- **list of objects** (records) → one row per object; keys become the header row.
- **list of lists** → rows verbatim.
- **dict of equal-length lists** → columns (keys become headers).
- **dict of scalars** → a two-column `key` / `value` sheet.

This means you can drop almost any JSON another tool wrote into abax and get a
sensible table back.

### The generic interchange envelope

The spec's "JSON everywhere" principle (§3e) is the shape

```json
{ "app": "<producer>", "schema_version": <int>, "written_at": "<iso8601>", "data": <payload> }
```

Any tool can write this; abax reads it by examining `data`. `app` is used as a
hint (for example an `app` containing `qrpn` is treated as a calculator save).
abax's own `to_exchange` simply returns the workbook envelope above — so abax's
native files *are* valid interchange envelopes.

## CSV / TSV / tab (`.csv`, `.tsv`, `.tab`)

Implemented in [`abax/core/io/csv_io.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/io/csv_io.py) on the stdlib
`csv` module. Import places each field as raw cell text (a field starting with
`=` becomes a formula); empty fields are skipped. `.tsv`/`.tab` use a tab
delimiter. Export writes **computed values** by default (`values=True`); the API
can also write raw text to preserve formulas (`values=False`). UTF-8 throughout.

```bash
python -m abax convert data.csv data.tsv
python -m abax view data.csv
```

### Streaming large CSVs

[`abax/core/io/csv_stream.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/io/csv_stream.py) imports big CSVs
without loading the whole file into memory. It provides:

- `sniff_csv(path)` — a fast **preview**: delimiter and header detection, a
  sample of rows, an approximate total row count (exact under 5 MB, estimated
  above), and a per-column inferred type (int / float / bool / date / text via
  `abax.core.typeinfer`).
- `iter_chunks(path, n)` — yields fixed-size chunks of rows; the file is never
  fully materialised.
- `load_csv_streaming(path, max_rows=..., coerce_types=True)` — builds a sheet
  from a bounded number of rows, optionally coercing each column to its inferred
  type.

## Excel (`.xlsx`, `.xlsm`) — needs `openpyxl`

[`abax/engine/excel_io.py`](https://github.com/leavesofgrass/abax/blob/main/abax/engine/excel_io.py) uses `openpyxl`. Every
worksheet becomes a sheet. The workbook is loaded with `data_only=False`, so
Excel formulas are kept **as text** and re-evaluated by abax rather than read as
cached values. On export the default writes **raw cell text** (so formulas
survive the round-trip into Excel); the API can write computed values instead.
Sheet titles are capped at Excel's 31-character limit.

### What round-trips (formatting fidelity)

Both directions also carry the formatting the native envelope persists, so a
styled workbook survives `.abax` → `.xlsx` → `.abax` (and a styled `.xlsx`
imports styled):

- **Number formats** — abax's specs map to Excel format codes (`comma` ↔
  `#,##0.00`, `currency` ↔ `$#,##0.00`, `percent` ↔ `0.00%`, `sci` ↔
  `0.000E+00`, `int` ↔ `0`, `fixedN` ↔ `0.00…`, `text` ↔ `@`). Importing a
  foreign file maps codes back best-effort (any `$` → currency, `%` → percent,
  …); codes with no abax counterpart (e.g. date masks) are left as general.
- **Cell styles** — bold/italic/underline, horizontal alignment, text colour,
  and fill colour (theme/indexed colours in foreign files are skipped; only
  concrete RGB maps).
- **Borders** — per-edge thin/medium/thick. Foreign edge styles fold to the
  nearest weight (`hair`/`dashed`/… → thin, `double`/`mediumDashed`/… → medium).
- **Layout** — column widths and row heights (abax stores pixels; widths
  convert to Excel's character units as `chars = (px − 5) / 7`, heights to
  points as `pt = px × 0.75`, and both invert exactly on import), frozen
  panes, and merged regions.
- **Conditional formatting** — comparison rules (`>`, `<`, `>=`, `<=`, `==`,
  `!=`, `between`), 2- and 3-colour scales, text rules (contains / begins with
  / ends with), blank/not-blank, above/below average, top/bottom N and %,
  duplicate/unique — including a rule's fill colour or CSS styling (mapped to
  an Excel differential style). abax's `regex` kind has no Excel counterpart
  and is skipped on export; Excel rule types abax has no model for (data bars,
  icon sets, formula rules) are skipped on import.

The fidelity pass is strictly additive: an unstyled workbook writes a plain
`.xlsx` exactly as before, and unmappable foreign styling is dropped rather
than erroring.

If `openpyxl` is not installed, both load and save raise a `RuntimeError` with a
clear hint:

```
pip install openpyxl
# or:  pip install abax[excel]
```

## OpenDocument spreadsheet (`.ods`)

[`abax/engine/ods_io.py`](https://github.com/leavesofgrass/abax/blob/main/abax/engine/ods_io.py) is **pure stdlib** — it
reads and writes the ODF `content.xml` directly with `zipfile` and
`xml.etree.ElementTree`, so it needs no `odfpy`/`ezodf`. Import reads the **first**
sheet, honouring `number-columns-repeated` / `number-rows-repeated` (repeats are
expanded, but trailing empty repeats are dropped so they never inflate the
sheet). Export writes the active sheet as a valid `.ods` ZIP (the `mimetype`
member is stored first, uncompressed, per the ODF packaging spec). Cells that
parse as numbers are written as `float`; everything else as `string`.

## Parquet / Feather (`.parquet`, `.pq`, `.feather`, `.ft`) — needs `pandas` + engine

[`abax/engine/parquet_io.py`](https://github.com/leavesofgrass/abax/blob/main/abax/engine/parquet_io.py) uses `pandas` plus
a columnar engine (`pyarrow` or `fastparquet`). The DataFrame's column names
become the header row; every value is stringified (nulls → empty cells). Export
treats row 0 as the header and writes the **active sheet** only, using displayed
values. The extension picks the writer: `.feather`/`.ft` → Feather, otherwise
Parquet.

Missing dependency raises `ParquetError`:

```
pip install pandas pyarrow
# or the full-fat set (bundles pandas + a parquet engine):  pip install abax[all]
```

## XML Spreadsheet / SpreadsheetML (`.xml`)

[`abax/core/io/xml_io.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/io/xml_io.py) reads and writes the Excel 2003
"XML Spreadsheet" dialect (`<Worksheet>/<Table>/<Row>/<Cell>/<Data>`), which both
Excel and gnumeric understand — pure stdlib. Notable details:

- Formulas are stored in **R1C1** in the `ss:Formula` attribute and converted
  to/from A1 via [`abax/core/r1c1.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/r1c1.py).
- Sparse rows and cells use `ss:Index` (so gaps don't bloat the file).
- `ss:Type` is written/read as `Number`, `String`, or `Boolean`.
- Cell errors are emitted as strings.

## Markdown GFM tables (`.md`, `.markdown`)

[`abax/core/io/markdown_io.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/io/markdown_io.py) treats GitHub-Flavored
Markdown tables as a first-class format. Export produces a padded,
alignment-aware table (per-column `l`/`c`/`r`), using the first row as the header
(or column letters if you turn headers off), and renders **computed values**.
Pipes, backslashes, and newlines in cell text are escaped (`\|`, `\\`, `<br>`).
Import parses the **first** GFM table found in the file and drops the alignment
separator row.

```markdown
| Item   | Price |
| :---   | ----: |
| Apple  | 1.10  |
| Pear   | 0.95  |
```

The GUI command palette also offers **Copy selection as Markdown**.

## Jupyter notebook (`.ipynb`)

[`abax/core/io/notebook_io.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/io/notebook_io.py) reads and writes
valid **nbformat 4.5** (per-cell `id`s) with **no `nbformat` dependency**, and
**round-trips the whole workbook losslessly**: the full workbook envelope
(formulas, multiple sheets, defined names, styles) is embedded in the notebook
metadata and restored on import, so a `.ipynb` written by abax converts back to a
`.abax` with nothing lost. Each sheet also renders as a Markdown-table cell, so the
notebook is readable in any viewer. A **foreign** notebook (not written by abax) is
imported by scanning its Markdown tables — each table becomes a sheet named after
the nearest heading. See [jupyter.md](jupyter.md) for rich display, the kernel, and
the editable-sheet widget; `abax.engine.nbvalidate` validates a notebook against
the nbformat schema when it's installed.

## R data.frame (`.r`, `.rdata`)

[`abax/core/io/r_io.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/io/r_io.py) exports each sheet as a
`name <- data.frame(col = c(...), ...)` block (first row supplies the column
names, `stringsAsFactors = FALSE`). Import is a **best-effort** parser for that
same shape and for bare `name <- c(...)` vectors. Strings are quoted/escaped,
`NA` round-trips to a blank cell, and `TRUE`/`FALSE`/`T`/`F` are recognised.

## JSON Lines (`.jsonl`, `.ndjson`)

[`abax/core/io/flatfile_io.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/io/flatfile_io.py) — one JSON object per
line. On import, row 0 is the ordered union of all object keys (first-seen
order); each later row holds that object's values as strings, with a missing key
left blank. On export, row 0 supplies the field names and each later row becomes
one JSON object `{field: value}` from the raw cell text (empty trailing fields
skipped).

## Fixed-width text (`.fixed`)

Also in [`abax/core/io/flatfile_io.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/io/flatfile_io.py). Import either
slices each line by explicit character widths or, by default, splits on runs of
two-or-more spaces (the layout of `column -t` output). Export renders each column
left-aligned and padded to its widest value plus a gap.

## ADIF amateur-radio logbook (`.adi`, `.adif`)

[`abax/core/io/adif_io.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/io/adif_io.py) reads and writes ADIF
(Amateur Data Interchange Format), the standard interchange format for
amateur-radio logbooks — pure stdlib. A logbook is text whose fields are written
as `<FIELDNAME:LENGTH>value` (the length is the value's **UTF-8 byte** count, so
values are parsed in bytes and survive multi-byte characters). An optional header
ends at `<EOH>`; each QSO record ends at `<EOR>` (both case-insensitive, and
field names are stored upper-cased).

Import loads the file into a single sheet named **`Log`**: row 0 is the union of
all field names (first-seen order), and each later row is one QSO, with a missing
field left blank. Export takes row 0 as the field names and writes each data row
back as a QSO record (empty cells are skipped), under an `abax` header
(`<ADIF_VER:5>3.1.4`, `<PROGRAMID:5>abax`, `<EOH>`). See the
[RF toolkit](rf-toolkit.md) for the ham-radio functions (band plan, CTCSS,
Maidenhead grid, and the `DXCC` prefix lookup) that pair with a logbook sheet.

## SQLite (`.db`, `.sqlite`, `.sqlite3`)

[`abax/core/io/sqlite_io.py`](https://github.com/leavesofgrass/abax/blob/main/abax/core/io/sqlite_io.py) uses the stdlib `sqlite3`
module. Opening a database loads **every user table** (excluding `sqlite_*`
internals) into its own sheet; row 0 is the column names and rows 1.. are the
data, all stored as text. Saving writes the active sheet to one table: row 0
supplies column names (sanitized to safe identifiers, blanks → `col_1`…),
columns are created as `TEXT`, and rows are inserted with **parameterized**
queries (empty cells become `NULL`). Identifiers are always double-quoted with
embedded quotes escaped; values are never string-formatted into SQL.

The module API also supports loading a single table or an arbitrary
`SELECT … ` query, and choosing `replace` / `append` / `fail` when a table
already exists.

## Statistical formats: Stata / SPSS (`.dta`, `.sav`) — needs `pyreadstat`

[`abax/engine/statfiles.py`](https://github.com/leavesofgrass/abax/blob/main/abax/engine/statfiles.py) reads Stata (`.dta`),
SPSS (`.sav`, `.zsav`) and SAS-transport-adjacent (`.por`) files via the optional
`pyreadstat` package. Variable names become the header row and values are
converted to abax's cell types (dates/datetimes render as ISO strings). Import
only — there's no writer. Without the package the read raises a clear
`install abax[stats-io]` message and the rest of the app is unaffected.

```bash
pip install "abax[stats-io]"   # or the full-fat: pip install "abax[all]"
```

## HDF5 (`.h5`, `.hdf5`) — needs `h5py`

[`abax/engine/hdf5_io.py`](https://github.com/leavesofgrass/abax/blob/main/abax/engine/hdf5_io.py) walks an HDF5 file's group
tree and loads each **tabular** (1-D/2-D) dataset into its own sheet (the
dataset's path becomes the sheet name); structured/compound arrays use their
field names as the header. Scalar, 3-D+, and empty datasets are skipped. Import
only; a missing `h5py` gives an `install abax[hdf5]` hint.

```bash
pip install "abax[hdf5]"
```

## 7-Zip archives (`.7z`) — needs `py7zr`

Handled by the file manager rather than a plain open: a **7z** button compresses
the selection, **Extract** unpacks a `.7z`, and **Open in archive** lists a
`.zip`/`.tar`/`.7z`'s contents and opens a supported member (CSV, Excel, Parquet,
ODS, `.abax`, …) straight into the grid — extracting just that member, no full
unpack. `.7z` needs the optional `py7zr` package (`pip install abax[sevenzip]`, in
the `thin`/`all` sets); without it `.zip`/`.tar` still work and the 7z actions show
an install hint. Extraction keeps the path-traversal (zip-slip) guard.

## Quick reference: converting between formats

The headless CLI converts by extension — no GUI required:

```bash
python -m abax convert sales.xlsx sales.csv      # Excel  → CSV
python -m abax convert data.csv data.parquet     # CSV    → Parquet
python -m abax convert book.abax book.ods        # native → OpenDocument
python -m abax convert table.db table.md          # SQLite → Markdown
```

See the [command-line interface](cli.md) for the full set of subcommands.
