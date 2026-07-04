"""On-demand auto-installation of abax's optional dependencies.

abax's core is stdlib-only and every heavier capability is an *optional* package
with a graceful fallback. abax installs **nothing on its own**: on first launch it
shows a chooser (also reachable from Tools → Install optional features and
Preferences → System) where the user picks which optional features to fetch —
**nothing is selected by default**. This module performs the best-effort background
pip installs the user opts into.

Design points:
- **Best-effort & non-blocking.** Installs run in a daemon thread; startup and the
  UI never wait on pip. If pip is missing, the machine is offline, or a build fails,
  abax silently keeps using its pure-Python fallbacks.
- **Attempted once per machine.** A marker file per package (under the cache dir)
  means a slow or failing install isn't retried on every launch. A *forced* install
  (the explicit "install optional features now" action) ignores the markers.
- **Opt-in, and revocable.** ``settings.auto_install = False`` (Preferences → System)
  or the ``ABAX_NO_AUTOINSTALL`` environment variable disables installs entirely — the
  first-run chooser won't appear and ``enabled()`` returns False.

The GUI binding itself (PySide6/PyQt6) is **not** auto-installed — you need a Qt
binding to launch the GUI in the first place, and it's the one heavyweight a user
deliberately chooses (`pip install abax[gui]`).
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import threading

# (pip distribution name, import module name) for every optional dependency.
# Ordered light -> heavy so the quick wins land first and the slowest (pymc) last.
_SCIENCE = [
    ("numpy", "numpy"), ("pandas", "pandas"), ("scipy", "scipy"),
    ("scikit-learn", "sklearn"), ("statsmodels", "statsmodels"),
    ("pingouin", "pingouin"), ("lifelines", "lifelines"),
    ("scikit-survival", "sksurv"),
]
# Bayesian stack, split out (pymc pulls pytensor + arviz + numba/llvmlite ~150 MB).
# Still part of the default full-fat `ALL` set below.
_BAYES = [("pymc", "pymc")]
# Reference-grade NEC antenna solver (compiled C++/SWIG extension). Part of the
# default full-fat `ALL` set; NOT in `thin`. May lack wheels on some platforms
# (notably Windows), in which case the best-effort install just fails silently and
# abax keeps using its built-in method-of-moments solver.
_NEC = [("PyNEC", "PyNEC")]
# Stata (.dta) / SPSS (.sav) readers. pyreadstat is a small compiled binding
# (ReadStat); pandas provides the DataFrame it returns (already in `science`).
# Part of the default full-fat `ALL` set; NOT in `thin`.
_STATS_IO = [("pyreadstat", "pyreadstat")]
# SQL database drivers (DB-API 2.0): psycopg for PostgreSQL, PyMySQL for MySQL.
# Both are optional — abax simply can't reach a SQL database without one. The
# psycopg[binary] wheel bundles libpq so there's no compiler/postgres-dev needed;
# PyMySQL is pure-Python. Part of the default full-fat `ALL` set; NOT in `thin`.
_DATABASE = [("psycopg[binary]", "psycopg"), ("PyMySQL", "pymysql")]
_TERMINAL = [("pyte", "pyte")]
if sys.platform == "win32":
    _TERMINAL.append(("pywinpty", "winpty"))   # ConPTY backend on Windows

FEATURES: dict[str, list[tuple[str, str]]] = {
    "fast-io": [("platformdirs", "platformdirs"), ("msgspec", "msgspec")],
    "excel": [("openpyxl", "openpyxl")],
    "sevenzip": [("py7zr", "py7zr")],
    "parquet": [("pyarrow", "pyarrow")],
    "terminal": _TERMINAL,
    "tui": [("textual", "textual")],
    "jupyter": [("nbformat", "nbformat"), ("ipykernel", "ipykernel"),
                ("anywidget", "anywidget")],
    "science": _SCIENCE,
    "bayes": _BAYES,
    "hdf5": [("h5py", "h5py")],
    "nec": _NEC,
    "stats-io": _STATS_IO,
    "database": _DATABASE,
}

# The full-fat set (the `all` extra), ordered light -> heavy so the quick wins
# land first and the heaviest (pymc) last; markers dedupe across features.
ALL: list[tuple[str, str]] = [
    ("platformdirs", "platformdirs"), ("msgspec", "msgspec"),
    ("openpyxl", "openpyxl"),
    ("py7zr", "py7zr"),
    *_TERMINAL,
    ("textual", "textual"),
    ("nbformat", "nbformat"), ("anywidget", "anywidget"),
    ("pyarrow", "pyarrow"),
    *_SCIENCE,
    ("ipykernel", "ipykernel"),
    *_STATS_IO,
    *_DATABASE,
    *_BAYES,
    ("h5py", "h5py"),
    *_NEC,          # compiled; last so a build failure can't block the rest
]

# Human-facing descriptions for the first-run chooser: feature -> (label,
# what it installs, approximate MB). Feature closures share dependencies, so the
# totals for a preset are smaller than the sum of the parts.
FEATURE_INFO: dict[str, tuple[str, str, int]] = {
    "fast-io": ("Faster settings & correct folders",
                "msgspec + platformdirs", 8),
    "excel": ("Excel spreadsheets (.xlsx)", "openpyxl", 4),
    "sevenzip": ("7-Zip (.7z) archives in the file manager", "py7zr", 6),
    "terminal": ("A true terminal panel",
                 "pyte" + (" + pywinpty" if sys.platform == "win32" else ""), 3),
    "tui": ("A richer terminal UI", "textual", 12),
    "jupyter": ("Jupyter integration",
                "nbformat + ipykernel + anywidget — notebook validation, the abax "
                "kernel, and the editable-sheet widget", 80),
    "parquet": ("Parquet / Feather data files", "pyarrow", 90),
    "science": ("Data science: statistics, ML, DataFrames, graphing",
                "numpy, pandas, scipy, scikit-learn, statsmodels, lifelines, "
                "pingouin, scikit-survival", 450),
    "bayes": ("Bayesian / probabilistic modeling (large)",
              "pymc + pytensor + arviz + numba/llvmlite", 150),
    "hdf5": ("HDF5 data files (.h5 / .hdf5)", "h5py", 15),
    "nec": ("Reference-grade NEC antenna solver",
            "PyNEC (compiled; may need a build toolchain on some platforms)", 5),
    "stats-io": ("Stata / SPSS data files (.dta / .sav)",
                 "pyreadstat", 10),
    "database": ("SQL databases (PostgreSQL / MySQL)",
                 "psycopg + PyMySQL — read tables from a live SQL connection", 15),
}

# The two common presets offered by the chooser. "thin" = the lean conveniences
# (matching the pip `thin` extra minus the Qt binding); "all" = everything.
PRESETS: dict[str, list[str]] = {
    "thin": ["fast-io", "excel", "sevenzip", "terminal", "tui"],
    "all": list(FEATURES),
}


def preset(name: str) -> list[str]:
    """Feature keys for a named preset (``"thin"`` / ``"all"``)."""
    return list(PRESETS.get(name, []))


# --- configuration / hooks (the install fn + marker dir are injectable for tests)
_INSTALL_FN = None          # set below; tests may replace it
_MARKER_DIR = None          # None -> CACHE_DIR/autodeps
_enabled_override: bool | None = None
_lock = threading.Lock()
_attempted_session: set[str] = set()


def set_enabled(flag: bool | None) -> None:
    """Force auto-install on/off (``None`` restores the default)."""
    global _enabled_override
    _enabled_override = flag


def enabled() -> bool:
    if os.environ.get("ABAX_NO_AUTOINSTALL"):
        return False
    if _enabled_override is not None:
        return _enabled_override
    return True


def installed(import_name: str) -> bool:
    try:
        return importlib.util.find_spec(import_name) is not None
    except Exception:
        return False


def _marker_dir():
    from pathlib import Path
    if _MARKER_DIR is not None:
        return Path(_MARKER_DIR)
    from ._runtime import CACHE_DIR
    return CACHE_DIR / "autodeps"


def _attempted(pip_name: str) -> bool:
    if pip_name in _attempted_session:
        return True
    try:
        return (_marker_dir() / f"{pip_name}.attempted").exists()
    except Exception:
        return False


def _mark(pip_name: str) -> None:
    _attempted_session.add(pip_name)
    try:
        d = _marker_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{pip_name}.attempted").write_text("1", encoding="utf-8")
    except Exception:
        pass


def _pip_install(pip_name: str, timeout: float = 1800) -> bool:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", pip_name],
            capture_output=True, timeout=timeout)
        return proc.returncode == 0
    except Exception:
        return False


_INSTALL_FN = _pip_install


def missing(packages) -> list[tuple[str, str]]:
    """The subset of ``(pip, module)`` pairs whose module isn't importable."""
    return [(pip, mod) for pip, mod in packages if not installed(mod)]


