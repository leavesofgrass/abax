"""engine/tts.py — the optional text-to-speech adapter.

Two concerns are covered:

* **Graceful no-op without a backend.** With ``pyttsx3`` absent, importing the
  module must succeed, ``available()`` must be False, and ``speak()`` must be a
  silent no-op that returns False — so callers never need their own guard. The
  thin CI env has no pyttsx3, so this path is exercised for real there.
* **Non-blocking async delivery.** The queue/worker machinery is driven with a
  *fake* pyttsx3 (a stub engine that records what it was asked to say), so we can
  assert phrases are spoken, that ``speak()`` returns immediately, and that a full
  queue drops the oldest phrase rather than blocking — all without a real audio
  device or the real dependency.

A final test uses ``importorskip('pyttsx3')`` to smoke-test the genuine backend
only when it happens to be installed.
"""

from __future__ import annotations

import sys
import time
import types

import pytest

from abax.engine import tts


@pytest.fixture(autouse=True)
def _clean_tts():
    """Reset the module's global worker/probe state around every test."""
    tts.shutdown()
    tts._have_pyttsx3 = None
    yield
    tts.shutdown()
    tts._have_pyttsx3 = None


# --- no-op-without-backend path --------------------------------------------

def test_available_false_without_pyttsx3(monkeypatch):
    # Force the probe to see no pyttsx3, regardless of what's installed.
    monkeypatch.setitem(sys.modules, "pyttsx3", None)  # import -> ImportError
    tts._have_pyttsx3 = None
    assert tts.available() is False


