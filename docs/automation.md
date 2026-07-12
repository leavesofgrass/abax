# Automation API

`abax.api` is a small, documented Python surface for driving abax **headlessly** —
open or create a workbook, read and write cells, let formulas recompute, and save
back out, all from an ordinary Python program. It is a thin convenience wrapper
over the engine ([`Document`](architecture.md) / `Workbook` / `Sheet`) and adds no
evaluation logic of its own, so anything you can do here you can also do against
the engine directly — this just makes the common case pleasant.

It needs only the standard library and the always-present engine; nothing on this
page requires an optional extra (opening a *foreign* format like `.xlsx` still uses
that format's adapter, exactly as the GUI does).

See also: [index](index.md) · [macros & scripting](macros-and-scripting.md) ·
[architecture](architecture.md) · [file formats](file-formats.md) ·
worked examples:
[first workbook](examples/getting-started/first-workbook/README.md),
[headless CLI](examples/scripting-and-cli/headless-cli/README.md).

## A first script

```python
import abax

book = abax.new()          # a fresh workbook (one blank "Sheet1")
sheet = book.active        # the active sheet

sheet["A1"] = 10           # write cells by A1 reference
sheet["A2"] = 20
sheet["A3"] = "=SUM(A1:A2)"

print(sheet["A3"])         # -> 30   (computed on read)

book.save("totals.abax")   # native JSON format, chosen from the extension
```

`abax.new()` and `abax.open(path)` are the two entry points; both return a
`Book`.

## Reading and writing cells

A `Sheet` is addressed two ways — pick whichever reads better at the call site.

**By A1 string (subscript).**

```python
sheet["B2"] = "=A1*2"      # write one cell
value  = sheet["B2"]       # read one computed value  -> a number/str/bool/None
block  = sheet["A1:B3"]    # read a range -> a 2-D list: rows of columns
raw    = sheet.formula("B2")   # the raw source text -> "=A1*2"
```

`sheet["A1:B3"]` returns a list of rows, each a list of column values:

```python
sheet["A1"] = 1; sheet["B1"] = 2
sheet["A2"] = "=A1+10"; sheet["B2"] = "=B1+10"
sheet["A1:B2"]        # -> [[1, 2], [11, 12]]
```

Assigning to a *range* key is rejected (raise cell-by-cell, or use `set` in a
loop) — a subscript write always targets a single cell.

**By zero-based coordinates** — convenient inside loops:

```python
for r in range(10):
    sheet.set(r, 0, r)             # A1..A10 = 0..9   (row, col are 0-based)
    sheet.set(r, 1, f"=A{r+1}*A{r+1}")
total = sum(sheet.value(r, 0) for r in range(10))
```

Values you write are coerced the way typing into a cell would be: strings pass
through verbatim (so `"=SUM(...)"` stays a formula), numbers and booleans
round-trip through the engine's literal parsing, and `None` clears the cell.

**Reads return computed values.** A blank cell reads as `None`; a formula that
errors reads as a `CellError` value (its `str()` is the Excel code):

```python
from abax.core.errors import CellError

sheet["A1"] = "=1/0"
v = sheet["A1"]
isinstance(v, CellError)   # True
str(v)                     # "#DIV/0!"
```

Use `sheet.formula(ref)` when you want the *source* text instead of the value.

## Recalculation

The API uses the engine's default **automatic** calculation. Every edit
invalidates the cached values of the cells that depend on it, so the next *read*
recomputes them lazily and on demand — reads always reflect the current formulas,
with no explicit step to remember:

```python
sheet["A1"] = 10
sheet["B1"] = "=A1*2"
sheet["B1"]          # -> 20
sheet["A1"] = 100    # a dependency changes...
sheet["B1"]          # -> 200   (refreshed on read, automatically)
```

`book.recalc()` forces a full recompute of every cell (the equivalent of the
GUI's **F9**). You rarely need it — reach for it after a bulk edit, to refresh a
volatile function, or if you have switched the underlying workbook to manual
calculation.

## Multiple sheets

```python
book = abax.new()
data = book.add_sheet("Data")     # add and return the new sheet
data["A1"] = 5

book["Sheet1"]["A1"] = "=Data!A1*2"   # cross-sheet reference
book["Sheet1"]["A1"]                  # -> 10

book.sheets            # -> ["Sheet1", "Data"]   (names, in order)
"Data" in book         # -> True
[s.name for s in book] # iterate sheets as Sheet wrappers
book["Missing"]        # -> KeyError (message lists the sheets that exist)
```

`add_sheet` with no name lets the engine pick the next `"SheetN"`; a duplicate
name raises `ValueError`.

## Opening, saving, round-tripping

`abax.open(path)` reads any format the engine recognizes from its extension —
`.abax` / `.json` (native), `.csv` / `.tsv`, `.xlsx`, `.parquet`, `.ods`, and
[more](file-formats.md). `book.save(path)` writes, choosing the format from the
extension; `book.save()` with no argument re-saves to the path the book was opened
from (and raises `ValueError` if there is none).

```python
book = abax.open("input.csv")
book.active["D1"] = "=SUM(A1:C1)"
book.save("output.abax")        # convert CSV -> native, formulas and all

again = abax.open("output.abax")
again.active["D1"]              # the formula survived and recomputes
```

## Context manager

A `Book` is a context manager, which is handy for scoping a short automation:

```python
with abax.open("data.abax") as book:
    book.active["A1"] = "=NOW()"
    book.save()
```

The `with` block does **not** auto-save on exit — persistence is always an
explicit `book.save(...)`, so a read-only or aborted block leaves the file
untouched.

## Reference

| Call | Result |
|------|--------|
| `abax.open(path)` | open a file → `Book` |
| `abax.new()` | fresh empty workbook → `Book` |
| `book[name]` | the named `Sheet` (`KeyError` if missing) |
| `book.active` | the active `Sheet` |
| `book.sheets` | list of sheet names, in order |
| `book.add_sheet(name=None)` | add and return a `Sheet` (`ValueError` on duplicate) |
| `book.recalc()` | force a full recompute (F9) |
| `book.save(path=None)` | write to `path`, or the opened-from path |
| `sheet[ref]` | computed value (scalar) or 2-D list (range) |
| `sheet[ref] = value` | set one cell (`value` coerced; `None` clears) |
| `sheet.value(row, col)` | computed value at zero-based `(row, col)` |
| `sheet.set(row, col, text)` | set the cell at zero-based `(row, col)` |
| `sheet.formula(ref)` | raw source text of a cell |
| `sheet.name` | the sheet's name |

For anything beyond this surface — styling, insert/delete rows, conditional
formats, the science/RF toolkit — reach through `book.workbook` (the core
`Workbook`) or `sheet.core` (the core `Sheet`); see
[macros & scripting](macros-and-scripting.md) and
[architecture](architecture.md).
```
