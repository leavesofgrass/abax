"""Editable sheet widget: the tested data-sync core + optional anywidget glue."""

from __future__ import annotations

import importlib.util

import pytest

from abax import widget
from abax.core.sheet import Sheet


def _sheet():
    s = Sheet()
    s.set_cell(0, 0, "qty")
    s.set_cell(0, 1, "price")
    s.set_cell(1, 0, "3")
    s.set_cell(1, 1, "4")
    s.set_cell(1, 2, "=A2*B2")
    return s


def test_sheet_state_shape_and_values():
    st = widget.sheet_state(_sheet())
    assert st["name"] == "Sheet1"
    assert st["rows"] == 2 and st["cols"] == 3
    assert st["cells"][0] == ["qty", "price", ""]
    assert st["cells"][1] == ["3", "4", "12"]      # the formula's computed value


def test_sheet_state_bounds():
    s = Sheet()
    for r in range(500):
        for c in range(10):
            s.set_cell(r, c, str(r))
    st = widget.sheet_state(s, max_rows=100, max_cols=5)
    assert st["rows"] == 100 and st["cols"] == 5   # both capped
    assert len(st["cells"]) == 100 and len(st["cells"][0]) == 5


def test_apply_edit_recomputes_formula():
    s = _sheet()
    widget.apply_edit(s, 1, 0, "10")               # A2 = 10
    assert s.display(1, 2) == "40"                  # C2 = A2*B2 recomputes
    widget.apply_edit(s, 1, 1, None)               # None -> blank
    assert s.get_raw(1, 1) == ""


def test_apply_edits_batch():
    s = _sheet()
    n = widget.apply_edits(s, [{"row": 2, "col": 0, "raw": "x"},
                               {"row": 2, "col": 1, "raw": "y"}])
    assert n == 2
    assert s.get_raw(2, 0) == "x" and s.get_raw(2, 1) == "y"


def test_esm_is_a_render_module():
    assert "export default" in widget._ESM
    assert "render" in widget._ESM
    assert "save_changes" in widget._ESM           # edits flow back to Python


def test_sheet_widget_requires_anywidget():
    if importlib.util.find_spec("anywidget") is None:
        with pytest.raises(SystemExit) as exc:
            widget.sheet_widget(_sheet())
        assert "anywidget" in str(exc.value)
    else:
        w = widget.sheet_widget(_sheet())
        assert list(w.cells[1]) == ["3", "4", "12"]
