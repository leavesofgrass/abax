"""Widened numpy accelerator: the criteria family (COUNTIFS/SUMIFS/AVERAGEIFS).

Every formula is run twice -- once with the numpy accelerator registered
(``npkernel.register()``) and once through a forced-stdlib path
(``set_aggregate_accelerator(None)``) -- and the two are asserted equal, so the
accelerator can never change a result. The accelerator only enters when every
criteria/value range is finite-numeric AND every criterion is a *numeric*
comparison; the fallback cases (a text criterion, a wildcard, a blank/text cell,
an empty range) must therefore return exactly what the stdlib loop does.

Oracle values are the plain Excel definitions of the conditional aggregates --
COUNTIFS counts the cells where every criterion holds, SUMIFS sums the aligned
sum_range over those cells, AVERAGEIFS averages them (and #DIV/0! when none match)
-- see Microsoft's "COUNTIFS", "SUMIFS" and "AVERAGEIFS function" references. Here
the criteria ranges are computed sequences, so the expected counts/sums are
derived arithmetically from those same definitions and checked independently of
either code path.
"""

from __future__ import annotations

import pytest

from abax import _runtime
from abax.core.errors import CellError
from abax.core.functions import FUNCTIONS
from abax.core.values import RangeValue

np = pytest.importorskip("numpy")

from abax.engine import npkernel  # noqa: E402

# Big enough that the criteria pool clears _ACCEL_MIN_CELLS (4096) in
# abax.core.stats_dist, so the numpy path is genuinely entered (then either
# reduces or bails, depending on the case).
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


def test_countifs_single_numeric_matches_stdlib(accel):
    # crit range is 0..N-1; ">5" selects i in 6..N-1 -> N-6 cells.
    crit = _col(_N)
    hot, cold = _both("COUNTIFS", [crit, ">5"])
    assert hot == cold
    assert cold == pytest.approx(float(_N - 6))


def test_countifs_two_numeric_criteria_matches_stdlib(accel):
    # A range 0..N-1 with two ANDed bounds: ">=10" and "<20" -> exactly 10 cells.
    crit = _col(_N)
    hot, cold = _both("COUNTIFS", [crit, ">=10", crit, "<20"])
    assert hot == cold
    assert cold == pytest.approx(10.0)


def test_countifs_equality_and_inequality(accel):
    # "=3" hits one cell; "<>3" hits the rest.
    crit = _col(_N)
    hot_eq, cold_eq = _both("COUNTIFS", [crit, "=3"])
    hot_ne, cold_ne = _both("COUNTIFS", [crit, "<>3"])
    assert hot_eq == cold_eq == pytest.approx(1.0)
    assert hot_ne == cold_ne == pytest.approx(float(_N - 1))


def test_sumifs_numeric_matches_stdlib(accel):
    # sum_range = 2*i; crit = i; ">5" keeps i in 6..N-1: sum of 2*i over that set.
    crit = _col(_N)
    sums = _col(_N, lambda i: 2.0 * i)
    hot, cold = _both("SUMIFS", [sums, crit, ">5"])
    assert hot == pytest.approx(cold, rel=1e-12)
    expected = sum(2.0 * i for i in range(_N) if i > 5)
    assert cold == pytest.approx(expected, rel=1e-12)


def test_sumifs_two_criteria_windowed_sum(accel):
    # Window 100 <= i < 110 over sum_range i*i -> sum of i*i on that window.
    crit = _col(_N)
    sq = _col(_N, lambda i: float(i) * float(i))
    hot, cold = _both("SUMIFS", [sq, crit, ">=100", crit, "<110"])
    assert hot == pytest.approx(cold, rel=1e-12)
    expected = sum(float(i) * float(i) for i in range(100, 110))
    assert cold == pytest.approx(expected, rel=1e-12)


def test_averageifs_numeric_matches_stdlib(accel):
    # avg over i where i >= N-4 (the top four): mean of {N-4, N-3, N-2, N-1}.
    crit = _col(_N)
    vals = _col(_N)
    hot, cold = _both("AVERAGEIFS", [vals, crit, ">=" + str(_N - 4)])
    assert hot == pytest.approx(cold, rel=1e-12)
    top = [float(i) for i in range(_N - 4, _N)]
    assert cold == pytest.approx(sum(top) / len(top), rel=1e-12)


def test_averageifs_no_match_is_div0_both_paths(accel):
    # A criterion no cell satisfies -> #DIV/0! from the numpy path *and* stdlib.
    crit = _col(_N)
    vals = _col(_N)
    hot, cold = _both("AVERAGEIFS", [vals, crit, ">" + str(_N + 1000)])
    assert _err(hot) and _err(cold)
    assert hot.code == cold.code == CellError.DIV0


# --- fallbacks: text / wildcard / dirty cells force the exact stdlib loop ----


def test_text_criterion_uses_stdlib(accel):
    # A text equality is not numeric-vectorisable: numeric_criterion -> None, so
    # the accelerator is skipped and the pure-Python predicate loop runs. Sprinkle
    # matching text through an otherwise-numeric-looking range and count it.
    grid = [[float(i)] for i in range(_N)]
    grid[10] = ["apple"]
    grid[20] = ["apple"]
    crit = RangeValue(grid)
    hot, cold = _both("COUNTIFS", [crit, "apple"])
    assert hot == cold
    assert cold == pytest.approx(2.0)


def test_wildcard_criterion_uses_stdlib(accel):
    # "a*" is a wildcard match -> stdlib. Two cells begin with 'a'.
    grid = [[float(i)] for i in range(_N)]
    grid[1] = ["apple"]
    grid[2] = ["apricot"]
    grid[3] = ["banana"]
    crit = RangeValue(grid)
    hot, cold = _both("COUNTIFS", [crit, "a*"])
    assert hot == cold
    assert cold == pytest.approx(2.0)


