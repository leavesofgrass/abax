# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the self-contained abax Windows build (onedir).

Three executables share one bundle directory:

  abax.exe        console subsystem — the full CLI (view/convert/get/tui/
                  doctor/...) plus the GUI (no args). Run this from a terminal.
  abaxw.exe       windowed subsystem — the GUI without a console window.
                  Pin/double-click this one.
  abax-worker.exe console subsystem — the isolated code-execution worker the
                  console/macros/scripts bridge spawns (CREATE_NO_WINDOW, so it
                  never shows). Its std handles always exist, even when the
                  parent is the windowed abaxw.exe.

Build (from the repo root):
    py -m PyInstaller packaging/windows/abax.spec --noconfirm --distpath dist/windows

Notes:
  * hiddenimports=collect_submodules("abax") is LOAD-BEARING: the formula packs
    are imported via __import__(f"abax.core.{pack}") inside try/except, which
    PyInstaller's static analysis cannot see — without this, ~400 functions
    silently vanish from the frozen build.
  * PyQt6 is EXCLUDED: abax's _qtcompat shim prefers PySide6; bundling both Qt
    stacks would double the size and risk DLL clashes on load.
  * PyNEC is not bundled (no Windows wheel); the built-in MoM solver works.
"""

import pathlib

from PyInstaller.utils.hooks import collect_submodules

SPEC_DIR = pathlib.Path(SPECPATH).resolve()  # noqa: F821 — SPECPATH is a PyInstaller global
REPO = SPEC_DIR.parents[1]


def _abax_submodules() -> "list[str]":
    """Every abax.* module, walked from the SOURCE TREE.

    collect_submodules("abax") imports the package to enumerate it — and when
    abax isn't pip-installed (a plain checkout) it silently returns nothing,
    which is exactly how ~400 dynamically-imported formula functions vanished
    from the first build. Walking the files needs no imports and no pip state.
    """
    out = ["abax"]
    for p in (REPO / "abax").rglob("*.py"):
        parts = list(p.relative_to(REPO).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            out.append(".".join(parts))
    return sorted(set(out))


ABAX_MODULES = _abax_submodules()
assert len(ABAX_MODULES) > 100, f"abax source walk found only {len(ABAX_MODULES)} modules"

# The data-science / database stack is loaded ENTIRELY dynamically
# (engine/analysis.py importlib.import_module, engine/dbapi.py __import__) —
# none of it is a static import anywhere in abax, so every package must be
# declared here or it silently drops out of the bundle (doctor showed exactly
# that on the first builds). Naming the top module lets modulegraph + the
# bundled PyInstaller hooks pull each package's own dependency chain.
_DYNAMIC_STACK = [
    "sklearn",          # ML tool (PCA / k-means / regression)
    "lifelines",        # survival analysis
    "pingouin",         # stats (pulls seaborn -> matplotlib, so mpl stays in)
    "sksurv",           # scikit-survival
    "pymc",             # Bayesian (pytensor runs in pure-Python mode frozen)
    "psycopg",          # PostgreSQL import
    "pymysql",          # MySQL import
]

HIDDEN = (
    ABAX_MODULES
    + collect_submodules("sklearn")   # sklearn lazy-loads submodules internally
    + _DYNAMIC_STACK
    # pyttsx3 loads its platform driver dynamically (pyttsx3.drivers.sapi5 via
    # comtypes on Windows) — invisible to static analysis.
    + collect_submodules("pyttsx3")
    + ["comtypes.client", "comtypes.stream", "win32com.client"]
)

EXCLUDES = [
    "PyQt6", "PyQt5", "PySide2",   # abax ships PySide6; never bundle a second Qt
    "tkinter", "_tkinter",          # matplotlib rides along for pingouin/seaborn,
                                    # but the Tk backend stays out (Agg suffices)
]

a = Analysis(
    ["launch_abax.py"],
    pathex=["../.."],
    hiddenimports=HIDDEN,
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)

w = Analysis(
    ["launch_worker.py"],
    pathex=["../.."],
    # The worker imports abax.core lazily through the envelope round-trip; give
    # it the same abax submodule set so packs resolve identically.
    hiddenimports=collect_submodules("abax"),
    excludes=EXCLUDES + ["PySide6"],   # the worker never touches Qt
    noarchive=False,
)
pyz_w = PYZ(w.pure)

exe_cli = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="abax",
    console=True,
    upx=False,                      # UPX trips antivirus heuristics; not worth it
)
exe_gui = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="abaxw",
    console=False,
    upx=False,
)
exe_worker = EXE(
    pyz_w, w.scripts, [],
    exclude_binaries=True,
    name="abax-worker",
    console=True,
    upx=False,
)

coll = COLLECT(
    exe_cli, exe_gui, exe_worker,
    a.binaries, a.datas,
    w.binaries, w.datas,
    strip=False,
    upx=False,
    name="abax",
)
