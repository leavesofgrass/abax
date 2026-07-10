"""Named, refreshable external data sources — the connection model + registry.

Technical users already pull data into a sheet from three ad-hoc importers:
a JSON REST endpoint (:mod:`abax.core.io.restimport`), a SQL database
(:mod:`abax.engine.dbapi`), and an HTML ``<table>`` on a web page
(:mod:`abax.core.io.webtable`). What has been missing is the idea of a *named*
source you can point at a destination and re-run: "the ``Sales`` connection
refreshes ``Data!A1`` from that REST feed." This module supplies that model.

It deliberately does **not** reinvent the importers. A :class:`Connection` is a
small description — *what kind* of source, *where* it points (a non-secret URL
or query), *where* a refresh writes (an A1 anchor), and *which non-secret
options* shape the pull. :func:`refresh` is a pure dispatcher: the caller
injects the real ``restimport`` / ``dbapi`` / ``webtable`` callables (or fakes,
in tests) and gets back a 2-D grid. Nothing here opens a socket.

SECURITY — secrets are never stored here. A connection knows a *URL/query/page*
(all non-secret) and, at most, a ``secret_ref``: the *name* of a credential held
elsewhere for the session only (see :class:`abax.sandbox.SecretsHolder`). The
password, bearer token, or credential-bearing DSN itself is **never** a field on
:class:`Connection`, never returned by :meth:`Connection.to_dict`, and therefore
never written to the workbook envelope or settings. That is precisely why a
:class:`ConnectionRegistry` is safe to persist alongside the names/tables
registries — round-tripping it can only ever move non-secret metadata.

Pure stdlib, so it belongs to ``abax/core/``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "ConnectionError",
    "Connection",
    "ConnectionRegistry",
    "refresh",
    "VALID_KINDS",
]

# The three source kinds abax knows how to import from today. Each maps to one
# injected fetch callable in :func:`refresh`.
VALID_KINDS = frozenset({"rest", "sql", "webtable"})


class ConnectionError(Exception):
    """Raised for an invalid connection or a refresh that cannot be dispatched.

    Deliberately shadows the builtin :class:`ConnectionError` *within this
    module* (as :mod:`abax.core.names` does with :class:`NameError`) so the
    connection layer raises one consistent, importable error type — matching the
    ``RestImportError`` / ``DatabaseError`` / ``WebTableError`` convention of the
    importers it models.
    """


# --- the Connection model --------------------------------------------------


@dataclass
class Connection:
    """One named, refreshable external data source (non-secret metadata only).

    Attributes:
        name: The display label, unique case-insensitively within a registry.
        kind: One of :data:`VALID_KINDS` — ``"rest"``, ``"sql"``, or
            ``"webtable"`` — selecting which importer a refresh dispatches to.
        target: Where the source points, and always **non-secret**: a REST URL,
            a SQL query (or table name), or a web-page URL. A credential-bearing
            DSN must *not* be put here; keep the secret out of band and name it
            via :attr:`secret_ref`.
        dest: The A1 anchor a refresh writes to, e.g. ``"Sheet1!A1"`` — the
            top-left cell of the grid the importer returns.
        options: Non-secret parameters shaping the pull — e.g.
            ``{"records_path": "data.items"}`` for REST, ``{"table_index": 0}``
            for a web table, ``{"delimiter": ";"}``. Never a password/token.
        last_refreshed: An ISO-8601 timestamp of the last successful refresh, or
            ``None`` if never refreshed. Stamped by the caller (see
            :func:`refresh`, which stays pure and does not touch it).
        secret_ref: The *name* of a session-only credential (a key into an
            :class:`abax.sandbox.SecretsHolder`), or ``None``. This is a lookup
            key, **not** a secret value — the value is resolved elsewhere at
            refresh time and never lives on the connection.

    There is intentionally no ``password`` / ``token`` / credential field: see
    the module docstring for why that keeps the registry safe to persist.
    """

    name: str
    kind: str
    target: str
    dest: str
    options: dict = field(default_factory=dict)
    last_refreshed: str | None = None
    secret_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ConnectionError(f"connection name must be a non-empty string: {self.name!r}")
        if self.kind not in VALID_KINDS:
            raise ConnectionError(
                f"unknown connection kind {self.kind!r} "
                f"(expected one of {', '.join(sorted(VALID_KINDS))})"
            )

    # -- serialization ------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a JSON-friendly snapshot of the **non-secret** fields only.

        Emits ``name``/``kind``/``target``/``dest``/``options``/
        ``last_refreshed``/``secret_ref``. Note what is *absent*: there is no
        password, token, or credential-bearing DSN key, because none is ever
        stored on the connection. ``secret_ref`` is a credential *name*, safe to
        persist; the value it names is not part of this snapshot.
        """
        return {
            "name": self.name,
            "kind": self.kind,
            "target": self.target,
            "dest": self.dest,
            "options": dict(self.options),
            "last_refreshed": self.last_refreshed,
            "secret_ref": self.secret_ref,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Connection:
        """Rebuild a :class:`Connection` from :meth:`to_dict` output.

        Any stray secret-looking keys in *d* are ignored: only the non-secret
        fields are read, so a tampered or hand-edited envelope can never inject a
        credential value into the live model.
        """
        return cls(
            name=d["name"],
            kind=d["kind"],
            target=d.get("target", ""),
            dest=d.get("dest", ""),
            options=dict(d.get("options") or {}),
            last_refreshed=d.get("last_refreshed"),
            secret_ref=d.get("secret_ref"),
        )


# --- the registry ----------------------------------------------------------


class ConnectionRegistry:
    """A case-insensitive registry of :class:`Connection` objects.

    Mirrors :class:`abax.core.tables.TableRegistry`: keyed on the upper-cased
    connection name, preserving each connection's display case. ``Workbook`` is
    *not* modified by this module — the integrator attaches an instance
    (``wb.connections = ConnectionRegistry()``) and persists it in the envelope.

    :meth:`to_dict` / :meth:`from_dict` round-trip **only non-secret metadata**
    (each :meth:`Connection.to_dict` omits any credential), so this registry is
    safe to write into the workbook envelope beside the names and tables
    registries — no password or token can ride along.
    """

    def __init__(self) -> None:
        self._by_upper: dict[str, Connection] = {}
        # Bumped on every mutation, so a GUI "Connections" panel can cheaply tell
        # whether it needs to redraw (parallels TableRegistry.version).
        self._version = 0

    @property
    def version(self) -> int:
        """A counter bumped on every mutation (add/remove/rename/touch)."""
        return self._version

    def touch(self) -> None:
        """Bump :attr:`version` after mutating a :class:`Connection` in place.

        The registry can't observe direct attribute writes (a refresh stamping
        ``conn.last_refreshed``), so such callers bump explicitly to mark the
        registry dirty for any cache keyed on :attr:`version`.
        """
        self._version += 1

    def __len__(self) -> int:
        return len(self._by_upper)

    def __iter__(self):
        return iter(self._by_upper.values())

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name.upper() in self._by_upper

    def add(self, conn: Connection) -> None:
        """Add (or overwrite) *conn*, keyed case-insensitively on its name."""
        if not isinstance(conn, Connection):
            raise ConnectionError(f"expected a Connection, got {type(conn).__name__}")
        self._by_upper[conn.name.upper()] = conn
        self._version += 1

    def get(self, name: str) -> Connection | None:
        """Return the connection named *name* (case-insensitive), or ``None``."""
        if not isinstance(name, str):
            return None
        return self._by_upper.get(name.upper())

    def has(self, name: str) -> bool:
        """Return ``True`` if a connection named *name* exists (case-insensitive)."""
        return isinstance(name, str) and name.upper() in self._by_upper

    def remove(self, name: str) -> None:
        """Remove the connection named *name*. Raises :class:`ConnectionError` if absent."""
        key = name.upper() if isinstance(name, str) else None
        if key is None or key not in self._by_upper:
            raise ConnectionError(f"no such connection: {name!r}")
        del self._by_upper[key]
        self._version += 1

    def rename(self, old: str, new: str) -> None:
        """Rename connection *old* to *new* (updating the stored display name).

        Raises :class:`ConnectionError` if *old* is missing, *new* is not a
        non-empty string, or *new* collides with a different existing connection.
        """
        old_key = old.upper() if isinstance(old, str) else None
        if old_key is None or old_key not in self._by_upper:
            raise ConnectionError(f"no such connection: {old!r}")
        if not isinstance(new, str) or not new.strip():
            raise ConnectionError(f"connection name must be a non-empty string: {new!r}")
        new_key = new.upper()
        if new_key != old_key and new_key in self._by_upper:
            raise ConnectionError(f"connection already exists: {new!r}")
        conn = self._by_upper.pop(old_key)
        conn.name = new
        self._by_upper[new_key] = conn
        self._version += 1

    def names(self) -> list[str]:
        """Display names, sorted case-insensitively."""
        return sorted((c.name for c in self._by_upper.values()), key=str.upper)

    def to_dict(self) -> dict:
        """Return ``{display_name: connection.to_dict()}`` — non-secret only.

        Because each :meth:`Connection.to_dict` omits every credential, the whole
        mapping is safe to persist in the workbook envelope. See the class
        docstring.
        """
        return {c.name: c.to_dict() for c in self._by_upper.values()}

    @classmethod
    def from_dict(cls, d: dict) -> ConnectionRegistry:
        """Rebuild a registry from :meth:`to_dict` output.

        Entries that fail validation (unknown ``kind``, blank ``name``, missing
        ``name``/``kind`` keys) are skipped rather than aborting the whole load,
        mirroring :meth:`abax.core.names.NameRegistry.from_dict`.
        """
        reg = cls()
        for payload in (d or {}).values():
            try:
                reg.add(Connection.from_dict(payload))
            except (ConnectionError, KeyError, TypeError):
                continue
        return reg


# --- the refresh dispatcher ------------------------------------------------


def refresh(
    conn: Connection,
    *,
    rest_fetch=None,
    sql_run=None,
    web_fetch=None,
) -> list[list]:
    """Run *conn* through the injected fetcher for its kind and return a grid.

    This is a **pure dispatcher**: it opens no socket and reads no database of
    its own. The caller injects the concrete fetch callables — one per kind —
    and :func:`refresh` picks the one matching ``conn.kind`` and calls it with
    the connection:

    * ``rest_fetch(conn)``  for ``kind == "rest"``
    * ``sql_run(conn)``     for ``kind == "sql"``
    * ``web_fetch(conn)``   for ``kind == "webtable"``

    Each fetcher returns a 2-D grid (``list`` of row ``list``s), typically the
    importer's header row followed by its data rows, ready to be written at
    ``conn.dest``. A fetcher is where the real work lives — reading
    ``conn.target`` / ``conn.options`` and, if ``conn.secret_ref`` is set,
    looking the credential up in the session credential store. Tests inject
    trivial fakes; the integrator wires the real
    ``restimport`` / ``dbapi`` / ``webtable`` adapters.

    :func:`refresh` does **not** mutate *conn* (it leaves ``last_refreshed``
    alone) so it stays side-effect free; the caller stamps the timestamp on
    success. Raises :class:`ConnectionError` if ``conn.kind`` is not one of
    :data:`VALID_KINDS` or if no fetcher was supplied for that kind. Any error
    raised by the fetcher itself (a ``RestImportError``, ``DatabaseError`` …)
    propagates unchanged.
    """
    fetchers = {"rest": rest_fetch, "sql": sql_run, "webtable": web_fetch}
    if conn.kind not in fetchers:
        raise ConnectionError(
            f"cannot refresh unknown connection kind {conn.kind!r} "
            f"(expected one of {', '.join(sorted(VALID_KINDS))})"
        )
    fetcher = fetchers[conn.kind]
    if fetcher is None:
        raise ConnectionError(
            f"no fetcher supplied for {conn.kind!r} connection {conn.name!r}"
        )
    return fetcher(conn)
