"""Optional numpy aggregate accelerator: identical results, safe fallbacks."""

from __future__ import annotations

import pytest

from abax import _runtime
from abax.core.functions import FUNCTIONS
from abax.core.values import RangeValue

np = pytest.importorskip("numpy")

from abax.engine import npkernel  # noqa: E402


@pytest.fixture()
def accel():
    npkernel.register()
    try:
        yield
    finally:
        _runtime.set_aggregate_accelerator(None)


def _col(n, f=lambda i: float(i)):
    return RangeValue([[f(i)] for i in range(n)])


def test_accelerated_matches_stdlib(accel):
    n = 5000
    rv = _col(n, lambda i: i * 0.5 - 7.0)
    _runtime.set_aggregate_accelerator(None)
    ref_sum = FUNCTIONS["SUM"]([rv])
    ref_avg = FUNCTIONS["AVERAGE"]([rv])
    npkernel.register()
    assert FUNCTIONS["SUM"]([rv]) == pytest.approx(ref_sum, rel=1e-12)
    assert FUNCTIONS["AVERAGE"]([rv]) == pytest.approx(ref_avg, rel=1e-12)
    assert FUNCTIONS["COUNT"]([rv]) == float(n)
    assert FUNCTIONS["MIN"]([rv]) == pytest.approx(-7.0)
    assert FUNCTIONS["MAX"]([rv]) == pytest.approx((n - 1) * 0.5 - 7.0)
    assert FUNCTIONS["PRODUCT"]([_col(5000, lambda i: 1.0)]) == 1.0


def test_reduce_range_ops_direct():
    rv = _col(5000)
    for op, expect in (("sum", sum(range(5000))),
                       ("count", 5000.0),
                       ("min", 0.0),
                       ("max", 4999.0)):
        handled, val = npkernel.reduce_range(rv, op)
        assert handled is True
        assert val == pytest.approx(expect)


def test_falls_back_on_text(accel):
    grid = [[1.0] for _ in range(5000)]
    grid[100] = ["not a number"]
    rv = RangeValue(grid)
    handled, _ = npkernel.reduce_range(rv, "sum")
    assert handled is False                          # text -> not handled
    assert FUNCTIONS["SUM"]([rv]) == pytest.approx(4999.0)   # stdlib skips it


def test_falls_back_on_blank_none(accel):
    grid = [[1.0] for _ in range(5000)]
    grid[50] = [None]
    rv = RangeValue(grid)
    handled, _ = npkernel.reduce_range(rv, "sum")
    assert handled is False                          # None -> NaN -> not handled
    assert FUNCTIONS["SUM"]([rv]) == pytest.approx(4999.0)


def test_falls_back_on_error_value(accel):
    from abax.core.errors import CellError

    grid = [[1.0] for _ in range(5000)]
    grid[10] = [CellError(CellError.DIV0)]
    rv = RangeValue(grid)
    handled, _ = npkernel.reduce_range(rv, "sum")
    assert handled is False
    assert isinstance(FUNCTIONS["SUM"]([rv]), CellError)   # stdlib propagates it


def test_below_threshold_not_accelerated(accel):
    rv = _col(10)
    assert FUNCTIONS["SUM"]([rv]) == pytest.approx(sum(range(10)))


def test_bools_count_as_one_and_zero():
    rv = RangeValue([[True] for _ in range(2000)] + [[False] for _ in range(3000)])
    handled, val = npkernel.reduce_range(rv, "sum")
    assert handled is True and val == pytest.approx(2000.0)


def test_engine_import_registers_accelerator():
    import importlib

    import abax.engine
    importlib.reload(abax.engine)
    assert _runtime.aggregate_accelerator() is npkernel.reduce_range
    _runtime.set_aggregate_accelerator(None)
