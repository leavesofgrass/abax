# Architecture

This is the contributor's map of abax: how the code is layered, the invariants
that keep the layers honest, and the moving parts of the Qt GUI. abax is a
keyboard-first, JSON-first spreadsheet written in Python (stdlib-first, with
optional accelerators and front-ends).

See also: [index](index.md) · [macros and scripting](macros-and-scripting.md) · [licensing](licensing.md).

## The three-layer seam

abax is organized as three layers, with dependencies flowing strictly
downward:

```
core  ──►  engine  ──►  gui / tui
(pure)     (adapters)   (front-ends)
```

- **`abax/core/` — pure, stdlib-only.** The spreadsheet engine and formula
  machinery (tokenizer, parser, evaluator, 620+ functions incl. `LET`/`LAMBDA`,
  the dynamic-array spill engine, sheet/workbook model,
  search, fill/sort, completion, reference-shifting) live at the `core/` root, with
  the pluggable libraries grouped into subpackages:
  - **`core/io/`** — tabular import/export adapters (CSV/TSV, XML, Markdown, SQLite,
    flat-file, JSON exchange, R, Jupyter).
  - **`core/calc/`** — calculator engines (RPN Voyager 12C/15C/16C, algebraic, TI).
    `core/calc/program.py` adds HP-15C-style program memory: a `Program` of
    recorded `Step`s that a `ProgramRunner` executes against the RPN engine, so
    the `LBL`/`GTO`/`GSB`/`RTN` flow-control keys and the `x<=y` / `x=0`
    conditional tests actually run rather than sitting inert.
  - **`core/science/`** — numerical/statistical engines (linear algebra, calculus/
    ODEs, signal/spectral, statistics, regression, ML, finance, units), the
    `wire_mom.py` method-of-moments antenna solver (multi-wire junctions +
    image-plane ground reflection), and `hamlog.py` — pure-stdlib amateur-radio
    contest/POTA/SOTA logging (per-band-per-mode dupe detection with callsign
    normalization, point/multiplier tally) that registers the `ISDUPE` and
    `QSOPOINTS` spreadsheet functions.
  - **`core/format/`** — cell value formatting, styles, conditional formatting,
    colour maps, ANSI palette.

  **No Qt, no curses, no Textual, no third-party imports** — ever. core can run
  headless with nothing but the standard library.
- **`abax/engine/` — adapters with optional dependencies.** This is where
  optional packages are allowed. `engine/excel_io.py` uses openpyxl;
  `engine/document.py` dispatches open/save by file extension;
  `engine/satellite.py` predicts satellite pass rise/culmination/set times and
  look-angles from a TLE + observer (propagation via the optional `sgp4` extra,
  look-angle geometry pure stdlib); `engine/tts.py` is a text-to-speech adapter
  over the optional `pyttsx3` extra (native SAPI5/NSSpeech/eSpeak, no network) that
  powers speak-on-move. Everything here has a fallback so the app still works when
  the optional dep is missing — importing an adapter never fails when its dep is
  absent (`available()` reports the truth; the feature no-ops or raises a clear
  "install X" message).
- **`abax/gui/` and `abax/tui/` — front-ends.** The Qt desktop GUI and the
  curses/Textual TUI. These depend on core and engine, never the other way
  around. The TUI is a package split by concern — `capabilities` (terminal
  detection), `themes`, `commands` (parsing), `editor` (the `TuiEditor` state
  machine), `keys` (keystroke dispatch), `render` (the curses draw loop), and
  `app` (`run_tui`) — re-exporting its public surface from `tui/__init__.py`. The
  GUI groups its widgets into subpackages: **`gui/grid/`** (the
  virtualized table model/view + frozen panes), **`gui/dialogs/`** (the ~20 modal
  dialogs and browsers), **`gui/calc/`** (the floating calculator panel + painted/
  image faceplates + the `ProgramPanel` that enters/steps/runs a keystroke
  program), and **`gui/console/`** (the embedded Python console, its
  out-of-process bridge, and the terminals). The main window, theming, and the
  `_qtcompat` shim stay at the `gui/` root. `MainWindow` composes focused mixins:
  `DocumentMixin` (open/save/edit — including cell borders via `BorderDialog`,
  merge/unmerge, and the speak-active-cell a11y hook wired to the grid's
  `currentCellChanged` signal), `NavigationMixin` (movement/selection), and
  `SettingsMixin` — itself composed from `ViewMixin` (theme/zoom/fonts/docks),
  `PaletteMixin` (command + shortcut palettes, About), `CalcMixin` (calculator),
  `ConsoleMixin` (console/terminal/consent), `MacroMixin` (record/replay/scripts),
  and `ToolsMixin` (data/science dialogs — including the SGP4 satellite-pass and
  POTA/SOTA activation-log dialogs — conditional format, clipboard, actions).

