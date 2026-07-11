# Python console

abax carries a full **Python REPL wired to the live workbook**. It is the fastest
way to poke at your data programmatically — read and write cells, pull a range into
pandas or numpy, run SQL across the sheets, or drive the built-in science toolkit —
without leaving the app or writing a macro file.

See also: [Macros & scripting](macros-and-scripting.md) (UDFs, command macros, the
script runner) · [Data science overview](data-science.md) · [Terminal](terminal.md)
· [Configuration](configuration.md).

> **Security & isolation.** The console runs **arbitrary Python with your full user
> privileges**, so it is gated behind a one-time **consent prompt** (remembered per
> profile). In the GUI it runs **out-of-process** in a resource-limited worker: a
> crash, hang, or runaway allocation there can't take abax down, and a runaway
> command can be **Interrupt**ed (which kills the worker; the next command respawns
> it). How far the worker is confined is the `code_isolation` setting — `off`,
> `isolated` (default), `restricted`, or `strict`. This matters for the file
> recipes below: reading and writing files on disk needs `off` or `isolated`;
> `restricted` and `strict` deliberately block filesystem and network access. See
> [Macros & scripting → security](macros-and-scripting.md) for the full four-level
> description.

## Opening the console

| Surface | How |
|---------|-----|
| **GUI** | **View → Python console** (`Ctrl+Shift+Y`), the toolbar "Python console" button, or the command palette (`Ctrl+Shift+P` → *Python console…*). It docks at the bottom. **View → Open default workspace** puts the console and [terminal](terminal.md) side by side under the grid. |
| **TUI** | `:py <python>` runs a one-off snippet against the active sheet, e.g. `:py put('A1', sum(range(10)))`. |

## The workbook namespace

The console starts with these names already bound (built by
`abax/core/console_ns.py`) — no imports needed:

| Name | What it is |
|------|-----------|
| `wb` | the live `Workbook` (all sheets) |
| `sheet()` | returns the active `Sheet` |
| `doc` | a document handle (`doc.workbook`) |
| `cell(ref)` | read a cell's computed value — `cell("B7")` |
| `put(ref, value)` | write a cell — `put("A1", 42)` |
| `read_matrix("A1:C3")` | a range → a list-of-lists of floats |
| `write_matrix("E1", mat)` | a list-of-lists → a range anchored at `E1` |
| `sheet_to_df([rng])` | a range (or the whole sheet) → a pandas `DataFrame` |
| `df_to_sheet(df, "A1")` | a `DataFrame` → the grid, anchored at `A1` |
| `sql(query)` | run SQL across the sheets → `(columns, rows)` |
| `describe()` | a per-column profile of the active sheet |
| `rpn` | a live RPN calculator instance |
| `compile_expr` | compile a math expression in `x` (used by the grapher) |

It also **preloads the whole science / RF stack** as modules — `matrix`, `eigen`,
`units`, `numeric`, `stats`, `ml`, `cluster`, `fft`, `signal`, `spectral`,
`filters`, `interp`, `ode`, `rf`, `antenna`, `mom`, `wire_mom`, `nec`, `chartsvg`,
and more — plus the optional data-science packages when installed (`numpy`/`np`,
`pandas`/`pd`, `scipy`, `statsmodels`/`sm`, `sklearn`, …). A `Sheet` echoed at the
prompt renders as a **Markdown table** (the rich-display protocol).

## Reading and writing cells

```python
>>> put("A1", 10); put("A2", 20); put("A3", 30)
>>> cell("A2")
20
>>> put("B1", "=SUM(A1:A3)")     # formulas work exactly as typed in a cell
>>> cell("B1")
60
```

`put` accepts numbers, strings, and formula strings (anything starting with `=`).
`cell` returns the **computed** value; use `sheet().get_raw("B1")` if you want the
underlying `=SUM(A1:A3)` source instead.

A quick loop to lay down a column and a running total:

```python
>>> for r, v in enumerate([12, 7, 19, 4], start=1):
...     put(f"A{r}", v)
>>> put("A5", "=SUM(A1:A4)")
>>> cell("A5")
42
```

## Working with ranges as a matrix

For bulk **numeric** work, `read_matrix` / `write_matrix` move a whole rectangle at
once as a list-of-lists — no per-cell round-trips. (`read_matrix` reads numbers,
with blanks as `0`; for mixed text/number tables use `sheet_to_df` below.)