def ensure(packages, *, background: bool = True, force: bool = False) -> list[str]:
    """Install any missing packages, best-effort and once.

    ``packages`` is a list of ``(pip_name, import_name)`` pairs. Returns the pip
    names it will attempt (empty if disabled, all present, or already attempted).
    With ``force`` it ignores the once-per-machine markers (still skips packages
    already importable).
    """
    if not enabled():
        return []
    todo: list[str] = []
    with _lock:
        for pip, mod in packages:
            if installed(mod):
                continue
            if not force and _attempted(pip):
                continue
            _mark(pip)                     # claim now so concurrent calls don't race
            todo.append(pip)
    if not todo:
        return []

    def work() -> None:
        for pip in todo:
            _INSTALL_FN(pip)

    if background:
        threading.Thread(target=work, name="abax-autodeps", daemon=True).start()
    else:
        work()
    return todo


def ensure_feature(key: str, *, background: bool = True, force: bool = False) -> list[str]:
    """Ensure the packages backing one feature (e.g. ``"science"``/``"excel"``)."""
    return ensure(FEATURES.get(key, []), background=background, force=force)


def prefetch_all(*, background: bool = True, force: bool = False) -> list[str]:
    """Fetch the entire full-fat optional stack (called once on GUI startup)."""
    return ensure(ALL, background=background, force=force)