### Why the seam matters

The seam is what lets abax ship as a headless CLI, a TUI, and a GUI from one
codebase, and what lets the test suite pass with **zero optional packages
installed**. If you find yourself reaching for Qt inside `core/`, or for a
third-party import inside `core/`, the change belongs in a different layer.

## Key invariants

These are enforced by tests and by convention. Don't break them:

- **`core/` imports only the standard library.** No third-party, no Qt, no
  curses/Textual. (`test_dependencies.py` checks the zero-optional-deps story.)
- **Qt is touched only through `abax/gui/_qtcompat.py`.** No module outside
  `abax/gui/` imports Qt, and no module — including inside the GUI — imports
  `PySide6`/`PyQt6` directly except `_qtcompat.py`.
- **All native persistence is JSON.** `.abax`/`.json` files use the workbook
  JSON envelope (`core/workbook.py`, `schema_version` 2); macro recordings use a
  JSON envelope; settings and state are JSON (`settings.py`, `SCHEMA_VERSION` 5).
  No pickle, no bespoke binary format. **Schema bumps stay back-compatible:** the
  workbook v2 view-fidelity keys (per-sheet `col_widths` / `row_heights` /
  `frozen` / `borders` / `merges`) are *omitted when empty* so a plain grid's file
  is byte-for-byte unchanged, and read back with a default so an older v1 file
  loads untouched (they survive row/column insert & delete); settings v5 added
  only defaulted, off/safe fields (iterative-calc knobs, accessibility toggles,
  plugin consent), so older settings files simply take the defaults on lazy
  migration.
- **All paths go through `abax/_runtime.py`.** Use `_runtime.CONFIG_DIR`,
  `DATA_DIR`, `CACHE_DIR`, `LOG_DIR`. No hardcoded paths.
