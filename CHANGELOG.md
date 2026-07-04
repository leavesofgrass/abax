# Changelog

All notable changes to abax are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

> **Note:** This project was renamed from `qcell` to `abax` in version 0.1.2
> (out of respect for an existing open-source project already using the `qcell`
> name on GitHub). Historical entries below use the old name.

## [Unreleased]

### Added
- **Drag fill-handle:** the small square at the bottom-right of the selection can
  be dragged in any direction — **down, up, right, or left** — to extend a series
  into the swept cells (dragging up/left continues the series backwards), matching
  the Excel/gnumeric gesture.
- **Name Box:** the reference box to the left of the formula bar shows the active
  cell's A1 reference and lets you jump to any cell or range — type e.g. `B12` or
  `A1:C9` and press Enter.
- **Blank-sheet hint:** an unobtrusive, theme-aware overlay on an empty sheet
  points to the key gestures (type to enter data, `=` for a formula,
  `Ctrl+Shift+P` / `F1` / `Ctrl+K`); it disappears the moment a cell is filled.
- **Paste Special** (Edit → Paste special…, `Ctrl+Alt+V`): paste **values only**
  (dropping formulas), **transpose** rows ↔ columns, and/or **skip blanks** so
  empty source cells don't overwrite the destination.
- **Connected Data — external data sources.** New importers (File menu + command
  palette): **web table** (fetch a page and import its largest HTML `<table>`, pure
  stdlib), **REST API** (pull a JSON endpoint's records — dotted records-path,
  headers/bearer), and **SQL database** (PostgreSQL / MySQL via the optional
  `database` extra — `psycopg` / `PyMySQL`; connection secrets are held in memory
  only, never persisted).
- **Headless notebook execution** — `abax notebook run FILE [-o OUT]` runs a
  Jupyter notebook against abax's own shell (no `nbclient`) and writes the executed
  outputs back into the `.ipynb`. The **kernel** now answers `do_complete` /
  `do_inspect` (Python-namespace completion, formula completion after `=`).
