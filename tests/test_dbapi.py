"""Tests for abax.engine.dbapi — SQL database connectivity (DB-API 2.0).

The adapter's read helpers (query / read_table / list_tables) are driver-
agnostic: any PEP 249 connection works, so the round-trip behaviour is exercised
here against the stdlib :mod:`sqlite3` — no external driver (psycopg / pymysql)
required, keeping the suite green with zero optional packages installed. The
graceful missing-driver message, the driver registry, and the three
registrations (autodeps / diagnostics / pyproject) are ALWAYS tested too.

SECURITY: two tests pin the fail-closed contract — the table-name argument is
validated against SQL injection, and connection DSNs are never written to disk.
"""

from __future__ import annotations

import sqlite3

import pytest

from abax import autodeps, diagnostics
from abax.engine import dbapi
from abax.engine.dbapi import DatabaseError

# --- driver-free contract tests (always run) --------------------------------


def test_available_returns_bool():
    # Importable without any optional driver; available() is always a plain bool.
    assert isinstance(dbapi.available(), bool)


def test_module_imports_without_drivers():
    # The module and DatabaseError exist regardless of any driver being installed.
    assert issubclass(DatabaseError, Exception)


def test_list_drivers_shape():
    drivers = dbapi.list_drivers()
    mods = {d["module"] for d in drivers}
    assert mods == {"psycopg", "pymysql"}
    for d in drivers:
        assert set(d) == {"module", "pip", "label", "available"}
        assert isinstance(d["available"], bool)
    # The advertised pip targets and DB labels match the task's mapping.
    by_mod = {d["module"]: d for d in drivers}
    assert by_mod["psycopg"]["pip"] == "psycopg[binary]"
    assert by_mod["psycopg"]["label"] == "PostgreSQL"
    assert by_mod["pymysql"]["pip"] == "PyMySQL"
    assert by_mod["pymysql"]["label"] == "MySQL"


def test_missing_driver_message_points_at_extra(monkeypatch):
    # With NO driver installed, connect() must raise a DatabaseError that names
    # both drivers and the pip extra — the graceful-fallback contract. We force
    # the absent path so this runs whether or not a real driver is present.
    monkeypatch.setattr(dbapi, "_installed", lambda mod: False)
    with pytest.raises(DatabaseError) as exc:
        dbapi.connect("postgresql://user:pw@localhost/db")
    msg = str(exc.value)
    assert "pip install abax[database]" in msg
    assert "psycopg" in msg and "pymysql" in msg


def test_connect_unknown_driver_rejected():
    with pytest.raises(DatabaseError) as exc:
        dbapi.connect(driver="oracle")
    assert "oracle" in str(exc.value)


def test_connect_ambiguous_without_scheme(monkeypatch):
    # Both drivers "installed" but no scheme / explicit driver -> a clear error
    # rather than an arbitrary pick.
    monkeypatch.setattr(dbapi, "_installed", lambda mod: True)
    with pytest.raises(DatabaseError) as exc:
        dbapi.connect(host="localhost", dbname="x")
    assert "which database driver" in str(exc.value)


# --- the three registrations (always run) -----------------------------------


def test_registered_in_autodeps():
    # New 'database' feature resolves to (pip, import) pairs for both drivers.
    assert autodeps.FEATURES["database"] == [
        ("psycopg[binary]", "psycopg"),
        ("PyMySQL", "pymysql"),
    ]
    # Folded into the full-fat set...
    assert ("psycopg[binary]", "psycopg") in autodeps.ALL
    assert ("PyMySQL", "pymysql") in autodeps.ALL
    # ...but PyNEC stays dead last (compiled build can't block the rest).
    assert autodeps.ALL[-1] == ("PyNEC", "PyNEC")
    assert autodeps.ALL.index(("PyMySQL", "pymysql")) < autodeps.ALL.index(
        ("PyNEC", "PyNEC")
    )
    # Chooser metadata is present.
    assert "database" in autodeps.FEATURE_INFO
    label, detail, mb = autodeps.FEATURE_INFO["database"]
    assert label and detail and isinstance(mb, int)
    # 'all' preset includes it; 'thin' does not.
    assert "database" in autodeps.preset("all")
    assert "database" not in autodeps.preset("thin")


def test_registered_in_diagnostics():
    for pkg in ("psycopg", "pymysql"):
        assert pkg in diagnostics.OPTIONAL_DEPENDENCIES
        entry = diagnostics.OPTIONAL_DEPENDENCIES[pkg]
        assert isinstance(entry["available"], bool)
        assert entry["fallback"] and entry["purpose"]


def test_registered_in_pyproject():
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    extras = data["project"]["optional-dependencies"]
    assert extras["database"] == ["psycopg[binary]", "PyMySQL"]
    # Folded into `all`.
    assert any("database" in dep for dep in extras["all"])


# --- identifier safety (always run) -----------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "users; DROP TABLE users",
        "users--",
        'users" OR "1"="1',
        "a.b.c",            # too many qualifiers
        "1users",           # starts with a digit
        "user name",        # space
        "",                 # empty
        "täble",            # non-ASCII
    ],
)
def test_read_table_rejects_injection(bad):
    # A hostile table name must be refused before any SQL is built/executed.
    conn = sqlite3.connect(":memory:")
    try:
        with pytest.raises(DatabaseError):
            dbapi.read_table(conn, bad)
    finally:
        conn.close()


