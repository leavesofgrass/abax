"""Fetch a remote data file to a local temp file — stdlib only, so it lives in core.

The app already knows how to open spreadsheets and data files by *extension*
(CSV, TSV, JSON, Markdown, XML, XLSX, ...). This module bridges "here is a URL"
to that existing extension-dispatch loader: it streams the URL down to a temp
file whose suffix is guessed from the URL path (preferred) or the response
content-type, and hands back the ``Path``. The caller then opens it as if the
user had picked a local file.

Kept to ``urllib.request`` on purpose so the whole ``core`` layer stays free of
third-party imports. Only ``http``/``https``/``ftp`` are allowed — ``file://``
and friends are refused so a stray URL can never quietly read a local path.
"""

from __future__ import annotations

import pathlib
import tempfile
import urllib.error
import urllib.parse
import urllib.request

# File extensions we recognise directly on a URL path. When the URL ends in one
# of these we trust it over the content-type (servers lie about MIME types far
# more often than users mistype an extension).
_KNOWN_EXTS = frozenset(
    {
        ".csv",
        ".tsv",
        ".tab",
        ".json",
        ".abax",
        ".md",
        ".markdown",
        ".xml",
        ".jsonl",
        ".ndjson",
        ".xlsx",
        ".xlsm",
        ".parquet",
        ".ods",
        ".adi",
        ".adif",
        ".r",
    }
)

# content-type -> suffix, consulted only when the URL path has no useful suffix.
_CONTENT_TYPE_SUFFIX = {
    "text/csv": ".csv",
    "application/json": ".json",
    "text/tab-separated-values": ".tsv",
    "application/vnd.ms-excel": ".xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/markdown": ".md",
    "application/xml": ".xml",
    "text/xml": ".xml",
}

_USER_AGENT = "abax/urlfetch"
_ALLOWED_SCHEMES = frozenset({"http", "https", "ftp"})
_CHUNK = 64 * 1024


class UrlFetchError(Exception):
    """Raised when a URL cannot be fetched or is disallowed."""


def guess_suffix(url: str, content_type: str | None = None) -> str:
    """Return a lowercased file extension (with the dot) for the download.

    Prefers the URL path's own extension when it is a known data extension;
    otherwise maps ``content_type`` through a small table. Falls back to
    ``.csv`` for any other ``text/*`` type and ``.bin`` otherwise. Never returns
    an empty string.
    """
    path = urllib.parse.urlsplit(url).path
    ext = pathlib.PurePosixPath(path).suffix.lower()
    if ext in _KNOWN_EXTS:
        return ext

    if content_type:
        # Strip any ``; charset=...`` parameters and normalise case.
        base = content_type.split(";", 1)[0].strip().lower()
        if base in _CONTENT_TYPE_SUFFIX:
            return _CONTENT_TYPE_SUFFIX[base]
        if base.startswith("text/"):
            return ".csv"

    return ".bin"


def _response_content_type(resp: object) -> str | None:
    """Pull a content-type string out of whatever urlopen handed back.

    Prefers ``resp.headers.get_content_type()`` (an ``email.message.Message``
    method) and falls back to a plain ``Content-Type`` header lookup, so the
    function copes with both real responses and simple fakes in tests.
    """
    headers = getattr(resp, "headers", None)
    if headers is None:
        return None
    getter = getattr(headers, "get_content_type", None)
    if callable(getter):
        try:
            return getter()
        except Exception:  # noqa: BLE001 - be forgiving of odd header objects
            pass
    get = getattr(headers, "get", None)
    if callable(get):
        return get("Content-Type")
    return None


def fetch_url(
    url: str,
    *,
    timeout: float = 30.0,
    max_bytes: int = 100 * 1024 * 1024,
    dest_dir: str | None = None,
) -> pathlib.Path:
    """Download ``url`` to a new temp file and return its ``Path``.

    The temp file's suffix comes from :func:`guess_suffix`. Only
    ``http``/``https``/``ftp`` URLs are allowed — anything else (notably
    ``file://``) raises :class:`UrlFetchError` to avoid local-file surprises.
    The response is streamed in chunks and aborted if it exceeds ``max_bytes``.
    ``dest_dir`` selects the temp directory (default: the system temp).
    """
    scheme = urllib.parse.urlsplit(url).scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise UrlFetchError(
            f"refusing to fetch {scheme or 'schemeless'!r} URL "
            f"(only http/https/ftp allowed): {url}"
        )

    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            suffix = guess_suffix(url, _response_content_type(resp))
            tmp = tempfile.NamedTemporaryFile(
                delete=False, suffix=suffix, dir=dest_dir
            )
            try:
                total = 0
                while True:
                    chunk = resp.read(_CHUNK)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise UrlFetchError(
                            f"download exceeded max_bytes ({max_bytes}): {url}"
                        )
                    tmp.write(chunk)
            finally:
                tmp.close()
    except UrlFetchError:
        # Clean up the partial temp file before re-raising the size error.
        _unlink_quietly(locals().get("tmp"))
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        _unlink_quietly(locals().get("tmp"))
        raise UrlFetchError(f"could not fetch {url}: {exc}") from exc

    return pathlib.Path(tmp.name)


def _unlink_quietly(tmp: object) -> None:
    """Best-effort removal of a partially written temp file."""
    name = getattr(tmp, "name", None)
    if not name:
        return
    try:
        pathlib.Path(name).unlink()
    except OSError:
        pass
