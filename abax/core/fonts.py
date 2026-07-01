"""On-demand fetch & cache of the OpenDyslexic font (SIL OFL 1.1).

OpenDyslexic is a free, openly-licensed typeface designed to ease reading for
people with dyslexia. The font files are downloaded from the upstream GitHub
repository into abax's cache dir on demand so the ``.pyz``/app can offer a
dyslexia-friendly font without bundling the binaries.

Everything here is best-effort and offline-safe: any network or IO error is
logged and swallowed, so callers always get a (possibly empty) list of paths
and never see an exception.
"""

from __future__ import annotations

import logging
import urllib.request
from pathlib import Path

from .._runtime import CACHE_DIR

_log = logging.getLogger(__name__)

# Pinned to an immutable commit SHA rather than a branch: upstream renamed its
# default branch master -> main (which 404'd the old URLs), and there are no
# tagged releases to pin to, so a commit SHA is the stable choice. Files live
# under compiled/ on antijingoist/opendyslexic.
_FONT_REF = "1824da5c0e41dc3e13ffc7f3a636dcaf695d61b7"
_FONT_BASE = f"https://raw.githubusercontent.com/antijingoist/opendyslexic/{_FONT_REF}/compiled"
FONT_URLS: list[str] = [
    f"{_FONT_BASE}/OpenDyslexic-Regular.otf",
    f"{_FONT_BASE}/OpenDyslexic-Bold.otf",
]


def family_name() -> str:
    """Return the font family name."""
    return "OpenDyslexic"


def font_dir() -> Path:
    """Return (and create) the directory where fetched fonts are cached."""
    path = CACHE_DIR / "fonts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def fetched_paths() -> list[Path]:
    """Return the existing ``*.otf`` files in :func:`font_dir`, sorted."""
    return sorted(font_dir().glob("*.otf"))


def is_fetched() -> bool:
    """Return ``True`` if the Regular ``.otf`` is present in the cache."""
    return (font_dir() / "OpenDyslexic-Regular.otf").exists()


def fetch(timeout: int = 15, force: bool = False) -> list[Path]:
    """Fetch any missing font files and return the cached fonts present.

    For each URL in :data:`FONT_URLS`, the target is ``font_dir()/basename``.
    If the target is missing (or *force* is true) it is downloaded via
    :func:`urllib.request.urlopen` and written to disk. Any exception on a
    single URL is logged and skipped — this function never raises.
    """
    directory = font_dir()
    for url in FONT_URLS:
        target = directory / Path(url).name
        if target.exists() and not force:
            continue
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                data = response.read()
            target.write_bytes(data)
        except Exception:  # noqa: BLE001 — offline-safe: log and skip.
            _log.warning("failed to fetch font from %s", url, exc_info=True)
            continue
    return fetched_paths()