- **Worker threads never touch Qt widgets.** Background work communicates with
  the UI exclusively via signals (see [async I/O](#async-io-workers)).
- **Optional deps are declared** in `diagnostics.OPTIONAL_DEPENDENCIES`; adding
  a new optional dependency means updating diagnostics. No new *required*
  dependencies without good reason.
- **`pyz_main.py` top-level imports are stdlib only** (verified by
  `test_pyz.py`); other imports are lazy.

## The binding shim (`gui/_qtcompat.py`)

abax supports both Qt for Python bindings, and `_qtcompat.py` is the **single
place** binding-specific code is allowed to live. It imports every Qt symbol the
rest of the GUI needs and re-exports a normalized surface, so no other module
ever branches on which binding is installed.

- **Default order: PySide6 (LGPL) first, then PyQt6.** PySide6's `Signal` is
  aliased to `pyqtSignal` so the rest of the code uses one name.
- **Override with `ABAX_QT_BINDING=PyQt6`** to force PyQt6 (useful for testing
  on the other binding).
- Any Qt class a GUI module needs must be added to the import lists *and*
  `__all__` in `_qtcompat.py`; modules then do
  `from ._qtcompat import QTableView, Qt, ...`.

## The virtualized grid (`gui/grid/grid_model.py`)

The grid is a `QTableView` backed by **`AbaxTableModel`**, a virtualized
`QAbstractTableModel` over the active `Sheet`. This is deliberately *not* a
`QTableWidget` with one widget per cell — that cost is exactly what the model
removes.

- **The model serves only the viewport.** A huge sheet costs nothing until
  scrolled into view; `rowCount`/`columnCount` report a generous extent
  (used range plus a margin) that grows on demand and never shrinks mid-session.
- **Display vs edit roles:** `DisplayRole` returns the *computed* value
  (`Sheet.display`); `EditRole` returns the *raw* text (`Sheet.get_raw`), so the
  in-cell editor seeds with the formula, not its result.
- **Lazy visual attributes.** Conditional-format fills, per-cell styles
  (bold/italic/underline, colors), and alignment are resolved on demand in
  `data()` via the Background/Foreground/Font/TextAlignment roles. Conditional
  formatting is computed *per painted cell* and cached for the current refresh
  generation, so a rule over a 20k-cell range costs nothing until those cells
  are visible.
- **Editing routes back through the host window.** `setData` calls the window's
  `_commit_cell`, so undo, macro recording, and validation stay in one place.
- **`refresh()` is cheap.** It rebuilds the lazy conditional-format state and
  extent and emits a single `dataChanged` over the whole range — the view only
  repaints the visible viewport — while dropping the per-cell fill cache so
  edited values re-color correctly.

## Async I/O workers (`workers.py`)

File open/save and other potentially slow work run off the main thread using the
`QObject` + `moveToThread` pattern. `workers.py` is imported only on the GUI
path, so importing Qt there is fine.

- **`IOWorker`** loads or saves a `Document` (`op` is `"open"` or `"save"`).
- **`FuncWorker`** runs an arbitrary zero-arg callable off-thread (e.g. the
  streaming CSV import).
- **Both share one signal contract:** `progress(int)`, `result(object)`,
  `error(str)`, `finished()`. The window's `_run_io` lifecycle wires `finished`
  to `thread.quit` and `deleteLater`.
- **Workers never raise across the thread boundary and never touch widgets.** A
  failure is caught and re-emitted as the `error` signal; results travel back as
  `result`. This is the concrete form of the "signals only" invariant.

`sys.excepthook` is installed at GUI startup (`gui/runner.py`) so anything that
does escape is logged rather than lost.

## Code execution & sandboxing

The Python console, the script runner, and command macros all run user code, so
they share one execution path with a **user-chosen isolation level** (the
`code_isolation` setting: `off` / `restricted` / `isolated` / `strict` — the
cycle order, *not* a single containment scale: `restricted` and `strict` both
wall off the OS but by different means, while `isolated` is only crash/resource
isolation). `make_exec_bridge(level)`
(`gui/console/console_bridge.py`) returns the transport; every transport exposes
the same `execute` / `execute_script` / `execute_macro` / `interrupt` / `close`
surface, so callers never branch on the level.

- **The worker (`console_worker.py`).** A `Worker` whose `handle` / `handle_script`
  / `handle_macro` methods are **pure** — the live `Workbook` crosses in and out
  as a JSON *envelope* per command, user vars persist in the child, and it
  dispatches by `op` (`exec` / `script` / `macro`). Being pure, it is unit-tested
  without a subprocess and reused directly in-process.
- **`off` — `InProcessBridge`.** Calls the pure `Worker` in this process. No
  subprocess, no limits, no confinement, no interrupt. Fastest; a crash takes the
  GUI down.
- **`restricted` — `ConsoleBridge(restricted=True)`.** Runs user code through an
  **AST allowlist** (`restricted.py`) inside the out-of-process worker: on top of
  the resource limits below, the code is restricted to a pure/safe language subset
  that rejects imports outside a small stdlib allowlist and blocks filesystem /
  network / OS access. The optional `restricted` extra (RestrictedPython) adds
  compile-time guards; the AST check runs either way. This sits between `off` and
  `isolated` for when a full OS sandbox isn't available on the platform.
- **`isolated` (default) — `ConsoleBridge`.** Spawns `console_worker` as a child
  and frames length-prefixed JSON over its pipes; a crash/hang/runaway there can't
  take down the GUI. **Resource limits** (`proclimits.py`): POSIX `setrlimit`
  applied in the child, or a Windows Job Object assigned by the parent (memory /
  CPU / process caps, kill-on-job-close), plus a wall-clock watchdog in the bridge.
- **`strict` — `ConsoleBridge(strict=True)`.** Adds OS confinement. `sandbox.py`
  is the platform-agnostic seam (a `Confinement` strategy + a private writable
  scratch dir); `sandbox_windows.py` (AppContainer, via `_winsandbox_ctypes.py`),
  `sandbox_linux.py` (bubblewrap), and `sandbox_macos.py` (sandbox-exec) implement
  it. The load-bearing safety mechanism is a **fail-closed self-test**: after
  confinement is applied the worker attempts to write outside scratch and open a
  socket, and refuses to run user code if either escape succeeds — and the bridge
  refuses to spawn at all when no confinement is available.

**Invariant (honesty).** `off`/`isolated` are documented as crash/resource
isolation, **not** a security boundary; `restricted` is labelled hardening (an
in-process language subset, defence-in-depth, *not* an OS boundary); `strict` is a
real boundary only where a platform primitive exists and the self-test passes, and
refuses everywhere else.
The GUI gates all code execution behind a one-time consent prompt (`ConsoleMixin`,
the `code_consent` setting) that states the active level plainly. See
[macros and scripting](macros-and-scripting.md) and `dev/sandbox-design.md`.

**Third-party plugins (`plugins.py`).** abax can also be extended by *installed*
packages that advertise user-defined functions or file-format importers/exporters
through `importlib.metadata` entry-point groups (`abax.udfs`, `abax.formats`).
Loading one runs third-party code with full privileges — the same untrusted-code
risk as the console — so it is **off by default** and gated on the
`plugins_enabled` consent setting: `load_plugins(enabled=...)` refuses to import
anything unless enabled, while `discovered()` merely *lists* advertised plugins
from package metadata without importing (always safe). Plugin loading is not a
security boundary; consent is the gate.

## Incremental recalculation

Editing a cell once cleared every sheet's value cache. A workbook-scoped
**reverse-dependents index** ([`core/depgraph.py`](../abax/core/depgraph.py))
inverts a formula's precedents, so an edit now invalidates only the edited cell
and the transitive closure that references it — cross-sheet edges included. The
contract is **over-approximation**: volatiles (`NOW`/`RAND`), dynamic references
(`INDIRECT`/`OFFSET`), defined names, unknown macros, and any workbook that
currently spills fall back to the full blanket-clear, so a stale value is never
served — a differential fuzz test compares incremental invalidation against a
full recalc across random edit streams. `ABAX_INCREMENTAL=0` restores the old
path; a `Workbook.calc_mode` of `"manual"` defers dependent recalc until `F9`.

**Iterative calculation (opt-in).** A genuine circular reference normally reports
`#CIRC!`. When the `calc_iterative` setting is on, `F9` calls
`Workbook.recalculate_iterative(max_iterations, max_change)` instead, which sweeps
every formula cell by capped fixed-point iteration — a circular read returns the
previous sweep's value — until the largest change is within `max_change` or the
`max_iterations` cap is hit, returning `(iterations, converged)`. It defaults off,
so the non-iterative path (and `#CIRC!`) is unchanged.

## Testing

- **Offscreen Qt.** GUI tests run with the offscreen Qt platform so they need no
  display; they exercise the model/window logic without a visible window.
- **Zero-optional-deps suite.** The full test suite passes with no optional
  packages installed (`test_dependencies.py`), which is the practical guarantee
  that core stays pure and every optional adapter has a working fallback.
- **`test_pyz.py`** verifies that `pyz_main.py`'s top-level imports are
  stdlib-only, protecting the zipapp's cold-start path.
- **CI matrix + quality gates.** `.github/workflows/ci.yml` runs `just check`
  across Linux/macOS/Windows × Python 3.11–3.13, plus a benchmark-regression gate
  (`scripts/bench_gate.py` vs. a committed baseline) and a ratcheting coverage
  floor on `abax/core`.

## Build

The `justfile` wraps the common tasks:

| Command | Produces |
|---------|----------|
| `just install` | dev setup — `.[dev,tui,gui,excel,fast-io]` |
| `just test` | the test suite |
| `just pyz` | `abax.pyz` zipapp — `optimize=2`, compressed, docstrings stripped |
| `just wheel` | a wheel — complete, **docstrings kept** |
| `just check` | lint + test + pyz + smoke |

Note the asymmetry: the **`.pyz` strips docstrings** (size), the **wheel keeps
them** (introspection, completion hints). Don't strip docstrings in the wheel.
