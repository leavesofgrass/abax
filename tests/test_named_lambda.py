"""Formula-valued / named-LAMBDA defined names.

A defined name whose target starts with ``=`` holds a formula (or a LAMBDA)
instead of a cell/range. ``=MYPI`` splices the body; ``=SQ(A1)`` calls a
LAMBDA-valued name. Round-trips through the JSON envelope with no schema change
(the target is just an ``=``-prefixed string).
"""

from __future__ import annotations

import pytest

from abax.core.errors import CellError
from abax.core.names import NameError as AbaxNameError
from abax.core.names import NameRegistry, normalize_target
from abax.core.workbook import Workbook


def _wb():
    wb = Workbook()
    s = wb.sheet
    s.set("A1", "4")
    s.set("A2", "10")
    s.set("A3", "6")
    return wb, s


def test_formula_constant_name():
    wb, s = _wb()
    wb.names.define("MYPI", "=2*PI()")
    s.set("B1", "=MYPI")
    assert s.get_value(0, 1) == pytest.approx(6.283185307, rel=1e-6)


def test_lambda_name_called_with_literal_and_cell():
    wb, s = _wb()
    wb.names.define("SQ", "=LAMBDA(x, x*x)")
    s.set("B2", "=SQ(5)")
    s.set("B3", "=SQ(A1)")
    assert s.get_value(1, 1) == 25.0
    assert s.get_value(2, 1) == 16.0


def test_formula_name_over_a_range_and_nesting():
    wb, s = _wb()
    wb.names.define("TOTAL", "=SUM(A1:A3)")
    wb.names.define("ADD", "=LAMBDA(a, b, a+b)")
    wb.names.define("SQ", "=LAMBDA(x, x*x)")
    s.set("B4", "=TOTAL*2")
    s.set("B5", "=ADD(SQ(3), TOTAL)")
    assert s.get_value(3, 1) == 40.0            # (4+10+6)*2
    assert s.get_value(4, 1) == 29.0            # 9 + 20


def test_cyclic_formula_name_is_name_error_not_a_hang():
    wb, s = _wb()
    wb.names.define("REC", "=REC+1")
    s.set("B6", "=REC")
    v = s.get_value(5, 1)
    assert isinstance(v, CellError) and v.code == CellError.NAME


def test_envelope_round_trip_preserves_formula_names():
    wb, s = _wb()
    wb.names.define("SQ", "=LAMBDA(x, x*x)")
    wb.names.define("MYPI", "=2*PI()")
    s.set("B3", "=SQ(A1)")
    wb2 = Workbook.from_envelope(wb.to_envelope())
    assert wb2.names.lookup("SQ") == "=LAMBDA(x, x*x)"
    assert wb2.names.lookup("MYPI") == "=2*PI()"
    assert wb2.sheet.get_value(2, 1) == 16.0


def test_normalize_target_accepts_formula_rejects_garbage():
    assert normalize_target("=LAMBDA(x, x*x)") == "=LAMBDA(x, x*x)"
    assert normalize_target("  =2*PI() ") == "=2*PI()"
    assert normalize_target("A1:C3") == "A1:C3"
    with pytest.raises(AbaxNameError):
        normalize_target("=this is (not a formula")


def test_registry_dict_round_trip_with_formula_target():
    reg = NameRegistry()
    reg.define("SQ", "=LAMBDA(x, x*x)")
    reg.define("VALS", "A1:A10")
    reg2 = NameRegistry.from_dict(reg.to_dict())
    assert reg2.lookup("SQ") == "=LAMBDA(x, x*x)"
    assert reg2.lookup("VALS") == "A1:A10"
