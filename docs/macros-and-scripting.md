# Macros and scripting

abax is scriptable in plain Python. There are two extension points — *command
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
> In the GUI, the **Python console, the script runner, and command macros all run
> out-of-process** in a shared isolated worker (the live workbook is shipped to it
> and back each command), so a crash, hang, or runaway allocation there can't
> freeze or take down abax — and a runaway command can be **Interrupt**ed (which
> kills the worker; the next command respawns it). The worker is also
> **resource-limited**: its memory, CPU time, and process count are capped (a
> Windows Job Object, or POSIX `rlimit`s), so an allocation bomb or fork bomb is
> killed by the OS instead of wedging the machine — and the script/macro runner
> arms a wall-clock timeout as a backstop. The caps are tunable via the
> `ABAX_WORKER_MEM_MB` / `ABAX_WORKER_CPU_S` / `ABAX_WORKER_PROCS` environment
> variables (the defaults are generous — big enough for real data-science work).
>
> **Code isolation is a setting with three levels** (`code_isolation`, or the
> command palette's **"Cycle code isolation (off / isolated / strict)"**):
>
> - **off** — code runs **in this process**, with no worker and no limits:
>   fastest and most direct, but a crash (e.g. in a C extension) can take down
>   abax and a runaway can't be interrupted. Choose this only for code you wrote
>   and trust.
> - **isolated** *(default)* — code runs in a separate, **resource-limited**
>   worker process (memory / CPU / process caps), so a crash, hang, or runaway
>   allocation there can't take down abax. This is **crash and resource
>   isolation, not a security sandbox** — the worker still runs with your full
>   privileges, so it can read/write your files and reach the network.
> - **strict** — a real **OS boundary**: the worker runs inside the platform's
>   OS sandbox (a **Windows AppContainer**, **Linux bubblewrap**, or **macOS
>   sandbox-exec**) with **no network access** and writes confined to a private
>   scratch directory. Strict mode is **fail-closed**: after the sandbox is
>   applied the worker runs a live escape self-test (it tries to write outside
>   the scratch dir and open a socket) and **refuses to run your code** if either
>   succeeds — and if no OS confinement is available on your platform (e.g. Linux
>   without `bwrap`), it refuses rather than run unconfined. So strict mode is
>   either a genuine boundary or nothing; it never pretends. Set it with
>   `ABAX_SANDBOX_STRICT=1` too. For untrusted code this is the mode to use; when
>   you can't, run abax in a throwaway VM or container.
>
> Regardless of level, loading a macro/UDF *file* executes it in-process (a UDF
> must be callable by the formula engine — that is what the consent gate covers),
> and the CLI (`abax macro run`) / TUI (`:macro`) run macros in-process — there
> you are running code you invoked on yourself. See `dev/sandbox-design.md` for
> the full design.
>
> The GUI gates all of these behind a one-time **consent prompt**: the first time
> you open the console/terminal or run a script/macro, abax warns you and asks you
> to explicitly *Enable code execution*. The choice is remembered per profile (the
> `code_consent` setting); set it back to `false` to be asked again.

## The two extension points

Both live in `abax/macros.py` and are activated by decorators that abax
injects into every macro file's namespace when it is loaded.

| Decorator | Makes a… | Invoked as |
|-----------|----------|------------|
| `@macro` | command macro `def name(ctx)` | `abax macro run NAME`, TUI `:macro NAME`, GUI palette |
| `@register_function("NAME")` | formula UDF | `=NAME(...)` inside any cell |

## Command macros

A command macro is a function that takes a single `ctx` argument — a
[`MacroContext`](#the-macrocontext-api) — and mutates the workbook through it.

```python
# saved as ~/.config/abax/macros/totals.py  (location varies by OS, see below)

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

Macro files do not need to import abax internals. abax injects a small set of
helpers into each file's namespace (see `_build_namespace` in `abax/macros.py`):

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

## The embedded Python console

Beyond macros and UDFs, abax carries a full **Python REPL wired to the live
workbook** — a GUI dock (part of the default workspace, or `` Ctrl+` ``-adjacent
via View) and the TUI `:py` mode. It is gated by the same one-time consent
prompt, and in the GUI it runs **out-of-process, off the UI thread** (a worker
holds a copy of the workbook; each command ships the workbook in and the mutated
workbook back, which the GUI then applies), so a crash, hang, or runaway
allocation there can't take the app down — **Interrupt** kills and respawns the
worker.

The namespace (built by `abax/core/console_ns.py`) binds these workbook helpers:

| Name | What it is |
|------|-----------|
| `wb` | the live `Workbook` |
| `sheet` | `sheet()` returns the active `Sheet` |
| `doc` | a document handle (`doc.workbook`) |
| `cell(ref)` | read a cell's value, e.g. `cell("B7")` |
| `put(ref, value)` | write a cell, e.g. `put("A1", 42)` |
| `read_matrix("A1:C3")` / `write_matrix("E1", mat)` | a range ↔ a list-of-lists of floats |
| `sheet_to_df([rng])` / `df_to_sheet(df, "A1")` | a range ↔ a pandas DataFrame (needs pandas) |
| `sql(query)` | run SQL across the sheets → `(columns, rows)` |
| `describe()` | a per-column profile of the active sheet |
| `rpn` | a live RPN calculator instance |
| `compile_expr` | compile a math expression in `x` (used by the grapher) |

It also **preloads the whole science / RF stack** as modules (`matrix`, `eigen`,
`units`, `numeric`, `stats`, `ml`, `cluster`, `gmm`, `trees`, `bayes`, `metrics`,
`signal`, `spectral`, `filters`, `fft`, `interp`, `ode`, `rf`, `antenna`, `mom`,
`wire_mom`, `nec`, `chartsvg`, `iq`, `wbdiff`, `html_report`, `urlfetch`,
`goalseek`, `dxcc`, `adif`, …) plus the optional data-science packages when
installed (`numpy`/`np`, `pandas`/`pd`, `scipy`, `statsmodels`/`sm`, `sklearn`,
`pingouin`/`pg`, `pymc`/`pm`, `sksurv`) — see [data-science.md](data-science.md)
for those. A `Sheet` echoed at the prompt renders as a **Markdown table** (the
rich-display protocol).

```python
>>> put("A1", 10); put("A2", 20)
>>> cell("A1")
10
>>> read_matrix("A1:A2")
[[10.0], [20.0]]
>>> df = sheet_to_df()                 # active sheet -> DataFrame (pandas)
>>> df_to_sheet(df.describe(), "E1")   # write the summary block back
>>> cols, rows = sql("SELECT * FROM Sheet1 WHERE B > 100")
```

## Running a script file

*Tools → Run Python script…* runs an arbitrary `.py` against the current
workbook, after the consent prompt. Like the console, the script runs
**out-of-process in the isolated, resource-limited worker** — a crash, hang, or
runaway is contained, and it can't take the GUI down. It runs in a *fresh*
namespace (console variables don't leak in) with the console handles —
`wb`, `sheet()`, `cell`, `put`, plus the engineering/data-science toolkit — and
`__name__ == "abax_script"`; the workbook crosses as an envelope and its edits are
applied on return. On success abax marks the document dirty and refreshes the
grid; any exception is reported with a traceback. Use this for one-off batch edits
over an open workbook (a macro is the better choice for anything you'll reuse).

## Discovery and loading

abax discovers macro files from:

1. **`CONFIG_DIR/macros/*.py`** — the per-user macro directory. `CONFIG_DIR`
   is resolved by `abax/_runtime.py` (platform-appropriate, e.g.
   `~/.config/abax/macros/` on Linux). All `.py` files there are loaded,
   sorted by name.
2. **`--macros PATH`** — an extra file *or* directory passed on the command
   line. A directory loads its `*.py`; a single file loads just that file.

A file that fails to load is reported and skipped — the rest stay loadable.
UDFs are made live by `install_functions`, which copies them into the formula
engine's `FUNCTIONS` registry. Saved recordings auto-load into the active
registry, so a freshly saved macro is immediately runnable.

## Macro recording

The recorder (`abax/recorder.py`) watches your edits and captures them as a
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
# Generated by abax macro recording. Edit freely.
@macro("recorded_20260629_101500")
def recorded_20260629_101500(ctx):
    ctx.set('A1', 'Item')
    ctx.set('B1', '=A1&" total"')
    ctx.recalc()
```

## Running macros

Once a macro is discovered/loaded:

- **CLI:** `abax macro run NAME FILE [--at A1]`. `--at` is the anchor for a
  relative macro (the cell it replays around).
- **TUI:** `:macro NAME` (replays at the cursor). The recorder is driven with
  `:rec` (toggle absolute), `:rec rel` (relative), `:rec start|stop|replay`, and
  `:rec save <path.py>`. The status bar shows `● REC N` / `● REL N`.
- **GUI:** the command palette offers Start / Start relative / Save /
  Replay-at-cursor; `● REC` / `● REL` appears in the title bar. Tools → Macros is
  rebuilt from the registry.

## Example: a complete macro file

```python
# ~/.config/abax/macros/sample.py

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
