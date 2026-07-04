"""Widened numpy accelerator: multi-range reductions + SUMPRODUCT.

Each formula is run twice -- once through the numpy path (``npkernel.register()``)
and once through a forced stdlib path (``set_aggregate_accelerator(None)``) -- and
the two are asserted equal, so the accelerator can never change a result. The
accelerator only enters on wholly finite-numeric input; the fallback cases (a
blank, text, or an empty range) must therefore return exactly what stdlib does.

The SUMPRODUCT worked example is checked against the Excel/gnumeric definition
SUMPRODUCT = Sum(a_i * b_i) -- see Microsoft's SUMPRODUCT reference
(support.microsoft.com, "SUMPRODUCT function") and the gnumeric manual entry --
using {1,2,3}.{4,5,6} = 4 + 10 + 18 = 32.
"""

from __future__ import annotations

import pytest

from abax import _runtime
from abax.core.functions import FUNCTIONS
from abax.core.values import RangeValue

np = pytest.importorskip("numpy")

from abax.engine import npkernel  # noqa: E402

# Big enough that even a single range clears _ACCEL_MIN_CELLS (4096), so the
# numpy path is genuinely entered (and then bails) on the fallback cases too.
_N = 5000


@pytest.fixture()
def accel():
    """Enable the numpy accelerator for the test, then clear the slot."""
    npkernel.register()
    try:
        yield
    finally:
        _runtime.set_aggregate_accelerator(None)


def _col(n, f=lambda i: float(i)):
    return RangeValue([[f(i)] for i in range(n)])


def _both(fn_name, args):
    """Return ``(numpy_result, stdlib_result)`` for the same formula/args."""
    npkernel.register()
    hot = FUNCTIONS[fn_name](args)
    _runtime.set_aggregate_accelerator(None)
    cold = FUNCTIONS[fn_name](args)
    return hot, cold


# --- multi-range reductions: numpy path == forced-stdlib path ---------------


@pytest.mark.parametrize("fn", ["SUM", "AVERAGE", "MIN", "MAX", "COUNT", "PRODUCT"])
def test_multirange_all_numeric_matches_stdlib(accel, fn):
    a = _col(_N, lambda i: i * 0.25 - 3.0)
    b = _col(_N, lambda i: 1.0 if i % 7 else 2.0)   # keeps PRODUCT finite (no 0)
    c = _col(_N, lambda i: -(i % 5) - 0.5)
    hot, cold = _both(fn, [a, b, c])
    assert hot == pytest.approx(cold, rel=1e-12)


def test_multirange_sum_worked_value(accel):
    # Two 2-cell ranges won't clear the accel threshold, so this exercises the
    # stdlib pool directly; the value is the plain Excel SUM over both blocks:
    # (1+2) + (3+4) = 10.
    a = RangeValue([[1.0], [2.0]])
    b = RangeValue([[3.0], [4.0]])
    assert FUNCTIONS["SUM"]([a, b]) == pytest.approx(10.0)


def test_multirange_count_pools_every_cell(accel):
    a = _col(_N)
    b = _col(_N)
    # COUNT over two finite-numeric blocks counts all cells in both.
    hot, cold = _both("COUNT", [a, b])
    assert hot == pytest.approx(cold)
    assert hot == pytest.approx(float(2 * _N))


# --- fallbacks: a dirty cell forces the exact stdlib result -----------------


def test_multirange_blank_matches_stdlib(accel):
    a = _col(_N)
    grid = [[1.0] for _ in range(_N)]
    grid[3] = [None]                 # a blank -> numpy would see NaN -> must bail
    b = RangeValue(grid)
    hot, cold = _both("SUM", [a, b])
    assert hot == pytest.approx(cold)
    # stdlib skips the blank: sum(0..N-1) + (N-1 ones).
    assert cold == pytest.approx(sum(range(_N)) + float(_N - 1))


def test_multirange_text_matches_stdlib(accel):
    a = _col(_N)
    grid = [[1.0] for _ in range(_N)]
    grid[7] = ["hello"]              # text -> dtype=float coercion fails -> bail
    b = RangeValue(grid)
    hot, cold = _both("AVERAGE", [a, b])
    assert hot == pytest.approx(cold)


def test_multirange_error_matches_stdlib(accel):
    from abax.core.errors import CellError

    a = _col(_N)
    grid = [[1.0] for _ in range(_N)]
    grid[9] = [CellError(CellError.DIV0)]
    b = RangeValue(grid)
    hot, cold = _both("SUM", [a, b])
    # stdlib propagates the first error; both paths agree on the error type.
    assert isinstance(hot, CellError) and isinstance(cold, CellError)
    assert hot.code == cold.code == CellError.DIV0


