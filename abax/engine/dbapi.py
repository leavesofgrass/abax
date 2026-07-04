"""SQL database connectivity via optional DB-API 2.0 drivers — safe, small API.

Relational databases are the last big gap in abax's importers: a table living in
PostgreSQL or MySQL can't be pulled into a sheet without a driver. This adapter
adds that through two optional packages — **psycopg** (PostgreSQL) and
**pymysql** (MySQL) — each a PEP 249 (DB-API 2.0) driver. Like the Parquet /
HDF5 / statfiles adapters, this module imports gracefully: importing it never
fails when a driver is absent, and any operation that actually needs one raises a
descriptive :class:`DatabaseError` telling the user how to enable it. That keeps
``abax/core/`` free of any hard third-party dependency (see docs/architecture.md).

Because every supported driver implements the same DB-API 2.0 surface
(``conn.cursor()`` → ``cursor.execute(sql, params)`` → ``cursor.description`` +
``cursor.fetchall()``), the read helpers below are driver-agnostic: they work
against *any* PEP 249 connection, including the stdlib :mod:`sqlite3`. Results
come back in abax's usual tabular shape — ``(headers, rows)`` where ``headers``
is a list of column-name strings and ``rows`` is a list of tuples of cell text
(NULL renders as the empty string, whole floats collapse to ints), matching the
CSV / Parquet / statfiles importers.

SECURITY (fail closed). A connection secret — a DSN, password, or the parameters
that embed one — is **never written anywhere persistent** by this adapter. It is
accepted as an argument, passed straight to the driver's ``connect()``, and held
only inside the live connection object the caller keeps in memory. Nothing here
touches settings, the recent-files list, the state cache, or any log: there is no
code path that serializes a DSN/params to disk. Callers must uphold the same
contract (do not stash the DSN in a saved workbook or preferences). Identifiers
interpolated into generated SQL (the table name in :func:`read_table`) are
validated and quoted defensively; user data always travels as bound parameters,
never string-formatted into SQL.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

Row = Tuple[str, ...]
Table = Tuple[List[str], List[Row]]


class DatabaseError(Exception):
    """Raised when a database operation cannot proceed (missing driver, etc.)."""


# (import module name, pip install target, human label) for every supported
# DB-API 2.0 driver. psycopg is v3 ("psycopg"); the binary wheel avoids a local
# libpq/compiler. PyMySQL is pure-Python (no build step).
_DRIVERS: List[Tuple[str, str, str]] = [
    ("psycopg", "psycopg[binary]", "PostgreSQL"),
    ("pymysql", "PyMySQL", "MySQL"),
]

_FALLBACK_MSG = (
    "SQL database import requires a DB-API driver: 'psycopg' for PostgreSQL or "
    "'pymysql' for MySQL. Install one with:\n"
    "    pip install psycopg[binary]      # PostgreSQL\n"
    "    pip install PyMySQL              # MySQL\n"
    "or install abax's database extra:  pip install abax[database]"
)


def _import(module: str):
    """Lazy-import one driver module, raising :class:`DatabaseError` if absent."""
    try:
        return __import__(module)
    except ImportError as exc:  # pragma: no cover - exercised only without dep
        raise DatabaseError(
            f"the '{module}' database driver is not installed.\n\n" + _FALLBACK_MSG
        ) from exc


def _installed(module: str) -> bool:
    """True iff *module* is importable, without importing it or raising."""
    import importlib.util

    try:
        return importlib.util.find_spec(module) is not None
    except Exception:
        return False


def available() -> bool:
    """True iff at least one supported DB-API driver is importable."""
    return any(_installed(mod) for mod, _pip, _label in _DRIVERS)


def list_drivers() -> List[dict]:
    """Describe every supported driver and whether it is currently installed.

    Returns one dict per driver — ``{"module", "pip", "label", "available"}`` —
    so a caller (a GUI chooser, ``--deps``-style output) can show what's present
    and how to install what isn't. Never imports a driver or raises.
    """
    return [
        {"module": mod, "pip": pip, "label": label, "available": _installed(mod)}
        for mod, pip, label in _DRIVERS
    ]


def connect(dsn: Optional[str] = None, **params: Any):
    """Open a live database connection through an installed DB-API driver.

    Pass either a ``dsn`` connection string (e.g.
    ``postgresql://user:pw@host/db`` or ``mysql://user:pw@host/db``) or keyword
    ``params`` (``host=``, ``user=``, ``password=``, ``dbname=``/``database=``,
    ``port=``); a ``driver="psycopg"`` / ``driver="pymysql"`` keyword forces the
    backend when it can't be inferred. The returned object is a standard DB-API
    connection — use it with :func:`list_tables`, :func:`read_table`,
    :func:`query`, and close it yourself (or via ``with``) when done.

    SECURITY: the ``dsn``/``params`` (which may embed a password) are forwarded
    straight to the driver and never persisted by abax — see the module
    docstring. Raises :class:`DatabaseError` if no suitable driver is installed
    or the backend can't be determined.
    """
    driver = params.pop("driver", None)
    module = _resolve_driver(driver, dsn)
    drv = _import(module)

    try:
        if module == "psycopg":
            # psycopg v3: connect(conninfo, **kwargs). A DSN goes positionally;
            # keyword params map straight through (host/dbname/user/...).
            return drv.connect(dsn, **params) if dsn is not None else drv.connect(**params)
        if module == "pymysql":
            # PyMySQL has no DSN string; translate a URL into its kwargs.
            kw = dict(params)
            if dsn is not None:
                kw = {**_parse_url(dsn), **kw}
            return drv.connect(**kw)
    except DatabaseError:
        raise
    except Exception as exc:  # driver-specific connection/authentication error
        # Deliberately terse: never echo the DSN/params (they may hold secrets).
        raise DatabaseError(f"could not connect via '{module}': {exc}") from exc

    # Unreachable: _resolve_driver only returns a supported module. (defensive)
    raise DatabaseError(f"unsupported database driver: {module!r}")


def _resolve_driver(driver: Optional[str], dsn: Optional[str]) -> str:
    """Pick a driver *module name*: explicit → URL scheme → the only installed one.

    Raises :class:`DatabaseError` when the choice is ambiguous or unavailable, so
    the failure is a clear message rather than a mysterious connect() error.
    """
    supported = {mod for mod, _pip, _label in _DRIVERS}
    if driver is not None:
        if driver not in supported:
            raise DatabaseError(
                f"unknown database driver {driver!r} "
                f"(supported: {', '.join(sorted(supported))})"
            )
        return driver

    scheme_module = _driver_for_scheme(dsn)
    if scheme_module is not None:
        return scheme_module

    installed = [mod for mod, _pip, _label in _DRIVERS if _installed(mod)]
    if len(installed) == 1:
        return installed[0]
    if not installed:
        raise DatabaseError(_FALLBACK_MSG)
    # More than one driver present and nothing to disambiguate on.
    raise DatabaseError(
        "cannot tell which database driver to use — pass a DSN with a scheme "
        "(postgresql:// or mysql://) or driver='psycopg'/'pymysql'."
    )


# URL scheme -> driver module. The common aliases each backend uses in SQLAlchemy
# / JDBC-style URLs are all accepted so a familiar DSN just works.
_SCHEMES = {
    "postgresql": "psycopg",
    "postgres": "psycopg",
    "psql": "psycopg",
    "mysql": "pymysql",
    "mariadb": "pymysql",
}


def _driver_for_scheme(dsn: Optional[str]) -> Optional[str]:
    """Map a DSN's URL scheme to a driver module, or ``None`` if not a known URL."""
    if not dsn or "://" not in dsn:
        return None
    scheme = dsn.split("://", 1)[0].lower()
    # Strip a SQLAlchemy-style ``+driver`` suffix, e.g. ``postgresql+psycopg``.
    scheme = scheme.split("+", 1)[0]
    return _SCHEMES.get(scheme)


def _parse_url(dsn: str) -> dict:
    """Turn a ``scheme://user:pw@host:port/db`` URL into PyMySQL connect kwargs.

    PyMySQL (unlike psycopg) takes no connection string, so a URL is decomposed
    into ``host``/``port``/``user``/``password``/``database`` here. Only keys that
    are actually present are emitted, so we never override PyMySQL's own defaults
    with empty strings.
    """
    from urllib.parse import unquote, urlsplit

    parts = urlsplit(dsn)
    kw: dict = {}
    if parts.hostname:
        kw["host"] = parts.hostname
    if parts.port:
        kw["port"] = parts.port
    if parts.username:
        kw["user"] = unquote(parts.username)
    if parts.password is not None:
        kw["password"] = unquote(parts.password)
    db = parts.path.lstrip("/")
    if db:
        kw["database"] = db
    return kw


def _stringify(value: Any) -> str:
    """Render one result-set cell as abax cell text.

    ``None`` (SQL NULL) -> ``""``; whole floats collapse to ints (``3.0`` -> ``3``);
    :class:`bytes` decode as UTF-8 (replacing undecodable bytes); everything else
    goes through ``str()`` — matching the CSV / Parquet / statfiles importers.
    """
    if value is None:
        return ""
    if isinstance(value, bool):  # bool before int/float (bool is an int subclass)
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _fetch(cursor) -> Table:
    """Materialize an executed DB-API cursor into ``(headers, rows)`` cell text.

    ``cursor.description`` is a 7-tuple sequence per PEP 249; element 0 of each is
    the column name. Rows are stringified cell-by-cell. A statement that returns
    no result set (``description is None``, e.g. a bare DDL) yields empty headers
    and no rows.
    """
    description = cursor.description
    if description is None:
        return [], []
    headers = [str(col[0]) for col in description]
    rows: List[Row] = [tuple(_stringify(v) for v in record) for record in cursor.fetchall()]
    return headers, rows


def query(conn, sql: str, params: Optional[Sequence[Any]] = None) -> Table:
    """Run an arbitrary SQL query and return ``(headers, rows)`` of cell text.

    Works against any DB-API 2.0 connection (psycopg, pymysql, or stdlib
    sqlite3). ``params`` are bound by the driver (never string-formatted into the
    SQL), so this is the safe way to pass user values. Rows come back as tuples
    of strings; NULL is the empty string. Raises :class:`DatabaseError` on any
    driver error; the SQL text is included in that message to aid debugging, but
    the bound ``params`` (which may hold sensitive values) are never echoed.
    """
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params or ())
        return _fetch(cursor)
    except DatabaseError:
        raise
    except Exception as exc:  # any DB-API driver error
        raise DatabaseError(f"query failed: {exc}\nSQL: {sql}") from exc
    finally:
        try:
            cursor.close()
        except Exception:
            pass


