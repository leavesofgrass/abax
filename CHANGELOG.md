# Changelog

All notable changes to qcell are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
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
- **Antenna pattern math (Phase A)** — `core/science/antenna.py`: analytic far-field
  patterns for centre-fed dipoles and uniform linear arrays (array factor), with
  numerically-integrated directivity/gain (dBi), half-power beamwidth, and polar
  pattern sampling — the first step toward full Method-of-Moments / NEC modeling.
- **Antenna pattern viewer** (*Tools → Scientific → Antenna pattern*) — a QPainter
  polar plot of the analytic patterns (half-/full-wave dipole, uniform linear array)
  with directivity (dBi) and half-power beamwidth readout.
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