def test_multirange_empty_range_matches_stdlib(accel):
    # An empty grid pooled with a full one: numpy's _finite_array rejects the
    # size-0 block, so the whole multi-range call falls back to stdlib.
    a = _col(_N)
    empty = RangeValue([])
    hot, cold = _both("SUM", [a, empty])
    assert hot == pytest.approx(cold)
    assert cold == pytest.approx(float(sum(range(_N))))


def test_scalar_arg_not_accelerated_matches_stdlib(accel):
    # A bare number mixed with a range is pooled by stdlib in a specific order;
    # the accelerator only fires when *every* arg is a range, so this must match.
    a = _col(_N)
    hot, cold = _both("SUM", [a, 100.0])
    assert hot == pytest.approx(cold)
    assert cold == pytest.approx(float(sum(range(_N))) + 100.0)


# --- SUMPRODUCT -------------------------------------------------------------


def test_sumproduct_worked_example(accel):
    # {1,2,3} . {4,5,6} = 4 + 10 + 18 = 32 (Microsoft SUMPRODUCT reference).
    a = RangeValue([[1.0], [2.0], [3.0]])
    b = RangeValue([[4.0], [5.0], [6.0]])
    assert FUNCTIONS["SUMPRODUCT"]([a, b]) == pytest.approx(32.0)


def test_sumproduct_all_numeric_matches_stdlib(accel):
    a = _col(_N, lambda i: i * 0.5 - 1.0)
    b = _col(_N, lambda i: 2.0 - i * 0.1)
    c = _col(_N, lambda i: (i % 9) + 0.25)
    hot, cold = _both("SUMPRODUCT", [a, b, c])
    assert hot == pytest.approx(cold, rel=1e-12)


def test_sumproduct_hits_numpy_path():
    # Direct kernel check: equal-shaped finite ranges vectorize.
    a = _col(_N, lambda i: float(i))
    b = _col(_N, lambda i: 2.0)
    handled, val = npkernel.sumproduct([a, b])
    assert handled is True
    assert val == pytest.approx(2.0 * sum(range(_N)))


def test_sumproduct_blank_matches_stdlib(accel):
    a = _col(_N)
    grid = [[1.0] for _ in range(_N)]
    grid[4] = [None]                 # blank -> numpy bails, stdlib coerces to 0.0
    b = RangeValue(grid)
    hot, cold = _both("SUMPRODUCT", [a, b])
    assert hot == pytest.approx(cold)
    # stdlib treats the blank as 0.0, so that row drops out of the sum.
    expected = sum(i * (1.0 if i != 4 else 0.0) for i in range(_N))
    assert cold == pytest.approx(expected)


def test_sumproduct_text_matches_stdlib(accel):
    a = _col(_N)
    grid = [[1.0] for _ in range(_N)]
    grid[6] = ["x"]                  # text -> numpy bails, stdlib coerces to 0.0
    b = RangeValue(grid)
    hot, cold = _both("SUMPRODUCT", [a, b])
    assert hot == pytest.approx(cold)


def test_sumproduct_shape_mismatch_matches_stdlib(accel):
    from abax.core.errors import CellError

    a = _col(_N)
    b = _col(_N - 1)
    hot = FUNCTIONS["SUMPRODUCT"]([a, b])
    npkernel.register()
    hot2 = FUNCTIONS["SUMPRODUCT"]([a, b])
    # Mismatched flat lengths -> stdlib #VALUE!; the accelerator must not swallow it.
    assert isinstance(hot, CellError) and hot.code == CellError.VALUE
    assert isinstance(hot2, CellError) and hot2.code == CellError.VALUE


def test_sumproduct_empty_range_matches_stdlib(accel):
    # No ranges at all -> stdlib returns 0.0 and the accelerator never runs.
    assert FUNCTIONS["SUMPRODUCT"]([]) == pytest.approx(0.0)


def test_sumproduct_with_inline_array_matches_stdlib(accel):
    # An inline list among the args means len(ranges) != len(args): the accel is
    # skipped and stdlib (which ignores non-range args) runs. Result: SUM of a.
    a = _col(_N)
    hot, cold = _both("SUMPRODUCT", [a, [1.0, 2.0]])
    assert hot == pytest.approx(cold)
    assert cold == pytest.approx(float(sum(range(_N))))
