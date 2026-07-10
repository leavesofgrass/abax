# abax Windows binary (self-contained, PyInstaller)

Builds a fully self-contained Windows folder bundle of abax — Python and the
whole optional stack included, nothing to install. Built natively on Windows
(no Docker; PyInstaller doesn't cross-compile).

## Layout

Three executables share **one** bundle directory (a single `_internal/` runtime
— the extra exes are just small bootloader stubs):

| Exe | Subsystem | Use |
|---|---|---|
| `abax.exe` | console | the full CLI (`view` / `convert` / `get` / `tui` / `doctor` / …) **and** the GUI (no args) — run from a terminal |
| `abaxw.exe` | windowed | the GUI without a console window — pin/double-click this one |
| `abax-worker.exe` | console | the isolated code-execution worker the console/macros bridge spawns (with `CREATE_NO_WINDOW`, so it never shows) |

## Build

From the repo root, on Windows, with the full dev environment installed
(`pip install -e ".[dev,all]" pyinstaller pyttsx3 RestrictedPython psycopg[binary] PyMySQL`):

```sh
py -m PyInstaller packaging/windows/abax.spec --noconfirm --distpath dist/windows
```

The result is `dist/windows/abax/` — zip that folder to distribute.

**CI:** the `windows-binary` job in `.github/workflows/release.yml` runs exactly
this on `windows-latest` for every `v*` tag, zips the bundle as
`abax-<version>-windows-x64.zip`, and attaches it to the GitHub Release. It
installs the components of the `all` extra **minus `nec`** (PyNEC has no Windows
wheel — see below), so a clean runner can resolve every dependency.

## Frozen-app design notes (why the source has `sys.frozen` guards)

- **Console worker.** Unfrozen, the bridge spawns `python -c "...console_worker..."`.
  Frozen, `sys.executable` *is* abax, so `-c` would be parsed as CLI arguments —
  the bridge instead spawns the sibling `abax-worker.exe` (or the
  `abax --run-console-worker` escape hatch in `abax.app.main` as a fallback).
  Job-Object resource limits and the strict-sandbox path wrap the child the same
  way in both worlds.
- **Auto-install is force-disabled** (`autodeps.enabled()` → `False` when
  frozen): a bundle can't gain modules at runtime, and `abax.exe -m pip` would
  relaunch the app. The first-run feature chooser consequently never offers
  installs in the frozen build — everything it would offer is already bundled.
- **Dynamic imports.** The formula packs load via `__import__(f"abax.core.{pack}")`
  inside `try/except` — invisible to PyInstaller's static analysis, so the spec's
  `hiddenimports=collect_submodules("abax")` is load-bearing (without it ~400
  functions silently vanish). The smoke test asserts the registry count.

## What's in / out

- **In:** PySide6 GUI, TUI, the full science stack (numpy/pandas/scipy/sklearn/
  statsmodels/lifelines/pingouin/scikit-survival), pymc, HDF5, Parquet, Excel,
  Stata/SPSS, SQL drivers (psycopg/PyMySQL), Jupyter libs, SGP4, TTS (pyttsx3 →
  SAPI5), RestrictedPython, 7-Zip, the PTY terminal (pywinpty).
- **Out:** **PyNEC** (no Windows wheel — the built-in Method-of-Moments antenna
  solver still works; only the reference-grade NEC2 path is absent) and **PyQt6**
  (abax ships PySide6; bundling a second Qt would double size and risk DLL
  clashes).
- **Caveat:** pymc's `pytensor` normally compiles C at runtime; without a
  compiler on the target machine it falls back to its slower pure-Python mode.
