"""Live-data hub, WebSocket codec, and REST/WEBSOCKET formula tests.

Network is never required: the hub is exercised with an injected in-memory
transport, and the one real-socket test stands up a localhost HTTP server. The
WebSocket frame codec is checked against the worked examples in RFC 6455.
"""

from __future__ import annotations

import json
import threading
import time

import pytest

from abax.core import livedata, wsclient
from abax.core.errors import CellError, is_error
from abax.core.livedata import (
    OFF_MARKER,
    LiveError,
    LiveHub,
    check_url,
    coerce,
    extract_path,
)


def _wait_for(pred, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return pred()


# -- pure helpers ----------------------------------------------------------

def test_extract_path_dotted_and_index():
    obj = {"data": {"tickers": [{"price": 42.5}, {"price": 99}]}}
    assert extract_path(obj, "data.tickers[0].price") == 42.5
    assert extract_path(obj, "data.tickers[-1].price") == 99
    assert extract_path(obj, "") == obj
    assert extract_path([10, 20, 30], "[1]") == 20


def test_extract_path_missing_raises():
    with pytest.raises((KeyError, IndexError, TypeError)):
        extract_path({"a": 1}, "b")
    with pytest.raises((KeyError, IndexError, TypeError)):
        extract_path({"a": [1]}, "a[5]")
    with pytest.raises((KeyError, IndexError, TypeError)):
        extract_path({"a": 1}, "a.b")  # scalar where a mapping was expected


def test_coerce_leaf_kinds():
    assert coerce(None) == ""
    assert coerce(3.5) == 3.5
    assert coerce(True) is True
    assert coerce("hi") == "hi"
    assert coerce({"x": 1}) == '{"x":1}'
    assert coerce([1, 2]) == "[1,2]"


def test_check_url_scheme_allowlist():
    for ok in ("http://h/x", "https://h", "ws://h", "wss://h/y"):
        check_url(ok)  # no raise
    for bad in ("file:///etc/passwd", "gopher://h", "nourl"):
        with pytest.raises(LiveError):
            check_url(bad)


# -- hub with an injected transport (no network) ---------------------------

def _scripted_transport(values, *, then_block=True):
    """A transport that yields each of *values* once, then optionally blocks."""
    def _t(url, *, interval, stop_event):
        for v in values:
            yield (True, v)
        if then_block:
            stop_event.wait()
    return _t


def test_hub_disabled_refuses_subscribe():
    hub = LiveHub()
    assert hub.enabled is False
    with pytest.raises(LiveError):
        hub.subscribe("rest", "http://h/x", transport=_scripted_transport([{"a": 1}]))
    assert hub.source_count() == 0


def test_hub_delivers_value_and_bumps_generation():
    hub = LiveHub()
    hub.set_enabled(True)
    try:
        g0 = hub.generation()
        key = hub.subscribe(
            "rest", "http://h/x", "price", 5.0,
            transport=_scripted_transport([{"price": 7}, {"price": 8}]))
        assert _wait_for(lambda: hub.latest(key)[0] == 8)
        assert hub.generation() > g0
        assert hub.source_count() == 1
    finally:
        hub.stop_all()


def test_hub_subscribe_is_idempotent():
    hub = LiveHub()
    hub.set_enabled(True)
    try:
        tr = _scripted_transport([{"v": 1}])
        k1 = hub.subscribe("rest", "http://h", "v", 5.0, transport=tr)
        k2 = hub.subscribe("rest", "http://h", "v", 5.0, transport=tr)
        assert k1 == k2
        assert hub.source_count() == 1
    finally:
        hub.stop_all()


def test_hub_path_error_recorded_but_survives():
    hub = LiveHub()
    hub.set_enabled(True)
    try:
        key = hub.subscribe(
            "rest", "http://h", "missing", 5.0,
            transport=_scripted_transport([{"present": 1}]))
        assert _wait_for(lambda: hub.latest(key)[1] is not None)
        value, error = hub.latest(key)
        assert value is None
        assert "path not found" in error
    finally:
        hub.stop_all()


def test_hub_disable_stops_sources():
    hub = LiveHub()
    hub.set_enabled(True)
    hub.subscribe("rest", "http://h", "v", 5.0,
                  transport=_scripted_transport([{"v": 1}]))
    assert hub.source_count() == 1
    hub.set_enabled(False)
    assert hub.source_count() == 0
    assert hub.enabled is False


# -- WebSocket codec against RFC 6455 --------------------------------------

def test_ws_accept_key_rfc_example():
    # RFC 6455 §1.3 worked example.
    assert wsclient.accept_key("dGhlIHNhbXBsZSBub25jZQ==") == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="


def test_ws_decode_unmasked_hello():
    # RFC 6455 §5.7: single unmasked frame containing "Hello".
    frame = b"\x81\x05\x48\x65\x6c\x6c\x6f"
    fin, opcode, payload, consumed = wsclient.decode_frame(frame)
    assert fin == 1 and opcode == wsclient.OP_TEXT
    assert payload == b"Hello" and consumed == 7


def test_ws_decode_masked_hello():
    # RFC 6455 §5.7: single masked frame containing "Hello".
    frame = b"\x81\x85\x37\xfa\x21\x3d\x7f\x9f\x4d\x51\x58"
    fin, opcode, payload, consumed = wsclient.decode_frame(frame)
    assert payload == b"Hello" and consumed == len(frame)


def test_ws_encode_unmasked_matches_spec():
    assert wsclient.encode_frame(wsclient.OP_TEXT, b"Hello", mask=False) == b"\x81\x05Hello"


def test_ws_encode_decode_masked_roundtrip():
    payload = b"the quick brown fox" * 20  # forces the 16-bit length path
    frame = wsclient.encode_frame(wsclient.OP_BINARY, payload, mask=True)
    fin, opcode, out, consumed = wsclient.decode_frame(frame)
    assert out == payload and opcode == wsclient.OP_BINARY and consumed == len(frame)


def test_ws_decode_incomplete_returns_none():
    assert wsclient.decode_frame(b"\x81") is None            # header short
    assert wsclient.decode_frame(b"\x81\x05Hel") is None     # payload short


# -- real REST transport against a localhost server ------------------------

def test_rest_transport_fetches_localhost_json():
    import http.server

    payload = {"quote": {"last": 123.75}}

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # silence
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/q"
        stop = threading.Event()
        gen = livedata.rest_transport(url, interval=0.5, stop_event=stop)
        ok, obj = next(gen)
        assert ok is True
        assert extract_path(obj, "quote.last") == 123.75
    finally:
        stop.set()
        server.shutdown()


# -- REST / WEBSOCKET formulas ---------------------------------------------

def test_formula_off_marker_when_disabled():
    from abax.core import livefuncs

    livedata.HUB.set_enabled(False)
    assert livefuncs._rest(["http://h/x", "a.b"]) == OFF_MARKER
    assert livefuncs._websocket(["ws://h/x"]) == OFF_MARKER
    assert livedata.HUB.source_count() == 0  # no connection opened


def test_formula_bad_args():
    from abax.core import livefuncs

    livedata.HUB.set_enabled(True)
    try:
        assert is_error(livefuncs._rest([""]))            # empty url
        assert is_error(livefuncs._rest([["a", "b"]]))    # range as url
        assert is_error(livefuncs._rest(["http://h", "p", "notanumber"]))
    finally:
        livedata.HUB.set_enabled(False)


def test_formula_returns_na_then_value():
    from abax.core import livefuncs

    livedata.HUB.set_enabled(True)
    try:
        url = "http://h/live"
        # Pre-seed the hub with an injected transport under the exact key the
        # formula will compute (kind/url/path/default interval); subscribe is
        # idempotent, so the formula reuses this source instead of opening one.
        key = livedata.HUB.subscribe(
            "rest", url, "p", 5.0,
            transport=_scripted_transport([{"p": 55}]))
        assert _wait_for(lambda: livedata.HUB.latest(key)[0] == 55)
        assert livefuncs._rest([url, "p"]) == 55
    finally:
        livedata.HUB.set_enabled(False)


def test_rest_and_websocket_are_volatile():
    from abax.core.depgraph import ALWAYS_DIRTY_FUNCS

    assert "REST" in ALWAYS_DIRTY_FUNCS
    assert "WEBSOCKET" in ALWAYS_DIRTY_FUNCS


def test_na_marker_distinct_from_off():
    from abax.core import livefuncs

    livedata.HUB.set_enabled(True)
    try:
        # subscribed with a never-yielding transport → still #N/A, not #OFF
        url = "http://h/pending"
        livedata.HUB.subscribe("rest", url, "p", 5.0,
                               transport=lambda u, **k: iter(()))
        result = livefuncs._rest([url, "p"])
        assert is_error(result) and result.code == CellError.NA
    finally:
        livedata.HUB.set_enabled(False)
