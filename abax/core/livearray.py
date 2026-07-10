"""Array-spilling live data — the ``RESTTABLE`` formula.

Where ``=REST(url, "data.items[0].price")`` tracks ONE scalar, ``RESTTABLE``
turns a JSON *list* of records into a spilled 2-D block::

    =RESTTABLE("https://api.example/quotes", "data.items", "sym,price", 10)

produces a header row plus one row per record, spilling down and right from the
formula's cell exactly like TEXTSPLIT or FILTER (any function returning a
``list[list[...]]`` spills — see :mod:`abax.core.spill`).

Signature::

    RESTTABLE(url, [records_path], [columns], [interval])

* ``url`` — the JSON endpoint to poll.
* ``records_path`` — dotted path to the record list inside the document
  (``"data.items"``); omitted/empty, the document root is used.
* ``columns`` — which record fields become columns, in order. Accepts a range
  (``B1:D1``), an array literal (``{"sym","price"}``), or a single
  comma-separated string (``"sym,price"``). Key names may be dotted
  (``"quote.last"``) to dig inside nested records. Omitted, the columns are the
  union of the records' top-level keys in first-seen order.
* ``interval`` — poll period in seconds (default 5, like ``REST``).

Hub protocol — shared with the scalar formulas
----------------------------------------------
``RESTTABLE`` does no I/O itself. It mirrors ``REST``'s protocol against the
process-wide :data:`abax.core.livedata.HUB` exactly:

* live data disabled (consent off) → :data:`~abax.core.livedata.OFF_MARKER`
  (``"#OFF!"``); no connection is opened.
* enabled but no document has arrived yet → ``#N/A``.
* a document has arrived → the shaped grid (numbers stay numbers).

The subscription is registered with an **empty path** —
``HUB.subscribe("rest", url, "", interval)`` — i.e. it watches the *whole
document*, and the record-list extraction happens here at read time. Because
:func:`~abax.core.livedata.make_key` includes the path, this means every
``RESTTABLE`` on a URL (whatever its ``records_path``/``columns``) and every
scalar ``=REST(url)`` with no path share one background poller. The hub caches
the whole document through :func:`~abax.core.livedata.coerce`, which compacts a
dict/list to JSON text, so the cached value is re-parsed here before shaping.

Shaping failures (records path missing, the node is not a list of objects, the
cached body is not JSON) return ``#VALUE!`` rather than raising. Like the other
live formulas, ``RESTTABLE`` must be listed in
:data:`abax.core.depgraph.ALWAYS_DIRTY_FUNCS` so every recalc re-reads the hub.

Everything here is pure stdlib (→ core); the record extraction is reused from
:mod:`abax.core.io.restimport`.
"""

from __future__ import annotations

import json
from typing import Any

from .errors import CellError, is_error
from .io.restimport import RestImportError, extract_records
from .livedata import HUB, OFF_MARKER, LiveError, coerce, extract_path
from .values import RangeValue

__all__ = ["records_to_grid", "register"]


# --- small arg helpers (mirroring the livefuncs conventions) ----------------


def _arg(args: list, i: int, default: Any = None) -> Any:
    return args[i] if i < len(args) else default


def _text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


# --- shaping -----------------------------------------------------------------


