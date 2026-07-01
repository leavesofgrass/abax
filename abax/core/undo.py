"""A snapshot-based undo/redo stack with coalescing and labels (Qt-free).

Snapshots are opaque, independent state objects (abax uses the workbook's
exchange-envelope dict). The caller takes a ``checkpoint(state, label, …)`` of the
CURRENT state *before* each mutation; ``undo``/``redo`` swap between the live state
and a stored one. Snapshot-based (rather than per-command inverses) keeps undo
correct across every kind of mutation — edits, fills, paste, sort, structural
row/column ops — without per-action inverse logic.

Two refinements:
- **Coalescing** — consecutive checkpoints sharing a ``coalesce_key`` within
  ``coalesce_window`` seconds collapse into the first one, so a burst of rapid
  edits is a single undo step. The caller supplies ``now`` (e.g. ``time.monotonic``)
  so the policy is testable/deterministic.
- **Labels** — each checkpoint carries a human label (``"edit A1"``, ``"paste"``)
  that travels with its transition, powering an undo-history view.
"""

from __future__ import annotations

from typing import Any

_DEFAULT_WINDOW = 0.8


class UndoStack:
    def __init__(self, max_depth: int = 100, coalesce_window: float = _DEFAULT_WINDOW) -> None:
        self._undo: list[tuple[Any, str]] = []
        self._redo: list[tuple[Any, str]] = []
        self._max = max(1, max_depth)
        self.coalesce_window = coalesce_window
        self._last_key: Any = None
        self._last_time: float | None = None

    def checkpoint(self, state: Any, label: str = "",
                   coalesce_key: Any = None, now: float | None = None) -> bool:
        """Record ``state`` (the state about to be mutated). Returns False if the
        checkpoint was coalesced into the previous one (no new undo step)."""
        if (coalesce_key is not None and coalesce_key == self._last_key
                and now is not None and self._last_time is not None
                and (now - self._last_time) < self.coalesce_window):
            self._last_time = now            # slide the window; keep pre-burst snap
            return False
        self._undo.append((state, label))
        if len(self._undo) > self._max:
            self._undo.pop(0)
        self._redo.clear()
        self._last_key = coalesce_key
        self._last_time = now
        return True

    def undo(self, current: Any) -> tuple[Any, str] | None:
        """Return ``(prior_state, label)`` to restore, saving ``current`` for redo."""
        if not self._undo:
            return None
        state, label = self._undo.pop()
        self._redo.append((current, label))
        self._last_key = None                # a new edit after undo shouldn't coalesce
        return state, label

    def redo(self, current: Any) -> tuple[Any, str] | None:
        if not self._redo:
            return None
        state, label = self._redo.pop()
        self._undo.append((current, label))
        self._last_key = None
        return state, label

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo_labels(self) -> list[str]:
        """Undoable action labels, oldest → most-recent."""
        return [lab for _s, lab in self._undo]

    def redo_labels(self) -> list[str]:
        """Redoable action labels, next-to-redo first."""
        return [lab for _s, lab in reversed(self._redo)]

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
        self._last_key = None
        self._last_time = None
