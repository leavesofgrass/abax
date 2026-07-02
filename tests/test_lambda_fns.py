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
    s.set("A1", "=LET(f, LAMBDA(x, x*x), f(1, 2))")   # too MANY args still errors
    assert "VALUE" in str(s.get("A1")).upper()


# --- optional (omitted) trailing parameters + ISOMITTED --------------------


def test_lambda_omitted_trailing_param():
    # b omitted -> ISOMITTED(b) is TRUE, so the guarded branch returns a.
    s = Sheet()
    s.set("A1", "=LET(f, LAMBDA(a, b, IF(ISOMITTED(b), a, a+b)), f(5))")
    assert s.get("A1") == 5


def test_lambda_omitted_trailing_param_supplied():
    # b supplied -> ISOMITTED(b) is FALSE, so a+b is returned.
    s = Sheet()
    s.set("A1", "=LET(f, LAMBDA(a, b, IF(ISOMITTED(b), a, a+b)), f(5, 3))")
    assert s.get("A1") == 8


def test_lambda_omitted_default_pattern():
    # A default-argument pattern: supply 10 when the second arg is omitted.
    s = Sheet()
    s.set("A1", "=LET(f, LAMBDA(a, b, a + IF(ISOMITTED(b), 10, b)), f(5))")
    assert s.get("A1") == 15
    s.set("A2", "=LET(f, LAMBDA(a, b, a + IF(ISOMITTED(b), 10, b)), f(5, 2))")
    assert s.get("A2") == 7


def test_isomitted_on_ordinary_value_is_false():
    s = Sheet()
    s.set("A1", "=ISOMITTED(1)")
    assert s.get("A1") is False


def test_omitted_param_in_arithmetic_errors():
    # Using an omitted parameter directly in arithmetic (unguarded) is #VALUE!.
    s = Sheet()
    s.set("A1", "=LET(f, LAMBDA(a, b, a + b), f(5))")
    assert "VALUE" in str(s.get("A1")).upper()


# --- direct LAMBDA-call syntax: LAMBDA(args...)(call_args...) -----------------


def test_lambda_direct_call_one_arg():
    s = Sheet()
    s.set("A1", "=LAMBDA(x, x*x)(5)")
    assert s.get("A1") == 25


def test_lambda_direct_call_two_args():
    s = Sheet()
    s.set("A1", "=LAMBDA(a, b, a+b)(3, 4)")
    assert s.get("A1") == 7


def test_lambda_direct_call_with_cell_ref():
    s = Sheet()
    s.set("A1", "10")
    s.set("B1", "=LAMBDA(x, x+1)(A1)")
    assert s.get("B1") == 11


def test_lambda_direct_call_wrong_arity():
    s = Sheet()
    s.set("A1", "=LAMBDA(x, x*x)(1, 2)")   # two args for a one-param lambda
    assert "VALUE" in str(s.get("A1")).upper()


def test_lambda_direct_call_in_expression():
    s = Sheet()
    s.set("A1", "=LAMBDA(x, x*x)(3) + LAMBDA(y, y+1)(9)")   # 9 + 10
    assert s.get("A1") == 19


def test_lambda_direct_call_still_named_via_let():
    # The LET-bound path (F(5)) must keep working alongside the new seam.
    s = Sheet()
    s.set("A1", "=LET(f, LAMBDA(x, x*x), f(5))")
    assert s.get("A1") == 25


def test_lambda_direct_call_chaining():
    # A lambda that returns a lambda, applied twice: (LAMBDA(a, LAMBDA(b, a+b)))
    s = Sheet()
    s.set("A1", "=LAMBDA(a, LAMBDA(b, a+b))(3)(4)")
    assert s.get("A1") == 7


def test_calling_a_non_lambda_is_value_error():
    # A parenthesized number applied like a function -> #VALUE!.
    s = Sheet()
    s.set("A1", "=(1+2)(3)")
    assert "VALUE" in str(s.get("A1")).upper()


def test_ordinary_function_call_unaffected():
    # SUM(A1:A3) must remain a plain function call (a Func, not a Call).
    from abax.core import ast_nodes as A
    from abax.core.parser import parse

    node = parse("SUM(A1:A3)")
    assert isinstance(node, A.Func)
    node2 = parse("LAMBDA(x, x)(5)")
    assert isinstance(node2, A.Call)


def test_lambda_direct_call_propagates_arg_error():
    s = Sheet()
    s.set("A1", "=LAMBDA(x, x+1)(1/0)")
    assert "DIV" in str(s.get("A1")).upper()


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