def records_to_grid(payload: Any, records_path: str | None = None,
                    columns: "list[str] | None" = None) -> "list[list[Any]]":
    """Shape the record list at *records_path* inside *payload* into a grid.

    The record list is dug out with
    :func:`abax.core.io.restimport.extract_records` (dotted path; the resolved
    node must be a list of objects, or a single object which becomes one row).
    The result is ``[header_row] + one row per record`` — the shape the spill
    engine lays out as a block.

    * ``columns`` given — the header row is exactly *columns*, and each cell is
      that key dug out of the record. Keys may be dotted / indexed
      (``"quote.last"``, ``"bids[0]"``, via
      :func:`abax.core.livedata.extract_path`); a key missing from a record
      yields ``""``. With no records the header row alone is returned.
    * ``columns`` omitted — the header is the union of the records' top-level
      keys in first-seen order (the :func:`records_to_table` convention); a key
      absent from a record yields ``""``. With no records there is nothing to
      derive columns from, so :class:`RestImportError` is raised.

    Values pass through :func:`abax.core.livedata.coerce`: numbers and booleans
    stay themselves (so the spilled cells compute), ``None`` becomes ``""``,
    and a nested dict/list leaf is compacted to JSON text.

    Raises :class:`RestImportError` when the records path is missing or the
    node cannot be shaped into rows.
    """
    records = extract_records(payload, records_path or None)

    if columns:
        header = [str(c) for c in columns]
        rows = [[_dig(record, key) for key in header] for record in records]
        return [header] + rows

    if not records:
        raise RestImportError(
            f"records path {records_path or '(root)'!r} has no records to "
            "derive columns from"
        )

    header = []
    seen: set = set()
    for record in records:
        for key in record:
            if key not in seen:
                seen.add(key)
                header.append(key)
    rows = [[coerce(record[h]) if h in record else "" for h in header]
            for record in records]
    return [list(header)] + rows


def _dig(record: dict, key: str) -> Any:
    """One cell: *key* (possibly dotted/indexed) dug out of *record*, or ``""``."""
    try:
        return coerce(extract_path(record, key))
    except (KeyError, IndexError, TypeError):
        return ""


def _columns_list(arg: Any) -> "list[str] | None":
    """Normalize the ``columns`` argument to a list of key names, or ``None``.

    Accepts a :class:`RangeValue` (flattened row-major), a list / list-of-lists
    (an array literal), or a scalar whose text is split on commas. Blank
    entries are dropped; an empty/blank argument means "derive the columns".
    """
    if arg is None:
        return None
    if isinstance(arg, RangeValue):
        vals = arg.flat()
    elif isinstance(arg, list):
        vals = []
        for item in arg:
            if isinstance(item, list):
                vals.extend(item)
            else:
                vals.append(item)
    else:
        vals = _text(arg).split(",")
    cols = [c for c in (_text(v).strip() for v in vals) if c]
    return cols or None


# --- the formula --------------------------------------------------------------


def _resttable(args: list) -> Any:
    """``RESTTABLE(url, [records_path], [columns], [interval])`` — spill a JSON
    record list as ``[header] + rows`` (see the module docstring for the full
    contract and the hub-sharing rationale)."""
    url_arg = _arg(args, 0)
    if is_error(url_arg):
        return url_arg
    if isinstance(url_arg, (RangeValue, list)):
        return CellError(CellError.VALUE)
    url = _text(url_arg).strip()
    if not url:
        return CellError(CellError.VALUE)

    path_arg = _arg(args, 1, "")
    if is_error(path_arg):
        return path_arg
    records_path = _text(path_arg).strip()

    cols_arg = _arg(args, 2)
    if is_error(cols_arg):
        return cols_arg
    columns = _columns_list(cols_arg)

    interval = 5.0
    if len(args) >= 4 and args[3] is not None:
        try:
            interval = float(args[3])
        except (TypeError, ValueError):
            return CellError(CellError.VALUE)

    # Hub protocol — identical to REST: consent gate, subscribe, read latest.
    # Path is EMPTY on purpose: one whole-document poller per URL, shared with
    # scalar REST cells; the records_path digging happens below, per read.
    if not HUB.enabled:
        return OFF_MARKER
    try:
        key = HUB.subscribe("rest", url, "", interval)
    except LiveError:
        return CellError(CellError.VALUE)

    value, _error = HUB.latest(key)
    if value is None:
        return CellError(CellError.NA)  # subscribed, awaiting first document

    # The hub coerced the whole document; a dict/list arrived as compact JSON
    # text, so parse it back before shaping. (A scalar document cannot hold
    # records — extract_records rejects it below.)
    payload = value
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            return CellError(CellError.VALUE)

    try:
        return records_to_grid(payload, records_path or None, columns)
    except (RestImportError, KeyError, IndexError, TypeError, ValueError):
        return CellError(CellError.VALUE)


_REGISTRY = {
    "RESTTABLE": _resttable,
}


def register(functions: dict) -> None:
    """Merge the array live-data formulas into the engine's function table."""
    functions.update(_REGISTRY)