def read_table(conn, table: str, limit: Optional[int] = None) -> Table:
    """Read all rows of one table into ``(headers, rows)`` of cell text.

    ``table`` may be schema-qualified (``schema.name``); each identifier is
    validated (letters/digits/underscore, optionally one dot) and double-quoted
    so it is safe to interpolate — user *data* never reaches this path, only a
    caller-chosen table name. ``limit`` caps the row count (bound as a parameter,
    not formatted in). Raises :class:`DatabaseError` for a malformed identifier or
    any driver error.
    """
    ident = _quote_identifier(table)
    sql = f"SELECT * FROM {ident}"
    params: List[Any] = []
    if limit is not None:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
            raise DatabaseError(f"limit must be a non-negative integer, got {limit!r}")
        sql += " LIMIT ?"
        params.append(limit)
    # sqlite3 uses '?' placeholders; psycopg/pymysql use '%s'. Adapt for non-sqlite
    # drivers so the same generated SQL works everywhere.
    sql = _adapt_placeholders(conn, sql)
    return query(conn, sql, params)


def _adapt_placeholders(conn, sql: str) -> str:
    """Rewrite ``?`` placeholders to the connection's paramstyle if it isn't qmark.

    PEP 249 exposes ``paramstyle`` on the driver *module*; we reach it via the
    connection's class module. sqlite3 is ``qmark`` (``?``); psycopg and pymysql
    are ``pyformat`` (``%s``). Only the un-parameterized ``?`` we generate in
    :func:`read_table` is affected — user SQL in :func:`query` is passed verbatim.
    """
    style = _paramstyle_for(conn)
    if style in ("format", "pyformat"):
        return sql.replace("?", "%s")
    return sql


