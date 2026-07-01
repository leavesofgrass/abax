"""On-demand auto-installation of qcell's optional dependencies.

qcell's core is stdlib-only and every heavier capability is an *optional* package
with a graceful fallback. By default qcell fetches those packages **automatically**
in the background, so a plain install grows into a "full-fat" one on its own — the
data-science stack, Excel/Parquet I/O, the PTY terminal, and Jupyter integration
all appear without the user running a single `pip install … [extra]`.

Design points:
- **Best-effort & non-blocking.** Installs run in a daemon thread; startup and the
  UI never wait on pip. If pip is missing, the machine is offline, or a build fails,
  qcell silently keeps using its pure-Python fallbacks.
- **Attempted once per machine.** A marker file per package (under the cache dir)
  means a slow or failing install isn't retried on every launch. A *forced* install
  (the explicit "install optional features now" action) ignores the markers.
- **Opt-out.** ``settings.auto_install = False`` or the ``QCELL_NO_AUTOINSTALL``
  environment variable disables it entirely.

The GUI binding itself (PySide6/PyQt6) is **not** auto-installed — you need a Qt
binding to launch the GUI in the first place, and it's the one heavyweight a user
deliberately chooses (`pip install qcell[gui]`).
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
_TERMINAL = [("pyte", "pyte")]
if sys.platform == "win32":
    _TERMINAL.append(("pywinpty", "winpty"))   # ConPTY backend on Windows

FEATURES: dict[str, list[tuple[str, str]]] = {
    "fast-io": [("platformdirs", "platformdirs"), ("msgspec", "msgspec")],
    "excel": [("openpyxl", "openpyxl")],
    "parquet": [("pyarrow", "pyarrow")],
    "terminal": _TERMINAL,
    "tui": [("rich", "rich"), ("textual", "textual")],
    "jupyter": [("nbformat", "nbformat"), ("ipykernel", "ipykernel"),
                ("anywidget", "anywidget")],
    "science": _SCIENCE,
    "bayes": _BAYES,
}

# The full-fat set (the `all` extra), ordered light -> heavy so the quick wins
# land first and the heaviest (pymc) last; markers dedupe across features.
ALL: list[tuple[str, str]] = [
    ("platformdirs", "platformdirs"), ("msgspec", "msgspec"),
    ("openpyxl", "openpyxl"),
    *_TERMINAL,
    ("rich", "rich"), ("textual", "textual"),
    ("nbformat", "nbformat"), ("anywidget", "anywidget"),
    ("pyarrow", "pyarrow"),
    *_SCIENCE,
    ("ipykernel", "ipykernel"),
    *_BAYES,
]

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
    if os.environ.get("QCELL_NO_AUTOINSTALL"):
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
        threading.Thread(target=work, name="qcell-autodeps", daemon=True).start()
    else:
        work()
    return todo


def ensure_feature(key: str, *, background: bool = True, force: bool = False) -> list[str]:
    """Ensure the packages backing one feature (e.g. ``"science"``/``"excel"``)."""
    return ensure(FEATURES.get(key, []), background=background, force=force)


def prefetch_all(*, background: bool = True, force: bool = False) -> list[str]:
    """Fetch the entire full-fat optional stack (called once on GUI startup)."""
    return ensure(ALL, background=background, force=force)
