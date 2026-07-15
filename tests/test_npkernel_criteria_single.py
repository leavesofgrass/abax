"""Single-criterion numpy accelerator: SUMIF / COUNTIF / AVERAGEIF.

The ``*IF`` functions are ``*IFS`` with one (range, criterion) pair, so they now
route through the same numpy kernels the ``*IFS`` family uses (COUNTIF -> countifs,
SUMIF/AVERAGEIF -> sumifs/averageifs with the aligned value block). This file is
the differential guard: every formula runs twice -- once with the accelerator
registered (``npkernel.register()``), once through a forced-stdlib path
(``set_aggregate_accelerator(None)``) -- and the two are asserted equal, so the
numpy path can never change a result. The accelerator only enters for a *numeric*
criterion over a finite-numeric block big enough to clear ``_ACCEL_MIN_CELLS``;
text, wildcard, bool, blank/text/error cells and small ranges all fall to the
exact stdlib loop, which those cases assert against directly.

Oracle values are the plain Excel definitions -- COUNTIF counts cells matching the
criterion, SUMIF sums the aligned sum_range over them (the criteria range itself
when sum_range is omitted), AVERAGEIF averages them (#DIV/0! when none match) --
derived arithmetically from the computed ranges, independent of either code path.
"""

from __future__ import annotations

import pytest

from abax import _runtime
from abax.core.errors import CellError
from abax.core.functions import FUNCTIONS
from abax.core.values import RangeValue

np = pytest.importorskip("numpy")

from abax.engine import npkernel  # noqa: E402

# Clears _ACCEL_MIN_CELLS (4096) in abax.core.functions.builtins, so the numpy
# path is genuinely entered (then reduces or bails per the case).
_N = 5000


@pytest.fixture()
def accel():
    """Register the numpy accelerator for the test, then clear the slot."""
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


def _err(x):
    return isinstance(x, CellError)


# --- numeric criteria: numpy path == forced-stdlib path (and == oracle) -----


def test_countif_numeric_matches_stdlib(accel):
    crit = _col(_N)                                   # 0..N-1
    hot, cold = _both("COUNTIF", [crit, ">5"])
    assert hot == cold
    assert cold == pytest.approx(float(_N - 6))


def test_countif_equality_and_inequality(accel):
    crit = _col(_N)
    hot_eq, cold_eq = _both("COUNTIF", [crit, "=3"])
    hot_ne, cold_ne = _both("COUNTIF", [crit, "<>3"])
    assert hot_eq == cold_eq == pytest.approx(1.0)
    assert hot_ne == cold_ne == pytest.approx(float(_N - 1))


def test_sumif_without_sum_range_sums_the_criteria_values(accel):
    # SUMIF(range, ">5") with no sum_range sums the criteria range itself.
    crit = _col(_N)
    hot, cold = _both("SUMIF", [crit, ">5"])
    assert hot == pytest.approx(cold, rel=1e-12)
    assert cold == pytest.approx(sum(i for i in range(_N) if i > 5), rel=1e-12)


def test_sumif_with_sum_range_matches_stdlib(accel):
    # sum_range = 2*i; criterion i>5 keeps i in 6..N-1.
    crit = _col(_N)
    sums = _col(_N, lambda i: 2.0 * i)
    hot, cold = _both("SUMIF", [crit, ">5", sums])
    assert hot == pytest.approx(cold, rel=1e-12)
    assert cold == pytest.approx(sum(2.0 * i for i in range(_N) if i > 5), rel=1e-12)


def test_averageif_matches_stdlib(accel):
    crit = _col(_N)
    vals = _col(_N, lambda i: 3.0 * i)
    hot, cold = _both("AVERAGEIF", [crit, ">=" + str(_N - 4), vals])
    assert hot == pytest.approx(cold, rel=1e-12)
    top = [3.0 * i for i in range(_N - 4, _N)]
    assert cold == pytest.approx(sum(top) / len(top), rel=1e-12)


def test_averageif_no_match_is_div0_both_paths(accel):
    crit = _col(_N)
    vals = _col(_N)
    hot, cold = _both("AVERAGEIF", [crit, ">" + str(_N + 1000), vals])
    assert _err(hot) and _err(cold)
    assert hot.code == cold.code == CellError.DIV0


