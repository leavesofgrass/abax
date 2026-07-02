# Configuration

abax is configured through a single JSON settings file, a handful of environment variables, and a set of platform-correct runtime directories that hold its config, data, cache, and logs. Almost nothing needs configuring to get started — the defaults are sensible and every optional feature degrades gracefully when its dependency is absent — but this page documents every knob: where settings live, what each field does, the environment variables, the theme presets, the on-demand OpenDyslexic font, and pandoc detection for equation rendering.

## Settings file

Settings are stored as JSON in `settings.json` inside abax's config directory (see [Runtime directories](#runtime-directories) below — typically `…/abax/settings.json`). The GUI and TUI load it at startup and write it back when you change a setting. If the file is missing or unreadable, abax silently uses the defaults, so deleting it is a safe way to reset.

JSON encoding uses `msgspec` when the `fast-io` extra is installed and falls back to the standard library otherwise; the behavior is identical either way. The schema is versioned and migrates lazily on read (for example, an old `color_scheme` field is renamed to `theme` automatically and written back).

### Settings fields

| Field | Type | Default | Meaning |
|-------|------|---------|---------|
| `theme` | string | `"obsidian"` | GUI theme preset (see [Themes](#themes)). |
| `vim_mode` | bool | `true` | Vim-style key bindings, on by default. |
| `tui_theme` | string | `"obsidian"` | TUI color theme. |
| `zoom` | float | `1.0` | GUI zoom factor. |
| `column_width` | int | `10` | Default column width. |
| `dyslexic_font` | bool | `false` | Use the OpenDyslexic font across the GUI (see [OpenDyslexic font](#opendyslexic-font)). |
| `calc_model` | string | `""` | Last-used calculator model key (e.g. `16c`, `15c`, `ti83`, `alg`); restored on launch. Empty = default (HP-16C). |
| `calc_style` | string | `"image"` | Last-used HP faceplate style (`image` or `vector`). |
| `calc_degrees` | bool | `false` | Calculator Deg/Rad mode, restored on launch. |
| `last_sheet` | int | `0` | Active sheet index, restored on launch. |
| `last_cell` | string | `""` | Cursor cell (A1), restored on launch. |
| `code_consent` | bool | `false` | Whether you've consented to run untrusted code (console/terminal/scripts/macros). Set back to `false` to be prompted again. |
| `code_isolation` | string | `"isolated"` | How code execution is isolated: `off` (in-process, no worker/limits), `isolated` (out-of-process worker + resource limits), or `strict` (also OS-confine filesystem + network). Cycle it from the command palette; see [Macros & scripting](macros-and-scripting.md). |
| `faceplate_assets_dir` | string | `""` | Folder of calculator faceplate artwork (see [Faceplate assets](#faceplate-assets)). |
| `show_toolbar` | bool | `true` | Show the GUI toolbar. |
| `autosave_enabled` | bool | `true` | Whether the GUI periodically autosaves `settings.json`. |
| `autosave_interval` | int | `30` | Autosave cadence in seconds (when enabled). |
| `recent_files` | list | `[]` | Recently opened file paths. |
| `window_geometry` | dict | `{}` | Saved GUI window position/size. |
| `fm_buttons` | list | `[]` | Your custom file-manager command buttons (`{label, command}`); see [File manager](file-manager.md). |
| `auto_install` | bool | `true` | Auto-install optional dependencies (and show the first-run chooser); see [Auto-install](#auto-install). Set `false` to opt out. |
| `deps_prompted` | bool | `false` | Whether the first-run optional-feature chooser has been shown. Set back to `false` to be asked again. |
| `schema_version` | int | `3` | Settings schema version (managed by abax). |

You can edit `settings.json` by hand while abax is closed, but most fields are also exposed through the GUI — the **Preferences** dialog (Edit → Preferences…, `Ctrl+,`) covers theme, font, default zoom, autosave, and code isolation, and individual menus/palette entries cover the toolbar and faceplate folder — and through the TUI, which is the recommended way to change them.

## Runtime directories

abax never hardcodes paths. It resolves four OS-appropriate directories at startup and creates them if needed. When the `platformdirs` package (from the `fast-io` extra) is installed it uses that; otherwise a built-in fallback mirrors the same logic.

| Directory | Holds |
|-----------|-------|
| **CONFIG** | `settings.json`, the `macros/` folder for auto-discovered macros. |
| **DATA** | Persistent application data, including an `exchange/` subfolder for the generic JSON interchange format. |
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

Set to any non-empty value to disable the background auto-installation of optional dependencies (equivalent to `auto_install: false` in settings). See [Auto-install](#auto-install).

## Auto-install

abax's core is pure stdlib and every heavier capability is an *optional* package with a graceful fallback. On **first GUI launch** abax shows a **chooser** that explains each optional feature group and offers two presets — **Thin** (lean everyday conveniences) and **All** (everything, recommended) — plus a checkbox per feature. Your selection is fetched in a background daemon thread (best-effort, non-blocking) and the choice is remembered (`deps_prompted`). In the TUI/headless there's no dialog: a one-time notice points you at `abax deps` (install everything) or `pip install abax[…]` (specific extras).

- **Best-effort and non-blocking.** Startup and the UI never wait on `pip`. If pip is unavailable, you're offline, or a build fails, abax silently keeps using its pure-Python fallbacks.
- **Once per machine.** A marker file per package (under the cache directory's `autodeps/` folder) means a slow or failing install is not retried on every launch.
- **Opt out** with `auto_install: false` in settings or `ABAX_NO_AUTOINSTALL=1`.
- The **Qt GUI binding** (PySide6/PyQt6) is *not* auto-installed — you need it to launch the GUI in the first place, so install it explicitly with `pip install abax[gui]`.

Controls: **Tools → Install optional features** re-opens the chooser (Thin / All / custom) any time; `abax deps` installs everything from the command line, synchronously; and `abax --deps` reports the auto-install state and how many optional packages are present.

## Themes

The GUI ships a set of theme presets in `abax/gui/theming.py`; the TUI has matching color themes. Set `theme` (GUI) or `tui_theme` (TUI) in `settings.json`, or switch from within the app. An unknown name falls back to the default (`obsidian`).

| Preset | Style |
|--------|-------|
| `obsidian` | Default dark theme. |
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
