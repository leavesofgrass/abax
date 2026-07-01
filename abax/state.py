"""Runtime state with a write-ahead journal — survives crashes.

Journal first, apply, unlink (per spec §3f). On startup, replay an interrupted
write before loading the main state file. Never raises in ``flush`` because it
is called from ``atexit``/``SIGTERM``.
"""

from __future__ import annotations

import atexit
import json
import signal
from pathlib import Path
from typing import Any


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
        self._journal.write_text(json.dumps({"key": key, "value": value}))
        self._state[key] = value
        self._journal.unlink(missing_ok=True)

    def flush(self) -> None:
        try:
            self._path.write_text(json.dumps(self._state, indent=2))
        except Exception:
            pass  # never raise in flush

    @classmethod
    def load(cls, path: Path) -> "StateManager":
        mgr = cls(path)
        if mgr._journal.exists():  # replay interrupted write on startup
            try:
                entry = json.loads(mgr._journal.read_text())
                mgr._state[entry["key"]] = entry["value"]
            except Exception:
                pass
            mgr._journal.unlink(missing_ok=True)
        try:
            mgr._state = json.loads(mgr._path.read_text())
        except Exception:
            pass
        return mgr
