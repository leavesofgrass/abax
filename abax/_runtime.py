"""Runtime detection: platform paths, optional-dependency booleans, version.

Imported widely, so it stays cheap: no Qt, no curses, no heavy work at import.
Mirrors the spec's _runtime.py exactly, parameterized for project "abax".
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "abax"

# --- optional dependency flags --------------------------------------------

try:
    import msgspec as _ms  # noqa: F401

    _HAS_MSGSPEC = True
except ImportError:
    _ms = None
    _HAS_MSGSPEC = False

try:
    import platformdirs as _pd_mod  # noqa: F401

    _HAS_PLATFORMDIRS = True
except ImportError:
    _pd_mod = None
    _HAS_PLATFORMDIRS = False

try:
    import openpyxl as _openpyxl  # noqa: F401

    _HAS_OPENPYXL = True
except ImportError:
    _openpyxl = None
    _HAS_OPENPYXL = False

try:
    import importlib.util as _ilu

    # GUI works on either Qt binding; PySide6 (LGPL) is preferred. Detect via
    # find_spec so the fast paths never import a heavy Qt stack just to check.
    _HAS_QT = (_ilu.find_spec("PySide6") is not None
               or _ilu.find_spec("PyQt6") is not None)
except Exception:
    _HAS_QT = False

try:
    import textual  # noqa: F401

    _HAS_TEXTUAL = True
except ImportError:
    _HAS_TEXTUAL = False

# --- version flags ---------------------------------------------------------

PY_VERSION = sys.version_info
HAS_LAZY_IMPORTS = PY_VERSION >= (3, 15)  # PEP 810

# --- platform paths --------------------------------------------------------

if _HAS_PLATFORMDIRS:
    from platformdirs import PlatformDirs as _PD

    _dirs = _PD(APP_NAME, appauthor=False)
    CONFIG_DIR = Path(_dirs.user_config_dir)
    DATA_DIR = Path(_dirs.user_data_dir)
    CACHE_DIR = Path(_dirs.user_cache_dir)
    LOG_DIR = Path(_dirs.user_log_dir)
else:
    # stdlib fallback — mirrors platformdirs logic.
    _home = Path.home()
    if sys.platform == "win32":
        _base = Path(os.environ.get("APPDATA", _home / "AppData/Roaming"))
        _local = Path(os.environ.get("LOCALAPPDATA", _home / "AppData/Local"))
        CONFIG_DIR = _base / APP_NAME
        DATA_DIR = _local / APP_NAME
        CACHE_DIR = _local / APP_NAME / "Cache"
        LOG_DIR = _local / APP_NAME / "Logs"
    elif sys.platform == "darwin":
        _sup = _home / "Library" / "Application Support" / APP_NAME
        CONFIG_DIR = _sup
        DATA_DIR = _sup
        CACHE_DIR = _home / "Library" / "Caches" / APP_NAME
        LOG_DIR = _home / "Library" / "Logs" / APP_NAME
    else:
        _cfg = Path(os.environ.get("XDG_CONFIG_HOME", _home / ".config"))
        _data = Path(os.environ.get("XDG_DATA_HOME", _home / ".local/share"))
        _cache = Path(os.environ.get("XDG_CACHE_HOME", _home / ".cache"))
        CONFIG_DIR = _cfg / APP_NAME
        DATA_DIR = _data / APP_NAME
        CACHE_DIR = _cache / APP_NAME
        LOG_DIR = _data / APP_NAME / "logs"

EXCHANGE_DIR = DATA_DIR / "exchange"

for _d in (CONFIG_DIR, DATA_DIR, CACHE_DIR, LOG_DIR, EXCHANGE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- optional aggregate accelerator ---------------------------------------
# The stdlib core reduces ranges itself; the engine layer may inject a faster
# numpy-backed reducer here for large all-numeric ranges. core reads the slot
# through this seam (abax._runtime is the one sanctioned cross-layer import),
# so it never imports numpy directly.
_aggregate_accelerator = None


def set_aggregate_accelerator(fn) -> None:
    """Register (or clear, with ``None``) the optional range-aggregate accelerator."""
    global _aggregate_accelerator
    _aggregate_accelerator = fn


def aggregate_accelerator():
    """The currently registered aggregate accelerator, or ``None``."""
    return _aggregate_accelerator
