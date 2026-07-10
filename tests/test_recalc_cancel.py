"""Cancellable / progress-reporting recalc (large-sheet responsiveness).

The plain recalc and the callback recalc must produce identical results; a
cancelled recalc stops partway, stays dirty, and can be resumed.
"""

from __future__ import annotations

from abax.core.workbook import RecalcCancelled, Workbook


def _chain(n: int) -> Workbook:
    """A1=1, A2=A1+1, ... An=A(n-1)+1 — a dependency chain of length n."""
    wb = Workbook()
    s = wb.sheet
    s.set_cell(0, 0, "1")
    for r in range(1, n):
        s.set_cell(r, 0, f"=A{r}+1")
    return wb


def test_progress_recalc_matches_plain_recalc():
    wb = _chain(20)
    wb.recalculate()  # plain
    plain = [wb.sheet.get_value(r, 0) for r in range(20)]

    wb2 = _chain(20)
    seen = []
    ok = wb2.recalculate(progress=lambda done, total: seen.append((done, total)))
    assert ok is True
    withcb = [wb2.sheet.get_value(r, 0) for r in range(20)]
    assert withcb == plain == [float(i + 1) for i in range(20)]
    # A final 100% progress call always fires.
    assert seen and seen[-1][0] == seen[-1][1]


def test_cancel_stops_and_marks_dirty():
    wb = _chain(50)
    calls = {"n": 0}

    def should_cancel():
        calls["n"] += 1
        return calls["n"] > 5  # cancel after a few cells

    ok = wb.recalculate(should_cancel=should_cancel)
    assert ok is False
    assert wb._calc_dirty is True  # partial recompute stays dirty
    # A subsequent full recalc completes and clears dirty.
    assert wb.recalculate() is True
    assert wb._calc_dirty is False
    assert wb.sheet.get_value(49, 0) == 50.0


def test_no_callbacks_is_the_fast_path():
    wb = _chain(10)
    assert wb.recalculate() is True  # returns True, no exceptions
    assert wb.sheet.get_value(9, 0) == 10.0


def test_should_cancel_never_true_completes():
    wb = _chain(15)
    ok = wb.recalculate(should_cancel=lambda: False,
                        progress=lambda d, t: None)
    assert ok is True
    assert wb._calc_dirty is False
    assert wb.sheet.get_value(14, 0) == 15.0


def test_recalc_cancelled_exception_from_sheet_directly():
    wb = _chain(10)
    import pytest

    with pytest.raises(RecalcCancelled):
        wb.sheet.recalculate(should_cancel=lambda: True)