def _paramstyle_for(conn) -> str:
    """Best-effort DB-API ``paramstyle`` for *conn* (defaults to ``qmark``)."""
    import sys

    module_name = type(conn).__module__ or ""
    # Walk from the most specific module up to the top-level package, returning
    # the first that declares a paramstyle (sqlite3, psycopg, pymysql all do).
    parts = module_name.split(".")
    for i in range(len(parts), 0, -1):
        mod = sys.modules.get(".".join(parts[:i]))
        style = getattr(mod, "paramstyle", None)
        if isinstance(style, str):
            return style
    return "qmark"


def list_tables(conn) -> List[str]:
    """List the user table names visible on *conn* (driver-appropriate query).

    Dispatches on the connection's paramstyle/module: sqlite3 reads
    ``sqlite_master``; PostgreSQL and MySQL read ``information_schema.tables``
    filtered to base tables in user-visible schemas. Returns a sorted list of
    plain (unqualified) names. Raises :class:`DatabaseError` on a driver error.
    """
    module_name = (type(conn).__module__ or "").split(".")[0]
    if module_name == "sqlite3":
        _headers, rows = query(
            conn,
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name",
        )
        return [r[0] for r in rows]

    if module_name == "psycopg":
        _headers, rows = query(
            conn,
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_type = 'BASE TABLE' "
            "AND table_schema NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY table_name",
        )
        return [r[0] for r in rows]

    if module_name == "pymysql":
        _headers, rows = query(
            conn,
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_type = 'BASE TABLE' "
            "AND table_schema = DATABASE() ORDER BY table_name",
        )
        return [r[0] for r in rows]

    # Unknown but DB-API-compatible connection: fall back to the SQL standard.
    _headers, rows = query(
        conn,
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_type = 'BASE TABLE' ORDER BY table_name",
    )
    return [r[0] for r in rows]


