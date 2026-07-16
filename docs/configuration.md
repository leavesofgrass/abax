# Configuration

abax is configured through a single JSON settings file, a handful of environment variables, and a set of platform-correct runtime directories that hold its config, data, cache, and logs. Almost nothing needs configuring to get started — the defaults are sensible and every optional feature degrades gracefully when its dependency is absent — but this page documents every knob: where settings live, what each field does, the environment variables, the theme presets, the on-demand OpenDyslexic font, and pandoc detection for equation rendering.

## Settings file

Settings are stored as JSON in `settings.json` inside abax's config directory (see [Runtime directories](#runtime-directories) below — typically `…/abax/settings.json`). The GUI and TUI load it at startup and write it back when you change a setting. If the file is missing or unreadable, abax silently uses the defaults, so deleting it is a safe way to reset.

JSON encoding uses `msgspec` when the `fast-io` extra is installed and falls back to the standard library otherwise; the behavior is identical either way. The schema is versioned and migrates lazily on read (for example, an old `color_scheme` field is renamed to `theme` automatically and written back).

### Settings fields

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `theme` | string | `"galaxy"` | GUI theme preset (see [Themes](#themes)). |
| `vim_mode` | bool | `true` | Vim-style key bindings, on by default. |
| `tui_theme` | string | `"galaxy"` | TUI color theme. |
| `zoom` | float | `1.0` | GUI zoom factor. |
| `dyslexic_font` | bool | `false` | Use the OpenDyslexic font across the GUI (see [OpenDyslexic font](#opendyslexic-font)). |
| `calc_model` | string | `""` | Last-used calculator model key (e.g. `16c`, `15c`, `ti83`, `alg`); restored on launch. Empty = default (HP-16C). |
| `calc_style` | string | `"image"` | Last-used HP faceplate style (`image` or `vector`). |
| `calc_degrees` | bool | `false` | Calculator Deg/Rad mode, restored on launch. |
| `last_sheet` | int | `0` | Active sheet index, restored on launch. |
| `last_cell` | string | `""` | Cursor cell (A1), restored on launch. |
| `code_consent` | bool | `false` | Whether you've consented to run untrusted code (console/terminal/scripts/macros). Set back to `false` to be prompted again. |
| `code_isolation` | string | `"isolated"` | How code execution is isolated: `off` (in-process, no worker/limits), `restricted` (the out-of-process, resource-limited worker **plus** an AST allowlist applied to your code that blocks OS/filesystem/network access — a language-level block, not an OS boundary; sits between `off` and `isolated` in the cycle; the optional `restricted` extra adds RestrictedPython compile-time guards), `isolated` (out-of-process worker + resource limits), or `strict` (also OS-confine filesystem + network). Cycle it from the command palette; see [Macros & scripting](macros-and-scripting.md). |
| `faceplate_assets_dir` | string | `""` | Folder of calculator faceplate artwork (see [Faceplate assets](#faceplate-assets)). |
| `show_toolbar` | bool | `true` | Show the GUI toolbar. |
| `autosave_enabled` | bool | `true` | Whether the GUI periodically autosaves `settings.json`. |
| `autosave_interval` | int | `30` | Autosave cadence in seconds (when enabled). |
| `recent_files` | list | `[]` | Recently opened file paths. |
| `window_geometry` | dict | `{}` | Saved GUI window position/size. |
| `fm_buttons` | list | `[]` | Your custom file-manager command buttons (`{label, command}`); see [File manager](file-manager.md). |
| `auto_install` | bool | `true` | Auto-install optional dependencies (and show the first-run chooser); see [Auto-install](#auto-install). Set `false` to opt out. |
| `deps_prompted` | bool | `false` | Whether the first-run optional-feature chooser has been shown. Set back to `false` to be asked again. |
| `calc_iterative` | bool | `false` | Resolve circular references by capped fixed-point iteration instead of surfacing `#CIRC!` (off by default, like Excel). |
| `calc_max_iterations` | int | `100` | Maximum iterations for iterative calculation (when `calc_iterative` is on). |
| `calc_max_change` | float | `0.001` | Convergence tolerance for iterative calculation — iteration stops once the largest cell change falls below this. |
| `high_contrast` | bool | `false` | High-contrast accessibility mode. |
| `speak_on_move` | bool | `false` | Speak the active cell aloud on cursor move (GUI + TUI); needs the `tts` extra. |
| `tui_screen_reader` | bool | `false` | Single-line, reader-friendly TUI rendering for screen readers. |
| `plugins_enabled` | bool | `false` | Whether third-party UDF/format plugins (entry points) may load. Off by default — loading runs third-party code with full privileges. |
| `live_data_enabled` | bool | `false` | Whether the `REST`/`WEBSOCKET` live-data formulas may open network connections. Off by default so a workbook opened from disk can never phone home; enable via **Tools → Enable live data** or TUI `:live on`. URLs are limited to http/https/ws/wss. |
| `external_refs_enabled` | bool | `false` | Whether closed-workbook external references (`=[Book.abax]Sheet1!A1`) may read other workbook files. Off by default so an opened file never pulls in others on its own; enable via **Tools → Enable external references** or TUI `:extern on`. Paths resolve relative to the open workbook's folder; only `.abax`/`.json` load. |
| `windowed_store_capacity` | int | `0` | Bounds resident cells **per sheet**, spilling the rest to a private temp file. Three-way: **`0` (default) = Auto** — when a file is opened, only sheets with **≥ 100,000 populated cells** are windowed (at 50,000 resident cells), so small workbooks are untouched; **a positive value** windows *every* sheet at that capacity; **`-1` = never**. A **memory ↔ latency trade-off** that matters for very large data imports (lots of literal cells — ~48% steady-state saving measured on a 125k-cell sheet); formula-heavy sheets see little benefit (the value cache and key index stay resident). Dependency chains evaluate correctly at **any** capacity (up to ~10,000 cells deep — the engine's recursion headroom, independent of this setting). Opening a native `.abax`/`.json` file applies the policy **during the load**: cells stream straight into the windowed store (spilling past-capacity cells as they arrive), so a huge file never materializes fully in memory first — peak usage tracks the parsed file plus the resident window instead of the whole workbook (measured on a 150k-cell file: below even a plain un-windowed load, where the old load-then-migrate path briefly exceeded it). Other formats (CSV, Excel, …) still load into the plain store and then migrate, and changing the capacity on an already-open workbook re-homes its cells likewise — those paths briefly cost extra memory (~1.5× while cells move); the savings are the steady state after it. Undo/redo restore snapshots under the same policy, so a windowed workbook stays on the bounded store across a Ctrl+Z instead of rehydrating into RAM. Set it from **Preferences → System → Performance** (or by hand in `settings.json`). |
| `chart_backend` | string | `"auto"` | How embedded charts (**Insert → Embedded chart (on sheet)…**) render in the GUI: `auto` = matplotlib when it is installed, else the built-in pure-stdlib SVG renderer; `svg` = always the built-in renderer; `matplotlib` = matplotlib, falling back to SVG (with a status-bar hint) when it isn't installed. Both backends draw the same data. Set it from **Preferences → Appearance → Embedded charts**. |
| `schema_version` | int | `7` | Settings schema version (managed by abax). |

You can edit `settings.json` by hand while abax is closed, but you rarely need to: the **Preferences** dialog (Edit → Preferences…, `Ctrl+,`) is the central place to manage every field, grouped into **Appearance** (GUI + TUI theme, font, zoom, toolbar, vim keys), **Calculator** (default model, faceplate style, angle mode, faceplate folder), and **System** (autosave, code-execution consent + isolation, optional-dependency install). Changing settings from the app is the recommended way — it persists and applies without a manual edit.

## Startup script (`init.py`)

For power users, abax runs an optional Python script at `CONFIG_DIR/init.py`
(e.g. `~/.config/abax/init.py`) when the GUI or TUI starts. It's your own
trusted config — like a `.vimrc` or `.pythonrc`, executed with your privileges —
and it receives an `abax` facade for **rebinding keys**, **adding macro-menu
entries**, and **registering custom formula functions**:

```python
# ~/.config/abax/init.py

def to_top(ed):
    ed.row = 0
    ed._reclamp()

# Rebind a key (rebinds override the built-in bindings). Works in every TUI
# mode: "normal", "insert", "command", "rpn", "visual", "browser".
abax.bind_key("normal", "K", to_top, desc="jump to top")
abax.bind_key("insert", "ctrl+w", lambda ed: ed.delete_word(), desc="del word")

# Register a named entry for the macro menu / palette.
abax.register_macro_menu("Uppercase cell", lambda ed: ed.sheet.set_cell(
    ed.row, ed.col, ed.sheet.get_raw(ed.row, ed.col).upper()))

# Register a custom formula function — usable in cells as =DOUBLE(A1).
def double(args):
    return (args[0] or 0) * 2
abax.register_function("DOUBLE", double)
# kind="lazy" receives unevaluated argument nodes (control-flow functions);
# kind="context" receives (arg_nodes, ctx) like ROW/OFFSET. A user function
# may deliberately shadow a built-in of the same name.
```

Bare keys are matched as the literal keystroke, so case matters (`"K"` ≠ `"k"`).
Modifier chords are **normalized**, so `"Ctrl+S"`, `"ctrl+s"` and `"C-s"` all
name the same binding. Rebinds fire in whichever `mode` you registered them for
(the six modes above); in `insert` and `command` mode only non-printable chords
like `ctrl+w` are intercepted, so ordinary typing is never captured. Run
`:map` in the TUI to list all your rebinds, or `:map <mode>` for one mode.

The `action` is called with the editor. A broken `init.py` never blocks
startup — the error is captured and surfaced in the status line, and abax
carries on with its defaults. This is **not** the sandboxed code-execution path
(console/macros); it is your own config, trusted by design.

## Runtime directories

abax never hardcodes paths. It resolves four OS-appropriate directories at startup and creates them if needed. When the `platformdirs` package (from the `fast-io` extra) is installed it uses that; otherwise a built-in fallback mirrors the same logic.

| Directory | Holds |
|-----------|-------|
| **CONFIG** | `settings.json`, the `macros/` folder for auto-discovered macros. |
| **DATA** | Persistent application data — an `exchange/` subfolder for the generic JSON interchange format, and `crash.log` (a stack dump written on a native / Qt crash). |
| **CACHE** | Downloaded assets — the OpenDyslexic font (`fonts/`). |
| **LOG** | Log files. |

Typical locations per platform:

| Platform | CONFIG | DATA | CACHE | LOG |
|----------|--------|------|-------|-----|
| Windows | `%APPDATA%\abax` | `%LOCALAPPDATA%\abax` | `%LOCALAPPDATA%\abax\Cache` | `%LOCALAPPDATA%\abax\Logs` |
| macOS | `~/Library/Application Support/abax` | same as config | `~/Library/Caches/abax` | `~/Library/Logs/abax` |
| Linux | `$XDG_CONFIG_HOME/abax` (`~/.config/abax`) | `$XDG_DATA_HOME/abax` (`~/.local/share/abax`) | `$XDG_CACHE_HOME/abax` (`~/.cache/abax`) | `…/abax/logs` |

To see the exact paths on your machine, run:

```bash
abax --deps
```

It prints the config, data, cache, and log directories at the bottom of the report (see [cli.md](cli.md)).

## Environment variables

### `ABAX_QT_BINDING`

Forces which Qt binding the GUI uses. abax prefers **PySide6** (LGPL) and falls back to **PyQt6**; no GUI code branches on the binding, so the app runs identically on either. Set this to override the default order:

```bash
ABAX_QT_BINDING=PyQt6 abax gui
```

Only `PyQt6` is treated specially: setting it forces the PyQt6 path even when PySide6 is installed. Any other value (or leaving it unset) keeps the default PySide6-then-PyQt6 order. This is mainly useful for testing both bindings. See [getting-started.md](getting-started.md) for installing each one.

### `ABAX_FACEPLATE_DIR`

Points at a **faceplate-assets root** — a directory that holds per-model subfolders of calculator faceplate artwork used by the GUI's photographic faceplate for the built-in RPN calculator. Each model subfolder must contain a `background.png` and at least one `.kml` layout file.

```bash
# Point at a local checkout's voyager assets
export ABAX_FACEPLATE_DIR=/path/to/qrpn-voyager/qrpn/assets/voyager
abax gui
```

See [Faceplate assets](#faceplate-assets) for the full resolution order. abax **bundles no artwork** and never copies these files — it only reads them in place.

### `PANDOC`

Points at a pandoc executable for rich equation rendering. See [Pandoc](#pandoc-for-equations) below.

### `ABAX_NO_AUTOINSTALL`

Set to any non-empty value to disable optional-dependency installs entirely — the first-run chooser won't appear and abax won't run `pip` (equivalent to `auto_install: false` in settings). See [Auto-install](#auto-install).

## Auto-install

abax's core is pure stdlib and every heavier capability is an *optional* package with a graceful fallback — **abax installs nothing on its own.** On **first GUI launch** it shows a **chooser** that explains each optional feature group; **nothing is selected by default** — you pick only what you want. Two presets make choosing a whole set one click: **Thin** (the lean everyday conveniences) and **All** (everything abax can use). Your selection is fetched in a background daemon thread (best-effort, non-blocking) and the fact that you were asked is remembered (`deps_prompted`), so the chooser doesn't reappear on its own. In the TUI/headless there's no dialog: a one-time notice points you at `abax deps` (install everything) or `pip install abax[…]` (specific extras).

- **Best-effort and non-blocking.** Startup and the UI never wait on `pip`. If pip is unavailable, you're offline, or a build fails, abax silently keeps using its pure-Python fallbacks.
- **Once per machine.** A marker file per package (under the cache directory's `autodeps/` folder) means a slow or failing install is not retried on every launch.
- **Opt in, and revocable.** Nothing installs unless you choose it. `auto_install: false` in settings (Preferences → System) or `ABAX_NO_AUTOINSTALL=1` disables installs entirely.
- The **Qt GUI binding** (PySide6/PyQt6) is *not* auto-installed — you need it to launch the GUI in the first place, so install it explicitly with `pip install abax[gui]`.

Add more any time: **Tools → Install optional features** or **Preferences → System → Manage optional features…** re-open the chooser; `abax deps` installs everything from the command line, synchronously; and `abax --deps` reports the install state and how many optional packages are present.

## Themes

The GUI ships a set of theme presets in `abax/gui/theming.py`; the TUI has matching color themes. Set `theme` (GUI) or `tui_theme` (TUI) in `settings.json`, or switch from within the app. An unknown name falls back to the default (`galaxy`).

| Preset | Style |
|--------|-------|
| `galaxy` | Default dark theme (purple on black). |
| `light` | Light theme. |
| `high_contrast` | High-contrast theme. |
| `nord` | Nord palette. |
| `dark_one` | Atom One Dark style. |
| `solarized` | Solarized. |
| `crt_green` | Green phosphor CRT. |
| `crt_amber` | Amber phosphor CRT. |

The GUI renders any preset through a token-based stylesheet, and the GUI theming module can also import themes from an Obsidian CSS snippet or a Zed JSON theme. The TUI maps each theme to the nearest 256-color terminal palette.

## OpenDyslexic font

abax can use the **OpenDyslexic** typeface (SIL OFL 1.1), a free, openly licensed font designed to ease reading for people with dyslexia. When enabled it applies **across the UI** — menus and dialogs, the grid cells, and the Python console / terminal — while the calculator's LCD and the painted faceplates keep their own display fonts. The binaries are **not bundled**: when you enable the dyslexic font (the `dyslexic_font` setting, toggled in the GUI), abax downloads the Regular and Bold `.otf` files from the upstream GitHub repository (pinned to a fixed commit) into its cache directory (`CACHE/fonts/`) on first use.

The fetch is best-effort and offline-safe — any network or file error is logged and swallowed, so toggling the font on without a connection simply leaves it unavailable rather than raising an error. Once cached, the font is reused with no further network access.

## Faceplate assets

The GUI's built-in RPN calculator can render a photographic faceplate (background image + key overlays + a `.kml` layout per calculator model). abax distributes **none** of this artwork; it reads asset files you supply. A faceplate is considered usable when its model folder contains a `background.png` and at least one `*.kml` layout file.

abax looks for a model's assets in this order and uses the first usable match:

1. The `faceplate_assets_dir` setting, if set (the assets-root folder).
2. The `ABAX_FACEPLATE_DIR` environment variable (also an assets-root folder).
3. A local `qrpn-voyager/` or `qv/` checkout found beside the working directory, its parent, or the abax source tree — assets are expected under `qrpn/assets/voyager/<model>/`. Contributors who keep that checkout handy get the artwork with no configuration.

Both `faceplate_assets_dir` and `ABAX_FACEPLATE_DIR` should point at the **assets root** (the directory that holds the per-model subfolders), for example a local qrpn-voyager checkout's `qrpn/assets/voyager`.

## Pandoc for equations

abax can render LaTeX math to MathML for its equation feature. It prefers a real **pandoc** binary and resolves one in this order:

1. The `PANDOC` environment variable, if it names an executable on the `PATH`.
2. A `pandoc` executable on the `PATH`.
3. A pandoc binary managed by the `pypandoc` package, if installed.

If none is found, abax can bootstrap one on demand by `pip install`-ing the `pypandoc_binary` wheel (which bundles the executable) and then exposing its path through the `PANDOC` environment variable. The whole process is graceful: with no network or no pip it simply reports pandoc as unavailable and falls back to a built-in subset MathML renderer — it never raises.

To point abax at a specific pandoc:

```bash
export PANDOC=/usr/local/bin/pandoc
abax gui
```

`abax --deps` reports whether pandoc is available and what the fallback is.

## See also

- [getting-started.md](getting-started.md) — install and first-run walkthrough.
- [cli.md](cli.md) — command-line reference (including `--deps`).
- [gui-guide.md](gui-guide.md) — GUI menus, palette, and shortcuts.
- [index.md](index.md) — documentation home.
