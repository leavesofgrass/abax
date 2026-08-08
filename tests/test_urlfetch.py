"""Tests for the URL-fetch helper — pure stdlib, no real network access.

The download tests monkeypatch ``urllib.request.urlopen`` with a fake response
object that streams bytes and exposes a header mapping, so nothing ever hits a
real server.
"""

from __future__ import annotations

import argparse
import io

import pytest

from abax.core.io import urlfetch
from abax.core.io.urlfetch import UrlFetchError, fetch_url, guess_suffix


class _FakeHeaders:
    """Minimal stand-in for an ``email.message.Message`` response header set."""

    def __init__(self, content_type: str | None):
        self._content_type = content_type

    def get_content_type(self) -> str:
        # Mimic email.message.Message: a sane default when nothing was set.
        return self._content_type or "application/octet-stream"

    def get(self, name: str, default=None):
        if name.lower() == "content-type":
            return self._content_type if self._content_type is not None else default
        return default


class _FakeResponse:
    """Context-managed fake of ``urlopen``'s return value."""

    def __init__(self, data: bytes, content_type: str | None = None):
        self._buf = io.BytesIO(data)
        self.headers = _FakeHeaders(content_type)

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


# --- guess_suffix: by URL extension ---------------------------------------


def test_guess_suffix_by_url_extension():
    assert guess_suffix("http://x/data.csv") == ".csv"
    assert guess_suffix("http://x/data.json") == ".json"
    assert guess_suffix("http://x/data.tsv") == ".tsv"


def test_guess_suffix_url_extension_beats_content_type():
    # A known URL extension is trusted over a conflicting content-type.
    assert guess_suffix("http://x/data.csv", "application/json") == ".csv"


# --- guess_suffix: by content-type ----------------------------------------


def test_guess_suffix_by_content_type():
    assert guess_suffix("http://x/download?id=5", "text/csv") == ".csv"
    assert guess_suffix("http://x/download?id=5", "application/json") == ".json"
    assert guess_suffix("http://x/download", "text/tab-separated-values") == ".tsv"


def test_guess_suffix_content_type_with_charset_param():
    assert guess_suffix("http://x/get", "text/csv; charset=utf-8") == ".csv"


# --- guess_suffix: fallbacks ----------------------------------------------


def test_guess_suffix_fallback_binary():
    assert guess_suffix("http://x/download?id=5", None) == ".bin"
    assert guess_suffix("http://x/blob", "application/octet-stream") == ".bin"


def test_guess_suffix_fallback_text_plain():
    assert guess_suffix("http://x/download", "text/plain") == ".csv"


def test_guess_suffix_never_empty():
    assert guess_suffix("http://x/nopath") == ".bin"


# --- fetch_url: happy path -------------------------------------------------


def test_fetch_url_downloads_and_round_trips(monkeypatch, tmp_path):
    payload = b"a,b,c\n1,2,3\n"
    _patch_urlopen(monkeypatch, _FakeResponse(payload, "text/csv"))

    path = fetch_url("http://example.test/download?id=5", dest_dir=str(tmp_path))

    assert path.suffix == ".csv"
    assert path.parent == tmp_path
    assert path.read_bytes() == payload


def test_fetch_url_suffix_from_url_extension(monkeypatch, tmp_path):
    payload = b'{"k": 1}'
    _patch_urlopen(monkeypatch, _FakeResponse(payload, "application/octet-stream"))

    path = fetch_url("http://example.test/data.json", dest_dir=str(tmp_path))

    assert path.suffix == ".json"
    assert path.read_bytes() == payload


# --- fetch_url: rejections -------------------------------------------------


def test_fetch_url_rejects_file_scheme(tmp_path):
    with pytest.raises(UrlFetchError):
        fetch_url("file:///etc/passwd", dest_dir=str(tmp_path))


def test_fetch_url_rejects_unknown_scheme(tmp_path):
    with pytest.raises(UrlFetchError):
        fetch_url("gopher://example.test/data", dest_dir=str(tmp_path))


def test_fetch_url_enforces_max_bytes(monkeypatch, tmp_path):
    payload = b"x" * 4096
    _patch_urlopen(monkeypatch, _FakeResponse(payload, "text/csv"))

    with pytest.raises(UrlFetchError):
        fetch_url(
            "http://example.test/big.csv",
            max_bytes=16,
            dest_dir=str(tmp_path),
        )


