"""OpenDyslexic font fetch & cache — offline, fully monkeypatched (no network)."""

from __future__ import annotations

import urllib.error
import urllib.request

from abax.core import fonts

_FAKE_OTF = b"OTTO\x00fake"


class _FakeResponse:
    """Minimal context-manager standing in for an ``urlopen`` response."""

    def __init__(self, payload: bytes = _FAKE_OTF) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload


def _patch_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(fonts, "font_dir", lambda: tmp_path)


def test_family_name():
    assert fonts.family_name() == "OpenDyslexic"


def test_font_urls_are_pinned_to_a_commit():
    # Must be pinned to an immutable commit SHA, not a moving branch — upstream
    # renamed master -> main, which 404'd the old branch URLs.
    import re

    urls = fonts.FONT_URLS
    assert [u.rsplit("/", 1)[1] for u in urls] == [
        "OpenDyslexic-Regular.otf",
        "OpenDyslexic-Bold.otf",
    ]
    for u in urls:
        assert u.startswith(
            "https://raw.githubusercontent.com/antijingoist/opendyslexic/")
        assert re.search(r"/[0-9a-f]{40}/compiled/", u), u
        assert "/master/" not in u and "/main/" not in u


def test_fetch_writes_both_files(monkeypatch, tmp_path):
    _patch_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda url, timeout=15: _FakeResponse()
    )

    paths = fonts.fetch()

    assert len(paths) == 2
    names = {p.name for p in paths}
    assert names == {"OpenDyslexic-Regular.otf", "OpenDyslexic-Bold.otf"}
    for p in paths:
        assert p.read_bytes() == _FAKE_OTF


def test_is_fetched_and_fetched_paths(monkeypatch, tmp_path):
    _patch_dir(monkeypatch, tmp_path)
    assert fonts.is_fetched() is False
    assert fonts.fetched_paths() == []

    monkeypatch.setattr(
        urllib.request, "urlopen", lambda url, timeout=15: _FakeResponse()
    )
    fonts.fetch()

    assert fonts.is_fetched() is True
    assert fonts.fetched_paths() == sorted(tmp_path.glob("*.otf"))
    assert len(fonts.fetched_paths()) == 2


def test_fetch_does_not_redownload_without_force(monkeypatch, tmp_path):
    _patch_dir(monkeypatch, tmp_path)
    calls = {"n": 0}

    def fake_urlopen(url, timeout=15):
        calls["n"] += 1
        return _FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    fonts.fetch()
    assert calls["n"] == 2

    # Second call: files already present, nothing re-downloaded.
    fonts.fetch()
    assert calls["n"] == 2

    # force=True re-downloads every URL.
    fonts.fetch(force=True)
    assert calls["n"] == 4


def test_fetch_offline_urlerror_returns_empty_without_raising(monkeypatch, tmp_path):
    _patch_dir(monkeypatch, tmp_path)

    def boom(url, timeout=15):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", boom)

    assert fonts.fetch() == []
    assert fonts.is_fetched() is False


def test_fetch_offline_oserror_returns_already_present(monkeypatch, tmp_path):
    _patch_dir(monkeypatch, tmp_path)

    # Pre-populate the Regular font, then go "offline" for the rest.
    (tmp_path / "OpenDyslexic-Regular.otf").write_bytes(_FAKE_OTF)

    def boom(url, timeout=15):
        raise OSError("network down")

    monkeypatch.setattr(urllib.request, "urlopen", boom)

    result = fonts.fetch()
    assert [p.name for p in result] == ["OpenDyslexic-Regular.otf"]
    assert fonts.is_fetched() is True


def test_fetch_never_raises_on_generic_exception(monkeypatch, tmp_path):
    _patch_dir(monkeypatch, tmp_path)

    def boom(url, timeout=15):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(urllib.request, "urlopen", boom)

    # Must not propagate.
    assert fonts.fetch() == []
