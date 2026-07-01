"""Notebook validation: abax's own export is valid; structural checks bite."""

from __future__ import annotations

from abax.core.sheet import Sheet
from abax.core.workbook import Workbook
from abax.engine import nbvalidate


def _workbook():
    s = Sheet()
    s.set_cell(0, 0, "a")
    s.set_cell(0, 1, "b")
    s.set_cell(1, 0, "1")
    s.set_cell(1, 1, "=A2+1")
    return Workbook.from_sheets([s]) if hasattr(Workbook, "from_sheets") else Workbook()


def test_our_export_validates_clean():
    # Regression guard: whatever notebook abax writes must be valid (4.5 ids etc.)
    assert nbvalidate.validate_workbook(_workbook()) == []


def test_structural_checks_catch_real_problems():
    bad = {
        "nbformat": 3,                       # wrong major
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {"cell_type": "code", "source": ""},          # missing id/outputs/exec
            {"cell_type": "frobnicate", "source": "", "id": "x"},  # bad type
            {"cell_type": "markdown", "id": "y"},          # missing source
        ],
    }
    errs = nbvalidate._structural_checks(bad)
    joined = " ".join(errs)
    assert "nbformat must be 4" in joined
    assert "missing 'id'" in joined          # the code cell has no id under 4.5
    assert "missing 'outputs'" in joined
    assert "invalid cell_type" in joined
    assert "missing 'source'" in joined


def test_structural_checks_accept_a_valid_notebook():
    good = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {"cell_type": "markdown", "id": "m1", "source": "# hi", "metadata": {}},
            {"cell_type": "code", "id": "c1", "source": "1+1", "metadata": {},
             "outputs": [], "execution_count": None},
        ],
    }
    assert nbvalidate._structural_checks(good) == []


def test_non_list_cells_and_non_dict():
    assert nbvalidate._structural_checks({"nbformat": 4, "cells": "nope"})
    assert nbvalidate._structural_checks([]) == ["notebook is not a JSON object"]


def test_validate_notebook_dispatches():
    # Whichever backend is active, a clean notebook validates and a broken one does not.
    good = nbvalidate.validate_workbook(_workbook())
    assert good == []
    assert nbvalidate.validate_notebook({"cells": "x"})
