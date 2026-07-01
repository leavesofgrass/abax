# Changelog

All notable changes to qcell are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
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

[0.1.1]: https://github.com/leavesofgrass/qcell/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/leavesofgrass/qcell/releases/tag/v0.1.0
