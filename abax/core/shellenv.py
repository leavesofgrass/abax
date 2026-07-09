"""Build the ``$ABAX_*`` environment variables that abax exports into a child
shell or terminal so external commands can see the current grid selection.

When the user drops to a shell (TUI ``:!`` command) or launches an embedded
terminal from the GUI, abax hands the child process a set of environment
variables describing the active selection:

* ``ABAX_ACTIVE_CELL``      — the top-left cell in A1 notation (e.g. ``"B2"``).
* ``ABAX_SELECTION_RANGE``  — the selection as ``"B2:D5"`` (or bare ``"B2"`` for
  a single cell).
* ``ABAX_SELECTION_JSON``   — a compact JSON 2-D array of the *computed* values.
* ``ABAX_SELECTION_TSV``    — the same block as tab-separated *raw* text.
* ``ABAX_SELECTION_TRUNCATED`` — ``"1"`` (only present) when the selection was
  too large and the JSON/TSV payloads were capped.

Pure standard library (``json``, ``os``); no dependency on the GUI/TUI layers,
so a caller can hand the result straight to ``subprocess`` / a PTY terminal.
"""

from __future__ import annotations

import json
import os
from typing import Any

from .reference import to_a1

# Guard against building a multi-megabyte environment variable from a giant
# selection: past this many cells we stop emitting values and flag truncation.
_MAX_CELLS = 10_000


def _json_scalar(value: Any) -> Any:
    """Coerce a computed cell value into a JSON-serialisable scalar.

    Numbers (``int``/``float``, but not ``bool``) pass through as numbers;
    ``None`` becomes JSON ``null``; everything else — text, booleans and
    ``CellError`` values (whose ``str`` is their ``#NAME?``-style code) — becomes
    a string. A value that somehow isn't JSON-serialisable falls back to
    ``str(value)``.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        # bool is an int subclass; keep it as text so it isn't emitted as 0/1.
        return str(value)
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value
    return str(value)


def selection_env(sheet: Any, r1: int, c1: int, r2: int, c2: int) -> dict[str, str]:
    """Build the ``$ABAX_*`` selection-context variables for one rectangle.

    ``sheet`` is a :class:`abax.core.sheet.Sheet`; ``(r1, c1)``–``(r2, c2)`` are
    zero-based, inclusive corners in any order (they are normalised so that
    ``r1 <= r2`` and ``c1 <= c2``). Returns a dict of environment-variable names
    to string values, ready to merge into a child process environment.
    """
    r1, r2 = (r1, r2) if r1 <= r2 else (r2, r1)
    c1, c2 = (c1, c2) if c1 <= c2 else (c2, c1)

    top_left = to_a1(r1, c1)
    bottom_right = to_a1(r2, c2)
    single = (r1 == r2 and c1 == c2)

    env: dict[str, str] = {
        "ABAX_ACTIVE_CELL": top_left,
        "ABAX_SELECTION_RANGE": top_left if single else f"{top_left}:{bottom_right}",
    }

    n_cells = (r2 - r1 + 1) * (c2 - c1 + 1)
    truncated = n_cells > _MAX_CELLS

    json_rows: list[list[Any]] = []
    tsv_lines: list[str] = []
    emitted = 0
    for r in range(r1, r2 + 1):
        if truncated and emitted >= _MAX_CELLS:
            break
        json_row: list[Any] = []
        raw_row: list[str] = []
        for c in range(c1, c2 + 1):
            if truncated and emitted >= _MAX_CELLS:
                break
            json_row.append(_json_scalar(sheet.get_value(r, c)))
            # Raw text: tabs/newlines would corrupt the TSV grid, so neutralise
            # them to spaces (rare, but a formula's raw source could contain one).
            raw = sheet.get_raw(r, c).replace("\t", " ").replace("\n", " ").replace("\r", " ")
            raw_row.append(raw)
            emitted += 1
        json_rows.append(json_row)
        tsv_lines.append("\t".join(raw_row))

    try:
        env["ABAX_SELECTION_JSON"] = json.dumps(json_rows, separators=(",", ":"))
    except (TypeError, ValueError):
        # Defensive: fall back to stringifying every element if some value slips
        # through the scalar coercion as non-serialisable.
        safe = [[str(v) for v in row] for row in json_rows]
        env["ABAX_SELECTION_JSON"] = json.dumps(safe, separators=(",", ":"))
    env["ABAX_SELECTION_TSV"] = "\n".join(tsv_lines)

    if truncated:
        env["ABAX_SELECTION_TRUNCATED"] = "1"

    return env


def merged_env(
    base: dict[str, str] | None,
    sheet: Any,
    r1: int,
    c1: int,
    r2: int,
    c2: int,
) -> dict[str, str]:
    """Return ``base`` (or :data:`os.environ`) overlaid with the selection vars.

    A convenience for callers wiring the selection context into ``subprocess``
    or a PTY terminal: the returned dict is a fresh copy — ``os.environ`` is not
    mutated — with every ``ABAX_*`` key from :func:`selection_env` layered on
    top of ``base``.
    """
    merged = dict(base if base is not None else os.environ)
    merged.update(selection_env(sheet, r1, c1, r2, c2))
    return merged
