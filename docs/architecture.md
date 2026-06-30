# Architecture

This is the contributor's map of qcell: how the code is layered, the invariants
that keep the layers honest, and the moving parts of the Qt GUI. qcell is a
keyboard-first, JSON-first spreadsheet written in Python (stdlib-first, with
optional accelerators and front-ends).

See also: [index](index.md) · [macros and scripting](macros-and-scripting.md) · [licensing](licensing.md).

## The three-layer seam

qcell is organized as three layers, with dependencies flowing strictly
downward:

```
core  ──►  engine  ──►  gui / tui
(pure)     (adapters)   (front-ends)
```

- **`qcell/core/` — pure, stdlib-only.** The spreadsheet engine and formula
  machinery (tokenizer, parser, evaluator, ~110 functions, sheet/workbook model,
  search, fill/sort, completion, reference-shifting) live at the `core/` root, with
  the pluggable libraries grouped into subpackages:
  - **`core/io/`** — tabular import/export adapters (CSV/TSV, XML, Markdown, SQLite,
    flat-file, JSON exchange, R, Jupyter).
  - **`core/calc/`** — calculator engines (RPN Voyager 12C/15C/16C, algebraic, TI).
  - **`core/science/`** — numerical/statistical engines (linear algebra, calculus/
    ODEs, signal/spectral, statistics, regression, ML, finance, units).
  - **`core/format/`** — cell value formatting, styles, conditional formatting,
    colour maps, ANSI palette.

  **No Qt, no curses, no Textual, no third-party imports** — ever. core can run
  headless with nothing but the standard library.
- **`qcell/engine/` — adapters with optional dependencies.** This is where
  optional packages are allowed. `engine/excel_io.py` uses openpyxl;
  `engine/document.py` dispatches open/save by file extension. Everything here
  has a fallback so the app still works when the optional dep is missing.
- **`qcell/gui/` and `qcell/tui/` — front-ends.** The Qt desktop GUI and the
  curses/Textual TUI. These depend on core and engine, never the other way
  around. The TUI is a package split by concern — `capabilities` (terminal
  detection), `themes`, `commands` (parsing), `editor` (the `TuiEditor` state
  machine), `keys` (keystroke dispatch), `render` (the curses draw loop), and
  `app` (`run_tui`) — re-exporting its public surface from `tui/__init__.py`. The
  GUI groups its widgets into subpackages: **`gui/grid/`** (the
  virtualized table model/view + frozen panes), **`gui/dialogs/`** (the ~20 modal
  dialogs and browsers), **`gui/calc/`** (the floating calculator panel + painted/
  image faceplates), and **`gui/console/`** (the embedded Python console, its
  out-of-process bridge, and the terminals). The main window, mixins, theming, and
  the `_qtcompat` shim stay at the `gui/` root.

### Why the seam matters

The seam is what lets qcell ship as a headless CLI, a TUI, and a GUI from one
codebase, and what lets the test suite pass with **zero optional packages
installed**. If you find yourself reaching for Qt inside `core/`, or for a
third-party import inside `core/`, the change belongs in a different layer.

## Key invariants

These are enforced by tests and by convention. Don't break them:

- **`core/` imports only the standard library.** No third-party, no Qt, no
  curses/Textual. (`test_dependencies.py` checks the zero-optional-deps story.)
- **Qt is touched only through `qcell/gui/_qtcompat.py`.** No module outside
  `qcell/gui/` imports Qt, and no module — including inside the GUI — imports
  `PySide6`/`PyQt6` directly except `_qtcompat.py`.
- **All native persistence is JSON.** `.qcell`/`.json` files use the workbook
  JSON envelope; macro recordings use a JSON envelope; settings and state are
  JSON. No pickle, no bespoke binary format.
- **All paths go through `qcell/_runtime.py`.** Use `_runtime.CONFIG_DIR`,
  `DATA_DIR`, `CACHE_DIR`, `LOG_DIR`. No hardcoded paths.
- **Worker threads never touch Qt widgets.** Background work communicates with
  the UI exclusively via signals (see [async I/O](#async-io-workers)).
- **Optional deps are declared** in `diagnostics.OPTIONAL_DEPENDENCIES`; adding
  a new optional dependency means updating diagnostics. No new *required*
  dependencies without good reason.
- **`pyz_main.py` top-level imports are stdlib only** (verified by
  `test_pyz.py`); other imports are lazy.

## The binding shim (`gui/_qtcompat.py`)

qcell supports both Qt for Python bindings, and `_qtcompat.py` is the **single
place** binding-specific code is allowed to live. It imports every Qt symbol the
rest of the GUI needs and re-exports a normalized surface, so no other module
ever branches on which binding is installed.

- **Default order: PySide6 (LGPL) first, then PyQt6.** PySide6's `Signal` is
  aliased to `pyqtSignal` so the rest of the code uses one name.
- **Override with `QCELL_QT_BINDING=PyQt6`** to force PyQt6 (useful for testing
  on the other binding).
- Any Qt class a GUI module needs must be added to the import lists *and*
  `__all__` in `_qtcompat.py`; modules then do
  `from ._qtcompat import QTableView, Qt, ...`.

## The virtualized grid (`gui/grid/grid_model.py`)

The grid is a `QTableView` backed by **`QcellTableModel`**, a virtualized
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

## Testing

- **Offscreen Qt.** GUI tests run with the offscreen Qt platform so they need no
  display; they exercise the model/window logic without a visible window.
- **Zero-optional-deps suite.** The full test suite passes with no optional
  packages installed (`test_dependencies.py`), which is the practical guarantee
  that core stays pure and every optional adapter has a working fallback.
- **`test_pyz.py`** verifies that `pyz_main.py`'s top-level imports are
  stdlib-only, protecting the zipapp's cold-start path.

## Build

The `justfile` wraps the common tasks:

| Command | Produces |
|---------|----------|
| `just install` | dev setup — `.[dev,tui,gui,excel,fast-io]` |
| `just test` | the test suite |
| `just pyz` | `qcell.pyz` zipapp — `optimize=2`, compressed, docstrings stripped |
| `just wheel` | a wheel — complete, **docstrings kept** |
| `just check` | lint + test + pyz + smoke |

Note the asymmetry: the **`.pyz` strips docstrings** (size), the **wheel keeps
them** (introspection, completion hints). Don't strip docstrings in the wheel.
