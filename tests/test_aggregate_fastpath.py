"""The fused aggregate fast-path (`_numbers_checked`) must be byte-for-byte
equivalent to the old ``_flatten`` + ``_first_error`` + ``_numbers_from`` chain,
and no slower on a large range.

This pins the "exact Excel SUM/AVERAGE semantics" guarantee: `_numbers_checked`
walks a range once and builds only the numeric list, but the numbers it keeps and
the first error it reports are identical to the reference composition over the
same arguments.
"""

from __future__ import annotations

import random
import time

from abax.core.errors import CellError
from abax.core.functions import (
    _first_error,
    _flatten,
    _numbers_checked,
    _numbers_from,
)
from abax.core.values import RangeValue


def _reference(args):
    """The pre-fast-path behaviour: flatten, then scan for error + numbers."""
    flat = _flatten(args)
    return _first_error(flat), _numbers_from(flat)


def _random_leaf(rng: random.Random):
    pick = rng.random()
    if pick < 0.45:
        return rng.randint(-1000, 1000)
    if pick < 0.65:
        return rng.uniform(-1e3, 1e3)
    if pick < 0.75:
        return rng.choice([True, False])
    if pick < 0.85:
        return rng.choice(["", "x", "text", None])
    if pick < 0.92:
        return CellError(rng.choice([CellError.DIV0, CellError.NA, CellError.VALUE]))
    return None


def _random_range(rng: random.Random) -> RangeValue:
    rows = rng.randint(1, 5)
    cols = rng.randint(1, 4)
    return RangeValue([[_random_leaf(rng) for _ in range(cols)] for _ in range(rows)])


def _random_args(rng: random.Random):
    args = []
    for _ in range(rng.randint(1, 4)):
        kind = rng.random()
        if kind < 0.5:
            args.append(_random_range(rng))
        elif kind < 0.75:
            args.append([_random_leaf(rng) for _ in range(rng.randint(0, 4))])
        else:
            args.append(_random_leaf(rng))
    return args


def test_numbers_checked_matches_reference_over_random_args():
    rng = random.Random(20260630)
    for _ in range(2000):
        args = _random_args(rng)
        ref_err, ref_nums = _reference(args)
        err, nums = _numbers_checked(args)
        assert nums == ref_nums
        # first error is the same object identity / code, in the same flatten order
        assert (err is None) == (ref_err is None)
        if err is not None:
            assert err.code == ref_err.code
            assert err is ref_err


def test_numbers_checked_first_error_is_first_in_flatten_order():
    e1 = CellError(CellError.DIV0)
    e2 = CellError(CellError.NA)
    args = [RangeValue([[1, e1], [e2, 2]])]
    err, nums = _numbers_checked(args)
    assert err is e1            # row-major: e1 precedes e2
    assert nums == [1.0, 2.0]


def test_numbers_checked_bool_and_blank_rules():
    args = [RangeValue([[True, False, None, "", "txt", 3, 2.5]])]
    err, nums = _numbers_checked(args)
    assert err is None
    assert nums == [1.0, 0.0, 3.0, 2.5]   # bools count as 1/0; text/blank skipped


def test_fastpath_not_slower_on_large_range():
    n = 100_000
    grid = [[float(i)] for i in range(n)]
    args = [RangeValue(grid)]

    def timed(fn) -> float:
        best = float("inf")
        for _ in range(3):
            t0 = time.perf_counter()
            fn()
            best = min(best, time.perf_counter() - t0)
        return best

    fused = timed(lambda: _numbers_checked(args))
    ref = timed(lambda: _reference(args))

    # identical numeric result
    assert _numbers_checked(args)[1] == _numbers_from(_flatten(args))
    # the fused walk does strictly less work (one list, one pass); allow generous
    # head-room for timer noise but it must not be materially slower.
    assert fused <= ref * 1.5
