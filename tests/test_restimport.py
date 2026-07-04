"""Tests for the JSON REST importer — pure stdlib, no real network access.

The pure shaping helpers (:func:`extract_records`, :func:`records_to_table`)
are exercised on literal Python/JSON fixtures. The fetch path monkeypatches
``urllib.request.urlopen`` with a fake response that records the request it was
handed, so header/param/token building is asserted without a server.
"""

from __future__ import annotations

import io
import json
import urllib.parse

import pytest

from abax.core.io import restimport
from abax.core.io.restimport import (
    RestImportError,
    extract_records,
    fetch_json,
    import_rest_table,
    records_to_table,
)


class _FakeHeaders:
    """Minimal response header set exposing a charset like the real thing."""

    def __init__(self, charset: str | None = "utf-8"):
        self._charset = charset

    def get_content_charset(self) -> str | None:
        return self._charset


class _FakeResponse:
    """Context-managed fake of ``urlopen``'s return value."""

    def __init__(self, data: bytes, charset: str | None = "utf-8"):
        self._buf = io.BytesIO(data)
        self.headers = _FakeHeaders(charset)

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc) -> bool:
        return False


def _patch_urlopen(monkeypatch, payload, *, capture: dict | None = None):
    """Patch urlopen to return ``payload`` (bytes or JSON-able) and record args."""
    if not isinstance(payload, (bytes, bytearray)):
        payload = json.dumps(payload).encode("utf-8")

    def fake_urlopen(request, timeout=None):  # noqa: ARG001 - signature match
        if capture is not None:
            capture["url"] = request.full_url
            capture["headers"] = dict(request.header_items())
        return _FakeResponse(payload)

    monkeypatch.setattr(restimport.urllib.request, "urlopen", fake_urlopen)


# --- extract_records -------------------------------------------------------


def test_extract_records_dotted_path():
    payload = {"data": {"items": [{"a": 1}, {"a": 2}]}}
    assert extract_records(payload, "data.items") == [{"a": 1}, {"a": 2}]


def test_extract_records_empty_path_uses_whole_payload():
    payload = [{"a": 1}, {"a": 2}]
    assert extract_records(payload, None) == payload
    assert extract_records(payload, "") == payload


def test_extract_records_single_object_is_wrapped():
    assert extract_records({"a": 1, "b": 2}, None) == [{"a": 1, "b": 2}]


def test_extract_records_skips_non_dict_entries_in_list():
    payload = {"items": [{"a": 1}, "junk", None, {"a": 2}]}
    assert extract_records(payload, "items") == [{"a": 1}, {"a": 2}]


def test_extract_records_missing_path_raises():
    with pytest.raises(RestImportError):
        extract_records({"data": {}}, "data.items")


def test_extract_records_list_of_scalars_raises():
    with pytest.raises(RestImportError):
        extract_records({"items": [1, 2, 3]}, "items")


def test_extract_records_wrong_leaf_type_raises():
    with pytest.raises(RestImportError):
        extract_records({"n": 5}, "n")


# --- records_to_table ------------------------------------------------------


def test_records_to_table_unions_keys_first_seen_order():
    records = [{"id": 1, "name": "A"}, {"name": "B", "city": "NYC"}]
    headers, rows = records_to_table(records)
    assert headers == ["id", "name", "city"]
    assert rows == [["1", "A", ""], ["", "B", "NYC"]]


def test_records_to_table_scalar_rendering():
    records = [{"i": 3, "f": 2.0, "b": True, "n": None, "s": "x"}]
    headers, rows = records_to_table(records)
    assert headers == ["i", "f", "b", "n", "s"]
    # int, float-integral -> no ".0", bool -> TRUE/FALSE, None -> "".
    assert rows == [["3", "2", "TRUE", "", "x"]]


def test_records_to_table_nested_value_becomes_json():
    records = [{"obj": {"k": 1}, "arr": [1, 2]}]
    headers, rows = records_to_table(records)
    assert headers == ["obj", "arr"]
    assert rows == [['{"k": 1}', "[1, 2]"]]


