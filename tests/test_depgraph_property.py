"""Differential fuzz: incremental invalidation must equal a full recalc.

Two workbooks are fed an identical, seeded stream of edits. ``wb_inc`` uses the
normal edit path (the incremental dependency graph). ``wb_full`` does the same
edits but calls :meth:`Workbook.invalidate_caches` after every one — the
always-correct oracle. After each op we compare *every* cell across both books:
if the incremental path ever leaves a stale value cached, a cell diverges and
the test fails, printing the seed and the offending op for direct reproduction.

Volatiles (RAND/NOW/…) are stubbed to constants so the only thing that can make
the two books differ is a genuine staleness bug, not nondeterminism. Pure
stdlib, no hypothesis — a fixed-seed ``random.Random`` keeps it reproducible.
"""

from __future__ import annotations

import random

import pytest

import abax.core.functions as fns
from abax.core.errors import CellError
from abax.core.workbook import Workbook

SHEETS = ("S1", "S2", "S3")
ROWS, COLS = 7, 7          # cells the generator writes into
GRID_R, GRID_C = 10, 10    # cells we compare (a little beyond, to catch shifts)


@pytest.fixture()
def stub_volatiles(monkeypatch):
    """Make the volatile functions deterministic so two independent workbooks
    agree when both are correct."""
    monkeypatch.setitem(fns.FUNCTIONS, "RAND", lambda args: 0.5)
    monkeypatch.setitem(fns.FUNCTIONS, "RANDBETWEEN", lambda args: 4.0)
    monkeypatch.setitem(fns.FUNCTIONS, "NOW", lambda args: 45000.0)
    monkeypatch.setitem(fns.FUNCTIONS, "TODAY", lambda args: 45000.0)
    yield


def _new_book():
    wb = Workbook()
    wb.sheets[0].name = SHEETS[0]
    for nm in SHEETS[1:]:
        wb.add_sheet(nm)
    return wb


def _a1(r, c):
    from abax.core.reference import to_a1

    return to_a1(r, c)


def _norm(v):
    # All errors collapse to one class: the *specific* code a cell in or below a
    # circular reference resolves to (#CIRC! vs #REF! vs …) is evaluation-order
    # dependent — a function of which caches happen to be populated, not of which
    # cells are stale. Partial caching (incremental) and full-clear can pick
    # different codes for a circular cell without either being wrong. What the
    # soundness contract actually forbids is a stale *value*: a wrong number, or
    # a number where there should be an error (or vice-versa) — all still caught.
    if isinstance(v, CellError):
        return "ERR"
    if isinstance(v, bool):
        return v
    if isinstance(v, float):
        return round(v, 9)
    return v


def _gen_raw(rng: random.Random, self_sheet: str) -> str:
    """A random cell content exercising every analysis class."""
    kind = rng.random()
    other = rng.choice(SHEETS)
    r1, c1 = rng.randrange(ROWS), rng.randrange(COLS)
    r2, c2 = rng.randrange(ROWS), rng.randrange(COLS)
    a = _a1(r1, c1)
    b = _a1(r2, c2)
    xsheet = "" if other == self_sheet else f"{other}!"
    if kind < 0.16:
        return str(rng.randint(-5, 20))
    if kind < 0.22:
        return rng.choice(["hi", "abax", "x"])
    if kind < 0.44:
        op = rng.choice(["+", "-", "*"])
        return f"={xsheet}{a}{op}{b}"
    if kind < 0.56:
        lo, hi = sorted((r1, r2))
        return f"=SUM({xsheet}{_a1(lo, c1)}:{_a1(hi, c1)})"
    if kind < 0.62:
        return f"=AVERAGE({xsheet}{a}:{_a1(max(r1, r2), max(c1, c2))})"
    if kind < 0.72:
        return f"=IF({a}>0,{b},{xsheet}{a})"
    if kind < 0.80:
        return f"=IFERROR({a}/{b},0)"
    if kind < 0.86:
        return f'=INDIRECT("{a}")'
    if kind < 0.90:
        return f"=OFFSET({a},0,0)"
    if kind < 0.94:
        return f"=SUM({xsheet}A1:A5000)"  # large range -> one rectangle
    return rng.choice(["=RAND()", "=RANDBETWEEN(1,9)", "=NOW()", "=TODAY()"])


def _apply(wb, sheet_name, r, c, raw):
    wb.get_sheet(sheet_name).set(_a1(r, c), raw)


def _assert_agree(wb_inc, wb_full, seed, opdesc):
    for sn in SHEETS:
        si, sf = wb_inc.get_sheet(sn), wb_full.get_sheet(sn)
        for r in range(GRID_R):
            for c in range(GRID_C):
                vi, vf = _norm(si.get_value(r, c)), _norm(sf.get_value(r, c))
                assert vi == vf, (
                    f"\nSTALE at {sn}!{_a1(r, c)}: incremental={vi!r} full={vf!r}"
                    f"\nseed={seed} last_op={opdesc}"
                )


@pytest.mark.parametrize("seed", [1, 7, 42, 1234, 99999])
def test_incremental_equals_full_recalc(seed, stub_volatiles):
    rng = random.Random(seed)
    wb_inc, wb_full = _new_book(), _new_book()

    for i in range(250):
        roll = rng.random()
        if roll < 0.06:
            # Structural op — applied identically to both books.
            sn = rng.choice(SHEETS)
            at = rng.randrange(ROWS)
            op = rng.choice(("insert_rows", "delete_rows", "insert_cols", "delete_cols"))
            for wb in (wb_inc, wb_full):
                getattr(wb.get_sheet(sn), op)(at, 1)
            opdesc = f"{sn}.{op}({at})"
        elif roll < 0.09:
            # Define a name both books can reference. A name (re)definition is a
            # structural event that triggers a recalc in the app (the GUI calls
            # invalidate_caches); model that here so both books see it.
            tgt = f"{rng.choice(SHEETS)}!{_a1(rng.randrange(ROWS), rng.randrange(COLS))}"
            for wb in (wb_inc, wb_full):
                wb.names.define("NM", tgt)
                wb.invalidate_caches()
            opdesc = f"define NM={tgt}"
        else:
            sn = rng.choice(SHEETS)
            r, c = rng.randrange(ROWS), rng.randrange(COLS)
            raw = _gen_raw(rng, sn)
            if rng.random() < 0.05:
                raw = "=A:A"          # deliberate parse error -> ok=False path
            if rng.random() < 0.06:
                raw = "=NM+1"          # reference the (maybe) defined name
            _apply(wb_inc, sn, r, c, raw)
            _apply(wb_full, sn, r, c, raw)
            opdesc = f"{sn}!{_a1(r, c)}={raw}"

        # Oracle: full workbook is force-cleared every op, so it is never stale.
        wb_full.invalidate_caches()
        _assert_agree(wb_inc, wb_full, seed, opdesc)