def test_speak_is_noop_without_backend(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyttsx3", None)
    tts._have_pyttsx3 = None
    # Must not raise, must report it did nothing, and must not start a worker.
    assert tts.speak("hello") is False
    assert tts._thread is None
    assert tts.is_speaking() is False


def test_stop_and_shutdown_safe_without_backend(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyttsx3", None)
    tts._have_pyttsx3 = None
    # Both must be safe to call when nothing was ever started.
    tts.stop()
    tts.shutdown()
    assert tts.is_speaking() is False


def test_speak_rejects_empty_text():
    # Empty / whitespace phrases are dropped up front, backend or not.
    assert tts.speak("") is False
    assert tts.speak("   ") is False
    assert tts.speak(None) is False  # type: ignore[arg-type]


# --- async delivery via a fake pyttsx3 -------------------------------------

class _FakeEngine:
    """Records phrases; runAndWait() blocks briefly to mimic real speech."""

    def __init__(self, spoken, delay=0.0):
        self._spoken = spoken
        self._delay = delay
        self._pending = None
        self.stopped = False

    def say(self, text):
        self._pending = text

    def runAndWait(self):
        if self._delay:
            time.sleep(self._delay)
        if self._pending is not None:
            self._spoken.append(self._pending)
            self._pending = None

    def stop(self):
        self.stopped = True


def _install_fake_pyttsx3(monkeypatch, spoken, delay=0.0, init_raises=False):
    mod = types.ModuleType("pyttsx3")

    def init(*a, **k):
        if init_raises:
            raise RuntimeError("no voice backend")
        return _FakeEngine(spoken, delay=delay)

    mod.init = init
    monkeypatch.setitem(sys.modules, "pyttsx3", mod)
    tts._have_pyttsx3 = None  # re-probe against the fake


def _wait_until(pred, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return pred()


def test_available_true_with_backend(monkeypatch):
    _install_fake_pyttsx3(monkeypatch, [])
    assert tts.available() is True


def test_speak_delivers_phrase_to_engine(monkeypatch):
    spoken: list[str] = []
    _install_fake_pyttsx3(monkeypatch, spoken)
    assert tts.speak("A1: 42") is True
    assert _wait_until(lambda: spoken == ["A1: 42"]), spoken


def test_speak_returns_immediately(monkeypatch):
    # A slow engine must not slow down speak(): enqueue then return at once.
    spoken: list[str] = []
    _install_fake_pyttsx3(monkeypatch, spoken, delay=0.3)
    start = time.perf_counter()
    tts.speak("slow phrase")
    elapsed = time.perf_counter() - start
    assert elapsed < 0.2, f"speak() blocked for {elapsed:.3f}s"
    # It does eventually get spoken.
    assert _wait_until(lambda: spoken == ["slow phrase"]), spoken


def test_multiple_phrases_spoken_in_order(monkeypatch):
    spoken: list[str] = []
    _install_fake_pyttsx3(monkeypatch, spoken, delay=0.02)
    for cell in ("A1", "A2", "A3"):
        assert tts.speak(cell) is True
    assert _wait_until(lambda: spoken == ["A1", "A2", "A3"]), spoken


def test_full_queue_drops_oldest_not_blocks(monkeypatch):
    # A slow engine + a burst larger than the queue: speak() must never block,
    # and old phrases get dropped in favour of newer ones (the latest cell wins).
    spoken: list[str] = []
    _install_fake_pyttsx3(monkeypatch, spoken, delay=0.05)
    n = tts._MAX_PENDING * 3
    start = time.perf_counter()
    for i in range(n):
        tts.speak(f"cell-{i}")
    elapsed = time.perf_counter() - start
    # Enqueuing far more than the queue holds still returns fast (no blocking on
    # the slow engine): well under the time it'd take to actually speak them all.
    assert elapsed < n * 0.05, f"speak() appears to block: {elapsed:.3f}s for {n}"
    # Let the worker drain; the final phrase must have made it through. The last
    # enqueued phrase is always kept (put after dropping the oldest), so wait for
    # it specifically rather than racing the busy flag.
    assert _wait_until(lambda: f"cell-{n - 1}" in spoken, timeout=5.0), spoken
    _wait_until(lambda: not tts.is_speaking(), timeout=5.0)
    assert spoken[-1] == f"cell-{n - 1}"
    # And we dropped some: fewer spoken than enqueued.
    assert len(spoken) < n


def test_engine_init_failure_degrades_quietly(monkeypatch):
    # If the engine can't be created (no audio device), speak() still accepts the
    # phrase (available() is True) but nothing is spoken and nothing hangs.
    spoken: list[str] = []
    _install_fake_pyttsx3(monkeypatch, spoken, init_raises=True)
    assert tts.available() is True
    assert tts.speak("hi") is True
    # Worker starts, fails to init, drains — never blocks the caller.
    assert _wait_until(lambda: not tts.is_speaking(), timeout=3.0)
    assert spoken == []


def test_shutdown_stops_worker(monkeypatch):
    spoken: list[str] = []
    _install_fake_pyttsx3(monkeypatch, spoken)
    tts.speak("bye")
    _wait_until(lambda: spoken == ["bye"])
    tts.shutdown()
    assert tts._thread is None
    assert tts._queue is None


def test_stop_drains_pending(monkeypatch):
    # A slow first phrase keeps the worker busy; stop() clears what's queued.
    spoken: list[str] = []
    _install_fake_pyttsx3(monkeypatch, spoken, delay=0.4)
    for i in range(5):
        tts.speak(f"p{i}")
    tts.stop()  # drop everything still queued
    _wait_until(lambda: not tts.is_speaking(), timeout=3.0)
    # At most the one already-in-flight phrase spoke; the rest were dropped.
    assert len(spoken) <= 1


# --- real backend smoke test (only when installed) -------------------------

def test_real_backend_available_and_speaks():
    pytest.importorskip("pyttsx3")
    tts._have_pyttsx3 = None
    # On a machine with pyttsx3, available() should be True and speak() should
    # accept the phrase without raising. We don't assert audible output.
    assert tts.available() is True
    # speak() returns True (enqueued) as long as a worker can start; even if the
    # platform has no voice, engine-init failure is swallowed by the worker.
    result = tts.speak("abax accessibility self test")
    assert result is True
    tts.shutdown()
