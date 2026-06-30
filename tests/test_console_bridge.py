"""Subprocess bridge — real child-process round-trip + crash isolation/recovery."""

from __future__ import annotations

import pytest

from qcell.core.workbook import Workbook
from qcell.gui.console.console_bridge import ConsoleBridge


@pytest.fixture()
def bridge():
    b = ConsoleBridge()
    yield b
    b.close()


def test_round_trip_through_subprocess(bridge):
    env = Workbook().to_envelope()
    r = bridge.execute("put('C3', '9'); print('hi')", env)
    assert not r.get("crashed")
    assert "hi" in r["output"]
    assert Workbook.from_envelope(r["envelope"]).sheet.get("C3") == 9


def test_crash_is_isolated_and_recovers(bridge):
    env = Workbook().to_envelope()
    r = bridge.execute("import os; os._exit(3)", env)        # hard-kill the worker
    assert r.get("crashed") is True
    assert r["envelope"] == env                              # workbook left untouched
    r2 = bridge.execute("put('A1', '1'); print('respawned')", env)
    assert not r2.get("crashed")
    assert "respawned" in r2["output"]


def test_interrupt_stops_a_runaway(bridge):
    import threading

    env = Workbook().to_envelope()
    timer = threading.Timer(1.5, bridge.interrupt)     # kill the worker mid-run
    timer.start()
    r = bridge.execute("while True: pass", env)        # blocks until interrupted
    timer.cancel()
    assert r.get("crashed") is True
    r2 = bridge.execute("print('back')", env)          # respawns and works
    assert "back" in r2["output"]
