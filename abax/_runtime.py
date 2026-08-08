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

# --- text encoding policy --------------------------------------------------
# abax has shipped the same defect twice, from the same root cause: a call that
# left the encoding implicit and so silently inherited whatever the platform
# said that day. Issue #1 was settings.py reading a UTF-8 settings.json back as
# the platform locale (mojibake, and on some bytes a silent reset to defaults);
# issue #5 was sandbox_windows._icacls decoding icacls output as strict UTF-8
# under ci.yml's PYTHONUTF8=1. ~40 other call sites spell the encoding out by
# hand, which is exactly why the two that forgot went unnoticed for so long.
# These are the shared spellings, so the next site has something to copy.
#
# _runtime is the home because it is dependency-free (a bare `pip install abax`
# and the portable abax.pyz keep working), it is already the one sanctioned
# cross-layer import, and it already owns CONFIG_DIR/DATA_DIR.
#
# Two different problems hide under "encoding bug", and they do NOT take the
# same fix:
#
#   FILES abax writes and reads back — settings.json, the state journal — are a
#   contract between abax and itself. UTF-8 on both sides, always. Use
#   read_text_utf8 / write_text_utf8.
#
#   SUBPROCESS PIPES carry whatever the child emits, which on Windows is
#   usually the console OEM codepage and is not UTF-8. Forcing UTF-8 there
#   would be as wrong as leaving it implicit, just differently — so there is no
#   read/write pair for pipes, only console_encoding() to name the codec, and
#   each call site passes encoding=/errors= itself (see console_encoding).

TEXT_ENCODING = "utf-8"
# Readers accept a BOM; writers never emit one. An editor that adds one (VS
# Code's "UTF-8 with BOM", PowerShell 5.1 redirection) would otherwise make a
# file abax wrote itself unreadable — settings.py hit exactly this and the two
# halves of that fix must not drift apart again.
TEXT_ENCODING_READ = "utf-8-sig"


def read_text_utf8(path, *, errors: str = "strict") -> str:
    """Read a file abax owns. UTF-8, tolerating a BOM."""
    return Path(path).read_text(encoding=TEXT_ENCODING_READ, errors=errors)


def write_text_utf8(path, text: str, *, errors: str = "strict") -> None:
    """Write a file abax owns. UTF-8, never a BOM."""
    Path(path).write_text(text, encoding=TEXT_ENCODING, errors=errors)


def console_encoding() -> str:
    """The codec for text pipes to and from a **console child process**.

    A captured pipe is not a terminal, so the child does not get to negotiate:
    Windows console programs (``icacls``, ``cmd /c ...``, ``clip``) write the
    **OEM** codepage, which is neither UTF-8 nor the ANSI codepage. Elsewhere
    the locale's preferred encoding is the child's best guess.

    Callers pair this with ``errors="replace"``. Every consumer of these pipes
    either shows the text to a human or compares one snapshot against another,
    so a byte we cannot decode must degrade to U+FFFD — never take down the
    feature. That is the actual lesson of issue #5: the crash was not caused by
    guessing the encoding wrong, it was caused by guessing *strictly*.

    Not for a child that is **defined** to speak UTF-8 regardless of locale —
    pandoc, for instance. Those sites pass ``encoding="utf-8"`` literally, and
    are right to; a blanket helper applied there would reintroduce the bug from
    the other side.

    One caveat worth naming, since misplaced trust in a default is the whole
    bug class: off Windows this reports UTF-8 whenever *we* are in UTF-8 mode
    (``PYTHONUTF8=1``, which ci.yml sets), because ``getpreferredencoding``
    answers for this interpreter rather than for the child's locale. Modern
    POSIX locales are UTF-8 anyway, so the two agree in practice — and where
    they would not, ``errors="replace"`` at every call site keeps the mismatch
    to a mangled character rather than a traceback.
    """
    if sys.platform == "win32":
        import codecs

        try:
            codecs.lookup("oem")
        except LookupError:  # pragma: no cover - CPython on Windows always has it
            pass
        else:
            return "oem"
    import locale

    return locale.getpreferredencoding(False) or TEXT_ENCODING

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
