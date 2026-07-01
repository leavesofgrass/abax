"""GitHub faceplate-asset fetch & extract — offline, no network."""

from __future__ import annotations

import io
import urllib.error
import urllib.request
import zipfile

import pytest

from abax.core import faceplate_assets as fa


def _patch_cache(monkeypatch, tmp_path):
    """Point the cache at *tmp_path* so every helper derives from it."""
    cache = tmp_path / "faceplates"
    cache.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(fa, "cache_dir", lambda: cache)


def _make_zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, payload in entries.items():
            zf.writestr(name, payload)
    return buf.getvalue()


_GOOD_ENTRIES = {
    "myrepo-main/qrpn/assets/voyager/16c/background.png": b"bg16",
    "myrepo-main/qrpn/assets/voyager/16c/overlay.png": b"ov16",
    "myrepo-main/qrpn/assets/voyager/16c/16c.kml": b"<kml16>",
    "myrepo-main/qrpn/assets/voyager/16c/keys/key_11.png": b"k11",
    "myrepo-main/qrpn/assets/voyager/15c/background.png": b"bg15",
    "myrepo-main/qrpn/assets/voyager/15c/15c.kml": b"<kml15>",
    "myrepo-main/qrpn/assets/voyager/15c/keys/key_01.png": b"k01",
    "myrepo-main/README.md": b"ignore me",
}


def test_extract_zip_lands_files_and_returns_models(monkeypatch, tmp_path):
    _patch_cache(monkeypatch, tmp_path)

    models = fa._extract_zip(_make_zip(_GOOD_ENTRIES))

    assert models == ["15c", "16c"]
    vdir = fa.voyager_dir()
    assert (vdir / "16c" / "background.png").read_bytes() == b"bg16"
    assert (vdir / "16c" / "overlay.png").read_bytes() == b"ov16"
    assert (vdir / "16c" / "16c.kml").read_bytes() == b"<kml16>"
    assert (vdir / "16c" / "keys" / "key_11.png").read_bytes() == b"k11"
    assert (vdir / "15c" / "background.png").read_bytes() == b"bg15"
    assert (vdir / "15c" / "keys" / "key_01.png").read_bytes() == b"k01"
    # README outside the assets path must not leak in.
    assert not (vdir / "README.md").exists()


def test_cached_models_and_model_dir_and_is_fetched(monkeypatch, tmp_path):
    _patch_cache(monkeypatch, tmp_path)
    assert fa.cached_models() == []
    assert fa.is_fetched() is False

    fa._extract_zip(_make_zip(_GOOD_ENTRIES))

    assert fa.cached_models() == ["15c", "16c"]
    assert fa.is_fetched() is True
    md = fa.model_dir("16c")
    assert md is not None and md.is_dir()
    assert fa.model_dir("99c") is None


def test_model_dir_requires_background_and_kml(monkeypatch, tmp_path):
    _patch_cache(monkeypatch, tmp_path)
    # background but no kml
    entries = {
        "r-main/qrpn/assets/voyager/16c/background.png": b"bg",
        "r-main/qrpn/assets/voyager/15c/15c.kml": b"<kml>",  # kml but no bg
    }
    fa._extract_zip(_make_zip(entries))
    assert fa.model_dir("16c") is None  # missing kml
    assert fa.model_dir("15c") is None  # missing background
    assert fa.cached_models() == []


def test_extract_zip_no_matching_assets_raises(monkeypatch, tmp_path):
    _patch_cache(monkeypatch, tmp_path)
    entries = {
        "myrepo-main/README.md": b"hi",
        "myrepo-main/src/main.py": b"print()",
    }
    with pytest.raises(fa.FaceplateFetchError):
        fa._extract_zip(_make_zip(entries))


def test_extract_zip_corrupt_raises(monkeypatch, tmp_path):
    _patch_cache(monkeypatch, tmp_path)
    with pytest.raises(fa.FaceplateFetchError):
        fa._extract_zip(b"not a zip file at all")


def test_zip_slip_entry_is_ignored(monkeypatch, tmp_path):
    _patch_cache(monkeypatch, tmp_path)
    entries = {
        # legitimate model so extraction succeeds
        "myrepo-main/qrpn/assets/voyager/16c/background.png": b"bg",
        "myrepo-main/qrpn/assets/voyager/16c/16c.kml": b"<kml>",
        # malicious traversal under the assets path
        "myrepo-main/qrpn/assets/voyager/16c/../../../../evil.png": b"pwned",
    }
    models = fa._extract_zip(_make_zip(entries))

    assert models == ["16c"]
    # Nothing escaped voyager_dir's parents.
    escaped = (fa.voyager_dir().resolve().parents[3] / "evil.png")
    assert not escaped.exists()
    assert not (tmp_path / "evil.png").exists()


def test_fetch_uses_cache_without_network(monkeypatch, tmp_path):
    _patch_cache(monkeypatch, tmp_path)
    fa._extract_zip(_make_zip(_GOOD_ENTRIES))
    assert fa.is_fetched() is True

    def boom(url, timeout=30):
        raise AssertionError("network must not be touched")

    monkeypatch.setattr(urllib.request, "urlopen", boom)

    assert fa.fetch("owner/name") == ["15c", "16c"]


def test_fetch_downloads_and_extracts(monkeypatch, tmp_path):
    _patch_cache(monkeypatch, tmp_path)
    payload = _make_zip(_GOOD_ENTRIES)

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return payload

    captured = {}

    def fake_urlopen(url, timeout=30):
        captured["url"] = url
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    models = fa.fetch("owner/name", branch="main")
    assert models == ["15c", "16c"]
    assert captured["url"] == (
        "https://codeload.github.com/owner/name/zip/refs/heads/main"
    )


def test_fetch_network_error_wrapped(monkeypatch, tmp_path):
    _patch_cache(monkeypatch, tmp_path)

    def boom(url, timeout=30):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", boom)

    with pytest.raises(fa.FaceplateFetchError):
        fa.fetch("owner/name")