def test_bool_cells_in_range_agree(accel):
    # A finite-numeric block that contains booleans: numpy coerces True/False to
    # 1.0/0.0 and stdlib's numeric predicate tests them the same way, so ">0"
    # must count identically on both paths (the subtle equivalence).
    grid = [[float(i)] for i in range(_N)]
    grid[0] = [True]
    grid[1] = [False]
    grid[2] = [True]
    crit = RangeValue(grid)
    hot, cold = _both("COUNTIF", [crit, ">0"])
    assert hot == cold


# --- fallbacks: text / wildcard / dirty cells force the exact stdlib loop ----


def test_text_criterion_uses_stdlib(accel):
    grid = [[float(i)] for i in range(_N)]
    grid[10] = ["apple"]
    grid[20] = ["apple"]
    crit = RangeValue(grid)
    hot, cold = _both("COUNTIF", [crit, "apple"])
    assert hot == cold
    assert cold == pytest.approx(2.0)


def test_wildcard_criterion_uses_stdlib(accel):
    grid = [[float(i)] for i in range(_N)]
    grid[1] = ["apple"]
    grid[2] = ["apricot"]
    grid[3] = ["banana"]
    crit = RangeValue(grid)
    hot, cold = _both("COUNTIF", [crit, "a*"])
    assert hot == cold
    assert cold == pytest.approx(2.0)


def test_numeric_criterion_over_blanky_range_uses_stdlib(accel):
    # A blank makes _finite_array reject the block (NaN) -> stdlib loop, which
    # skips the blank (never > 5 anyway).
    grid = [[float(i)] for i in range(_N)]
    grid[7] = [None]
    crit = RangeValue(grid)
    hot, cold = _both("COUNTIF", [crit, ">5"])
    assert hot == cold
    assert cold == pytest.approx(float(sum(1 for i in range(_N) if i != 7 and i > 5)))


def test_sumif_dirty_sum_range_uses_stdlib(accel):
    # Clean numeric criteria, but a text cell in the sum_range forces the stdlib
    # loop, which coerces that matched text cell to 0.0.
    crit = _col(_N)
    sgrid = [[1.0] for _ in range(_N)]
    sgrid[8] = ["not a number"]          # i=8 satisfies ">5" but is text -> 0.0
    sums = RangeValue(sgrid)
    hot, cold = _both("SUMIF", [crit, ">5", sums])
    assert hot == pytest.approx(cold, rel=1e-12)
    assert cold == pytest.approx(float(sum(1 for i in range(_N) if i > 5) - 1))


def test_error_cell_in_range_uses_stdlib(accel):
    grid = [[float(i)] for i in range(_N)]
    grid[5] = [CellError(CellError.DIV0)]
    crit = RangeValue(grid)
    hot, cold = _both("COUNTIF", [crit, ">5"])
    assert hot == cold
    assert cold == pytest.approx(float(sum(1 for i in range(_N) if i != 5 and i > 5)))


def test_mismatched_sum_range_length_uses_stdlib(accel):
    # sum_range shorter than the criteria range: the kernel's equal-length gate
    # bails, and the stdlib zip truncates to the shorter -> both agree.
    crit = _col(_N)
    sums = _col(_N - 100, lambda i: 2.0 * i)
    hot, cold = _both("SUMIF", [crit, ">5", sums])
    assert hot == pytest.approx(cold, rel=1e-12)
    # zip stops at N-100; only i in 6..N-101 both match and have a sum value.
    assert cold == pytest.approx(sum(2.0 * i for i in range(6, _N - 100)), rel=1e-12)


# --- below the threshold: small ranges stay on the stdlib loop ---------------


def test_small_range_below_threshold_is_correct(accel):
    # Under _ACCEL_MIN_CELLS the accelerator is never offered; the result must
    # still be the plain stdlib one.
    crit = _col(100)
    hot, cold = _both("COUNTIF", [crit, ">5"])
    assert hot == cold
    assert cold == pytest.approx(float(100 - 6))


def test_accelerator_disabled_no_crash():
    # Slot cleared (numpy absent, or present-but-unregistered): stdlib results.
    _runtime.set_aggregate_accelerator(None)
    crit = _col(_N)
    sums = _col(_N, lambda i: 2.0 * i)
    assert FUNCTIONS["COUNTIF"]([crit, ">5"]) == pytest.approx(float(_N - 6))
    assert FUNCTIONS["SUMIF"]([crit, ">5", sums]) == pytest.approx(
        sum(2.0 * i for i in range(_N) if i > 5), rel=1e-12
    )
    assert FUNCTIONS["AVERAGEIF"]([crit, ">=" + str(_N - 4), crit]) == pytest.approx(
        sum(range(_N - 4, _N)) / 4.0, rel=1e-12
    )
