# abax macOS app (self-contained, PyInstaller)

Builds a self-contained **`Abax.app`** bundle — Python and the whole optional
stack included, nothing to install. Built natively on macOS (PyInstaller can't
cross-compile), **arm64 (Apple Silicon) only**; Intel Macs use `pip install abax`
or the portable `abax.pyz`.

## Layout

Two executables share one bundle (`Abax.app/Contents/MacOS/`):

| Executable | Use |
|---|---|
| `abax` | the `CFBundleExecutable` — the GUI on double-click, **and** the full CLI (`view` / `convert` / `get` / `tui` / `doctor` / …) when run from a terminal |
| `abax-worker` | the isolated code-execution worker the console/macros/scripts bridge spawns; it sits beside `abax` so `console_bridge` finds it via `dirname(sys.executable)` |

## Build

On macOS (Apple Silicon), from the repo root, with the dev environment installed
(`pip install -e ".[dev,all]" pyinstaller`):

```sh
python -m PyInstaller packaging/macos/abax.spec --noconfirm --distpath dist/macos
```

The result is `dist/macos/Abax.app`. The release CI job additionally generates an
`.icns` from `packaging/appimage/abax.svg` (sips + iconutil) and packages the app
into a `.dmg` with `create-dmg`.

## Differences from the Windows recipe

- A `BUNDLE()` step wraps the onedir output into `Abax.app` with an `Info.plist`
  (bundle id `org.abax.abax`, `LSMinimumSystemVersion` 13.0, `.abax` document type).
- **No pywinpty** — the PTY terminal uses the stdlib POSIX `pty` path on macOS.
- **TTS**: pyttsx3's macOS driver is `nsss` (NSSpeechSynthesizer via pyobjc), so
  the hidden imports pull `pyobjc` (`objc` / `Foundation` / `AppKit`) instead of
  the Windows SAPI5 `comtypes` / `win32com`.
- **PyNEC is included**: on Apple Silicon it (and pymc/pytensor) resolve from
  prebuilt wheels, so the full `[all]` set installs with no compiler — unlike the
  Windows build, which drops PyNEC for lack of a wheel.

## Gatekeeper: opening an unsigned build

The app is **not code-signed or notarized** (a hobby/OSS project — no Apple
Developer account yet), so macOS quarantines it on download and may say *"abax is
damaged and can't be opened."* That message means *unsigned*, not corrupt. Clear
the quarantine flag once, then it opens normally:

```sh
xattr -dr com.apple.quarantine /Applications/Abax.app
```

Or, via the GUI: try to open it once, then **System Settings → Privacy &
Security → Open Anyway** (macOS Sequoia removed the old right-click → Open
one-click bypass). Notarization is a planned follow-up.

## What's in / out

- **In:** the PySide6 GUI, curses TUI, the full science stack, pymc, HDF5,
  Parquet, Excel, Stata/SPSS, SQL drivers, Jupyter libs, SGP4, TTS (NSSpeech via
  pyobjc), RestrictedPython, 7-Zip, the PTY terminal (stdlib pty), and **PyNEC**.
- **Caveat:** PyTensor (under pymc) JIT-compiles C at runtime for fast mode; on a
  machine without the Xcode Command Line Tools it falls back to a slower
  pure-Python mode.
