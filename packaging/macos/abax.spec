# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the self-contained abax macOS app bundle (onedir → .app).

Adapted from packaging/windows/abax.spec. Produces ``dist/macos/Abax.app`` with
two executables in Contents/MacOS sharing one runtime:

  abax         the main executable (CFBundleExecutable) — GUI on double-click,
               and the full CLI (view/convert/get/tui/doctor/...) when run from
               a terminal. Windowed (no forced console).
  abax-worker  the isolated code-execution worker the console/macros/scripts
               bridge spawns; it sits beside `abax` so console_bridge finds it
               via os.path.dirname(sys.executable) + "abax-worker".

Build (from the repo root, on macOS — PyInstaller cannot cross-compile):
    python -m PyInstaller packaging/macos/abax.spec --noconfirm --distpath dist/macos

Differences from the Windows spec:
  * A BUNDLE() step wraps the onedir COLLECT into a .app with an Info.plist.
  * No pywinpty — the PTY terminal uses the stdlib POSIX pty path on macOS.
  * TTS: pyttsx3's macOS driver is `nsss` (NSSpeechSynthesizer via pyobjc), so
    the hidden imports pull pyobjc (objc/Foundation/AppKit) instead of the
    Windows SAPI5 comtypes/win32com.
  * arm64 only (Apple Silicon); Intel Macs use pip / abax.pyz.
"""

import pathlib
import re

from PyInstaller.utils.hooks import collect_submodules

SPEC_DIR = pathlib.Path(SPECPATH).resolve()  # noqa: F821 — SPECPATH is a PyInstaller global
REPO = SPEC_DIR.parents[1]

_pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
VERSION = re.search(r'^version = "(.*)"', _pyproject, re.M).group(1)


def _abax_submodules() -> "list[str]":
    """Every abax.* module, walked from the SOURCE TREE.

    collect_submodules("abax") imports the package to enumerate it — and on a
    plain checkout (abax not pip-installed) it silently returns nothing, which is
    how ~400 dynamically-imported formula functions vanished from the first
    Windows builds. Walking the files needs no imports and no pip state.
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


def _abax_datas() -> "list[tuple[str, str]]":
    """Every NON-Python file inside the abax package, preserving its layout
    (the QSS themes apply_current_theme reads at GUI startup, etc.)."""
    out = []
    for p in (REPO / "abax").rglob("*"):
        if p.is_file() and p.suffix not in (".py", ".pyc") and "__pycache__" not in p.parts:
            out.append((str(p), str(p.parent.relative_to(REPO))))
    return out


ABAX_DATAS = _abax_datas()
assert ABAX_DATAS, "abax data walk found nothing — the QSS themes must be bundled"

# Loaded ENTIRELY dynamically (engine/analysis.py, engine/dbapi.py) — declare
# each top module so modulegraph + the bundled hooks pull its dependency chain.
_DYNAMIC_STACK = [
    "sklearn",          # ML tool (PCA / k-means / regression)
    "lifelines",        # survival analysis
    "pingouin",         # stats (pulls seaborn -> matplotlib)
    "sksurv",           # scikit-survival
    "pymc",             # Bayesian (pytensor)
    "psycopg",          # PostgreSQL import
    "pymysql",          # MySQL import
]

HIDDEN = (
    ABAX_MODULES
    + collect_submodules("sklearn")   # sklearn lazy-loads submodules internally
    + _DYNAMIC_STACK
    # pyttsx3 loads its platform driver dynamically. On macOS that is `nsss`
    # (NSSpeechSynthesizer via pyobjc) — invisible to static analysis.
    + collect_submodules("pyttsx3")
    + ["pyttsx3.drivers.nsss", "objc", "Foundation", "AppKit"]
    # The PTY terminal's imports are all function-level try/excepts (stdlib pty).
    + collect_submodules("pyte")
)

EXCLUDES = [
    "PyQt6", "PyQt5", "PySide2",   # abax ships PySide6; never bundle a second Qt
    "tkinter", "_tkinter",          # matplotlib rides along for pingouin/seaborn,
                                    # but the Tk backend stays out (Agg suffices)
]

a = Analysis(
    ["launch_abax.py"],
    pathex=["../.."],
    datas=ABAX_DATAS,
    binaries=[],
    hiddenimports=HIDDEN,
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)

w = Analysis(
    ["launch_worker.py"],
    pathex=["../.."],
    # The worker imports abax.core lazily through the envelope round-trip; give
    # it the same source-walked module set so packs resolve identically even on
    # a non-pip-installed checkout.
    hiddenimports=ABAX_MODULES,
    excludes=EXCLUDES + ["PySide6"],   # the worker never touches Qt
    noarchive=False,
)
pyz_w = PYZ(w.pure)

exe_main = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="abax",
    console=False,                  # windowed .app; stdio still works from a shell
    target_arch="arm64",
    upx=False,
)
exe_worker = EXE(
    pyz_w, w.scripts, [],
    exclude_binaries=True,
    name="abax-worker",
    console=True,
    target_arch="arm64",
    upx=False,
)

coll = COLLECT(
    exe_main, exe_worker,
    a.binaries, a.datas,
    w.binaries, w.datas,
    strip=False,
    upx=False,
    name="abax",
)

# Optional .icns (generated in CI from packaging/appimage/abax.svg); omitted for
# a plain local build, in which case the .app uses the default PyInstaller icon.
_icns = SPEC_DIR / "abax.icns"
ICON = str(_icns) if _icns.exists() else None

app = BUNDLE(
    coll,
    name="Abax.app",
    icon=ICON,
    bundle_identifier="org.abax.abax",
    version=VERSION,
    info_plist={
        "CFBundleName": "abax",
        "CFBundleDisplayName": "abax",
        "CFBundleExecutable": "abax",   # the main exe launches on double-click
        "CFBundleIdentifier": "org.abax.abax",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "13.0",   # PySide6 6.11 wheels target macOS 13+
        "NSHighResolutionCapable": True,
        "CFBundleDocumentTypes": [{
            "CFBundleTypeName": "abax workbook",
            "CFBundleTypeExtensions": ["abax"],
            "CFBundleTypeRole": "Editor",
            "LSHandlerRank": "Owner",
        }],
    },
)
