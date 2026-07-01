"""Tests for the PTY terminal backend.

These cover three layers, from least to most environment-dependent:

* :func:`pty_available` returns a plain ``bool`` and never raises.
* A pure pyte screen-feeding unit test that needs no real PTY — it exercises the
  exact byte-stream approach the reader thread uses.
* A guarded live test that spawns a real shell in a PTY, only when a backend is
  actually available; otherwise it skips.
"""

from __future__ import annotations

import time

import pytest

from abax.core.ptyterm import PtyError, PtyTerminal, pty_available


def test_pty_available_returns_bool() -> None:
    result = pty_available()
    assert isinstance(result, bool)


def test_pyte_screen_feeding() -> None:
    """Verify the screen-feeding approach the reader thread relies on."""
    pyte = pytest.importorskip("pyte")
    screen = pyte.Screen(20, 3)
    stream = pyte.ByteStream(screen)
    stream.feed(b"hello")
    assert screen.display[0].startswith("hello")


def test_start_raises_when_unavailable() -> None:
    if pty_available():
        pytest.skip("PTY backend is available; cannot test the unavailable path")
    term = PtyTerminal(cols=40, rows=6)
    with pytest.raises(PtyError):
        term.start()


def test_live_pty_echo() -> None:
    if not pty_available():
        pytest.skip("no PTY backend available on this host")

    term = PtyTerminal(cols=40, rows=6)
    term.start()
    try:
        assert term.alive
        term.write("echo abaxpty\r\n")

        found = False
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if any("abaxpty" in line for line in term.read_screen()):
                found = True
                break
            time.sleep(0.1)
        assert found, "expected 'abaxpty' to appear on the PTY screen"

        row, col = term.cursor()
        assert isinstance(row, int) and isinstance(col, int)
    finally:
        term.close()