def test_fetch_url_wraps_urlerror(monkeypatch, tmp_path):
    def boom(request, timeout=None):  # noqa: ARG001 - signature match
        raise urlfetch.urllib.error.URLError("nope")

    monkeypatch.setattr(urlfetch.urllib.request, "urlopen", boom)

    with pytest.raises(UrlFetchError):
        fetch_url("http://example.test/data.csv", dest_dir=str(tmp_path))


# --- fetched(): the download must not outlive its consumer ------------------
#
# A successful fetch_url leaves a full copy of the (possibly private) remote
# data in the temp directory. Every caller is expected to consume the download
# inside urlfetch.fetched(), which removes it afterwards no matter how the
# block exits. These tests pin that contract and the two production callers.


def _redirect_tempdir(monkeypatch, tmp_path):
    """Point bare ``tempfile`` (no ``dest_dir=``) at ``tmp_path``.

    The production callers do not pass ``dest_dir``, so this is how a test can
    watch what they leave behind in "the system temp directory".
    """
    monkeypatch.setattr(urlfetch.tempfile, "tempdir", str(tmp_path))


def test_fetched_removes_the_download_on_success(monkeypatch, tmp_path):
    _patch_urlopen(monkeypatch, _FakeResponse(b"a,b\n1,2\n", "text/csv"))

    with urlfetch.fetched("http://example.test/data.csv", dest_dir=str(tmp_path)) as path:
        inside = path
        assert inside.exists()
        assert inside.read_bytes() == b"a,b\n1,2\n"

    assert not inside.exists()
    assert list(tmp_path.iterdir()) == []


def test_fetched_removes_the_download_when_the_body_raises(monkeypatch, tmp_path):
    _patch_urlopen(monkeypatch, _FakeResponse(b"a,b\n1,2\n", "text/csv"))

    seen = []
    with pytest.raises(ValueError):
        with urlfetch.fetched(
            "http://example.test/data.csv", dest_dir=str(tmp_path)
        ) as path:
            seen.append(path)
            raise ValueError("consumer blew up")

    assert seen and not seen[0].exists()
    assert list(tmp_path.iterdir()) == []


def test_fetched_tolerates_an_already_removed_download(monkeypatch, tmp_path):
    _patch_urlopen(monkeypatch, _FakeResponse(b"a,b\n1,2\n", "text/csv"))

    with urlfetch.fetched("http://example.test/data.csv", dest_dir=str(tmp_path)) as path:
        path.unlink()  # a consumer that moved/consumed the file itself

    assert list(tmp_path.iterdir()) == []


def test_document_opened_inside_fetched_survives_the_cleanup(monkeypatch, tmp_path):
    """Document.open must read eagerly — the GUI returns a doc past the block."""
    from abax.engine.document import Document

    _patch_urlopen(monkeypatch, _FakeResponse(b"a,b\n1,2\n3,4\n", "text/csv"))

    with urlfetch.fetched("http://example.test/data.csv", dest_dir=str(tmp_path)) as path:
        doc = Document.open(str(path))

    assert list(tmp_path.iterdir()) == []
    sheet = doc.workbook.sheet
    assert sheet.get_value(1, 0) == 1.0
    assert sheet.get_value(2, 1) == 4.0


# --- the CLI caller: abax fetch --------------------------------------------


def test_cmd_fetch_leaves_no_temp_file_on_success(monkeypatch, tmp_path, capsys):
    from abax import app

    _patch_urlopen(monkeypatch, _FakeResponse(b"a,b\n1,2\n", "text/csv"))
    _redirect_tempdir(monkeypatch, tmp_path)

    rc = app._cmd_fetch(argparse.Namespace(url="http://example.test/data.csv", sheet=None))

    assert rc == 0
    assert "a" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []


def test_cmd_fetch_leaves_no_temp_file_on_bad_sheet(monkeypatch, tmp_path):
    from abax import app

    _patch_urlopen(monkeypatch, _FakeResponse(b"a,b\n1,2\n", "text/csv"))
    _redirect_tempdir(monkeypatch, tmp_path)

    rc = app._cmd_fetch(
        argparse.Namespace(url="http://example.test/data.csv", sheet="nope")
    )

    assert rc == 2
    assert list(tmp_path.iterdir()) == []


def test_cmd_fetch_leaves_no_temp_file_when_open_fails(monkeypatch, tmp_path):
    from abax import app

    # .bin has no loader, so the download succeeds and Document.open raises.
    _patch_urlopen(monkeypatch, _FakeResponse(b"\x00\x01", "application/octet-stream"))
    _redirect_tempdir(monkeypatch, tmp_path)

    rc = app._cmd_fetch(argparse.Namespace(url="http://example.test/blob", sheet=None))

    assert rc == 4
    assert list(tmp_path.iterdir()) == []