def test_records_to_table_empty_is_empty():
    assert records_to_table([]) == ([], [])


# --- fetch_json ------------------------------------------------------------


def test_fetch_json_parses_body(monkeypatch):
    _patch_urlopen(monkeypatch, {"ok": True, "n": 5})
    assert fetch_json("http://api.test/x") == {"ok": True, "n": 5}


def test_fetch_json_merges_params_and_keeps_existing_query(monkeypatch):
    cap: dict = {}
    _patch_urlopen(monkeypatch, {"ok": 1}, capture=cap)

    fetch_json("http://api.test/x?a=1", params={"b": 2, "flag": True})

    parts = urllib.parse.urlsplit(cap["url"])
    q = dict(urllib.parse.parse_qsl(parts.query))
    assert q == {"a": "1", "b": "2", "flag": "true"}


def test_fetch_json_sets_bearer_token_header(monkeypatch):
    cap: dict = {}
    _patch_urlopen(monkeypatch, {"ok": 1}, capture=cap)

    fetch_json("http://api.test/x", token="secret123")

    # urllib title-cases header keys on the Request object.
    assert cap["headers"].get("Authorization") == "Bearer secret123"


def test_fetch_json_explicit_authorization_header_wins(monkeypatch):
    cap: dict = {}
    _patch_urlopen(monkeypatch, {"ok": 1}, capture=cap)

    fetch_json(
        "http://api.test/x",
        token="ignored",
        headers={"Authorization": "Basic abc"},
    )
    assert cap["headers"].get("Authorization") == "Basic abc"


def test_fetch_json_custom_headers_passed_through(monkeypatch):
    cap: dict = {}
    _patch_urlopen(monkeypatch, {"ok": 1}, capture=cap)

    fetch_json("http://api.test/x", headers={"X-Api-Key": "k"})
    assert cap["headers"].get("X-api-key") == "k"


def test_fetch_json_rejects_file_scheme():
    with pytest.raises(RestImportError):
        fetch_json("file:///etc/passwd")


def test_fetch_json_rejects_ftp_scheme():
    with pytest.raises(RestImportError):
        fetch_json("ftp://host/data.json")


def test_fetch_json_invalid_json_raises(monkeypatch):
    _patch_urlopen(monkeypatch, b"not json at all")
    with pytest.raises(RestImportError):
        fetch_json("http://api.test/x")


def test_fetch_json_wraps_urlerror(monkeypatch):
    def boom(request, timeout=None):  # noqa: ARG001 - signature match
        raise restimport.urllib.error.URLError("nope")

    monkeypatch.setattr(restimport.urllib.request, "urlopen", boom)
    with pytest.raises(RestImportError):
        fetch_json("http://api.test/x")


def test_fetch_json_enforces_max_bytes(monkeypatch):
    _patch_urlopen(monkeypatch, b'{"x": 1}' + b" " * 4096)
    with pytest.raises(RestImportError):
        fetch_json("http://api.test/x", max_bytes=8)


# --- import_rest_table (end to end, faked transport) -----------------------


def test_import_rest_table_end_to_end(monkeypatch):
    payload = {
        "meta": {"page": 1},
        "data": {
            "items": [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob", "email": "bob@x.test"},
            ]
        },
    }
    _patch_urlopen(monkeypatch, payload)

    headers, rows = import_rest_table(
        "http://api.test/users", records_path="data.items"
    )
    assert headers == ["id", "name", "email"]
    assert rows == [["1", "Alice", ""], ["2", "Bob", "bob@x.test"]]


def test_import_rest_table_root_list(monkeypatch):
    _patch_urlopen(monkeypatch, [{"a": 1}, {"a": 2, "b": 3}])
    headers, rows = import_rest_table("http://api.test/x")
    assert headers == ["a", "b"]
    assert rows == [["1", ""], ["2", "3"]]