def _quote_identifier(name: str) -> str:
    """Validate and double-quote a (optionally schema-qualified) SQL identifier.

    Accepts ``name`` or ``schema.name`` where each part is a non-empty run of
    ASCII letters, digits, and underscores not starting with a digit. Anything
    else — spaces, quotes, semicolons, extra dots — is rejected with
    :class:`DatabaseError`, closing off SQL injection through the table argument.
    Each part is wrapped in double quotes (the SQL-standard identifier quote,
    honored by PostgreSQL, MySQL in ANSI_QUOTES mode, and sqlite3).
    """
    if not isinstance(name, str) or not name:
        raise DatabaseError(f"invalid table name: {name!r}")
    parts = name.split(".")
    if len(parts) > 2:
        raise DatabaseError(
            f"invalid table name {name!r}: at most one schema qualifier is allowed"
        )
    quoted = []
    for part in parts:
        if not _is_identifier(part):
            raise DatabaseError(
                f"invalid SQL identifier {part!r} in table name {name!r}"
            )
        quoted.append('"' + part + '"')
    return ".".join(quoted)


def _is_identifier(part: str) -> bool:
    """True iff *part* is a safe bare SQL identifier (``[A-Za-z_][A-Za-z0-9_]*``)."""
    if not part:
        return False
    first = part[0]
    if not (first.isascii() and (first.isalpha() or first == "_")):
        return False
    return all(ch.isascii() and (ch.isalnum() or ch == "_") for ch in part)


__all__ = [
    "DatabaseError",
    "available",
    "list_drivers",
    "connect",
    "list_tables",
    "read_table",
    "query",
]
