"""Resolved-AST cache: name resolution is memoized but stays correct when the
name registry or the cell formula changes (the formula-engine hot-path
optimization — a defined-name formula no longer re-walks/rewrites its AST on
every evaluation)."""

from __future__ import annotations

from abax.core.workbook import Workbook


def _fresh():
    wb = Workbook()
    sh = wb.sheets[0]
    return wb, sh


def test_resolved_ast_is_cached_and_reused():
    wb, sh = _fresh()
    sh.set("B1", "42")
    sh.set("A1", "=SALES")
    wb.names.define("SALES", "B1")
    wb.invalidate_caches()
    assert sh.get("A1") == 42.0
    # The resolved AST is now cached for A1 at the current registry versions.
    # The key is (names_version, tables_version); the tables registry is empty
    # here, so its slot is the -1 "absent registry" sentinel.
    key = (0, 0)
    assert key in sh._rast_cache
    ver, _ = sh._rast_cache[key]
    assert ver == (wb.names.version, -1)
    # A second read reuses it (value cache) — and forcing a recompute keeps it.
    sh._value_cache.clear()
    assert sh.get("A1") == 42.0
    assert sh._rast_cache[key][0] == ver


def test_redefining_name_invalidates_resolution():
    wb, sh = _fresh()
    sh.set("B1", "42")
    sh.set("C1", "99")
    sh.set("A1", "=SALES")
    wb.names.define("SALES", "B1")
    wb.invalidate_caches()
    assert sh.get("A1") == 42.0
    # Point the name at a different cell; the version bump must invalidate the
    # cached resolved AST even though A1's formula text is unchanged.
    wb.names.define("SALES", "C1")
    wb.invalidate_caches()
    assert sh.get("A1") == 99.0


def test_removing_name_invalidates_resolution():
    wb, sh = _fresh()
    sh.set("B1", "42")
    sh.set("A1", "=SALES")
    wb.names.define("SALES", "B1")
    wb.invalidate_caches()
    assert sh.get("A1") == 42.0
    wb.names.remove("SALES")
    wb.invalidate_caches()
    # Undefined name -> #NAME? error.
    assert "NAME" in str(sh.get("A1")).upper()


def test_editing_formula_drops_resolved_entry():
    wb, sh = _fresh()
    sh.set("B1", "42")
    sh.set("C1", "7")
    sh.set("A1", "=SALES")
    wb.names.define("SALES", "B1")
    wb.invalidate_caches()
    assert sh.get("A1") == 42.0
    assert (0, 0) in sh._rast_cache
    # Rewriting the cell must drop its resolved-AST entry.
    sh.set("A1", "=SALES+C1")
    assert (0, 0) not in sh._rast_cache
    assert sh.get("A1") == 49.0


def test_no_names_skips_resolution_cache():
    wb, sh = _fresh()
    sh.set("A1", "=1+1")
    assert sh.get("A1") == 2.0
    # With no defined names, the resolved-AST cache stays empty.
    assert sh._rast_cache == {}
