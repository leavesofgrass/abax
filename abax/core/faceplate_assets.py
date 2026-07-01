"""On-demand fetch & cache of HP calculator faceplate artwork from GitHub.

The image faceplate (background.png + overlay.png + a ``.kml`` layout + a
``keys/`` directory, per calculator model) lets abax render a photographic HP
Voyager faceplate. abax **bundles no artwork**: the assets are downloaded from
a *user-configured* GitHub repository into abax's cache dir on demand, exactly
like the OpenDyslexic font fetch — so a fresh install can pull the faceplate at
runtime without shipping any binaries.

The downloaded archive is a GitHub repo ``.zip`` (from ``codeload.github.com``)
whose entries are prefixed with a top-level directory (``<repo>-<branch>/``).
Per-model asset trees live under ``<topdir>/<assets_subpath>/<model>/`` and are
extracted into :func:`voyager_dir`/``<model>/`` preserving their layout.

Network and zip errors are wrapped in :class:`FaceplateFetchError`; a raw
``urllib`` exception never escapes :func:`fetch`.
"""

from __future__ import annotations

import io
import logging
import shutil
import urllib.request
import zipfile
from pathlib import Path

from .._runtime import CACHE_DIR

_log = logging.getLogger(__name__)

DEFAULT_ASSETS_SUBPATH = "qrpn/assets/voyager"
"""Path within the repo to the per-model faceplate directories."""


class FaceplateFetchError(Exception):
    """Raised when faceplate assets cannot be downloaded or extracted."""


def cache_dir() -> Path:
    """Return (and create) the directory where faceplate assets are cached."""
    path = CACHE_DIR / "faceplates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def voyager_dir() -> Path:
    """Return (and create) the dir holding per-model faceplate subdirectories."""
    path = cache_dir() / "voyager"
    path.mkdir(parents=True, exist_ok=True)
    return path


def model_dir(model: str) -> Path | None:
    """Return ``voyager_dir()/<model>`` if it is a usable faceplate, else None.

    A directory is usable when it contains ``background.png`` and at least one
    ``*.kml`` layout file.
    """
    path = voyager_dir() / model
    if not path.is_dir():
        return None
    if not (path / "background.png").exists():
        return None
    if not any(path.glob("*.kml")):
        return None
    return path


def cached_models() -> list[str]:
    """Return the sorted model names that have a usable faceplate cached."""
    root = voyager_dir()
    models = [child.name for child in root.iterdir() if child.is_dir()]
    return sorted(name for name in models if model_dir(name) is not None)


def is_fetched() -> bool:
    """Return ``True`` if at least one usable faceplate is cached."""
    return bool(cached_models())


def _extract_zip(
    data: bytes, assets_subpath: str = DEFAULT_ASSETS_SUBPATH
) -> list[str]:
    """Extract per-model faceplate assets from a GitHub repo ``.zip``.

    *data* is the raw bytes of a GitHub repo archive whose entries are prefixed
    with a top-level directory (e.g. ``myrepo-main/``). Entries under
    ``<topdir>/<assets_subpath>/<model>/...`` are extracted into
    :func:`voyager_dir`/``<model>/...`` preserving the per-model layout
    (``background.png``, ``overlay.png``, ``*.kml``, ``keys/*``).

    Returns the sorted list of model names extracted. Raises
    :class:`FaceplateFetchError` if the zip is corrupt or contains no matching
    assets. Absolute paths and ``..`` traversal entries are ignored (zip-slip
    guard): every target is resolved and must stay within :func:`voyager_dir`.
    """
    marker = f"/{assets_subpath}/"
    root = voyager_dir()
    root_resolved = root.resolve()
    models: set[str] = set()

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError) as exc:
        raise FaceplateFetchError("corrupt or unreadable zip archive") from exc

    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            idx = name.find(marker)
            if idx < 0:
                continue
            rel = name[idx + len(marker) :]  # "<model>/<rest>"
            if not rel:
                continue
            # Zip-slip guard: drop absolute or traversal components.
            parts = [p for p in rel.split("/") if p not in ("", ".")]
            if not parts or ".." in parts or Path(rel).is_absolute():
                _log.warning("ignoring unsafe zip entry %r", info.filename)
                continue
            model = parts[0]
            if len(parts) < 2:
                # bare "<model>" with no file beneath it
                continue
            target = (root / Path(*parts)).resolve()
            try:
                target.relative_to(root_resolved)
            except ValueError:
                _log.warning("ignoring escaping zip entry %r", info.filename)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            models.add(model)

    if not models:
        raise FaceplateFetchError(
            f"no faceplate assets found under {assets_subpath!r} in archive"
        )
    return sorted(models)


def fetch(
    repo: str,
    branch: str = "main",
    assets_subpath: str = DEFAULT_ASSETS_SUBPATH,
    timeout: int = 30,
    force: bool = False,
) -> list[str]:
    """Download and cache faceplate assets from a GitHub repo; return models.

    *repo* is ``"owner/name"``. If a faceplate is already cached and *force* is
    false, the cached model names are returned without any network access.
    Otherwise the repo archive is downloaded from ``codeload.github.com`` and
    extracted via :func:`_extract_zip`.

    Any network or zip error is wrapped in :class:`FaceplateFetchError` (chained
    to the original); a raw ``urllib`` exception never escapes.
    """
    if is_fetched() and not force:
        return cached_models()

    url = f"https://codeload.github.com/{repo}/zip/refs/heads/{branch}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            data = response.read()
    except FaceplateFetchError:
        raise
    except Exception as exc:  # noqa: BLE001 — wrap any network error.
        raise FaceplateFetchError(f"failed to download {url}") from exc

    return _extract_zip(data, assets_subpath)
