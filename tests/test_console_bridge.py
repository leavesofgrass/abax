"""Subprocess bridge — real child-process round-trip + crash isolation/recovery."""

from __future__ import annotations

import sys

import pytest

from abax.core.workbook import Workbook
from abax.gui.console.console_bridge import ConsoleBridge


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
    # Warm the worker FIRST so it is already spawned and answering before the
    # interrupt timer is armed. interrupt() is a no-op while `bridge._proc` is
    # still None, so racing the timer against a cold spawn is a hang waiting to
    # happen: under full-suite load (parallel xdist workers + AV scanning every
    # fresh python.exe) CreateProcess can take longer than the timer delay, the
    # interrupt fires into nothing, and the runaway below blocks forever.
    # Against a live worker, a kill at any moment yields crashed=True.
    assert "warm" in bridge.execute("print('warm')", env)["output"]
    timer = threading.Timer(1.5, bridge.interrupt)     # kill the worker mid-run
    timer.start()
    # exec() so the loop actually runs — a bare one-line `while True: pass` is
    # "incomplete" to the interactive interpreter and returns without executing.
    r = bridge.execute('exec("while True: pass")', env)   # blocks until interrupted
    timer.cancel()
    assert r.get("crashed") is True
    r2 = bridge.execute("print('back')", env)          # respawns and works
    assert "back" in r2["output"]


# --- sandbox Phase 1: scripts and macros through the same worker ---------------


def test_script_round_trip_and_crash_isolation(bridge):
    env = Workbook().to_envelope()
    r = bridge.execute_script("put('B2', '7')\nprint('script ok')", "s.py", env)
    assert not r.get("crashed") and r["error"] is None
    assert "script ok" in r["output"]
    assert Workbook.from_envelope(r["envelope"]).sheet.get("B2") == 7
    # A script that hard-kills its process is contained; the workbook is untouched.
    r2 = bridge.execute_script("import os; os._exit(5)", "s.py", env)
    assert r2.get("crashed") is True and r2["envelope"] == env
    r3 = bridge.execute_script("print('respawned')", "s.py", env)
    assert "respawned" in r3["output"]


def test_macro_round_trip_through_subprocess(bridge, tmp_path):
    f = tmp_path / "m.py"
    f.write_text("@macro\ndef fill(ctx):\n    ctx.set('A1', 99)\n    ctx.log('filled')\n",
                 encoding="utf-8")
    env = Workbook().to_envelope()
    r = bridge.execute_macro("fill", [str(f)], (0, 0), env)
    assert not r.get("crashed") and r["error"] is None
    assert "filled" in r["output"]
    assert Workbook.from_envelope(r["envelope"]).sheet.get("A1") == 99


# --- sandbox Phase 2: hard timeout + OS resource limits -------------------------


def test_timeout_watchdog_kills_a_hung_worker(bridge):
    env = Workbook().to_envelope()
    # exec() so the loop genuinely hangs the worker (see note above); the
    # wall-clock watchdog must then kill it.
    r = bridge.execute('exec("while True: pass")', env, timeout=5)
    assert r.get("crashed") is True
    r2 = bridge.execute("print('ok after timeout')", env)
    assert "ok after timeout" in r2["output"]


@pytest.mark.skipif(sys.platform == "darwin",
                    reason="macOS doesn't enforce the worker memory cap (no RLIMIT_AS)")
def test_memory_bomb_is_contained(monkeypatch):
    """An unbounded allocation hits the OS cap (Job Object / RLIMIT_AS) instead
    of swapping the machine: either Python gets a MemoryError (reported as
    output/error) or the OS kills the worker (crashed) — both are contained."""
    monkeypatch.setenv("ABAX_WORKER_MEM_MB", "256")
    b = ConsoleBridge()
    try:
        env = Workbook().to_envelope()
        r = b.execute("x = bytearray(800 * 1024 * 1024); print('allocated')", env,
                      timeout=30)
        contained = (r.get("crashed") is True
                     or "MemoryError" in (r.get("output") or "")
                     or "MemoryError" in (r.get("error") or ""))
        assert contained, f"allocation was not contained: {r!r}"
        assert "allocated" not in (r.get("output") or "")
    finally:
        b.close()


def test_cpu_bomb_is_killed_by_process_time_limit(monkeypatch):
    """A busy-loop exceeds the per-process CPU-time cap and the OS terminates
    the worker (Job Object on Windows, RLIMIT_CPU on POSIX)."""
    monkeypatch.setenv("ABAX_WORKER_CPU_S", "1")
    b = ConsoleBridge()
    try:
        env = Workbook().to_envelope()
        # exec() so the loop actually burns CPU; a generous watchdog backstops
        # the OS CPU-time limit in case the platform doesn't enforce it.
        r = b.execute('exec("while True: pass")', env, timeout=30)
        assert r.get("crashed") is True
    finally:
        b.close()
