"""Iterative calculation — capped fixed-point resolution of circular references.

Off by default (circular reads are #CIRC!); when enabled, an explicit
``recalculate_iterative()`` sweep settles convergent cycles and caps divergent
ones. Normal evaluation is unchanged.
"""

from __future__ import annotations

from abax.core.errors import CellError
from abax.core.workbook import Workbook


def test_circular_is_circ_by_default():
    wb = Workbook()
    wb.sheet.set("A1", "=(A1+10)/2")
    v = wb.sheet.get_value(0, 0)
    assert isinstance(v, CellError) and v.code == CellError.CIRC


def test_convergent_self_reference():
    wb = Workbook()
    wb.calc_iterative = True
    wb.sheet.set("A1", "=(A1+10)/2")  # x = (x+10)/2 -> 10
    iterations, converged = wb.recalculate_iterative()
    assert converged
    assert abs(wb.sheet.get_value(0, 0) - 10.0) <= wb.calc_max_change * 2


def test_convergent_two_cell_cycle():
    wb = Workbook()
    wb.calc_iterative = True
    s = wb.sheet
    s.set("A1", "10")
    s.set("B1", "=A1+C1")
    s.set("C1", "=0.5*B1")           # B1 = 10 + 0.5*B1 -> 20 ; C1 -> 10
    _iters, converged = wb.recalculate_iterative()
    assert converged
    assert abs(s.get_value(0, 1) - 20.0) < 0.05
    assert abs(s.get_value(0, 2) - 10.0) < 0.05


def test_divergent_caps_without_converging():
    wb = Workbook()
    wb.calc_iterative = True
    wb.calc_max_iterations = 40
    wb.sheet.set("A1", "=A1+1")       # never settles
    iterations, converged = wb.recalculate_iterative()
    assert not converged and iterations == 40


def test_cycle_free_settles_quickly():
    wb = Workbook()
    wb.calc_iterative = True
    s = wb.sheet
    s.set("A1", "5")
    s.set("A2", "=A1*2")
    iterations, converged = wb.recalculate_iterative()
    assert converged and iterations <= 2
    assert s.get_value(1, 0) == 10


def test_respects_explicit_caps():
    wb = Workbook()
    wb.calc_iterative = True
    wb.sheet.set("A1", "=(A1+10)/2")
    iters, _conv = wb.recalculate_iterative(max_iterations=3, max_change=1e-9)
    assert iters == 3  # tight tolerance -> runs to the (small) cap
