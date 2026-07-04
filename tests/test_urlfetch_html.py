"""Tests for urlfetch's additive HTML-routing branch — stdlib, no real network.

These cover the new ``is_html_target`` predicate and the ``fetch_text`` /
``fetch_html_tables`` / ``fetch_largest_table`` helpers that route an HTML page
through :mod:`abax.core.io.webtable`. ``urlopen`` is monkeypatched with a fake
response (as in ``test_urlfetch``), so nothing hits a server.
"""

from __future__ import annotations

import io

import pytest

from abax.core.io import urlfetch
from abax.core.io.urlfetch import (
    UrlFetchError,
    fetch_html_tables,
    fetch_largest_table,
    fetch_text,
    guess_suffix,
    is_html_target,
)
from abax.core.io.webtable import WebTableError


class _FakeHeaders:
    def __init__(self, content_type: str | None, charset: str | None = "utf-8"):
        self._content_type = content_type
        self._charset = charset

    def get_content_type(self) -> str:
        return self._content_type or "application/octet-stream"

    def get_content_charset(self) -> str | None:
        return self._charset

    def get(self, name: str, default=None):
        if name.lower() == "content-type":
            return self._content_type if self._content_type is not None else default
        return default


class _FakeResponse:
    def __init__(
        self, data: bytes, content_type: str | None = None, charset: str | None = "utf-8"
    ):
        self._buf = io.BytesIO(data)
        self.headers = _FakeHeaders(content_type, charset)

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc) -> bool:
        return False


def _patch_urlopen(monkeypatch, response: _FakeResponse):
    def fake_urlopen(request, timeout=None):  # noqa: ARG001 - signature match
        return response

    monkeypatch.setattr(urlfetch.urllib.request, "urlopen", fake_urlopen)


_PAGE = """
<html><body>
<table><tr><td>nav</td></tr></table>
<table>
  <tr><th>City</th><th>Pop</th></tr>
  <tr><td>Oslo</td><td>700000</td></tr>
</table>
</body></html>
"""


# --- is_html_target --------------------------------------------------------


def test_is_html_target_by_extension():
    assert is_html_target("http://x/page.html") is True
    assert is_html_target("http://x/page.htm") is True


def test_is_html_target_by_content_type_when_no_data_extension():
    assert is_html_target("http://x/wiki/Oslo", "text/html; charset=utf-8") is True
    assert is_html_target("http://x/view", "application/xhtml+xml") is True


def test_is_html_target_extension_beats_html_content_type():
    # A real .csv served (wrongly) as text/html is still a CSV download.
    assert is_html_target("http://x/data.csv", "text/html") is False


def test_is_html_target_false_for_plain_data():
    assert is_html_target("http://x/data.json", "application/json") is False
    assert is_html_target("http://x/get", None) is False


# --- guess_suffix now knows about HTML ------------------------------------


def test_guess_suffix_html_extension_and_content_type():
    assert guess_suffix("http://x/page.html") == ".html"
    assert guess_suffix("http://x/wiki/Oslo", "text/html") == ".html"


# --- fetch_text ------------------------------------------------------------


def test_fetch_text_decodes_body(monkeypatch):
    _patch_urlopen(monkeypatch, _FakeResponse(b"<p>hi</p>", "text/html"))
    assert fetch_text("http://x/page.html") == "<p>hi</p>"


def test_fetch_text_uses_response_charset(monkeypatch):
    body = "café".encode("latin-1")
    _patch_urlopen(monkeypatch, _FakeResponse(body, "text/html", charset="latin-1"))
    assert fetch_text("http://x/page.html") == "café"


def test_fetch_text_rejects_file_scheme():
    with pytest.raises(UrlFetchError):
        fetch_text("file:///etc/passwd")


def test_fetch_text_enforces_max_bytes(monkeypatch):
    _patch_urlopen(monkeypatch, _FakeResponse(b"x" * 4096, "text/html"))
    with pytest.raises(UrlFetchError):
        fetch_text("http://x/big.html", max_bytes=16)


def test_fetch_text_wraps_urlerror(monkeypatch):
    def boom(request, timeout=None):  # noqa: ARG001 - signature match
        raise urlfetch.urllib.error.URLError("nope")

    monkeypatch.setattr(urlfetch.urllib.request, "urlopen", boom)
    with pytest.raises(UrlFetchError):
        fetch_text("http://x/page.html")


# --- fetch_html_tables / fetch_largest_table ------------------------------


def test_fetch_html_tables_returns_all_grids(monkeypatch):
    _patch_urlopen(monkeypatch, _FakeResponse(_PAGE.encode("utf-8"), "text/html"))
    tables = fetch_html_tables("http://x/page.html")
    assert tables == [
        [["nav"]],
        [["City", "Pop"], ["Oslo", "700000"]],
    ]


def test_fetch_largest_table_picks_data_table(monkeypatch):
    _patch_urlopen(monkeypatch, _FakeResponse(_PAGE.encode("utf-8"), "text/html"))
    grid = fetch_largest_table("http://x/page.html")
    assert grid == [["City", "Pop"], ["Oslo", "700000"]]


def test_fetch_largest_table_raises_without_table(monkeypatch):
    _patch_urlopen(monkeypatch, _FakeResponse(b"<p>no tables</p>", "text/html"))
    with pytest.raises(WebTableError):
        fetch_largest_table("http://x/page.html")
