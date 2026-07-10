# abax macOS app (self-contained, PyInstaller)

Builds a self-contained **`Abax.app`** bundle — Python and the whole optional
stack included, nothing to install. Built natively on macOS (PyInstaller can't
cross-compile). The release CI builds **both** architectures, in two **separate**
jobs with deliberately different coupling to the release:

| Arch | Runner | Job | Stack | Blocks the Release? |
|---|---|---|---|---|
| **arm64** (Apple Silicon) | `macos-15` | `macos-binary` | full `[all]` (incl. PyNEC + pymc, all from wheels) | **Yes** — in `release.needs`; runners are plentiful/fast, so the arm64 `.dmg` is reliably attached |
| **x86_64** (Intel) | `macos-13` | `macos-binary-intel` | `[all]` **minus PyNEC** (no Intel-mac wheel; built-in MoM solver still works) | **No** — best-effort |

**Why two jobs, not one matrix.** GitHub-hosted `macos-13` (Intel) runners are
scarce and can sit unassigned in the queue for a long time. If the Intel leg
shared a `needs` edge with the release (as it did on v0.1.11, where it starved
for 30+ min while every other artifact was ready), it would block the whole
GitHub Release. So the Intel job is kept **out of `release.needs`** entirely and
attaches its own `.dmg` to the release once built (`gh release upload`, tag
pushes only). If no Intel runner ever frees up, the release simply ships without
the Intel `.dmg` — Intel users still have `pip install abax` or `abax.pyz`.

Both jobs share `packaging/macos/make_icns.sh` (icon generation) and
`packaging/macos/sign_and_notarize.sh` (signing/notarization) so they stay
identical.

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
- **PyNEC**: on Apple Silicon it (and pymc/pytensor) resolve from prebuilt
  wheels, so the arm64 leg installs the full `[all]` set with no compiler. The
  Intel leg drops PyNEC (no x86_64-mac wheel, and no Fortran toolchain on the
  runner) — exactly like the Windows build; the built-in Method-of-Moments
  antenna solver still ships.

## Code signing & notarization (scaffolded, off by default)

By default the app is **not code-signed or notarized** (a hobby/OSS project), so
macOS quarantines it on download and may say *"abax is damaged and can't be
opened."* That message means *unsigned*, not corrupt. Clear the quarantine flag
once, then it opens normally:

```sh
xattr -dr com.apple.quarantine /Applications/Abax.app
```

Or, via the GUI: try to open it once, then **System Settings → Privacy &
Security → Open Anyway** (macOS Sequoia removed the old right-click → Open
one-click bypass).

The release job already runs `sign_and_notarize.sh`, which **codesigns the app
with a hardened runtime and notarizes + staples the `.dmg`** — but only when the
signing secrets below are present. Absent them it is a clean no-op, so unsigned
builds keep shipping unchanged. To turn signing on, add these repository secrets
(an Apple Developer Program membership is required):

| Secret | What it is |
|---|---|
| `MACOS_CERTIFICATE_P12` | base64 of a *Developer ID Application* `.p12` |
| `MACOS_CERTIFICATE_PASSWORD` | that `.p12`'s export password |
| `MACOS_SIGN_IDENTITY` | e.g. `Developer ID Application: Your Name (TEAMID1234)` |
| `MACOS_NOTARY_APPLE_ID` | Apple ID e-mail for `notarytool` |
| `MACOS_NOTARY_TEAM_ID` | 10-character Team ID |
| `MACOS_NOTARY_PASSWORD` | an app-specific password for that Apple ID |

With the certificate secrets but no notary credentials the build is **signed but
not notarized**; with all six it is signed, notarized, and stapled so it opens
with no quarantine prompt.

## What's in / out

- **In:** the PySide6 GUI, curses TUI, the full science stack, pymc, HDF5,
  Parquet, Excel, Stata/SPSS, SQL drivers, Jupyter libs, SGP4, TTS (NSSpeech via
  pyobjc), RestrictedPython, 7-Zip, the PTY terminal (stdlib pty), and **PyNEC**.
- **Caveat:** PyTensor (under pymc) JIT-compiles C at runtime for fast mode; on a
  machine without the Xcode Command Line Tools it falls back to a slower
  pure-Python mode.
