# Changelog

All notable changes to qcell are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

## [0.1.1]

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
  `gui/calc`, and `gui/console`. The spreadsheet engine and formula machinery stay
  at `core/` root. Heads-up for code that imports qcell internals: module paths
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

[0.1.1]: https://github.com/leavesofgrass/qcell/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/leavesofgrass/qcell/releases/tag/v0.1.0
