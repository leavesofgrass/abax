"""Manual vs automatic calculation mode.

In auto mode (default) an edit recomputes dependents immediately via the
incremental dependency graph. In manual mode dependent recalculation is deferred
until :meth:`Workbook.recalculate` (the GUI's F9) — the escape hatch for very
large/slow sheets. The edited cell itself still reflects its new content; its
dependents keep their last-calculated values until the recalc.
"""

from __future__ import annotations

import pytest

from abax.core.workbook import Workbook


def _wb():
    wb = Workbook()
    s = wb.sheets[0]
    s.set("A1", "1")
    s.set("B1", "=A1*2")
    s.set("C1", "=B1+A1")
    assert (s.get("A1"), s.get("B1"), s.get("C1")) == (1, 2.0, 3.0)
    return wb, s


def test_auto_is_default_and_live():
    wb, s = _wb()
    assert wb.calc_mode == "auto"
    s.set("A1", "9")
    assert (s.get("B1"), s.get("C1")) == (18.0, 27.0)


def test_manual_defers_dependent_recalc():
    wb, s = _wb()
    wb.set_calc_mode("manual")
    s.set("A1", "10")
    # The edited cell reflects its new content immediately...
    assert s.get("A1") == 10
    # ...but dependents keep their last-calculated (now stale) values.
    assert s.get("B1") == 2.0
    assert s.get("C1") == 3.0
    assert wb._calc_dirty is True
    # F9 — a full recalc brings everything current and clears the dirty flag.
    wb.recalculate()
    assert (s.get("B1"), s.get("C1")) == (20.0, 30.0)
    assert wb._calc_dirty is False


def test_switch_back_to_auto_forces_recompute():
    wb, s = _wb()
    wb.set_calc_mode("manual")
    s.set("A1", "5")
    assert s.get("B1") == 2.0  # stale while manual
    wb.set_calc_mode("auto")   # switching to auto flushes the deferred edits
    assert (s.get("B1"), s.get("C1")) == (10.0, 15.0)
    assert wb._calc_dirty is False


def test_edits_after_auto_are_live_again():
    wb, s = _wb()
    wb.set_calc_mode("manual")
    s.set("A1", "5")
    wb.set_calc_mode("auto")
    s.set("A1", "7")               # a normal live edit
    assert (s.get("B1"), s.get("C1")) == (14.0, 21.0)


def test_invalid_mode_rejected():
    wb, _ = _wb()
    with pytest.raises(ValueError):
        wb.set_calc_mode("sometimes")


def test_manual_uncached_dependent_still_computes():
    # A dependent that was never read has no cached value; in manual mode reading
    # it computes against current inputs (there's nothing stale to preserve).
    wb = Workbook()
    s = wb.sheets[0]
    s.set("A1", "3")
    wb.set_calc_mode("manual")
    s.set("B1", "=A1*4")   # first ever read below
    assert s.get("B1") == 12.0