- **`abax doctor`** — an aggregated health report: Python/platform, the optional-
  dependency matrix, the active code-isolation level and available sandbox
  confinement, the runtime directories (and whether they're writable), and whether
  `settings.json` parses.
- **Formula:** `FVSCHEDULE` and `ISPMT`; numeric-overflow now reports `#NUM!`
  (matching Excel/gnumeric) for `FACT`/`FACTDOUBLE`/`MULTINOMIAL`/`COMBIN`/`COMBINA`/
  `PERMUT`/`PERMUTATIONA`/`POWER`/`^` instead of `#VALUE!`. **620 functions**, 96.5%
  of the curated Excel/Gnumeric target.
- **TUI parity:** a **scrolling viewport** (the cursor is no longer pinned near the
  top-left), a **persistent formula bar** showing the active cell's reference and raw
  content, and **sheet switching** (`gt` / `gT`, `:sheet <name|index>`, `:sheets`) so
  multi-tab `.xlsx`/`.ods` workbooks are navigable over SSH.
- **Print / PDF export** (File → Print, `Ctrl+P`; File → Export PDF…): render the
  active workbook to a printer or a PDF.
- **Format painter** (Format → Copy / Paste format): copy a cell's style and number
  format onto the selection in one undo step.
- **RF radiation pattern** in the Antenna Modeler (Tools → Radio): plot an
  azimuth/elevation cut of the current model (built-in Method-of-Moments, or PyNEC
  when installed) as a polar chart, and write the samples to the sheet — labelled
  **(free space)**, since without ground reflection the elevation cut is not an
  installed-height take-off pattern.
- **In-cell argument hints:** editing a formula directly in a cell now shows the same
  function signature tooltip the formula bar shows.

### Fixed
- **Number-format changes are now undoable** (a missing document checkpoint meant
  `Ctrl+Z` couldn't revert a number-format change).

### Performance
- **Incremental recalc now survives dynamic arrays (Phase B).** Previously a single
  spilling formula (`SEQUENCE`/`UNIQUE`/`SORT`/`FILTER`/…) anywhere in a workbook
  forced a full-workbook cache clear on *every* keystroke. Now only edits that
  actually interact with a spill fall back to the full clear; unrelated edits stay
  precisely scoped even when spills exist elsewhere. Sound by over-approximation and
  proven equal to a full recalc by a differential fuzz over spilling workbooks.

### Changed
- **Discoverability:** menu items now show a status-bar hint (with the shortcut)
  on hover, and the icon-only toolbar's tooltips spell out each button's keyboard
  shortcut.

### Removed
- Dropped two settings fields that were never read (`column_width` and the
  obsolete `faceplate_repo`); a schema migration (v3 → v4) strips them from
  existing `settings.json` files on next load. No user-facing change.

## [0.1.5] — 2026-07-02

_A UI refinement release: a centralized Preferences hub, a fully theme-aware and
HiDPI-crisp icon set, mouse/discoverability improvements, and — importantly —
optional features are now truly opt-in._

### Added
- **Centralized Preferences** (Edit → Preferences, `Ctrl+,`): every persistent
  setting in one tabbed dialog — **Appearance** (GUI + TUI theme, OpenDyslexic
  font, zoom, toolbar, vim keys), **Calculator** (default model, faceplate style,
  angle mode, faceplate folder), **System** (autosave, code isolation, optional
  dependencies). Includes a **code-execution consent** control — grant or **revoke**
  the permission that gates the console / terminal / scripts / macros (enabling it
  confirms first), previously only settable by hand-editing `settings.json` — and a
  **Manage optional features…** button.
- **Mouse & discoverability:** File → **Open Recent** (the tracked recent-files list
  was never surfaced); **double-click a column/row border to autofit**; **Autofit**
  entries and click-to-select in the header right-click menus; **Select All**
  (`Ctrl+A`); a **Command palette** entry in Help; header tooltips advertising the
  right-click menus; and a startup status-bar hint (`Ctrl+Shift+P` / `F1` / `Ctrl+K`).
- **Icons:** directional structure glyphs (insert row above/below, column
  left/right), the previously-blank **cut** and **conditional-format** icons, and
  distinct ascending/descending **sort** icons.
- **Native-crash logging:** on a fatal signal (segfault, access violation) that
  bypasses the Python excepthook, `faulthandler` now dumps a stack to
  `DATA_DIR/crash.log`.

### Changed
- **Optional features are now opt-in.** The first-run chooser selects **nothing** by
  default (it used to default to "All"); the presets (Thin / All) are one click and
  neither is nudged as "recommended"; the base is complete on its own. Reachable any
  time from Tools → Install optional features or Preferences → System. Docs updated
  throughout — abax never installs anything unprompted.
- **Icons are theme-aware and HiDPI-crisp.** Glyphs tint from the active abax theme
  (not the OS palette) and **re-tint live** when the theme changes; rendering is
  device-pixel-ratio aware and painter-scaled to size. Plus a redraw/polish pass
  (grid → 2×2 lattice, bolder insert/delete marks, redrawn pivot / stats / histogram
  / command-palette glyphs, a consolidated accent vocabulary, box-fit and crispness
  cleanups).
- **About dialog** now notes the name's origin — Ancient Greek _ábax_ (ἄβαξ), a
  reckoning tablet and the root of _abacus_.

### Fixed
- **Theme / number-format / macros menus crashed when chosen by mouse.** Loop-built
  menu actions bound `QAction.triggered`'s `checked` bool into their captured
  variable (e.g. `set_theme(False)`), which then crashed. The bool is now absorbed.
- Right-clicking a column/row header targeted the previous selection instead of the
  clicked header.
- The toolbar's View-menu checkmark could go stale when the toolbar was toggled from
  Preferences; a dyslexic-font **Cancel** could revert against a state that never
  applied (e.g. offline).
- Changelog release links point at the renamed GitHub repository (`/abax`).

## [0.1.4.1] — 2026-07-02

_Patch: a crash in CSV **streaming** on Python 3.11/3.12, caught by the new CI
matrix on its first run._

### Fixed
- **CSV streaming on Python 3.11 / 3.12.** `csv_stream.py` used
  `Path.read_text(newline="")`, but the `newline=` keyword on `read_text()` only
  exists on Python 3.13+ — so streaming a CSV raised `TypeError` on 3.11/3.12.
  Now uses `Path.open(newline="")`, which works on every supported Python.
  (Regular, non-streaming CSV loading was unaffected.)
- **CI / tests:** the multi-OS × multi-Python CI matrix went green — the justfile
  interpreter is now overridable (`JUST_PYTHON`) so a runner's `py` launcher can't
  pick a Python without the dev deps; the macOS `RLIMIT_AS` sandbox tests are
  restricted to Linux (macOS doesn't enforce it); and the Windows strict-
  AppContainer e2e test is skipped on hosted runners (verified on real Windows).

## [0.1.4] — 2026-07-02

_A large feature release: incremental recalculation, deeper formula & `LAMBDA`
support, a broad data-science / RF / calculator / TUI wave, new import formats,
and quality tooling (CI matrix, benchmark + coverage gates)._

### Added
- **Nonparametric & rank statistics** (`core/science/nonparam.py`, pure stdlib):
  Mann-Whitney U, Wilcoxon signed-rank, Kruskal-Wallis H, Spearman ρ and
  Kendall τ-b — each with a two-sided p-value and tie handling, oracle-tested
  against known values. Exposed as `nonparam` in the Python console. Fills a
  real gap: parametric tests were strong but rank tests needed scipy.
- **Distribution charts** in the pure-stdlib SVG grapher
  (`core/science/chartsvg.py`): **box-and-whisker**, **violin** (Gaussian KDE),
  **normal Q-Q**, **ECDF**, and a **correlation heatmap** (viridis) — the four
  distribution views an analyst reaches for first, plus a heatmap. Offered from
  the Graph dialog; works in the cold-start `.pyz` and TUI SVG export.
- **REGEX text functions** — `REGEXTEST`, `REGEXEXTRACT` (first / all-spilling /
  capture-group modes), `REGEXREPLACE` (`core/regex_fns.py`, Python `re`,
  cached compile, `re.error` → `#VALUE!`). Registry: **584 → 587**.
- **Antenna Modeler dialog** (*Tools → Radio → Antenna modeler*) — a GUI over
  the built-in Method-of-Moments solver (`core/science/wire_mom.py`): define a
  dipole or Yagi and read gain (dBi), front-to-back (dB), feed-point impedance,
  and a polar radiation pattern. Surfaces a solver that was built and tested but
  previously reachable only from the console (sanity: ½λ dipole ≈ 2.15 dBi/85 Ω,
  3-element Yagi ≈ 7.6 dBi, F/B ≈ 25 dB).
- **ADIF logbook** — `.adi`/`.adif` files open and save as sheets (*Tools →
  Radio → Open logbook (ADIF)*), with best-effort `CALL → DXCC` entity
  enrichment on open. The ADIF engine existed but was console-only.
- **HP-15C statistics registers** — Σ+/Σ-/mean/std-dev/L.R. (linear regression)/
  lin-est,r now work on the 15C float RPN engine (they were unimplemented
  `_PROGRAM_KEYS`), reusing the HP-12C's proven accumulator pattern.
- **Transmission-line RF functions** — `ZINLINER`/`ZINLINEX` (real/imag of a
  lossless line's input impedance, mirroring the `DIPOLER`/`DIPOLEX` pair) and
  `LINELOSS` (matched line loss, dB), backed by `rf_math.zin_line` /
  `line_loss_db` plus a `stub_match_short` helper. Oracle-tested on the classic
  λ/4 impedance inversion and λ/2 repeat. Registry: **587 → 590**.
- **HP-15C `SOLVE` and `∫`** — immediate-mode root-finding (hybrid
  secant/bisection with automatic bracketing) and adaptive-Simpson integration
  on the Voyager engine, backed by new pure-stdlib `core/science/numeric.py`
  routines (root of x²−2 → √2, ∫₀^π sin → 2, all to 1e-6).
- **TI calculator STAT** — an L1–L6 list store with **1-Var Stats** (mean, Σx,
  Σx², sample/population sd, five-number summary), **2-Var Stats**, and
  **LinReg(ax+b)** (slope, intercept, r, r²), reusing the `core/science` stats
  and regression helpers.
- **Preferences dialog** (*Edit → Preferences…*, `Ctrl+,`) — a tabbed panel for
  theme, dyslexic font, default zoom, autosave (now on/off + interval, no longer
  hardcoded at 30 s), and the code-isolation level. Persists to `settings.json`
  via the existing loader (schema bumped to v3; older files take the defaults);
  appearance applies live.
- **Cell comments / notes** — attach a note to any cell (right-click →
  *Insert/Edit/Delete comment*). Commented cells show a small marker and expose
  the note as a tooltip; comments are metadata (not formula inputs), shift with
  row/column insert-delete, and round-trip in the `.abax` envelope. Undo/redo
  covers them.
- **Stata / SPSS import** — open `.dta`, `.sav` (plus `.zsav`/`.por`) straight
  into the grid via the optional **`pyreadstat`** package (`pip install
  abax[stats-io]`, in the full-fat set). Variable names become the header row;
  without the package the rest of the app is unaffected and the reader shows a
  clear install hint — the engine-layer adapter pattern used for `.7z`/Parquet.
- **Goal Seek** (*Data → Analyze → Goal seek…*) — find the input value that drives
  a formula cell to a target, by root-finding on `core/science/numeric.solve_root`
  (the same solver behind the HP-15C `SOLVE`). Restores the cell unchanged if no
  solution is found.
- **Descriptive Statistics** (*Data → Analyze → Descriptive Statistics…*) — a
  one-click summary of a range (count, sum, mean, median, mode, min, Q1, Q3, max,
  range, sample/population variance & sd, skewness, kurtosis), shown in a table or
  written to a new sheet. Pure-stdlib `core/science/descriptive.py`.
- **Curve fitting** (*Data → Analyze → Curve fit…*) — least-squares **linear /
  polynomial(n) / exponential / power** fits over an X/Y selection, reporting the
  coefficients and R² and optionally writing a fitted-values column. Pure stdlib
  (own Gaussian elimination, no numpy) in `core/science/curvefit.py`.
- **Smith chart** (*Tools → Radio → Smith chart → SVG…*) — a pure-stdlib SVG
  Smith chart (`core/science/smithsvg.py`): constant-R/X circles, each load
  plotted at its reflection coefficient Γ, and an optional constant-VSWR circle.
- **Direct `LAMBDA` calls** — `=LAMBDA(x, x*x)(5)` → 25 now works: a `LAMBDA(...)`
  (or any expression that yields a lambda) can be applied inline, and calls
  chain (`=LAMBDA(a,LAMBDA(b,a+b))(3)(4)` → 7). A new `Call` AST node + a parser
  postfix layer; ordinary `SUM(A1:A3)` calls are unchanged.
- **Cluster-count selection** — for the clustering tools, an **elbow** curve and
  **silhouette** sweep (k-means) plus **BIC/AIC** model selection (GMM) suggest
  how many clusters to use; surfaced in the ML dialog and the console.
- **Optional `LAMBDA` parameters + `ISOMITTED`** — a `LAMBDA` may now be called
  with fewer args than declared; the trailing params are *omitted*, and
  `ISOMITTED(param)` tests for that, enabling default-argument patterns like
  `=LAMBDA(a,b, IF(ISOMITTED(b), a, a+b))`. Registry: **590 → 591**.
- **HDF5 import** — open `.h5`/`.hdf5` files via the optional **`h5py`** package
  (`pip install abax[hdf5]`, in the full-fat set): each tabular dataset loads
  into its own sheet. Graceful fallback when the package is absent — the same
  engine-adapter pattern as the Stata/SPSS and Parquet readers.
- **7-Zip (`.7z`) archives in the file manager** — a **7z** button compresses the
  selection, **Extract** handles `.7z`, and **Open in archive** lists a
  `.zip`/`.tar`/`.7z`'s contents and opens a supported member (CSV, Excel,
  Parquet, ODS, `.abax`, …) straight into the grid. Needs the optional **`py7zr`**
  package (`pip install abax[sevenzip]`, in the `thin`/`all` sets); without it
  `.zip`/`.tar` still work and the 7z actions show an install hint. Engine-layer
  adapter (`engine/archive7z.py`) behind a unified facade; extraction keeps the
  zip-slip guard.

### Changed
- **Faster `used_bounds()`** — the sheet extent (used on every grid refresh,
  export, and TUI render) is now tracked incrementally instead of re-scanned:
  ~0.4 µs/call on a 10,000-cell sheet, independent of size.
- A generated **function-coverage dashboard** (`scripts/function_coverage.py` →
  `docs/function-coverage.md`) reports formula parity vs. the common Excel /
  Gnumeric set (currently ~96%).
- **Manual / automatic calculation mode** (*Data → Calculation: auto/manual*).
  In manual mode an edit updates only the edited cell and defers all dependent
  recalculation until **F9** (`Shift+F9` for the active sheet) — the escape hatch
  for very large sheets. Switching back to auto flushes the pending edits.
- **Grid screen-reader accessibility** — the grid now exposes accessible
  text/description for every cell (its A1 address + value, and the formula when
  present) and for row/column headers, so a screen reader can drive it.
- **Recalculation is now incremental.** Editing a cell used to clear *every*
  sheet's value cache, so the next repaint re-evaluated the whole workbook. A new
  reverse-dependents index (`core/depgraph.py`) inverts a formula's precedents,
  so an edit invalidates only the cells that can actually be affected — the
  edited cell and the transitive closure that reaches it (cross-sheet edges
  included). On a 3,000-cell sheet, an edit-plus-repaint drops from ~340 ms to
  ~18 ms (~19×). Soundness is by over-approximation: volatiles (`NOW`/`RAND`…),
  dynamic refs (`INDIRECT`/`OFFSET`), defined-name references, unknown macros,
  and any workbook that currently spills fall back to the exact previous
  blanket-clear, so no stale value is ever served (proved by a differential
  fuzz test vs. full recalc). Set `ABAX_INCREMENTAL=0` to restore the old path.
- **`IFERROR` / `IFNA` are now array-aware.** They catch errors **element-wise**
  over a spilled array (like the array-aware `IF`), so
  `=IFERROR(A1:A100/B1:B100, 0)` guards a whole column — previously per-cell
  errors inside a spill survived uncaught.
- **TUI: undo/redo, a help overlay, and range plots.** Destructive TUI actions
  now checkpoint, so `u` / `Ctrl-R` (and `:undo`/`:redo`) work; `?` / `:help`
  opens a scrollable list of every key and command; and `:plot A1:A50 [B1:B50]`
  graphs a sheet range (the expression form still works).
- **TUI visual selection mode.** `v` selects a cell range (`V` whole rows),
  movement keys / arrows extend it from the anchor, and the status line shows a
  live **sum / count / average** of the selection; `y` yanks it, `d`/`x` clear it
  under an undo checkpoint, `Esc` cancels.
- **Pivot tables go deeper.** `pivot_table` gained **grand-total margins**
  (recomputed from the pooled raw cells, so a mean/median margin is the true
  aggregate — not a mean of means), **multiple value fields** with per-field
  aggregators, and **percent-of-total** (grand / row / column). The pivot dialog
  exposes margins and % of total; all new parameters are optional, so existing
  calls are unchanged.

## [0.1.3] — 2026-07-01

### Added
- **Code execution is isolated at a level you choose** — a new
  **`code_isolation`** setting (palette: *Cycle code isolation (off / isolated /
  strict)*) with three levels:
  - **off** — run the console / scripts / macros **in-process**, no worker and
    no limits (fastest, full access, no crash isolation).
  - **isolated** *(default)* — the out-of-process, resource-limited worker
    (crash + resource isolation, not a security boundary).
  - **strict** — **Phases 3 & 4: a real, opt-in OS boundary**. The worker runs
    inside the platform's OS sandbox — a **Windows AppContainer**, **Linux
    bubblewrap**, or **macOS sandbox-exec** — with **no network** and filesystem
    writes confined to a private scratch dir. It is **fail-closed**: after the
    sandbox is applied the worker runs a live escape self-test (tries to write
    outside scratch and open a socket) and *refuses to run code* if either
    succeeds, and refuses if no OS confinement is available on the platform — so
    strict mode is a genuine boundary or nothing, never a pretense. The Windows
    AppContainer path is verified end-to-end (worker runs; user code is denied
    home-writes and network; ACL grants + profile reverted on teardown). When no
    OS sandbox is available, the **Phase 4** AST-allowlist executor
    (`restricted.py`) offers *labelled hardening* (not a security boundary)
    against accidental harm. Also settable via `ABAX_SANDBOX_STRICT=1`.
- **Code-execution sandbox — Phases 1 & 2** (see `dev/sandbox-design.md`). The
  GUI's **script runner and command macros now run out-of-process** in the same
  isolated worker as the Python console (`console_worker.py` grew `exec` /
  `script` / `macro` ops; `ConsoleBridge` grew `execute_script`/`execute_macro`),
  so a crash, hang, or runaway there is contained and can't take down abax — the
  in-process `exec()` gap is closed. The worker is now **resource-limited**
  (`abax/proclimits.py`): a Windows **Job Object** (process-memory / CPU-time /
  active-process caps + kill-on-job-close) or POSIX **`rlimit`s**
  (`RLIMIT_AS`/`_CPU`/`_FSIZE`/`_NPROC`), plus a wall-clock **watchdog timeout**
  in the bridge — an allocation bomb, fork bomb, or infinite loop is killed by
  the OS instead of wedging the machine. Caps are tunable via `ABAX_WORKER_MEM_MB`
  / `_CPU_S` / `_FSIZE_MB` / `_PROCS` / `_NPROC` (generous defaults). This is
  **crash and resource isolation, not a security boundary** — the worker still
  runs with your privileges; OS filesystem/network confinement (strict mode) is
  the planned Phase 3. The consent prompt and docs are updated to say so plainly.
- **Array constants.** Inline literal arrays with braces — `={1,2,3}` (a row),
  `={1;2;3}` (a column), `={1,2;3,4}` (a block). They spill and compose like any
  array: `=SORT({3,1,2})`, `=SUM({1,2,3,4})`, `={1,2,3}*10`.
- **`IF` broadcasts over an array condition.** `=IF(A1:A9>0,"+","−")` spills a
  result per row and `=SUM(IF(A1:A9>0,A1:A9,0))` works directly — the classic
  array-formula idiom without Ctrl+Shift+Enter.
- **Matrix functions that spill** — `MMULT` (product), `MINVERSE` (inverse, or
  `#NUM!` when singular), `MUNIT(n)` (identity), backed by the existing
  `core/science/matrix` solver. They compose too: `=SUM(MMULT(A1:B2,D1:E2))`.
- **Array arithmetic & broadcasting.** Operators now apply element-wise across
  array operands and spill the result: `=A1:A3*2`, `=10+A1:A3`, `=A1:A3>9` and
  even outer products like `=A1:C1*E1:E2` (a row × a column) all work. Shapes
  broadcast numpy-style (a dimension must match or be 1); incompatible shapes
  give `#VALUE!`. A knock-on benefit: `=FILTER(A1:A9, A1:A9>100)` now works,
  because the comparison yields a boolean array.
- **Spill-range reference `A1#`.** `A1#` refers to the whole array that spilled
  from anchor `A1` — `=SUM(A1#)` totals a dynamic spill, `=A1#` mirrors it, and
  the reference tracks the source as it grows or shrinks. A `#` on a non-spilling
  cell gives `#REF!`.
- **Implicit-intersection operator `@`.** `=@A1:A10` returns the single value
  from the range aligned with the calling cell's row/column; `=@SEQUENCE(5)`
  forces a function's first value (opt out of spilling).
- **TI calculator letter variables + ALPHA entry.** The TI-83/84's `STO>` and
  full **ALPHA** keypad now work: press ALPHA then a key to type its green letter
  (A–Z, θ; ALPHA twice = A-LOCK), so `5` `STO>` `ALPHA` `A` stores `5→A` and `A`
  recalls it in later expressions (unset variables read as `0`). A physical letter
  key types the variable too. The remaining TI subsystem keys (STAT PLOT, PRGM,
  CALC, …) report a clear one-line note.
- **Dynamic-array spill.** A formula whose result is an array now *spills* across
  the neighbouring cells: the formula lives in the top-left **anchor** and the
  remaining values fill the range below/right of it. Blocked spills surface as
  **`#SPILL!`** (a non-empty or already-claimed target cell) and an empty result
  (e.g. `FILTER` with no matches) as **`#CALC!`**. Only the anchor's source
  formula is stored — spilled cells are never persisted, so the `.abax` envelope
  round-trips a single `=SEQUENCE(3)` and re-spills on load. The spill map is a
  lazy, memoized pass on the `Sheet` (candidate formulas only, so sheets with no
  array formulas pay nothing) that recomputes on edit and propagates to
  dependents. The GUI paints a dashed blue spill outline; the TUI tints the
  range. `SORT`/`UNIQUE`/`SEQUENCE`/`FILTER`/`TRANSPOSE` and the reshaping family
  now work standalone, not only nested inside an aggregate.
- **14 dynamic-array reshaping functions** (`core/arrayfuncs.py`): **TRANSPOSE**,
  **VSTACK**/**HSTACK**, **TAKE**/**DROP**, **CHOOSEROWS**/**CHOOSECOLS**,
  **SORTBY**, **TOROW**/**TOCOL**, **EXPAND**, **WRAPROWS**/**WRAPCOLS**, and
  **RANDARRAY**. `SEQUENCE(rows, cols)` now returns a 2-D block that spills.
- **Wave H — Gnumeric-parity functions** (~100 new functions across three
  pure-stdlib packs, each oracle-tested; the registry grew 419 → 519):
  - **The R.\* distribution family** (`core/gnumeric_fns.py`): density /
    cumulative / quantile (`R.D…`/`R.P…`/`R.Q…`) for the normal, log-normal,
    exponential, gamma, beta, Weibull, chi-square, Student-t, F, uniform, Cauchy,
    **Gumbel, Laplace, logistic, skew-normal, Rayleigh and Pareto** continuous
    distributions, plus binomial, Poisson, geometric, negative-binomial and
    hypergeometric discrete ones (with quantiles). Built on the existing
    incomplete-gamma/beta backbone.
  - **Special math & number theory** (`core/gnumeric_math.py`): `BETA`,
    `BETALN`, `POCHHAMMER`, `GD` (Gudermannian), and Gnumeric's number-theory
    pack — `ITHPRIME`, `ISPRIME`, `NT_PI` (prime counting), `NT_D` (divisor
    count), `NT_SIGMA` (divisor sum), `NT_PHI` (Euler totient) and `NT_MU` (Möbius).
  - **More statistics** (`core/gnumeric_stats.py`): the `…A` variants
    (`MAXA`/`MINA`/`VARA`/`VARPA`/`STDEVA`/`STDEVPA`), the *exclusive* percentile
    family (`PERCENTILE.EXC`/`QUARTILE.EXC`/`PERCENTRANK.EXC`), `SKEWP`, `KURTP`,
    `COVARIANCE.S`, `RANGE`, `PROB`, and the array-returning (now-spilling)
    `FREQUENCY`, `MODE.MULT`, `TREND`,
    `GROWTH`, `LINEST` and `LOGEST`. `LINEST`/`LOGEST` do **multiple** regression
    (several predictor columns), returning coefficients in Excel's right-to-left
    order; `TREND`/`GROWTH` are single-predictor.
- **Wave I — modern-Excel completeness** (two more oracle-tested pure-stdlib
  packs; the registry grew 519 → 562 eager, **575 names** in all):
  - **Everyday modern Excel** (`core/excel_modern.py`): **`TEXTSPLIT`** (spills
    a row/grid; multi-delimiter, `ignore_empty`, case-insensitive mode, pad
    value), `ARRAYTOTEXT`/`VALUETOTEXT`, **`XMATCH`** (exact / next-smaller /
    next-larger / wildcard; forward or reverse) and the classic **`LOOKUP`**
    (vector + array forms), `CEILING.MATH`/`FLOOR.MATH`, the workhorse
    **`SUBTOTAL`** (1–11 / 101–111) and **`AGGREGATE`** (1–19 with the
    ignore-errors options), `WORKDAY.INTL`/`NETWORKDAYS.INTL` (weekend numbers
    or a `"0000011"` mask), and the complex tail `IMTAN`/`IMCOT`/`IMSEC`/
    `IMCSC`/`IMSINH`/`IMCOSH`/`IMTANH`/`IMSECH`/`IMCSCH`/`IMLOG2`/`IMLOG10`.
  - **The dotted distribution family** (`core/dist_dotted.py`): the left-tail /
    density halves the legacy right-tail names lacked — `NORM.S.DIST`,
    `T.DIST`/`T.DIST.RT`/`T.DIST.2T`, `T.INV`/`T.INV.2T`, `CHISQ.DIST`/
    `CHISQ.INV`, `F.DIST`/`F.INV`, `CONFIDENCE.T` — plus real hypothesis tests:
    **`T.TEST`** (1/2 tails; paired, pooled or Welch), **`Z.TEST`**,
    **`F.TEST`** and **`CHISQ.TEST`** (with the `ZTEST`/`FTEST`/`CHITEST`
    legacy aliases), and the `FORECAST.LINEAR`/`SKEW.P`/`GAMMALN.PRECISE`
    dotted aliases.
  - **The info half of the context family** (`core/reffuncs.py`; 575 → **581
    names**): **`ISREF`**, **`ISFORMULA`**, **`FORMULATEXT`**, **`SHEET`**,
    **`SHEETS`** and **`CELL`** (`address`/`row`/`col`/`contents`/`type`/
    `filename`). These see the raw *reference* and the calling cell, so
    `EvalContext` gained two optional hooks the `Sheet` provides: a raw
    cell-source lookup (backing `ISFORMULA`/`FORMULATEXT`/`CELL`) and a
    sheet-index/count lookup (backing `SHEET`/`SHEETS`).
- **Wave D tail — bond & security financial functions**
  (`core/finance_bonds.py`; 22 new, → **584 eager / 603 names**), each pinned
  to the worked examples in the Excel documentation: the coupon-schedule
  family **`COUPPCD`/`COUPNCD`/`COUPNUM`/`COUPDAYBS`/`COUPDAYS`/`COUPDAYSNC`**
  (walking back from maturity with the end-of-month rule, day-count bases
  0–4), coupon-bond **`PRICE`**/**`YIELD`** (yield inverts price by bisection)
  and **`DURATION`**/**`MDURATION`**, the discounted-security family
  **`DISC`**/**`PRICEDISC`**/**`YIELDDISC`**/**`INTRATE`**/**`RECEIVED`**,
  interest-at-maturity **`ACCRINT`**/**`ACCRINTM`**/**`PRICEMAT`**/
  **`YIELDMAT`**, and the Treasury-bill trio **`TBILLEQ`** (including the
  long-bill semiannual-compounding form)/**`TBILLPRICE`**/**`TBILLYIELD`**.
  The odd-period functions (ODDF*/ODDL*) remain out of scope.
- **`LET`, `LAMBDA` and the functional helpers** (`core/lambda_fns.py`; →
  **611 names**) — modern Excel's named bindings and first-class functions:
  - **`LET(name, value, …, calculation)`** — sequential bindings (later values
    see earlier names, scopes nest and shadow); a LET whose calculation is an
    array *spills*. Powered by an `env` on `EvalContext` that the evaluator's
    `Name` branch consults before erroring — nested scopes are chained child
    contexts, so there is no AST rewriting.
  - **`LAMBDA(params…, body)`** — a first-class function value that closes
    over its defining scope. Used by passing it to a helper or by naming it
    via LET and *calling the name*: `=LET(f, LAMBDA(x, x*x), f(5))` → `25`
    (an unknown function name that matches a bound lambda invokes it). An
    un-applied lambda in a cell shows **`#CALC!`**, like Excel.
  - **`MAP` / `REDUCE` / `SCAN` / `BYROW` / `BYCOL` / `MAKEARRAY`** — the
    functional array helpers; MAP/SCAN/BYROW/BYCOL/MAKEARRAY spill and all
    compose inside aggregates (`=SUM(MAP(A1:A3, LAMBDA(x, x*x)))`).
  - Limitations (documented): no direct-call syntax `=LAMBDA(…)(args)`,
    binding names must not look like cell references (Excel's restriction
    too), and workbook-defined names take precedence over LET names.
- **HP-16C: the immediate bit/word keys are implemented** (were stubs) — `MASKL`,
  `MASKR`, `#B` (bit count), `ABS`, `ASR`, `RMD`, `1's`/`2's` complement, `SB`/
  `CB`/`B?` (set/clear/test bit) and `RLn`/`RRn`. Programming-mode keys (GTO/GSB/
  LBL/…) now report *"programming-mode key (no program memory)"* rather than a
  bare "not implemented".
- **HP-15C: hyperbolic, combinatorics and gradians** — `HYP`/`HYP-1` prefixes
  (sinh/cosh/tanh and inverses), `Cy,x`/`Py,x` (combinations/permutations) and
  the `GRD` angle mode now work; solver/matrix/program keys report a clear
  "needs program/solver memory" message.

### Changed
- **TUI: arrow keys navigate the sheet** alongside the vim keys `h`/`j`/`k`/`l`
  (and drive the function/file browser lists), so you don't have to use vi
  bindings to move around.
- **Code-isolation level is a menu item.** *Tools → Code isolation (sandbox)*
  offers **Off / Isolated / Strict** as checkable options (reflecting the
  current `code_isolation` setting), so the sandbox level is set from the UI
  rather than by editing settings or only via the command palette.
- **The Radio (RF/amateur-radio) menu moved under *Tools*** as a submenu, alongside
  *Scientific*, rather than a top-level menu.
- **The Help → About dialog is more concise** — a short capability summary
  instead of the previous multi-paragraph blurb.
- **The curses TUI works on Windows out of the box.** The `tui` extra now pulls
  in `windows-curses` (via a `sys_platform == 'win32'` marker, so it's a no-op on
  Linux/macOS), so `pip install abax[tui]` then `abax tui` just works — no more
  "curses is unavailable" notice.
- **Faster parallel test runs.** `pytest-xdist` and `pytest-timeout` are in the
  `dev` extra; `just test-fast` runs the whole suite across all cores
  (`pytest -n auto`) — the ~40-minute single-threaded suite finishes in a few
  minutes. (Made reliable by the GUI-window disposal fix below.)
- **Bulk load no longer double-scans cells.** `Sheet.set_cells_bulk` detects
  array-formula anchors inside its existing loop instead of a second full pass,
  restoring CSV/Parquet load speed after the spill engine landed (see
  [`benchmarks/rescout.md`](benchmarks/rescout.md)).

### Fixed
- **GUI tests now dispose their windows.** The `test_gui_*` fixtures built a
  `MainWindow` per test but never tore it down, so a long-lived process
  accumulated live windows until a later test that restyled the whole widget tree
  (the zoom test's repeated global `setStyleSheet`) crawled or segfaulted Qt — a
  pre-existing offscreen-Qt fragility (it reproduces on 0.1.2). The fixtures now
  yield-and-delete their window, and a conftest autouse pass sweeps up any strays,
  so the whole suite runs green in one process again and `just test-fast` is back
  to a plain `pytest -n auto`.

## [0.1.2] — 2026-07-01

### Changed
- **First-run optional-features chooser is truly one-shot.** Dismissing it via the
  window's close button or Esc (not just the Install / Skip buttons) now also marks
  it seen, so it never auto-opens again — matching the code-consent / terminal gate.
  It stays reachable on demand via *Tools → Install optional features*.
- **RF reference panel sends values to the grid** (like the calculator) — the bands
  / CTCSS dialog is now non-modal, and double-clicking a value (or selecting it and
  pressing "Send to cell") writes it into the current grid cell(s) as one undoable
  edit, so you can drop a band edge, wavelength, or PL tone straight into a sheet.
- **PyNEC (reference-grade NEC antenna solver) is now part of the full-fat set.**
  A new `nec` extra (`pip install abax[nec]`) and, since it's included in `all`, the
  background auto-installer now fetches **PyNEC** on a default install — but it stays
  out of `thin`. PyNEC is a compiled C++/SWIG extension without wheels on every
  platform, so the best-effort install can fail silently; abax then keeps using its
  built-in method-of-moments solver. `abax --deps` reports its status.
- **Renamed the project from `qcell` to `abax`.** The Python package
  (`qcell/` → `abax/`), all imports and CLI entry points (`abax`, `abax-kernel`),
  the environment-variable prefix (`QCELL_*` → `ABAX_*`), and the native file
  extension (`.qcell` → `.abax`) all change accordingly.
- **Tokenizer: function names with interior digits now parse** — a name like
  `DEC2BIN`/`BIN2DEC` was mis-lexed (`DEC2` as a cell reference, then `BIN`), because
  the ref pattern matched a letters-then-digits prefix even when more name characters
  followed. Ref-like tokens now require that no name character follows, so
  digit-infix function names tokenize whole (cell refs like `A1`/`Sheet1!A1` and
  trailing-digit names like `LOG10`/`ATAN2` are unchanged).
- **Menu reorganization** — with the RF/ham suite now sizeable, all of it moves out
  of *Tools → Scientific* into a **dedicated top-level `Radio` menu** (RF toolkit,
  Smith chart, antenna pattern, RF reference, I/Q → SVG, PyNEC solver); *Scientific*
  keeps the general-math tools (matrix, solver, signal, ODE, ML). Charting is
  consolidated under *Insert* (chart/graph + export-SVG, previously duplicated in
  *Data → Analyze*), *Data → Analyze* is now purely data-science (stats, SQL,
  profile, pandas, recode, pivot, goal-seek), the HTML-report export moves to *File*
  and workbook-compare to *Data*. Command palette and shortcuts are unchanged.
- **File manager: Worker-style button bank** — the dual-pane manager's toolbar is
  reorganized into Worker's two banks plus a utilities row. Row 1: **Home**, **F3
  View**, **F4 Edit**, **F5 Copy**, **F6 Move**, **F7 New dir**, **F8 Delete** (the
  function keys are live shortcuts); row 2: **/** (filesystem root), **All**,
  **Invert**, **Start prog**, **Duplicate**, **Reload**, **Find file**, **Dirsize**.
  New actions: view/edit a file in place, select-all / invert, duplicate into the
  same pane, run an ad-hoc program (with the `{dir}`/`{sel}`/… placeholders), and a
  recursive directory-size readout (new pure-stdlib `fileops.tree_size`).
- **Name-resolved formula ASTs are cached** — on a workbook with any defined name,
  every formula evaluation used to re-walk and rewrite its whole AST to substitute
  named ranges (on each `get_value`, defeating the parsed-AST cache), and the guard
  that gated it rebuilt a sorted list just to test emptiness. The name registry now
  carries an O(1) version counter, and each cell memoizes its name-resolved AST,
  re-resolving only when its formula text or the registry actually changes.
  Workbooks with no defined names skip the path entirely. No behaviour change.
- **`core/functions.py` split into a `functions/` package** (maintainability; no
  behaviour change) — the ~1850-line module becomes a package: the shared coercion
  toolbox (`helpers.py`), the spreadsheet-function implementations (`builtins.py`),
  the RF/ham domain functions (`rf.py`), and the two registries assembled in
  `__init__.py`. `FUNCTIONS` / `LAZY_FUNCTIONS` and the helper re-exports macros rely
  on are unchanged; a golden test pins the exact registry (201 + 6).
- **Formula-engine hot-path optimizations** — `RangeValue.flat()` memoizes its single
  materialization (a range flattened more than once in a formula — SUMPRODUCT, AND/OR,
  COUNTIF — is ~50× cheaper on the repeats); `Sheet.used_bounds()` (called on every
  grid refresh/export/render) walks the cell dict once instead of twice; and
  `CORREL`/`SLOPE`/`SUMPRODUCT` coerce each value once instead of repeatedly. No
  behaviour change.
- **Optional dependencies: a first-run chooser, then on-demand install** — a new
  `qcell/autodeps.py` installs optional packages (the data-science stack,
  Excel/Parquet I/O, the PTY terminal, Jupyter integration) in a best-effort
  background thread, attempted once per machine. On **first GUI launch** qcell shows
  a **chooser** that explains each optional feature and offers two presets —
  **Thin** (lean, ~25 MB) and **All** (everything, recommended) — plus a checkbox
  per feature, so the user decides what's fetched instead of it happening silently.
  The choice is remembered and re-openable from **Tools → Install optional
  features**. The heavy Bayesian stack (`pymc`) is now its own **`bayes`** extra
  (kept in `[all]`). Headless/TUI shows a one-time notice pointing at **`qcell
  deps`** (install everything) or `pip install qcell[…]`. Controls: the
  `auto_install` / `deps_prompted` settings and the `QCELL_NO_AUTOINSTALL`
  environment variable. The Qt GUI binding is the one thing not auto-installed (you
  need it to launch the GUI). `qcell --deps` reports the state and package count.
- **Optional numpy aggregate accelerator** — when numpy is installed, `SUM`,
  `AVERAGE`, `MIN`, `MAX`, `PRODUCT`, `SUMSQ` and `COUNT` over a large
  (≥4096-cell) range that is wholly finite-numeric are reduced with numpy's
  vectorized kernels (~3–4× faster than the Python loop). The accelerator lives in
  the engine layer (`engine/npkernel.py`) and is injected through the
  `qcell._runtime` seam, so the stdlib core never imports numpy. Any range with
  text, blanks, errors or NaN transparently falls back to the exact stdlib
  reducer, so results are unchanged — this is pure speed.
- **`mixin_document` split** (maintainability; no behaviour change) — the
  ~900-line document mixin is now two: file lifecycle (new/open/save/import, the
  background `IOWorker` plumbing, recent-files and window title) moves to a new
  `DocumentIOMixin` in `gui/mixin_io.py`, leaving `DocumentMixin` focused on the
  table↔sheet sync and cell-editing surface. The window composes both; no public
  behaviour changes.
- **Aggregate fast-path** — `SUM`, `AVERAGE`, `MIN`, `MAX`, `PRODUCT`, `MEDIAN`,
  `SUMSQ`, `COUNT` and the descriptive-stats family now walk a range **once**,
  building only the numeric list instead of materializing the full value list and
  then scanning it twice. For a large range (e.g. `SUM(A1:A100000)`) that removes
  two whole-range allocations. Behaviour is byte-for-byte identical — a property
  test pins it against the previous implementation over thousands of random inputs
  (errors, booleans, text, blanks, nested ranges), and a benchmark gate guards the
  speed.

### Added
- **Reference / context functions** — `ROW`, `COLUMN`, `ROWS`, `COLUMNS`, `OFFSET`,
  `INDIRECT` and `ADDRESS` (`core/reffuncs.py`). These need the *calling cell* and the
  raw argument **reference** (ROW(A1) is 1, not A1's value), so the evaluator gained a
  third calling convention: an `EvalContext` (the 0-based calling cell + resolver) is
  threaded through evaluation and handed to a `CONTEXT_FUNCTIONS` registry. OFFSET and
  INDIRECT return live ranges that compose inside aggregates (`SUM(OFFSET(A1,0,0,3,1))`).
- **~180 new formula functions toward Excel / Gnumeric parity** (223 → 405) across
  five pure-stdlib packs, each registered into the `functions/` package:
  - **Math / trig / info** (`core/math_fns.py`, 43): hyperbolic & reciprocal trig
    (SINH…COTH, SEC/CSC/COT), EVEN/ODD/MROUND/QUOTIENT/SQRTPI, COMBIN/COMBINA/
    PERMUT/PERMUTATIONA/MULTINOMIAL/FACTDOUBLE, SUMX2MY2/SUMX2PY2/SUMXMY2/SERIESSUM,
    ROMAN/ARABIC/BASE/DECIMAL, GAMMA/GAMMALN, and the IS*/N/TYPE/ERROR.TYPE family.
  - **Statistics & distributions** (`core/stats_dist.py`, 46): the distribution set
    (BINOM/NEGBINOM/POISSON/HYPGEOM/EXPON/GAMMA/BETA/WEIBULL/LOGNORM, dist + inverse,
    legacy and dotted names), DEVSQ/AVEDEV/AVERAGEA/TRIMMEAN/PERCENTRANK/STANDARDIZE/
    STEYX/PEARSON/FISHER, RANK.EQ/RANK.AVG, and the conditional aggregates
    **SUMIFS/COUNTIFS/AVERAGEIFS/MAXIFS/MINIFS**.
  - **Text & date/time** (`core/text_datetime_fns.py`, 19): TEXTJOIN/TEXTBEFORE/
    TEXTAFTER/CLEAN/UNICHAR/UNICODE/DOLLAR/FIXED/NUMBERVALUE; TIME/TIMEVALUE/
    DATEVALUE/EOMONTH/WORKDAY/NETWORKDAYS/WEEKNUM/ISOWEEKNUM/YEARFRAC/DAYS360.
  - **Financial** (`core/finance_fns.py`, 25): the time-value-of-money set
    (FV/PV/PMT/IPMT/PPMT/NPER/RATE), cashflow analysis (NPV/IRR/XNPV/XIRR/MIRR/
    CUMIPMT/CUMPRINC), depreciation (SLN/SYD/DB/DDB/VDB) and EFFECT/NOMINAL/
    DOLLARDE/DOLLARFR/PDURATION/RRI.
  - **Engineering & database** (`core/engineering_fns.py`, 39): base conversions
    (BIN/OCT/DEC/HEX, all 12), bitwise (BITAND/OR/XOR/LSHIFT/RSHIFT),
    DELTA/GESTEP/ERF/ERFC and Bessel (BESSELJ/Y/I/K), and the database D-functions
    (DSUM/DCOUNT/DCOUNTA/DAVERAGE/DMAX/DMIN/DGET/DPRODUCT/DSTDEV/DSTDEVP/DVAR/DVARP).
  - Plus **16 modern dotted aliases** (STDEV.S, VAR.P, NORM.DIST, PERCENTILE.INC,
    COVARIANCE.P, CHISQ.DIST.RT, …) for existing legacy-named functions.
  Each function is oracle-tested against documented Excel/LibreOffice values;
  the shared criteria engine (`core/criteria.py`) backs SUMIF/*IFS/D-functions.
- **SQL over sheets** (*Data → Analyze → SQL query*) — run SQL against the workbook:
  each sheet becomes an in-memory SQLite table (first row = headers, types inferred),
  so `SELECT` / `JOIN` / `GROUP BY` work across sheets; results view in a grid and
  drop into a new sheet. Console `sql(query)`. Pure-stdlib `core/sqlsheets.py`.
- **Column profiler** (*Data → Analyze → Profile columns*) — a per-column report
  (dtype, count, missing, unique, and numeric min/max/mean/median/std) written to a
  new sheet. Console `describe()`. Pure-stdlib `core/profile.py`.
- **SVG charts** (*Data → Analyze → Export chart as SVG*) — pure-Python line / bar /
  scatter / histogram charts with axes and legend (`core/science/chartsvg.py`);
  export the selection or use `chartsvg` in the console.
- **ADIF ham logbook** — open and save `.adi`/`.adif` amateur-radio logs
  (`core/io/adif_io.py`), so File → Open / Save As round-trip a logbook through a sheet.
- **DXCC callsign lookup** — a `DXCC(callsign)` formula function (e.g. `=DXCC("W1AW")`
  → `United States`) backed by a 378-prefix table (`core/science/dxcc.py`); handles
  portable prefixes and operational suffixes.
- **Dynamic-array functions** — `XLOOKUP`, `UNIQUE`, `SORT`, `FILTER` and `SEQUENCE`
  (pure-stdlib `core/arrayfuncs.py`). They return lists that compose inside the
  existing aggregates, so `=SUM(UNIQUE(B1:B4))`, `=COUNT(FILTER(A1:A9, B1:B9>0))` and
  `=SUM(SEQUENCE(5))` work without a spill grid.
- **Goal Seek** (*Data → Analyze → Goal seek*) — set a target cell to a chosen value
  by solving for one input cell (secant with a bracketing-bisection fallback,
  `core/goalseek.py`); the original value is restored if it can't converge.
- **I/Q constellation export** (*Scientific → I/Q constellation → SVG*) — read a
  two-column (I, Q) selection and export the constellation as an SVG, reporting
  power in dBFS. Backed by `core/science/iq.py` (constellation / eye-diagram / EVM /
  power), available in the console as `iq`.
- **Workbook compare** (*Data → Analyze → Compare workbook*) — diff the current
  workbook against another file into a new **Diff** sheet (added / removed / changed
  cells, per-sheet, with a summary). Pure-stdlib `core/wbdiff.py`, console `wbdiff`.
- **HTML report export** (*Data → Analyze → Export as HTML report*) — write the whole
  workbook to a standalone, escaped HTML document (`core/io/html_report.py`, console
  `html_report`).
- **Import from URL** (*File → Import from URL*) — download a remote data file
  (CSV, JSON, Excel, Parquet, …) and open it; the extension is guessed from the URL
  or content type and the file is loaded through the same dispatch as File → Open.
  The download and parse run off the UI thread. Pure-stdlib `core/io/urlfetch.py`,
  console `urlfetch`.
- **Radio math — 16 new RF formula functions** (`core/science/rf_math.py`):
  resonant-circuit component values (`CFROMXC`, `LFROMXL`, `RESONANTC`,
  `RESONANTL`), loaded-Q / bandwidth (`QBW`, `BWQ`), single-layer air-core inductor
  design via Wheeler (`AIRCOILL`, `AIRCOILN`), toroid design from an AL value
  (`TOROIDL`, `TOROIDN`), quarter-wave matching-transformer impedance (`QWMATCH`),
  SWR from forward/reflected power (`SWRPWR`), full-wave loop length (`LOOPLEN`),
  parabolic-dish gain and beamwidth (`DISHGAIN`, `DISHBW`), and Doppler shift
  (`DOPPLER`). SI base units, with function-browser signatures.
- **RF reference panel** (*Scientific → RF reference (bands / CTCSS)*) — a
  filterable view of the US amateur band plan (with width and mid-band wavelength)
  and the 50 EIA CTCSS tones; "Bands → new sheet" drops the band plan into the
  workbook.
- **Optional PyNEC solver** (*Scientific → Solve NEC deck (PyNEC)*) — when the
  optional `PyNEC` package is installed, solve a NEC antenna deck for reference-grade
  feed impedance (`engine/necpy.py`); the built-in method-of-moments solver continues
  to work without it.
- **Budgeting tools** (*Tools → Budget wizard*) — a guided dialog to set up and
  track expenses: enter monthly income, seed categories from the **50/30/20 rule**
  (or start blank), tweak the amounts, and *Create budget sheet*. It drops a **live
  budget worksheet** into the workbook — a Category / Budgeted / Spent / Remaining
  table where **Spent is a `SUMIF`** over an Expenses log and Remaining is
  `Budgeted − Spent`, so logging an expense updates the budget through qcell's own
  formula engine. Backed by a new pure-stdlib `core/budget.py` (model + worksheet
  builder), fully tested including an end-to-end recompute.
- **Dual-pane file manager** (*Tools → File manager*, `Ctrl+Shift+F`) — a Worker /
  Directory Opus-style browser: two independent panes where operations act on the
  active pane's selection with the other pane as the target. Copy / move / delete /
  rename / new-folder, one-click **`.zip` and `.tar.gz` creation** and safe
  extraction, and recursive **find** by name glob and file contents. A row of
  **configurable command buttons** runs shell commands with `{dir}` / `{path}` /
  `{name}` / `{sel}` / `{dest}` placeholders (Worker scripts these in Lua; qcell
  keeps it in Python). Built on new pure-stdlib core modules — `core/fileops.py`,
  `core/archive.py` (zip-slip/tar-slip-safe), `core/filesearch.py`,
  `core/fmbuttons.py` — each fully tested without a GUI.
- **Editable sheet widget (Jupyter roadmap Phase 3)** — `qcell/widget.py` exposes a
  qcell sheet as an interactive grid inside a notebook via **anywidget**:
  `sheet_widget(sheet)` renders an editable HTML table whose cell edits round-trip
  back into the live sheet and recompute formulas. The data-sync core
  (`sheet_state` / `apply_edit` / `apply_edits`) is plain, tested functions over a
  Sheet; anywidget is imported only when the widget is built, so it stays opt-in.
- **qcell as a Jupyter kernel (Jupyter roadmap Phase 2)** — a new `qcell/kernel.py`.
  Its brain, `QcellShell`, runs notebook cells in the qcell console namespace over
  a workbook and returns results already in Jupyter execute-result shape (a
  `richdisplay` mime-bundle + captured stdout), so a Sheet renders as an HTML table
  in JupyterLab. `install_kernelspec()` registers the "qcell" kernel; `python -m
  qcell.kernel` launches it. ipykernel is an **opt-in** dependency, imported only
  at launch — the default lightweight JSON console is unchanged. The shell and
  kernelspec are fully tested; the thin ZMQ glue activates with ipykernel.
- **Notebook validation (Jupyter roadmap Phase 1)** — `engine/nbvalidate.py` checks
  a notebook against the real **nbformat** schema when it's installed, and against
  focused stdlib structural checks otherwise (nbformat version, cell types, the
  4.5 per-cell `id`, code-cell `outputs`/`execution_count`). A regression test pins
  that qcell's own `.ipynb` export always validates.
- **Rich display protocol (Jupyter roadmap Phase 1)** — a new `core/richdisplay.py`
  implements the IPython display protocol (`_repr_mimebundle_` plus the per-format
  `_repr_html_` / `_repr_markdown_` / … hooks, with a `text/plain` fallback). The
  embedded Python console now echoes expression results through it, so an object
  with a rich representation prints readably instead of an opaque `repr` — a
  **Sheet shows as a Markdown table** in the console (and as HTML in Jupyter). Sheets
  gained `_repr_markdown_` for the compact console view.
- **Jupyter notebook fidelity (roadmap Phase 0)** — `.ipynb` export is now valid
  **nbformat 4.5** (per-cell `id`s) and **round-trips losslessly**: the full workbook
  envelope (formulas, multiple sheets, names, styles) rides in the notebook metadata
  and is restored on import, with a graceful markdown-table fallback for foreign
  notebooks. Sheets gained `_repr_html_` so they render as a grid in Jupyter /
  IPython / rich-display contexts. (See the Jupyter compatibility roadmap.)
- **Autocomplete & tab-completion, everywhere** — formula completion now offers the
  workbook's **defined names and sheet names** plus `TRUE`/`FALSE` (not just
  function names); the **in-cell editor** gained the same popup completion as the
  formula bar; the **TUI** completes names/sheets too; and the **Python console**
  gained **Tab completion** over its namespace, Python keywords, and builtins.
  Functions still complete with a trailing `(`; names/sheets/constants insert bare.
- **Ham-radio reference data** — a new `core/science/rf_bands.py` (US Part 97 band
  plan + the 50 standard EIA CTCSS tones) with three formula functions:
  `HAMBAND(freq_hz)` (frequency → band name, e.g. 14.1 MHz → `20m`),
  `CTCSSTONE(n)` (tone number 1–50 → Hz), and `NEARESTCTCSS(freq_hz)` (snap a
  measured tone to the nearest standard).
- **RF / ham-radio formula functions** — ~39 functions backed by a new
  `core/science/rf.py` (pure stdlib): power/level (`DBM2W`, `W2DBM`, `DBADD`,
  `DBUV2DBM`, `SUNIT2DBM`, `NOISEFLOOR`, `NF2NT`…), transmission line & matching
  (`VSWR`, `RETURNLOSS`, `REFLCOEF`, `MISMATCHLOSS`, `Z0COAX`, `VELFACTOR`), link
  budget & propagation (`FSPL`, `FRIIS`, `EIRP`, `FRESNEL`, `RADIOHORIZON`,
  `SKINDEPTH`), reactance/resonance (`XL`, `XC`, `RESFREQ`), wavelength/antenna
  (`WAVELENGTH`, `WL2FREQ`, `DIPOLELEN`, `MONOPOLELEN`, `DBI2DBD`/`DBD2DBI`), and the
  **Maidenhead grid locator** (`GRIDSQUARE`, `GRIDLAT`/`GRIDLON`, `GRIDDIST`,
  `GRIDBEARING`). SI units, with arg-hint signatures; documented in
  [`docs/rf-toolkit.md`](docs/rf-toolkit.md).
- **RF toolkit dialog** (*Tools → Scientific → RF toolkit*) — a mode-switching form
  for **link budget**, **coax line**, **antenna dimensions**, and **L-network
  matching**, with results shown in both metric and imperial where it helps
  (antenna lengths in m and ft).
- **Smith chart** (*Tools → Scientific → Smith chart*) — a QPainter Smith chart that
  plots a load impedance and its reflection coefficient, reports VSWR / return loss,
  and computes the two L-network matching solutions.
- **NEC `.nec` antenna-deck I/O** — `core/science/nec.py` reads and writes NEC2
  decks (GW/GE/EX/FR cards, comments; unknown cards noted and skipped), scaling
  the metre geometry to wavelengths via the frequency card, and solves them with
  the built-in MoM. Round-trips losslessly and reproduces the direct solver, so
  qcell can exchange wire-antenna models with NEC tools (4nec2, EZNEC, xnec2c).
  Available in the console as `nec`.
- **General 3-D multi-wire MoM (antenna Phase C)** — `core/science/wire_mom.py`
  generalizes the dipole solver to arbitrary polyline wires in 3-D: bent wires,
  V / inverted-V antennas, and multi-element parasitic arrays (Yagi-Uda). Adds the
  segment-tangent dot product to the vector-potential term and a midpoint-rule
  far-field (`radiation_vector`, `far_field_intensity`, `front_to_back_db`).
  Validated: it reproduces the dedicated dipole solver to 1e-4, gives the correct
  figure-8 dipole pattern, and a reflector+driven+director **Yagi beams forward at
  ~11 dB front-to-back** with a coupled driven impedance — all from first
  principles. Available in the console as `wire_mom`.
- **Thin-wire Method of Moments (antenna Phase B)** — `core/science/mom.py`: a real
  multi-segment MoM for a center-fed dipole. The current is expanded in
  piecewise-sinusoidal basis functions, the EFIE is tested Galerkin-style (kernel
  integrated by Gauss-Legendre quadrature; a stdlib complex Gaussian solver), and
  the feed impedance is read off the solved current. With a single basis it
  reproduces the induced-EMF impedance to 5 significant figures (a rigorous
  correctness check); with a finer mesh it converges to the physically-correct
  ~85 + 45j Ω of a real 0.5 λ dipole (just past resonance), in agreement with NEC.
  Available in the Python console as `mom`. The next antenna step is bent/multi-wire
  geometries and a PyNEC adapter.
- **Dipole input impedance (induced-EMF method)** — `core/science/antenna_impedance.py`
  computes the center-fed thin-wire dipole impedance in closed form (sine/cosine
  integrals), reproducing the textbook half-wave result **73.1 + j42.5 Ω** and the
  finite-radius shortening to resonance (X = 0 near 0.47–0.48 λ). Formula functions
  `DIPOLER` / `DIPOLEX` (input R / X), `RADRESIST` (radiation resistance) and
  `RESONANTLEN` (resonant length vs wire radius). This analytic model is the
  validation oracle for the multi-segment Method-of-Moments solver above.
- **Antenna pattern math (Phase A)** — `core/science/antenna.py`: analytic far-field
  patterns for centre-fed dipoles and uniform linear arrays (array factor), with
  numerically-integrated directivity/gain (dBi), half-power beamwidth, and polar
  pattern sampling — the first step toward full Method-of-Moments / NEC modeling.
- **Antenna pattern viewer** (*Tools → Scientific → Antenna pattern*) — a QPainter
  polar plot of the analytic patterns (half-/full-wave dipole, uniform linear array)
  with directivity (dBi) and half-power beamwidth readout. The plot now **re-renders
  live** as you edit N / spacing / phase (not only on the Plot button), and it can
  **export the pattern as SVG** (pure-Python `antenna.polar_svg`) or **export a NEC
  `.nec` deck** of the geometry (dipole, or an N-element dipole array with the
  progressive phase as complex feed voltages) at a chosen frequency.
- **Welch power-spectral-density estimate** — `core.science.spectral.welch_psd`
  (averaged Hann-windowed periodograms; lower-variance than a single FFT). Real
  input gives a one-sided PSD; **complex I/Q** input gives the two-sided spectrum
  sorted over −fs/2…+fs/2 — so positive and negative offsets of a quadrature radio
  signal are distinguished. Exposed in the **Signal / data tool** as *Welch PSD dB*,
  where a **two-column selection is read as I/Q** (first column I, second Q).

## [0.1.1] — 2026-06-30

### Added
- **Right-click context menu on the grid** — clipboard (cut/copy/paste, copy as
  Markdown), Insert/Delete row·column, clear, a Format submenu (bold/italic/
  underline, text/fill colour, clear styles), a Number-format submenu, conditional
  format, and a Data submenu (sort, fill series, recode/clean, open selection in
  pandas). All wired to the existing actions.
- **Searchable clipboard history** (`Ctrl+Shift+V`) — a `rofi`/`dmenu`-style palette
  over the copy history: type to fuzzy-filter, Enter pastes the entry at the cursor
  (pinned entries first). Pin/remove/clear live in **Manage clipboard…**.
- **Command palette** redesigned as a `rofi`/`dmenu`-style panel: a search box over
  a live fuzzy-filtered list, fully keyboard-driven (↑/↓, PageUp/Down, Enter, Esc).
- **Base-aware calculator send** — on the programmer (HP-16C) model, *Send to cell*
  writes the value in the current base as **bare digits** (`FF`, `377`, `1010`)
  instead of converting to decimal; decimal mode still sends a plain number.
- **OpenDyslexic now applies across the UI** — menus, dialogs, the grid cells, and
  the Python console (the calculator LCD, painted faceplates, and the terminal keep
  their own fonts).
- **Calculator choice persists** — the chosen model and faceplate style are saved
  (`calc_model` / `calc_style`) and restored on next launch.
- **Install profiles & granular extras** — new `thin` (lean desktop, no heavy data
  libraries) and `all` (everything) extras, plus `terminal`, `parquet`, and
  `science`. Documented installed-size tiers (core < 1 MB, GUI/thin ~0.22 GB,
  all ~0.9 GB; comparable on Windows and Linux).
- Guard so a *Send to cell* re-anchors and scrolls the target into view and reports
  its A1 address (keeps the write visible behind a floating calculator).

### Changed
- **Codebase reorganized into logical subpackages** (maintainability; no behaviour
  change): the flat `core/` is grouped into `core/io` (tabular adapters),
  `core/calc` (calculator engines), `core/science` (numeric/stats/ML), and
  `core/format` (cell formatting); `gui/` gains `gui/dialogs`, `gui/grid`,
  `gui/calc`, and `gui/console`; the `tui.py` monolith becomes a `tui/` package
  (capabilities / themes / commands / editor / keys / render / app). The
  spreadsheet engine and formula machinery stay at `core/` root. Heads-up for code that imports qcell internals: module paths
  moved accordingly (e.g. `qcell.core.csv_io` → `qcell.core.io.csv_io`); the public
  CLI/GUI/formula behaviour is unchanged.
- **GUI dependency is now `PySide6-Essentials`** (no QtWebEngine/Addons) — a
  GUI-only install drops from ~0.65 GB to ~0.22 GB.
- Calculator model list reordered linearly: **Algebraic → HP-12C/15C/16C →
  TI-82/83/84/84 CE** (default model unchanged: HP-16C).
- Calculator "Send to cell(s)" button/menu/palette entries → singular **"Send to
  cell"**; the About box now names the built-in calculators.
- **Help → Keyboard shortcuts** is now a searchable `rofi`/`dmenu`-style palette
  (type to filter by action or key; Enter launches the action), replacing the
  static text dump.
- The code-execution **consent prompt** is clearer: it explains the console runs in
  its own sub-process and suggests a virtual environment for stronger isolation.
- **First launch opens to a clean grid** — the calculator, Python console, and
  terminal no longer auto-open, so a first run isn't a stack of panels and the
  consent prompt only appears when you actually open the console/terminal. Open the
  full layout any time via **View → Open default workspace** (or the panels'
  shortcuts: `Ctrl+K`, `Ctrl+Shift+Y`, `` Ctrl+` ``).

### Fixed
- **Grid copy/cut/paste reliability** — the grid view now handles `Ctrl+C`/`Ctrl+X`/
  `Ctrl+V` directly, so they work even when a focused cell editor or an ambiguous
  menu shortcut would otherwise swallow them.
- **Right-click targets the clicked cell** — right-clicking a cell outside the
  current selection now moves to it (Excel/gnumeric behaviour), so context-menu
  Paste / Clear / Format act where you clicked rather than on the copy source.
- **Menu/label text mangled under OpenDyslexic** — the accessibility font has no
  glyphs for `… → › · ↑ ↓ ● ○`, so Qt fell back to a CJK font with overlapping
  metrics. All rendered GUI labels (menus, the keyboard-shortcuts palette, status
  indicators, dialogs) are now ASCII; the painted calculator faceplates keep their
  own glyphs.
- **Menus/lists pin an explicit UI font** — the theme stylesheet set a font *size*
  with no *family*, so the default (non-OpenDyslexic) chrome could fall back to a
  poorly-hinted font that renders even ASCII text with overlapping metrics. The
  chrome now requests a cross-platform sans-serif stack (Segoe UI / Helvetica Neue /
  Cantarell / DejaVu Sans / …); the monospace console/terminal are untouched, and
  the layer steps aside when OpenDyslexic is enabled.
- **Named ranges and data-validation ranges now follow row/column insert & delete.**
  Previously only cell formulas and conditional-format rules were adjusted, so a
  named range like `Vals = A1:A3` (or a validation region) kept pointing at stale
  coordinates after rows/columns shifted above it. They now shift, clamp on partial
  deletion, and drop when wholly deleted — consistent with formula references. A new
  `test_layering.py` also pins the core/engine/gui import seam after the reorg.
- **Intermittent crash when scrolling quickly** — model growth is now deferred out
  of the scrollbar signal (`QTimer.singleShot`) instead of mutating the model
  mid-scroll.
- **OpenDyslexic now reaches the grid cells** — applied via the cell font role (a
  QSS font-family on the view wasn't honored by the item delegate's painter).
- **OpenDyslexic font download 404** — the fetch URL pointed at the upstream
  `master` branch (renamed to `main`); re-pinned to an immutable commit SHA.

### Removed
- **QtWebEngine + MathJax live equation preview** — too heavy for the install size.
  The equation editor keeps its live Unicode preview and MathML output (pandoc, or
  a built-in subset converter).

### Known issues
- On some font configurations the **Help → Keyboard shortcuts** menu item can still
  render with overlapping/garbled glyphs. The shortcut labels are plain ASCII and the
  chrome pins a sans-serif font, so this looks like a platform menu-rendering quirk
  rather than a content problem; it is cosmetic — the action and the F1 shortcuts
  palette work normally. Tracked for a future release.

## [0.1.0] — 2026-06-29

Initial public release.

- A keyboard-first statistics and data-science workstation built on a scriptable
  spreadsheet: Qt desktop GUI (default), a vim-style curses/Textual TUI, and a
  headless CLI.
- ~150 formula functions (aggregate, stats, statistical distributions, lookup,
  text, date, engineering); cross-sheet references; errors-as-values.
- Wide tabular I/O — CSV/TSV, Excel, ODS, Parquet, SQLite, XML, Markdown, Jupyter,
  R, JSON Lines, and the native `.qcell` envelope.
- Built-in analysis, pivot/recode, graphing, ML tools, a pandas hand-off, RPN /
  graphing / algebraic calculators, macros + UDFs + recording, and an embedded
  Python console.
- Stdlib-only core; every heavier capability is an optional dependency with a
  graceful fallback. Licensed **GPL-3.0-or-later** (PySide6/LGPL default binding).
- Tag-driven CI builds and publishes the wheel, sdist, and `qcell.pyz` to GitHub
  Releases.

[0.1.3]: https://github.com/leavesofgrass/abax/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/leavesofgrass/abax/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/leavesofgrass/abax/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/leavesofgrass/abax/releases/tag/v0.1.0
