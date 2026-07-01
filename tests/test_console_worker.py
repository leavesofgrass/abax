"""Out-of-process console worker — `Worker.handle` is pure (no subprocess needed)."""

from __future__ import annotations

from abax.console_worker import Worker
from abax.core.workbook import Workbook


def _env():
    return Workbook().to_envelope()


def test_workbook_round_trips():
    w = Worker()
    r = w.handle("put('A1', '5')", _env())
    assert Workbook.from_envelope(r["envelope"]).sheet.get("A1") == 5


def test_variables_persist_across_commands():
    w = Worker()
    r1 = w.handle("x = 21", _env())
    r2 = w.handle("print(x * 2)", r1["envelope"])
    assert r2["output"].strip() == "42"


def test_error_is_captured_not_fatal():
    w = Worker()
    r = w.handle("1 / 0", _env())
    assert "ZeroDivisionError" in r["output"]
    r2 = w.handle("print('still alive')", r["envelope"])   # worker survives
    assert "still alive" in r2["output"]


def test_exit_is_ignored():
    w = Worker()
    r = w.handle("exit()", _env())
    assert "ignored" in r["output"].lower()
