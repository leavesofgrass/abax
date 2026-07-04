"""Import a table from a JSON REST endpoint — stdlib only, so it lives in core.

Where :mod:`abax.core.io.urlfetch` streams an arbitrary URL to a temp file for
the extension-dispatch loader, this module is the narrower "call a JSON API and
put the records in a grid" path. It builds a GET request with
:mod:`urllib.request` — optional query ``params``, arbitrary ``headers``, and a
convenience ``token`` that becomes an ``Authorization: Bearer`` header — parses
the JSON body, digs out the list of record dicts at a dotted ``records_path``
(e.g. ``"data.items"``), and flattens them to ``(headers, rows)``.

The column ``headers`` are the union of the records' keys in first-seen order
(so every record contributes its columns even when the API omits nulls), and
each row is that record's values as strings, blank where a key is missing.

Only ``http``/``https`` are allowed — like ``urlfetch``, a stray ``file://``
URL can never quietly read a local path. Everything is stdlib (``urllib`` +
``json``) → core.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

__all__ = [
    "RestImportError",
    "fetch_json",
    "extract_records",
    "records_to_table",
    "import_rest_table",
]

_USER_AGENT = "abax/restimport"
_ALLOWED_SCHEMES = frozenset({"http", "https"})


class RestImportError(Exception):
    """Raised when a REST endpoint cannot be fetched or its JSON cannot be shaped."""


def _scalar(value: Any) -> str:
    """Render one JSON scalar as a cell string (matches the other io adapters).

    Non-scalar values (a nested object or list left inside a record) are dumped
    back to compact JSON so the cell keeps the information rather than Python's
    ``repr`` of a dict.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (int, float, str)):
        return str(value)
    # dict / list — keep it as JSON text rather than a bare repr.
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def fetch_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    token: str | None = None,
    timeout: float = 30.0,
    max_bytes: int = 100 * 1024 * 1024,
) -> Any:
    """GET ``url`` and return the parsed JSON body.

    ``params`` are URL-encoded and merged onto any query string already on
    ``url``. ``headers`` are sent verbatim; ``token`` adds
    ``Authorization: Bearer <token>`` (an explicit ``Authorization`` header in
    ``headers`` wins). ``Accept: application/json`` is sent unless overridden.

    Only ``http``/``https`` are allowed; the body is capped at ``max_bytes``.
    Any transport, decoding, or JSON error is wrapped in
    :class:`RestImportError`.
    """
    full_url = _build_url(url, params)

    scheme = urllib.parse.urlsplit(full_url).scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise RestImportError(
            f"refusing to fetch {scheme or 'schemeless'!r} URL "
            f"(only http/https allowed): {url}"
        )

    hdrs = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if token and not _has_header(hdrs, "authorization"):
        hdrs["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(full_url, headers=hdrs)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            body = resp.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise RestImportError(
                    f"response exceeded max_bytes ({max_bytes}): {url}"
                )
            charset = _charset(resp) or "utf-8"
            text = body.decode(charset, errors="replace")
    except RestImportError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError, LookupError) as exc:
        raise RestImportError(f"could not fetch {url}: {exc}") from exc

    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise RestImportError(f"response from {url} was not valid JSON: {exc}") from exc


def extract_records(payload: Any, records_path: str | None = None) -> list[dict]:
    """Return the list of record dicts at ``records_path`` inside ``payload``.

    ``records_path`` is a dotted key path (``"data.items"``); an empty/``None``
    path uses ``payload`` itself. The resolved value must be either a list of
    objects (returned as-is, non-dict entries skipped) or a single object
    (wrapped in a one-element list). A missing key or an unusable shape raises
    :class:`RestImportError`.
    """
    node = payload
    if records_path:
        for key in records_path.split("."):
            if not isinstance(node, dict) or key not in node:
                raise RestImportError(
                    f"records path {records_path!r} not found (missing {key!r})"
                )
            node = node[key]

    if isinstance(node, dict):
        return [node]
    if isinstance(node, list):
        records = [item for item in node if isinstance(item, dict)]
        if not records and node:
            raise RestImportError(
                f"records path {records_path or '(root)'!r} is a list of "
                "non-objects; cannot union keys into columns"
            )
        return records
    raise RestImportError(
        f"records path {records_path or '(root)'!r} resolved to "
        f"{type(node).__name__}, expected a list of objects or an object"
    )


def records_to_table(records: list[dict]) -> tuple[list[str], list[list[str]]]:
    """Flatten record dicts to ``(headers, rows)``.

    ``headers`` is the union of the records' keys in first-seen order; each row
    holds that record's values as strings, blank where a key is absent. An empty
    ``records`` list yields ``([], [])``.
    """
    headers: list[str] = []
    seen: set[str] = set()
    for record in records:
        for key in record:
            if key not in seen:
                seen.add(key)
                headers.append(key)

    rows: list[list[str]] = []
    for record in records:
        rows.append([_scalar(record[h]) if h in record else "" for h in headers])
    return headers, rows


def import_rest_table(
    url: str,
    *,
    records_path: str | None = None,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    token: str | None = None,
    timeout: float = 30.0,
    max_bytes: int = 100 * 1024 * 1024,
) -> tuple[list[str], list[list[str]]]:
    """Fetch ``url``, dig out ``records_path``, and return ``(headers, rows)``.

    The one-call convenience over :func:`fetch_json` +
    :func:`extract_records` + :func:`records_to_table`; see those for the
    meaning of each keyword. Raises :class:`RestImportError` on any failure.
    """
    payload = fetch_json(
        url,
        params=params,
        headers=headers,
        token=token,
        timeout=timeout,
        max_bytes=max_bytes,
    )
    records = extract_records(payload, records_path)
    return records_to_table(records)


# --- helpers --------------------------------------------------------------


def _build_url(url: str, params: dict[str, Any] | None) -> str:
    """Merge ``params`` onto ``url``'s query string, preserving any existing one."""
    if not params:
        return url
    parts = urllib.parse.urlsplit(url)
    existing = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    # Stringify param values so bools/ints encode predictably (True -> "True").
    merged = existing + [(k, _param_str(v)) for k, v in params.items()]
    query = urllib.parse.urlencode(merged)
    return urllib.parse.urlunsplit(parts._replace(query=query))


def _param_str(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _has_header(headers: dict[str, str], name: str) -> bool:
    return any(k.lower() == name for k in headers)


def _charset(resp: object) -> str | None:
    """Pull a charset from the response headers, tolerant of fakes in tests."""
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
