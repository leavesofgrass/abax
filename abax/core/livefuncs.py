"""Live-data formulas — ``REST`` and ``WEBSOCKET``.

Two volatile functions that turn a cell into a live view of an external JSON
source. They do no I/O themselves: each call registers a subscription with the
process-wide :data:`abax.core.livedata.HUB` (idempotent, so many cells watching
one URL share a single background thread) and returns the latest value the hub
has cached.

* ``REST(url, [path], [interval])`` — poll a JSON endpoint every *interval*
  seconds (default 5, floored at 0.5).
* ``WEBSOCKET(url, [path])`` — stream JSON text frames from a WebSocket.

*path* digs a leaf out of the decoded JSON (``"data.price"``, ``"[0].last"``);
omitted, the whole document is shown. Both are registered volatile in
:data:`abax.core.depgraph.ALWAYS_DIRTY_FUNCS`, so each recalc re-reads the hub.

Values, by state:

* live data disabled (consent off) → :data:`~abax.core.livedata.OFF_MARKER`
  (``"#OFF!"``); no connection is opened.
* enabled but no value has arrived yet → ``#N/A``.
* a value has arrived → that value (numbers stay numbers).
* the last fetch/path failed but an earlier value exists → the last good value
  (a transient blip does not blank the cell).
"""

from __future__ import annotations

from typing import Any

from .errors import CellError, is_error
from .livedata import HUB, OFF_MARKER, LiveError
from .values import RangeValue


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


def _live(kind: str, args: list, *, default_interval: float) -> Any:
    url_arg = _arg(args, 0)
    if is_error(url_arg):
        return url_arg
    if isinstance(url_arg, (RangeValue, list)):
        return CellError(CellError.VALUE)
    url = _text(url_arg).strip()
    if not url:
        return CellError(CellError.VALUE)
    path = _text(_arg(args, 1, "")).strip()

    interval = default_interval
    if len(args) >= 3 and args[2] is not None:
        try:
            interval = float(args[2])
        except (TypeError, ValueError):
            return CellError(CellError.VALUE)

    if not HUB.enabled:
        return OFF_MARKER
    try:
        key = HUB.subscribe(kind, url, path, interval)
    except LiveError:
        return CellError(CellError.VALUE)

    value, _error = HUB.latest(key)
    if value is None:
        return CellError(CellError.NA)  # subscribed, awaiting first frame
    return value


def _rest(args: list) -> Any:
    return _live("rest", args, default_interval=5.0)


def _websocket(args: list) -> Any:
    return _live("websocket", args, default_interval=0.0)


_REGISTRY = {
    "REST": _rest,
    "WEBSOCKET": _websocket,
}


def register(functions: dict) -> None:
    """Merge the live-data formulas into the engine's function table."""
    functions.update(_REGISTRY)