def test_quote_identifier_accepts_schema_qualified():
    assert dbapi._quote_identifier("public.my_table") == '"public"."my_table"'
    assert dbapi._quote_identifier("t1") == '"t1"'


# --- DSNs are never persisted (security contract) ---------------------------


def test_url_parsing_maps_to_kwargs():
    kw = dbapi._parse_url("mysql://alice:s%40cret@db.example.com:3307/shop")
    assert kw == {
        "host": "db.example.com",
        "port": 3307,
        "user": "alice",
        "password": "s@cret",  # percent-decoded
        "database": "shop",
    }


def test_dsn_not_written_to_disk(tmp_path, monkeypatch):
    """Fail-closed: opening a connection must not write the DSN (which may embed
    a password) anywhere on disk. We point every abax runtime dir at an empty
    temp tree, attempt a connect that fails at the driver, and assert the secret
    never appears in any file created underneath."""
    from abax import _runtime as rt

    for attr in ("CONFIG_DIR", "DATA_DIR", "CACHE_DIR", "LOG_DIR"):
        monkeypatch.setattr(rt, attr, tmp_path, raising=False)

    secret = "sup3r-s3cret-pw"
    dsn = f"postgresql://user:{secret}@localhost:5432/db"
    # Force a driver to be "present" so connect() proceeds to the driver call,
    # which then fails (no server) — the point is that nothing is persisted.
    monkeypatch.setattr(dbapi, "_installed", lambda mod: mod == "psycopg")

    class _FakeDriver:
        def connect(self, *a, **k):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(dbapi, "_import", lambda mod: _FakeDriver())
    with pytest.raises(DatabaseError) as exc:
        dbapi.connect(dsn)
    # The secret must not leak into the raised message either.
    assert secret not in str(exc.value)

    # No file anywhere under the runtime tree may contain the secret.
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert secret not in path.read_bytes()


# --- round-trip against stdlib sqlite3 (always run — sqlite3 is stdlib) ------


def _make_conn():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE people (id INTEGER, name TEXT, height REAL, note TEXT);
        INSERT INTO people VALUES (1, 'Alice', 1.5, NULL);
        INSERT INTO people VALUES (2, 'Bob',   2.0, 'hi');
        CREATE TABLE other (x INTEGER);
        """
    )
    return conn


def test_query_returns_headers_and_cell_text():
    conn = _make_conn()
    try:
        headers, rows = dbapi.query(
            conn, "SELECT id, name, height, note FROM people ORDER BY id"
        )
        assert headers == ["id", "name", "height", "note"]
        # NULL -> ""; whole float 2.0 -> "2"; non-whole float stays; ints str'd.
        assert rows[0] == ("1", "Alice", "1.5", "")
        assert rows[1] == ("2", "Bob", "2", "hi")
    finally:
        conn.close()


def test_query_binds_params_not_formatted():
    conn = _make_conn()
    try:
        # Passing a value that would be dangerous if string-formatted proves the
        # driver binds it as data. sqlite3 uses '?' placeholders.
        headers, rows = dbapi.query(
            conn, "SELECT name FROM people WHERE name = ?", ("Bob",)
        )
        assert headers == ["name"]
        assert rows == [("Bob",)]
    finally:
        conn.close()


def test_read_table_all_rows():
    conn = _make_conn()
    try:
        headers, rows = dbapi.read_table(conn, "people")
        assert headers == ["id", "name", "height", "note"]
        assert len(rows) == 2
    finally:
        conn.close()


def test_read_table_limit():
    conn = _make_conn()
    try:
        headers, rows = dbapi.read_table(conn, "people", limit=1)
        assert len(rows) == 1
    finally:
        conn.close()


def test_read_table_negative_limit_rejected():
    conn = sqlite3.connect(":memory:")
    try:
        with pytest.raises(DatabaseError):
            dbapi.read_table(conn, "people", limit=-3)
    finally:
        conn.close()


def test_list_tables_sqlite():
    conn = _make_conn()
    try:
        assert dbapi.list_tables(conn) == ["other", "people"]
    finally:
        conn.close()


def test_query_error_wrapped_without_params():
    conn = _make_conn()
    try:
        with pytest.raises(DatabaseError) as exc:
            dbapi.query(conn, "SELECT * FROM does_not_exist")
        # The SQL is echoed to aid debugging; it's a DatabaseError, not a raw
        # sqlite3.OperationalError leaking to the caller.
        assert "does_not_exist" in str(exc.value)
    finally:
        conn.close()


def test_paramstyle_adaptation_for_pyformat_driver():
    # read_table generates a '?' LIMIT placeholder; for a pyformat driver it must
    # be rewritten to '%s'. Simulate one by faking the connection's paramstyle.
    class _Cur:
        description = None

        def execute(self, sql, params):
            self.seen_sql = sql

        def fetchall(self):
            return []

        def close(self):
            pass

    captured = {}

    class _Conn:
        def cursor(self):
            captured["cur"] = _Cur()
            return captured["cur"]

    monkeypatch_style = "pyformat"
    # Patch the paramstyle resolver via the module-level helper.
    import abax.engine.dbapi as m

    orig = m._paramstyle_for
    m._paramstyle_for = lambda conn: monkeypatch_style
    try:
        m.read_table(_Conn(), "people", limit=5)
    finally:
        m._paramstyle_for = orig
    assert "%s" in captured["cur"].seen_sql
    assert "?" not in captured["cur"].seen_sql