```python
>>> block = read_matrix("A1:C3")          # [[1.0, 2.0, 3.0], [4.0, ...], ...]
>>> doubled = [[x * 2 for x in row] for row in block]
>>> write_matrix("E1", doubled)           # writes a 3×3 block starting at E1
```

## The pandas hand-off

If pandas is installed, the console is the most direct way to reshape data and
push the result back into the grid:

```python
>>> df = sheet_to_df()                     # active sheet -> DataFrame
>>> summary = df.describe()                # count/mean/std/min/quartiles/max
>>> df_to_sheet(summary, "H1")             # drop the summary block at H1
```

```python
>>> df = sheet_to_df("A1:D100")            # just a range
>>> top = df.sort_values("revenue", ascending=False).head(10)
>>> df_to_sheet(top, "F1")                 # the 10 biggest rows, at F1
```

## SQL across your sheets

`sql()` treats each sheet as a table (the sheet name is the table name; the first
row is treated as the header), so you can join and aggregate with plain SQL:

```python
>>> cols, rows = sql("SELECT region, SUM(sales) AS total "
...                  "FROM Sheet1 GROUP BY region ORDER BY total DESC")
>>> cols
['region', 'total']
>>> rows[0]
('West', 48210.0)
```

Write the result back as a labelled block — hand it to pandas and use
`df_to_sheet`, which lays down the header row and handles text columns:

```python
>>> import pandas as pd
>>> df_to_sheet(pd.DataFrame(rows, columns=cols), "J1")
```

## Using the built-in toolkit

The science modules are already imported, so ad-hoc analysis is a one-liner:

```python
>>> col = [x for row in read_matrix("A1:A50") for x in row]
>>> stats.mean(col), stats.stdev(col)
(51.3, 12.87)
>>> describe()                             # per-column profile of the whole sheet
```

With numpy present you can mix it freely with `read_matrix`/`write_matrix`:

```python
>>> import numpy as np
>>> a = np.array(read_matrix("A1:A100"))
>>> write_matrix("B1", (a / a.sum()).tolist())    # normalize into column B
```

## Working with files

In `off` or `isolated` isolation the console is ordinary Python, so the stdlib and
pandas file readers work directly. **Import** a CSV from disk into the grid:

```python
>>> import pandas as pd
>>> df = pd.read_csv("sales.csv")
>>> df_to_sheet(df, "A1")                  # the file is now in the sheet
```

…or without pandas, using the stdlib — write each field with `sheet().set_cell`,
which takes zero-based `(row, col)` and stores text as-is:

```python
>>> import csv
>>> sh = sheet()
>>> with open("sales.csv", newline="") as f:
...     for r, row in enumerate(csv.reader(f)):
...         for c, val in enumerate(row):
...             sh.set_cell(r, c, val)     # numbers-as-text parse back to numbers
```

**Export** the active sheet (or a computed view) back out to disk:

```python
>>> sheet_to_df().to_csv("cleaned.csv", index=False)
>>> import json
>>> json.dump(read_matrix("A1:C10"), open("block.json", "w"))
```

> If a file recipe raises `PermissionError` or a "filesystem is not available"
> message, you're in `restricted` or `strict` isolation — switch to `isolated`
> (Tools → Code isolation, or the palette's *Cycle code isolation*) for code you
> trust to touch your files. For a **reusable** batch job over files, prefer a
> command macro or the script runner (below) over retyping into the console.

## Console vs. script runner vs. macros

The console is for **interactive** exploration. For anything you'll run more than
once, reach for the neighbouring tools — they share the same workbook handles:

- **Tools → Run Python script…** runs a `.py` file against the current workbook in
  the same isolated worker, in a *fresh* namespace with `wb`, `sheet()`, `cell`,
  `put`, and the toolkit bound. Good for one-off batch edits over an open sheet.
- **Command macros** (`@macro`) and **UDFs** (`@register_function`) are the durable,
  reusable extension points — see [Macros & scripting](macros-and-scripting.md).

## TUI: `:py`

In the terminal UI, `:py` runs a single Python statement against the active sheet
with the same helpers available:

```
:py put('A1', sum(range(10)))
:py for r in range(5): put(f'B{r+1}', r*r)
```

The result (or any error) is shown on the status line. For multi-line work, launch
the GUI console or use the script runner.
