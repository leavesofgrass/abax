# Macros and scripting

qcell is scriptable in plain Python. There are two extension points — *command
macros* that drive a workbook, and *user-defined functions* (UDFs) that become
callable inside formulas — plus a *macro recorder* that turns your edits into a
runnable macro. Everything is written to ordinary `.py` files: code stays code
and is never embedded in a JSON data file.

See also: [index](index.md) · [architecture](architecture.md) · [licensing](licensing.md).

> **Security — read this first.** Macros, the embedded Python console, the script
> runner, and the system terminal all run **arbitrary code with your full user
> privileges** — code can read and write any file you can, open network
> connections, and run shell commands. Only load and run code you trust; treat a
> downloaded macro the way you would treat any executable.
>
> The **Python console runs out-of-process and off the UI thread** (a separate
> worker; the live workbook is shipped to it and back each command), so a crash,
> hang, or runaway allocation there can't freeze or take down qcell — and a runaway
> command can be **Interrupt**ed (which kills the worker; the next command respawns
> it). That is **crash/memory isolation, not a security sandbox** — the worker
> still runs with your full privileges. (Macros and the script runner currently run
> in-process; a real security sandbox is planned.)
>
> The GUI gates all of these behind a one-time **consent prompt**: the first time
> you open the console/terminal or run a script/macro, qcell warns you and asks you
> to explicitly *Enable code execution*. The choice is remembered per profile (the
> `code_consent` setting); set it back to `false` to be asked again. (A real
> sandbox is planned — this consent gate is the interim safeguard.)

## The two extension points

Both live in `qcell/macros.py` and are activated by decorators that qcell
injects into every macro file's namespace when it is loaded.

| Decorator | Makes a… | Invoked as |
|-----------|----------|------------|
| `@macro` | command macro `def name(ctx)` | `qcell macro run NAME`, TUI `:macro NAME`, GUI palette |
| `@register_function("NAME")` | formula UDF | `=NAME(...)` inside any cell |

## Command macros

