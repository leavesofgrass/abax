"""Named ranges resolving in formulas + validation/name envelope persistence."""

from __future__ import annotations

from abax.core.validation import list_rule, number_rule
from abax.core.workbook import Workbook


def _wb():
    wb = Workbook()
    s = wb.sheet
    for i, v in enumerate([10, 20, 30], 1):
        s.set(f"A{i}", str(v))
    return wb, s


def test_named_range_in_formula():
    wb, s = _wb()
    wb.names.define("Vals", "A1:A3")
    wb.names.define("Tax", "A1")
    s.set("B1", "=SUM(Vals)")
    s.set("B2", "=Tax*2")
    s.set("B3", "=AVERAGE(Vals)")
    wb.invalidate_caches()
    assert s.get("B1") == 60.0
    assert s.get("B2") == 20.0
    assert s.get("B3") == 20.0


def test_name_redefine_and_remove_reevaluate():
    wb, s = _wb()
    wb.names.define("X", "A1")
    s.set("B1", "=X+1")
    wb.invalidate_caches()
    assert s.get("B1") == 11.0
    wb.names.define("X", "A2")          # redefine to A2 (=20)
    wb.invalidate_caches()
    assert s.get("B1") == 21.0
    wb.names.remove("X")                # now X is unknown -> #NAME?
    wb.invalidate_caches()
    assert str(s.get("B1")) == "#NAME?"


def test_names_and_validations_envelope_roundtrip():
    wb, s = _wb()
    wb.names.define("Vals", "A1:A3")
    s.validations.append((0, 1, 4, 1, list_rule(("yes", "no"))))
    s.validations.append((0, 2, 0, 2, number_rule("whole", "between", "1", "10")))
    env = wb.to_envelope()
    wb2 = Workbook.from_envelope(env)
    assert wb2.names.lookup("vals") == "A1:A3"
    assert len(wb2.sheet.validations) == 2
    r1, c1, r2, c2, rule = wb2.sheet.validations[0]
    assert (r1, c1, r2, c2) == (0, 1, 4, 1)
    assert rule.kind == "list" and rule.values == ("yes", "no")


def test_validation_for_lookup():
    wb, s = _wb()
    s.validations.append((0, 1, 4, 1, list_rule(("a", "b"))))
    assert s.validation_for(2, 1) is not None       # inside the range
    assert s.validation_for(2, 0) is None            # outside
    assert s.validation_for(5, 1) is None            # below the range
