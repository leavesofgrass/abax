"""LET, LAMBDA and the functional array helpers (MAP/REDUCE/SCAN/BYROW/BYCOL/
MAKEARRAY) — name bindings on the EvalContext, lambda values, and spill
integration."""

from __future__ import annotations

from abax.core.sheet import Sheet


def _sheet_123():
    s = Sheet()
    for r, val in enumerate([1, 2, 3]):
        s.set_cell(r, 0, str(val))       # A1:A3 = 1,2,3
    for r, val in enumerate([10, 20, 30]):
        s.set_cell(r, 1, str(val))       # B1:B3 = 10,20,30
    return s


def _vals(s, refs):
    return [s.get(r) for r in refs]


# --- LET ---------------------------------------------------------------------


def test_let_basic():
    s = Sheet()
    s.set("A1", "=LET(x, 2, x*3)")
    assert s.get("A1") == 6


def test_let_sequential_bindings():
    s = Sheet()
    s.set("A1", "=LET(x, 2, y, x+1, x*y)")   # y sees x
    assert s.get("A1") == 6


def test_let_binds_ranges():
    s = _sheet_123()
    s.set("D1", "=LET(v, A1:A3, SUM(v))")
    assert s.get("D1") == 6.0
    # A LET whose calculation is an array spills.
    s.set("E1", "=LET(v, A1:A3, v*2)")
    assert _vals(s, ["E1", "E2", "E3"]) == [2, 4, 6]


def test_let_nested_and_shadowing():
    s = Sheet()
    s.set("A1", "=LET(x, 1, LET(x, 10, x) + x)")   # inner x shadows outer
    assert s.get("A1") == 11


def test_let_validation():
    s = Sheet()
    s.set("A1", "=LET(x, 1)")           # even arg count: no calculation
    assert "VALUE" in str(s.get("A1")).upper()
    s.set("A2", '=LET("x", 1, 2)')      # binding name must be a name
    assert "VALUE" in str(s.get("A2")).upper()


def test_let_name_unknown_outside_scope():
    s = Sheet()
    s.set("A1", "=LET(x, 5, x)")
    s.set("A2", "=x")                    # x is not in scope here
    assert s.get("A1") == 5
    assert "NAME" in str(s.get("A2")).upper()


# --- LAMBDA ---------------------------------------------------------------------


def test_uncalled_lambda_is_calc_error():
    s = Sheet()
    s.set("A1", "=LAMBDA(x, x+1)")
    assert "CALC" in str(s.get("A1")).upper()


def test_named_lambda_call_via_let():
    s = Sheet()
    s.set("A1", "=LET(f, LAMBDA(x, x*x), f(5))")
    assert s.get("A1") == 25
    # Two-parameter lambda, called twice.
    s.set("A2", "=LET(add, LAMBDA(a, b, a+b), add(2,3) + add(10,20))")
    assert s.get("A2") == 35


def test_lambda_wrong_arity():
    s = Sheet()
    s.set("A1", "=LET(f, LAMBDA(x, x*x), f(1, 2))")
    assert "VALUE" in str(s.get("A1")).upper()


# --- MAP / REDUCE / SCAN ----------------------------------------------------------


def test_map_single_array_spills():
    s = _sheet_123()
    s.set("D1", "=MAP(A1:A3, LAMBDA(x, x*2))")
    assert _vals(s, ["D1", "D2", "D3"]) == [2, 4, 6]


def test_map_two_arrays():
    s = _sheet_123()
    s.set("D1", "=MAP(A1:A3, B1:B3, LAMBDA(x, y, x+y))")
    assert _vals(s, ["D1", "D2", "D3"]) == [11, 22, 33]


def test_map_shape_mismatch():
    s = _sheet_123()
    s.set("D1", "=MAP(A1:A3, B1:B2, LAMBDA(x, y, x+y))")
    assert "VALUE" in str(s.get("D1")).upper()


def test_reduce():
    s = _sheet_123()
    s.set("D1", "=REDUCE(0, A1:A3, LAMBDA(acc, v, acc+v))")
    assert s.get("D1") == 6
    s.set("D2", "=REDUCE(1, A1:A3, LAMBDA(acc, v, acc*v))")
    assert s.get("D2") == 6
    s.set("D3", "=REDUCE(100, A1:A3, LAMBDA(acc, v, acc+v))")
    assert s.get("D3") == 106


def test_scan_spills_running_total():
    s = _sheet_123()
    s.set("D1", "=SCAN(0, A1:A3, LAMBDA(acc, v, acc+v))")
    assert _vals(s, ["D1", "D2", "D3"]) == [1, 3, 6]


# --- BYROW / BYCOL / MAKEARRAY ------------------------------------------------------


def test_byrow_and_bycol():
    s = _sheet_123()
    s.set("D1", "=BYROW(A1:B3, LAMBDA(r, SUM(r)))")     # row sums, spilled column
    assert _vals(s, ["D1", "D2", "D3"]) == [11.0, 22.0, 33.0]
    s.set("F1", "=BYCOL(A1:B3, LAMBDA(c, MAX(c)))")     # column maxima, spilled row
    assert _vals(s, ["F1", "G1"]) == [3.0, 30.0]


def test_makearray():
    s = Sheet()
    s.set("A1", "=MAKEARRAY(2, 3, LAMBDA(r, c, r*c))")
    assert [s.get_value(0, c) for c in range(3)] == [1, 2, 3]
    assert [s.get_value(1, c) for c in range(3)] == [2, 4, 6]


def test_map_composes_in_aggregates():
    s = _sheet_123()
    s.set("D1", "=SUM(MAP(A1:A3, LAMBDA(x, x*x)))")     # 1+4+9
    assert s.get("D1") == 14


def test_lambda_closes_over_let_bindings():
    s = _sheet_123()
    # The lambda body uses a name bound by the enclosing LET (a closure).
    s.set("D1", "=LET(k, 10, SUM(MAP(A1:A3, LAMBDA(x, x*k))))")
    assert s.get("D1") == 60
