"""Tests for the named-connection registry (``abax.core.connections``).

Covers the :class:`Connection` dataclass, the case-insensitive
:class:`ConnectionRegistry` CRUD + versioning, the non-secret-only round-trip
(the security guarantee), and the :func:`refresh` dispatcher.
"""

from __future__ import annotations

import pytest

from abax.core.connections import (
    VALID_KINDS,
    Connection,
    ConnectionError,
    ConnectionRegistry,
    refresh,
)

# --- fixtures --------------------------------------------------------------


def _rest_conn() -> Connection:
    return Connection(
        name="Sales",
        kind="rest",
        target="https://api.example.com/v1/sales",
        dest="Data!A1",
        options={"records_path": "data.items"},
        secret_ref="sales_token",
    )


def _registry() -> ConnectionRegistry:
    reg = ConnectionRegistry()
    reg.add(_rest_conn())
    return reg


# --- the Connection model --------------------------------------------------


def test_connection_fields():
    c = _rest_conn()
    assert c.name == "Sales"
    assert c.kind == "rest"
    assert c.target == "https://api.example.com/v1/sales"
    assert c.dest == "Data!A1"
    assert c.options == {"records_path": "data.items"}
    assert c.last_refreshed is None
    assert c.secret_ref == "sales_token"


def test_connection_defaults():
    c = Connection(name="Q", kind="sql", target="SELECT 1", dest="Sheet1!A1")
    assert c.options == {}
    assert c.last_refreshed is None
    assert c.secret_ref is None


def test_connection_has_no_secret_value_field():
    """The model must not carry a password/token/credential value anywhere."""
    c = _rest_conn()
    for banned in ("password", "token", "secret", "credential", "dsn"):
        assert not hasattr(c, banned)


@pytest.mark.parametrize("kind", sorted(VALID_KINDS))
def test_valid_kinds_construct(kind):
    c = Connection(name="c", kind=kind, target="t", dest="A1")
    assert c.kind == kind


def test_unknown_kind_rejected():
    with pytest.raises(ConnectionError):
        Connection(name="c", kind="graphql", target="t", dest="A1")


@pytest.mark.parametrize("bad", ["", "   ", None, 123])
def test_blank_or_nonstring_name_rejected(bad):
    with pytest.raises(ConnectionError):
        Connection(name=bad, kind="rest", target="t", dest="A1")


# --- registry CRUD ---------------------------------------------------------


def test_add_get_and_len():
    reg = _registry()
    assert len(reg) == 1
    assert reg.get("Sales").target.endswith("/sales")


def test_get_missing_returns_none():
    reg = _registry()
    assert reg.get("nope") is None
    assert reg.get(123) is None  # non-string is tolerated, not an error


def test_case_insensitive_lookup():
    reg = _registry()
    assert reg.get("sales") is reg.get("SALES") is reg.get("Sales")
    assert reg.has("sAlEs")
    assert "SALES" in reg
    assert 123 not in reg  # __contains__ tolerates non-strings


def test_add_overwrites_same_name_case_insensitively():
    reg = _registry()
    reg.add(Connection(name="SALES", kind="sql", target="SELECT 2", dest="Z9"))
    assert len(reg) == 1
    assert reg.get("sales").kind == "sql"


def test_names_sorted_case_insensitively():
    reg = _registry()
    reg.add(Connection(name="apex", kind="rest", target="t", dest="A1"))
    reg.add(Connection(name="Beta", kind="rest", target="t", dest="A1"))
    assert reg.names() == ["apex", "Beta", "Sales"]


def test_iter_yields_connections():
    reg = _registry()
    assert [c.name for c in reg] == ["Sales"]


def test_remove():
    reg = _registry()
    reg.remove("SALES")
    assert len(reg) == 0
    assert not reg.has("Sales")


def test_remove_missing_raises():
    reg = _registry()
    with pytest.raises(ConnectionError):
        reg.remove("ghost")


def test_rename_keeps_connection_and_updates_display_name():
    reg = _registry()
    reg.rename("sales", "Revenue")
    assert not reg.has("Sales")
    assert reg.has("Revenue")
    assert reg.get("revenue").name == "Revenue"


def test_rename_missing_raises():
    reg = _registry()
    with pytest.raises(ConnectionError):
        reg.rename("ghost", "New")


def test_rename_collision_raises():
    reg = _registry()
    reg.add(Connection(name="Other", kind="rest", target="t", dest="A1"))
    with pytest.raises(ConnectionError):
        reg.rename("Other", "sales")


def test_rename_to_blank_raises():
    reg = _registry()
    with pytest.raises(ConnectionError):
        reg.rename("Sales", "   ")


def test_add_rejects_non_connection():
    reg = ConnectionRegistry()
    with pytest.raises(ConnectionError):
        reg.add({"name": "x", "kind": "rest"})


# --- version counter -------------------------------------------------------


def test_version_bumps_on_mutations():
    reg = ConnectionRegistry()
    assert reg.version == 0
    reg.add(_rest_conn())
    v1 = reg.version
    assert v1 == 1
    reg.rename("Sales", "Rev")
    assert reg.version == v1 + 1
    reg.touch()
    assert reg.version == v1 + 2
    reg.remove("Rev")
    assert reg.version == v1 + 3