A command macro is a function that takes a single `ctx` argument — a
[`MacroContext`](#the-macrocontext-api) — and mutates the workbook through it.

```python
# saved as ~/.config/qcell/macros/totals.py  (location varies by OS, see below)

@macro
def totals(ctx):
    """Write a SUM under column A and label it."""
    ctx.set("A10", "Total")
    ctx.set("B10", "=SUM(B1:B9)")
    ctx.recalc()
    ctx.log("wrote totals row")
```

The decorator can be used bare (`@macro`, the function name lowercased becomes
the macro name) or with an explicit name (`@macro("my_name")`). After the macro
runs, anything passed to `ctx.log(...)` is collected on `ctx.messages` so the
CLI/TUI/GUI front-end can display it.

### The `MacroContext` API

`ctx` is your handle on the workbook. The full surface:

| Member | What it does |
|--------|--------------|
| `ctx.workbook` | the underlying `Workbook` (multi-sheet) |
| `ctx.sheet` | the active `Sheet` (property; `ctx.workbook.sheet`) |
| `ctx.cursor` | the active cell `(row, col)` when invoked, or `None` headless |
| `ctx.get(ref)` | read a cell's value by A1 ref, e.g. `ctx.get("B7")` |
| `ctx.set(ref, value)` | set a cell by A1 ref; non-strings are coerced to text |
| `ctx.set_rc(row, col, value)` | set a cell by zero-based `(row, col)`; negative coords are ignored (used by relative macros) |
| `ctx.get_sheet(name)` | fetch a sheet by name |
| `ctx.add_sheet(name=None)` | add (and return) a new sheet |
| `ctx.recalc()` | recalculate the whole workbook |
| `ctx.log(message)` | record a message for the front-end |

`ctx.cursor` matters for *relative* recorded macros (below): run from an editor
it offsets from the active cell; run headlessly (`cursor is None`) it falls back
to the recorded anchor.

## User-defined functions (UDFs)

`@register_function("NAME")` installs a function that becomes callable in
formulas as `=NAME(...)`. UDFs follow the same calling convention as the
built-ins: they receive a **list of already-evaluated arguments** and return a
value (a number, string, `bool`, `RangeValue`, or a `CellError`).

```python
@register_function("TAXED")
def taxed(args):
    """=TAXED(amount, rate) -> amount * (1 + rate)."""
    amount = as_number(args[0])
    rate = as_number(args[1])
    return amount * (1 + rate)
```

Once the macro file is loaded, `=TAXED(100, 0.2)` evaluates to `120`. The name
is upper-cased on registration, so `=taxed(...)` works too.

### Injected helpers

Macro files do not need to import qcell internals. qcell injects a small set of
helpers into each file's namespace (see `_build_namespace` in `qcell/macros.py`):

| Helper | Purpose |
|--------|---------|
| `flatten(x)` | flatten a `RangeValue` (or nested values) into a flat list |
| `numbers(args)` | pull just the numeric values out of an argument list |
| `as_number(x)` | coerce a single value to a number |
| `text(x)` | coerce a single value to its text form |
| `CellError` | construct/return spreadsheet errors (`#VALUE!`, `#NUM!`, …) |
| `RangeValue` | the 2-D range value type, for UDFs that return ranges |
| `shift_refs(raw, dr, dc)` | offset relative refs in a formula (used by relative recorded macros) |

A UDF that sums a range argument:

```python
@register_function("MYSUM")
def mysum(args):
    return sum(numbers(args)) or 0
```

## Discovery and loading

qcell discovers macro files from:

1. **`CONFIG_DIR/macros/*.py`** — the per-user macro directory. `CONFIG_DIR`
   is resolved by `qcell/_runtime.py` (platform-appropriate, e.g.
   `~/.config/qcell/macros/` on Linux). All `.py` files there are loaded,
   sorted by name.
2. **`--macros PATH`** — an extra file *or* directory passed on the command
   line. A directory loads its `*.py`; a single file loads just that file.

A file that fails to load is reported and skipped — the rest stay loadable.
UDFs are made live by `install_functions`, which copies them into the formula
engine's `FUNCTIONS` registry. Saved recordings auto-load into the active
registry, so a freshly saved macro is immediately runnable.

## Macro recording

The recorder (`qcell/recorder.py`) watches your edits and captures them as a
list of JSON-serializable `Action`s (`set` / `clear` / `add_sheet` /
`select_sheet`). From that list it can **replay** the actions, **emit a runnable
`.py` macro**, or **round-trip through JSON**.

### Absolute vs relative

`recorder.start(relative=...)` chooses the mode:

- **Absolute** (default): actions target the exact cells you edited. `replay`
  ignores any `at` argument and reproduces the edits verbatim.
- **Relative**: the recorder anchors on the **first edited cell**. `replay(at=(r, c))`
  shifts every target cell — and every relative formula reference — by
  `at - anchor`. Absolute `$`-anchored references stay put; targets that fall
  off the edge become `#REF!` and are skipped.

### Replay at the cursor, save as runnable `.py`

- `replay(workbook, at=None)` applies the actions. For relative recordings, pass
  the current cursor as `at` to replay the captured pattern at a new location.
- `to_macro_source()` / `save_macro(path)` emit a runnable `@macro` `.py` file.
  A relative recording emits a macro that offsets from `ctx.cursor` (or the baked
  anchor when run headlessly), using the injected `shift_refs` helper.
- `save_json(path)` / `load_json(path)` round-trip through the self-describing
  envelope (`app`, `schema_version`, `kind`, `relative`, `anchor`, `actions`).

An emitted absolute macro looks just like one you would hand-write:

```python
# Generated by qcell macro recording. Edit freely.
@macro("recorded_20260629_101500")
def recorded_20260629_101500(ctx):
    ctx.set('A1', 'Item')
    ctx.set('B1', '=A1&" total"')
    ctx.recalc()
```

## Running macros

Once a macro is discovered/loaded:

- **CLI:** `qcell macro run NAME FILE [--at A1]`. `--at` is the anchor for a
  relative macro (the cell it replays around).
- **TUI:** `:macro NAME` (replays at the cursor). The recorder is driven with
  `:rec` (toggle absolute), `:rec rel` (relative), `:rec start|stop|replay`, and
  `:rec save <path.py>`. The status bar shows `● REC N` / `● REL N`.
- **GUI:** the command palette offers Start / Start relative / Save /
  Replay-at-cursor; `● REC` / `● REL` appears in the title bar. Tools → Macros is
  rebuilt from the registry.

## Example: a complete macro file

```python
# ~/.config/qcell/macros/sample.py

@macro
def uppercase_headers(ctx):
    """Upper-case row 1 across the used columns."""
    sheet = ctx.sheet
    used_rows, used_cols = sheet.used_bounds()
    for c in range(used_cols):
        ctx.set_rc(0, c, text(ctx.sheet.get_raw(0, c)).upper())
    ctx.recalc()
    ctx.log(f"upper-cased {used_cols} header(s)")


@register_function("REVERSE")
def reverse(args):
    """=REVERSE(text) -> the text reversed."""
    return text(args[0])[::-1]
```

Drop this in your macro directory and you can run `:macro uppercase_headers` in
the TUI and use `=REVERSE("abc")` in any cell.
