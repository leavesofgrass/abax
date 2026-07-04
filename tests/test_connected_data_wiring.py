"""Integration wiring for the Connected Data release.

The feature modules (nbrun, doctor, dbapi, webtable, restimport) have their own
unit tests; this covers the *wiring* the integrator added: the CLI subcommands
in app.py and the GUI grid-import path in mixin_io.
"""

from __future__ import annotations

import io
import json
import os
import uuid
from contextlib import redirect_stdout

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# --- CLI wiring (app.py) ---------------------------------------------------


def test_cli_doctor_returns_zero():
    from abax import app

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = app.main(["doctor"])
    out = buf.getvalue()
    assert rc == 0
    assert "environment health report" in out.lower()
    assert "Optional dependencies" in out


def test_cli_notebook_run_executes_in_place(tmp_path):
    from abax import app

    nb = {
        "nbformat": 4, "nbformat_minor": 5, "metadata": {},
        "cells": [{
            "id": str(uuid.uuid4()), "cell_type": "code",
            "source": "put('A1', 6)\nput('A2', 7)\ncell('A1') * cell('A2')",
            "metadata": {}, "outputs": [], "execution_count": None,
        }],
    }
    p = tmp_path / "nb.ipynb"
    p.write_text(json.dumps(nb))
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = app.main(["notebook", "run", str(p)])
    assert rc == 0
    executed = json.loads(p.read_text())
    outs = executed["cells"][0]["outputs"]
    assert outs, "the cell should have gained an execute_result output"
    text = outs[0]["data"]["text/plain"]
    assert "42" in (text if isinstance(text, str) else "".join(text))


def test_cli_notebook_no_subcommand_is_usage_error():
    from abax import app

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = app.main(["notebook"])
    assert rc == 2  # usage error, not a crash


def test_doctor_and_notebook_are_subcommands():
    from abax import app

    assert {"doctor", "notebook"} <= app._SUBCOMMANDS  # not normalized to `gui`


# --- GUI grid-import wiring (mixin_io) -------------------------------------


@pytest.fixture(scope="module")
def app_qt():
    pytest.importorskip("abax.gui._qtcompat")
    from abax.gui._qtcompat import QApplication

    return QApplication.instance() or QApplication([])


def _win():
    from abax.gui.main_window import MainWindow
    from abax.settings import Settings

    return MainWindow(Settings())


def test_grid_import_builds_a_live_sheet(app_qt):
    win = _win()
    grid = [["name", "qty"], ["apples", "5"], ["pears", "8"], ["=A2", "=B2*2"]]
    win._grid_import_succeeded(grid, "web table")
    s = win._doc.workbook.sheet
    assert s.display(0, 0) == "name"
    assert s.display(1, 1) == "5"
    # imported formulas evaluate live (=A2 -> apples, =B2*2 -> 10)
    assert s.display(3, 0) == "apples"
    assert s.display(3, 1) == "10"


def test_grid_import_empty_is_a_noop(app_qt):
    win = _win()
    before = win._doc
    win._grid_import_succeeded([], "web table")
    assert win._doc is before  # nothing replaced


def test_database_import_guards_when_no_driver(app_qt, monkeypatch):
    win = _win()
    import abax.engine.dbapi as dbapi

    monkeypatch.setattr(dbapi, "available", lambda: False)
    shown = {}
    import abax.gui._qtcompat as qc

    monkeypatch.setattr(qc.QMessageBox, "information",
                        staticmethod(lambda *a, **k: shown.setdefault("msg", a)))
    win.import_database()
    assert "msg" in shown  # the graceful "install a driver" path fired
