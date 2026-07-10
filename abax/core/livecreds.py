"""Session-only credential store for live-data HTTP requests.

Live-data sources (``=REST``, ``=WEBSERVICE`` — see :mod:`abax.core.livedata`)
often need an ``Authorization`` header or an API key to reach real endpoints.
abax's security rule for connection secrets is simple: **they are never
persisted** — not to settings, not to the workbook envelope, not to the
recent-files list. Credentials are registered at runtime, live in process
memory only, and vanish when the app exits.

Consequences of that rule, all deliberate:

* :class:`CredentialStore` has **no serialization surface** — no ``to_dict``,
  no ``save``, no JSON hooks — and actively refuses pickling. Do not add any;
  a serializer here would be one careless call away from writing a bearer
  token to disk.
* Listings expose host *names* only. :meth:`CredentialStore.hosts` and
  ``repr()`` never reveal header names or values.
* Anything credential-adjacent that might reach a log line, an error message,
  or the screen should pass through :func:`redact` first.

Registration is keyed by **hostname** with exact matching — case-insensitive
and scheme/port-insensitive, so a token registered for ``api.example.com``
rides along on ``http://api.example.com/v1`` and
``https://api.example.com:8443/v2`` alike, but never leaks to any other host
(no suffix or wildcard matching: ``evil-api.example.com.attacker.tld`` and
even the subdomain ``sub.api.example.com`` both miss).

:func:`build_request` is the single integration point: HTTP transports build
their :class:`urllib.request.Request` through it and the per-host overlay
from the process-wide :data:`CREDS` store is applied automatically.
"""

from __future__ import annotations

import threading
import urllib.parse
import urllib.request

#: Leading characters :func:`redact` leaves visible.
_REDACT_KEEP = 4

#: Fixed-width mask appended by :func:`redact` (fixed so the true length of
#: the secret is not revealed either).
_MASK = "****"


def _norm_host(host: str) -> str:
    """Reduce *host* to a bare lowercase hostname.

    Accepts a plain hostname (``api.example.com``), a host:port pair
    (``api.example.com:8443``), an IPv6 literal (``[::1]:9000``), or a full
    URL (``https://api.example.com/v1``) — every form normalizes to the same
    hostname, so registration and lookup can never disagree about spelling.

    Raises :class:`ValueError` if no hostname can be extracted.
    """
    host = (host or "").strip()
    if "://" in host:
        name = urllib.parse.urlsplit(host).hostname
    else:
        # urlsplit only treats text after "//" as a netloc; prefixing one lets
        # bare "host", "host:port" and "[v6]:port" forms all parse uniformly.
        name = urllib.parse.urlsplit("//" + host).hostname
    if not name:
        raise ValueError(f"no hostname in {host!r}")
    return name  # .hostname already lowercases


class CredentialStore:
    """Thread-safe, in-memory map of hostname → extra HTTP headers.

    Register headers once per host (e.g. ``{"Authorization": "Bearer …"}``)
    and every request built for that host via :func:`build_request` carries
    them. The store is the session's only home for connection secrets.

    .. note::
       This class deliberately has **no** serialization methods — no
       ``to_dict`` / ``save`` / ``dumps`` — and :meth:`__reduce__` blocks
       pickling. Connection secrets are session-only by policy
       (see the module docstring); do not add a way to write them out.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_host: dict[str, dict[str, str]] = {}

    # -- registration --------------------------------------------------------

    def set_headers(self, host: str, headers: dict[str, str]) -> None:
        """Register extra HTTP *headers* for *host*, replacing any previous set.

        *host* may be a bare hostname, a ``host:port`` pair, or a full URL —
        all are normalized to the hostname (see :func:`_norm_host`). The
        mapping is copied, so later mutation of the caller's dict has no
        effect. Replacement (not merging) is intentional: rotating a token
        must not leave the stale one registered. An empty mapping removes the
        registration entirely, so every listed host always carries at least
        one header.

        Raises :class:`ValueError` for an empty host and :class:`TypeError`
        for non-string header names or values.
        """
        name = _norm_host(host)
        clean: dict[str, str] = {}
        for key, value in dict(headers).items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise TypeError("header names and values must be str")
            clean[key] = value
        with self._lock:
            if clean:
                self._by_host[name] = clean
            else:
                self._by_host.pop(name, None)

    # -- lookup ----------------------------------------------------------------

    def headers_for(self, url: str) -> dict[str, str]:
        """Headers registered for *url*'s hostname; ``{}`` when none match.

        Matching is exact on the hostname (``urllib.parse.urlsplit(url).hostname``)
        and therefore insensitive to scheme, port, path, and case — and immune
        to suffix tricks, since nothing but the exact registered name matches.
        Returns a copy; mutating it does not touch the store.
        """
        try:
            name = _norm_host(url)
        except ValueError:
            return {}
        with self._lock:
            found = self._by_host.get(name)
            return dict(found) if found else {}

    def hosts(self) -> list[str]:
        """Sorted hostnames with registered headers — names only, never values."""
        with self._lock:
            return sorted(self._by_host)

    def __len__(self) -> int:
        with self._lock:
            return len(self._by_host)

    # -- teardown --------------------------------------------------------------

    def clear(self, host: str | None = None) -> None:
        """Forget the registration for *host*, or every registration if ``None``.

        Clearing an unregistered host is a no-op, so teardown paths need not
        check first.
        """
        with self._lock:
            if host is None:
                self._by_host.clear()
            else:
                self._by_host.pop(_norm_host(host), None)

    # -- leak guards -------------------------------------------------------------

    def __repr__(self) -> str:
        """Reveal only a count — a repr landing in a log must never leak a secret."""
        return f"<CredentialStore: {len(self)} host(s)>"

    def __reduce__(self) -> tuple:
        """Refuse pickling: secrets are session-only and must never be written out."""
        raise TypeError("CredentialStore is session-only and cannot be pickled")


#: Process-wide store used by :func:`build_request` (mirrors ``livedata.HUB``).
CREDS = CredentialStore()


def build_request(url: str, *, accept: str | None = None,
                  user_agent: str = "abax-livedata/1") -> urllib.request.Request:
    """Construct a :class:`urllib.request.Request` with base + credential headers.

    The base headers are ``User-Agent`` (always) and ``Accept`` (only when
    *accept* is given). Any headers registered in :data:`CREDS` for *url*'s
    hostname are overlaid on top, so a registered header wins over a default
    of the same name — e.g. a host-specific ``User-Agent`` override.

    URL scheme allow-listing is *not* repeated here: the live hub gates every
    URL with :func:`abax.core.livedata.check_url` before a transport runs.
    """
    headers: dict[str, str] = {"User-Agent": user_agent}
    if accept is not None:
        headers["Accept"] = accept
    headers.update(CREDS.headers_for(url))
    return urllib.request.Request(url, headers=headers)  # noqa: S310 — scheme checked by hub


def redact(text: object) -> str:
    """Mask a credential-looking value for diagnostics.

    Keeps the first four characters and replaces everything else with a
    fixed-width ``****`` (fixed so the mask does not reveal the secret's
    length): ``redact("Bearer eyJhb…")`` → ``'Bear****'``. Values of four
    characters or fewer — where the head *is* the secret — are masked
    entirely. Route any stored header value through this before it can reach
    a log line, an exception message, or the screen.
    """
    s = "" if text is None else str(text)
    if len(s) <= _REDACT_KEEP:
        return _MASK
    return s[:_REDACT_KEEP] + _MASK
