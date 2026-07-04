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

HTML pages are a special case: a spreadsheet has nothing to open a ``.html``
file *as a file*, but such a page often holds a data ``<table>``. So an
``.html``/``.htm`` URL (or a ``text/html`` response) can instead be routed
through :mod:`abax.core.io.webtable` with :func:`fetch_html_tables` /
:func:`fetch_largest_table`, which return parsed grids rather than a temp path.
"""

from __future__ import annotations

import pathlib
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from . import webtable

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
        ".html",
        ".htm",
    }
)

# URL path extensions that mean "this is an HTML page, extract its tables"
# rather than "download this file". Kept separate from ``_KNOWN_EXTS`` so the
# HTML-routing branch can test membership without re-deriving the suffix.
_HTML_EXTS = frozenset({".html", ".htm"})

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
    "text/html": ".html",
    "application/xhtml+xml": ".html",
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


# --- HTML pages -> tables --------------------------------------------------
#
# An HTML page is not a file we can open; instead we extract its data table(s).
# These helpers are the additive "route through webtable" branch: they fetch the
# page's text (reusing the same scheme guard and size cap as ``fetch_url``) and
# hand it to :mod:`abax.core.io.webtable`.


def is_html_target(url: str, content_type: str | None = None) -> bool:
    """Return whether ``url`` (or its ``content_type``) should be read as HTML.

    True when the URL path ends in ``.html``/``.htm``, or — only when the path
    carries no known data extension of its own — the content-type is an HTML
    type. The extension check comes first so a ``data.csv`` served (mislabelled)
    as ``text/html`` is still downloaded as CSV, matching :func:`guess_suffix`'s
    "trust the extension" rule.
    """
    path = urllib.parse.urlsplit(url).path
    ext = pathlib.PurePosixPath(path).suffix.lower()
    if ext in _HTML_EXTS:
        return True
    if ext in _KNOWN_EXTS:
        return False
    if content_type:
        base = content_type.split(";", 1)[0].strip().lower()
        return base in ("text/html", "application/xhtml+xml")
    return False


def fetch_text(
    url: str,
    *,
    timeout: float = 30.0,
    max_bytes: int = 100 * 1024 * 1024,
) -> str:
    """Fetch ``url`` and return its body decoded as text (not a temp file).

    Shares :func:`fetch_url`'s scheme allow-list and ``max_bytes`` cap. The
    charset comes from the response headers, defaulting to UTF-8, and undecodable
    bytes are replaced rather than raising. Errors raise :class:`UrlFetchError`.
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
            body = resp.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise UrlFetchError(
                    f"download exceeded max_bytes ({max_bytes}): {url}"
                )
            charset = _response_charset(resp) or "utf-8"
    except UrlFetchError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UrlFetchError(f"could not fetch {url}: {exc}") from exc

    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        # Unknown charset name from the server — fall back to UTF-8.
        return body.decode("utf-8", errors="replace")


def fetch_html_tables(
    url: str,
    *,
    timeout: float = 30.0,
    max_bytes: int = 100 * 1024 * 1024,
) -> list[list[list[str]]]:
    """Fetch an HTML page and return every ``<table>`` in it as a text grid.

    Thin bridge over :func:`fetch_text` + :func:`webtable.tables_from_html`;
    see :mod:`abax.core.io.webtable` for the grid shape and colspan/rowspan
    handling. Returns ``[]`` when the page has no table.
    """
    text = fetch_text(url, timeout=timeout, max_bytes=max_bytes)
    return webtable.tables_from_html(text)


def fetch_largest_table(
    url: str,
    *,
    timeout: float = 30.0,
    max_bytes: int = 100 * 1024 * 1024,
) -> list[list[str]]:
    """Fetch an HTML page and return only its largest ``<table>`` as a grid.

    Bridges to :func:`webtable.largest_table_from_html`, which raises
    :class:`webtable.WebTableError` when the page has no table.
    """
    text = fetch_text(url, timeout=timeout, max_bytes=max_bytes)
    return webtable.largest_table_from_html(text)


def _response_charset(resp: object) -> str | None:
    """Pull a charset from the response headers (tolerant of test fakes)."""
    headers = getattr(resp, "headers", None)
    if headers is None:
        return None
    getter = getattr(headers, "get_content_charset", None)
    if callable(getter):
        try:
            return getter()
        except Exception:  # noqa: BLE001 - be forgiving of odd header objects
            return None
    return None