# --- serialization round-trip (the security guarantee) ---------------------


def test_to_dict_from_dict_round_trip():
    reg = _registry()
    reg.add(Connection(name="Prices", kind="webtable",
                       target="https://example.com/prices",
                       dest="Prices!A1", options={"table_index": 2}))
    restored = ConnectionRegistry.from_dict(reg.to_dict())
    assert restored.names() == reg.names()
    s = restored.get("Sales")
    assert s.kind == "rest"
    assert s.target == "https://api.example.com/v1/sales"
    assert s.dest == "Data!A1"
    assert s.options == {"records_path": "data.items"}
    assert s.secret_ref == "sales_token"
    assert restored.get("Prices").options == {"table_index": 2}


def test_serialized_form_carries_no_secret_value():
    """secret_ref (a name) survives; no password/token VALUE is ever emitted."""
    reg = _registry()
    dumped = reg.to_dict()
    entry = dumped["Sales"]
    # The non-secret credential *reference* round-trips...
    assert entry["secret_ref"] == "sales_token"
    # ...but no secret VALUE key exists anywhere in the serialized payload.
    for banned in ("password", "token", "secret", "credential", "dsn", "auth"):
        assert banned not in entry
    # Belt-and-braces: scan the whole flattened payload for a value key.
    assert set(entry) == {
        "name", "kind", "target", "dest", "options",
        "last_refreshed", "secret_ref",
    }


def test_connection_to_dict_keys_are_exactly_the_non_secret_fields():
    d = _rest_conn().to_dict()
    assert set(d) == {
        "name", "kind", "target", "dest", "options",
        "last_refreshed", "secret_ref",
    }


def test_from_dict_ignores_stray_secret_keys():
    """A hand-edited/tampered envelope with a secret value can't inject one."""
    payload = {
        "Evil": {
            "name": "Evil", "kind": "rest", "target": "http://x", "dest": "A1",
            "options": {}, "last_refreshed": None, "secret_ref": "k",
            # Attacker-planted extras — must be dropped, not absorbed.
            "password": "hunter2", "token": "abc123",
        }
    }
    reg = ConnectionRegistry.from_dict(payload)
    c = reg.get("Evil")
    assert not hasattr(c, "password")
    assert not hasattr(c, "token")
    # And a re-serialize still carries no secret value.
    assert "password" not in reg.to_dict()["Evil"]
    assert "token" not in reg.to_dict()["Evil"]


def test_from_dict_skips_invalid_entries():
    payload = {
        "Good": {"name": "Good", "kind": "rest", "target": "t", "dest": "A1"},
        "BadKind": {"name": "BadKind", "kind": "nope", "target": "t", "dest": "A1"},
        "Nameless": {"kind": "rest", "target": "t", "dest": "A1"},  # missing name
    }
    reg = ConnectionRegistry.from_dict(payload)
    assert reg.names() == ["Good"]


def test_from_dict_empty_and_none():
    assert len(ConnectionRegistry.from_dict({})) == 0
    assert len(ConnectionRegistry.from_dict(None)) == 0


# --- the refresh dispatcher ------------------------------------------------


def test_refresh_dispatches_to_rest_fetcher():
    conn = _rest_conn()
    grid = [["Region", "Amount"], ["West", "10"]]
    seen = {}

    def rest_fetch(c):
        seen["conn"] = c
        return grid

    def sql_run(c):  # pragma: no cover - must not be called for a rest conn
        raise AssertionError("sql_run should not be called for kind=rest")

    out = refresh(conn, rest_fetch=rest_fetch, sql_run=sql_run)
    assert out is grid
    assert seen["conn"] is conn  # the whole Connection is handed to the fetcher


def test_refresh_dispatches_per_kind():
    cases = {
        "rest": ("rest_fetch", [["r"]]),
        "sql": ("sql_run", [["s"]]),
        "webtable": ("web_fetch", [["w"]]),
    }
    for kind, (param, grid) in cases.items():
        conn = Connection(name=kind, kind=kind, target="t", dest="A1")
        out = refresh(conn, **{param: lambda c, g=grid: g})
        assert out == grid


def test_refresh_missing_fetcher_raises():
    conn = _rest_conn()
    with pytest.raises(ConnectionError):
        refresh(conn)  # no rest_fetch supplied
    with pytest.raises(ConnectionError):
        refresh(conn, sql_run=lambda c: [[1]])  # wrong kind's fetcher


def test_refresh_unknown_kind_raises():
    conn = _rest_conn()
    conn.kind = "graphql"  # bypass construction guard to hit the dispatcher guard
    with pytest.raises(ConnectionError):
        refresh(conn, rest_fetch=lambda c: [[1]])


def test_refresh_does_not_mutate_connection():
    conn = _rest_conn()
    assert conn.last_refreshed is None
    refresh(conn, rest_fetch=lambda c: [["x"]])
    # The dispatcher is pure: it never stamps last_refreshed itself.
    assert conn.last_refreshed is None


def test_refresh_propagates_fetcher_errors():
    conn = _rest_conn()

    class Boom(Exception):
        pass

    def rest_fetch(c):
        raise Boom("network down")

    with pytest.raises(Boom):
        refresh(conn, rest_fetch=rest_fetch)
