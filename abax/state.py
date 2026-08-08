"""Runtime state with a write-ahead journal — survives crashes.

Journal first, apply, unlink (per spec §3f). On startup, load the main state
file and then replay an interrupted write *over* it — the journal entry is the
newer of the two, so it wins. Never raises in ``flush`` because it is called
from ``atexit``/``SIGTERM``.

Both files are written and read back by abax alone, so their encoding is a
contract abax has with itself: UTF-8 on both sides, via
:func:`abax._runtime.read_text_utf8` / :func:`~abax._runtime.write_text_utf8`.
Leaving it to the platform default is the defect that shipped as issue #1 in
``settings.py``. Here the same defect is quieter and costs more: ``load``
swallows every exception, so a byte it cannot decode is not an error, it is an
empty state dict — the *whole* dict, not just the key the byte sat in — and the
next ``flush`` writes that empty dict back over the file. One bad byte, every
key gone, nothing left to recover from.

Which is why the reader is not strict UTF-8. A state file written before this
contract was pinned is in the platform's encoding, and refusing to decode it is
that same total loss by a different route — see :func:`_read_text`.
"""

from __future__ import annotations

import atexit
import json
import locale
import signal
from pathlib import Path
from typing import Any

from ._runtime import read_text_utf8, write_text_utf8


def _read_text(path: Path) -> str:
    """Read one state file: UTF-8, with a single fallback for legacy files.

    What abax writes is UTF-8. What abax *wrote*, before the encoding was named,
    is whatever the platform default was on that machine, so a strict UTF-8 read
    of such a file raises on its first non-ASCII byte — and both callers funnel
    that into "the state is empty", after which ``flush`` overwrites the file.
    So retry once with :func:`locale.getpreferredencoding`, which is by
    construction the codec that wrote it. ``flush`` re-emits UTF-8, so the file
    migrates itself on the first save and the fallback is never taken twice.

    Retrying as UTF-8 with ``errors="replace"`` would be the smaller edit and
    the wrong one: it turns legacy bytes into U+FFFD rather than into the
    characters they stand for, and ``flush`` then writes that back — trading a
    recoverable failure for permanent, silent corruption. The locale codec can
    at least be *right*, and on the common path (same machine, same locale as
    wrote the file) it is.

    ``errors="replace"`` on that second read is the last resort, for the file
    carried over from a different locale. There it does mean one mangled
    character — but the alternative is discarding the other keys as well, and
    both roads end at the same ``flush`` overwrite, so the one that keeps more
    of the user's data wins.
    """
    try:
        return read_text_utf8(path)
    except UnicodeDecodeError:
        return Path(path).read_text(
            encoding=locale.getpreferredencoding(False), errors="replace")


class StateManager:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._journal = self._path.with_suffix(".journal")
        self._state: dict[str, Any] = {}
        atexit.register(self.flush)
        try:
            signal.signal(signal.SIGTERM, lambda *_: self.flush())
        except (ValueError, OSError):
            # SIGTERM unavailable on some platforms / non-main threads.
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Journal first, then apply — survives a crash between the two."""
        write_text_utf8(self._journal, json.dumps({"key": key, "value": value}))
        self._state[key] = value
        self._journal.unlink(missing_ok=True)

    def flush(self) -> None:
        try:
            write_text_utf8(self._path, json.dumps(self._state, indent=2))
        except Exception:
            pass  # never raise in flush

    @classmethod
    def load(cls, path: Path) -> "StateManager":
        mgr = cls(path)
        # Main file first, journal second. The other order looks equivalent and
        # is not: replaying into ``_state`` and *then* assigning the parsed main
        # file over it drops the replayed entry on every run where the main file
        # is readable — i.e. the normal one — which leaves the journal doing
        # nothing except in the rare case that the main file is missing too.
        try:
            mgr._state = json.loads(_read_text(mgr._path))
        except Exception:
            pass
        if mgr._journal.exists():  # replay interrupted write on startup
            try:
                entry = json.loads(_read_text(mgr._journal))
                mgr._state[entry["key"]] = entry["value"]
            except Exception:
                pass
            mgr._journal.unlink(missing_ok=True)
        return mgr