def test_numeric_criterion_over_blanky_range_uses_stdlib(accel):
    # A numeric criterion, but the criteria block has a blank -> _finite_array
    # rejects it (NaN), the kernel bails, and the exact stdlib loop runs. The
    # blank never satisfies ">5", so the count is unchanged from an all-numeric
    # block minus the blanked cell.
    grid = [[float(i)] for i in range(_N)]
    grid[7] = [None]                 # blank inside the criteria range
    crit = RangeValue(grid)
    hot, cold = _both("COUNTIFS", [crit, ">5"])
    assert hot == cold
    # i>5 for i in 6..N-1 except the blanked i=7 (which is None, not > 5 anyway).
    expected = sum(1 for i in range(_N) if i != 7 and i > 5)
    assert cold == pytest.approx(float(expected))


def test_sumifs_dirty_sum_range_uses_stdlib(accel):
    # Clean numeric criteria (so the mask *could* build), but a text cell in the
    # sum_range makes _finite_array reject it -> kernel bails -> stdlib, which
    # skips the text cell. The masked text row must contribute nothing.
    crit = _col(_N)
    sgrid = [[1.0] for _ in range(_N)]
    sgrid[8] = ["not a number"]      # i=8 satisfies ">5" but is text -> skipped
    sums = RangeValue(sgrid)
    hot, cold = _both("SUMIFS", [sums, crit, ">5"])
    assert hot == pytest.approx(cold, rel=1e-12)
    # 1.0 for every i in 6..N-1 except i=8 (text -> not summed).
    expected = float(sum(1 for i in range(_N) if i > 5) - 1)
    assert cold == pytest.approx(expected)


def test_mixed_error_cell_in_criteria_uses_stdlib(accel):
    # An error object in the criteria block -> not finite-numeric -> stdlib.
    grid = [[float(i)] for i in range(_N)]
    grid[5] = [CellError(CellError.DIV0)]
    crit = RangeValue(grid)
    hot, cold = _both("COUNTIFS", [crit, ">5"])
    assert hot == cold
    # The error cell doesn't satisfy the numeric predicate either.
    expected = sum(1 for i in range(_N) if i != 5 and i > 5)
    assert cold == pytest.approx(float(expected))


def test_ragged_criteria_ranges_are_value_error_both_paths(accel):
    # Two criteria ranges of different lengths -> stdlib #VALUE!; the kernel's
    # equal-length gate makes it bail rather than swallow the mismatch.
    a = _col(_N)
    b = _col(_N - 1)
    hot, cold = _both("COUNTIFS", [a, ">0", b, ">0"])
    assert _err(hot) and _err(cold)
    assert hot.code == cold.code == CellError.VALUE


# --- empty ranges -----------------------------------------------------------


def test_empty_criteria_range_matches_stdlib(accel):
    # An empty grid: stdlib COUNTIFS over a zero-length range is 0.0; the kernel's
    # _finite_array rejects the size-0 block and bails to that same stdlib result.
    empty = RangeValue([])
    hot, cold = _both("COUNTIFS", [empty, ">5"])
    assert hot == cold
    assert cold == pytest.approx(0.0)


def test_empty_sumifs_matches_stdlib(accel):
    empty = RangeValue([])
    hot, cold = _both("SUMIFS", [empty, empty, ">5"])
    assert hot == cold
    assert cold == pytest.approx(0.0)


# --- direct kernel checks ---------------------------------------------------


def test_kernel_countifs_hits_numpy_path(accel):
    # Direct: finite-numeric block + numeric op vectorizes; value is the count.
    grid = [[float(i)] for i in range(_N)]
    handled, val = npkernel.countifs([grid], [(">", 5.0)])
    assert handled is True
    assert val == pytest.approx(float(_N - 6))


def test_kernel_sumifs_hits_numpy_path(accel):
    cgrid = [[float(i)] for i in range(_N)]
    vgrid = [[2.0 * i] for i in range(_N)]
    handled, val = npkernel.sumifs(vgrid, [cgrid], [(">", 5.0)])
    assert handled is True
    assert val == pytest.approx(sum(2.0 * i for i in range(_N) if i > 5), rel=1e-12)


def test_kernel_bails_on_text_block(accel):
    grid = [[float(i)] for i in range(_N)]
    grid[3] = ["text"]
    handled, val = npkernel.countifs([grid], [(">", 5.0)])
    assert handled is False
    assert val is None


def test_kernel_averageifs_no_match_signals_div0(accel):
    grid = [[float(i)] for i in range(_N)]
    handled, val = npkernel.averageifs(grid, [grid], [(">", float(_N + 10))])
    # No cell matches -> handled True but value None (caller maps to #DIV/0!).
    assert handled is True
    assert val is None


def test_accelerator_disabled_no_crash():
    # With the slot cleared, the *IFS functions must still return correct stdlib
    # results (this is the CI thin-env default: numpy present but slot unset, or
    # numpy absent entirely).
    _runtime.set_aggregate_accelerator(None)
    crit = _col(_N)
    sums = _col(_N, lambda i: 2.0 * i)
    assert FUNCTIONS["COUNTIFS"]([crit, ">5"]) == pytest.approx(float(_N - 6))
    assert FUNCTIONS["SUMIFS"]([sums, crit, ">5"]) == pytest.approx(
        sum(2.0 * i for i in range(_N) if i > 5), rel=1e-12
    )
