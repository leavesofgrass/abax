"""Text-to-speech adapter via pyttsx3 — optional, non-blocking, with a no-op fallback.

abax's accessibility features (speak-on-move, screen-reader hints) route every
spoken phrase through this one module. It wraps the optional ``pyttsx3`` package,
which drives the platform's native speech engine (SAPI5 on Windows, NSSpeech-
Synthesizer on macOS, eSpeak on Linux) with no network access. Like every other
adapter under :mod:`abax.engine`, importing this module NEVER fails when the
dependency is absent: :func:`speak` simply becomes a silent no-op and
:func:`available` returns ``False``, so callers need no ``try``/``except`` of
their own. This keeps ``abax/core/`` and the front-ends free of any hard
third-party dependency (see docs/architecture.md).

Non-blocking by construction. pyttsx3's own ``say`` + ``runAndWait`` loop is
*synchronous* — it blocks until the phrase finishes speaking, which would freeze
the GUI/TUI event loop for the duration of every cell move. Instead, this module
owns a single daemon worker thread with a bounded queue: :func:`speak` only
enqueues the text (a fast, thread-safe operation that returns immediately) and
the worker pulls phrases off the queue and speaks them one at a time. Because the
engine is created and driven entirely inside that one worker thread, we never
touch a pyttsx3/COM object from two threads — the usual failure mode for naive
threaded TTS. A tiny queue bound means a fast typist mashing arrow keys can't
build an unbounded backlog: when the queue is full the oldest pending phrase is
dropped in favour of the newest (the current cell is what matters, not a stale
one). :func:`stop` and :func:`shutdown` let a caller interrupt speech or tear the
worker down cleanly (e.g. on app exit or when the user disables the feature).

The engine is created lazily on the first successful :func:`speak`, so importing
this module — or calling :func:`speak` when pyttsx3 is missing — costs nothing.
"""

from __future__ import annotations

import queue
import threading

__all__ = [
    "available",
    "speak",
    "stop",
    "shutdown",
    "is_speaking",
]

# How many phrases may sit un-spoken before we start dropping the oldest. Small
# on purpose: for speak-on-move the *latest* cell is what the user cares about, a
# backlog of stale positions is noise. 8 leaves a little slack for short bursts.
_MAX_PENDING = 8

# A sentinel enqueued by shutdown() to tell the worker to exit its loop.
_STOP = object()

# Module-global worker state, guarded by _lock. The worker thread and queue are
# created lazily on the first speak() that has a working backend, so an import
# (or a speak() without pyttsx3) spins nothing up.
_lock = threading.Lock()
_thread: "threading.Thread | None" = None
_queue: "queue.Queue | None" = None
_speaking = threading.Event()

# Cached result of probing for pyttsx3, so available() is cheap after the first
# call. None = not yet probed; True/False = the probed answer.
_have_pyttsx3: "bool | None" = None


def _probe_pyttsx3() -> bool:
    """True if ``pyttsx3`` can be imported. Cached after the first probe."""
    global _have_pyttsx3
    if _have_pyttsx3 is None:
        try:
            import pyttsx3  # type: ignore  # noqa: F401

            _have_pyttsx3 = True
        except Exception:
            # ImportError when absent; some backends raise other errors at import
            # (e.g. a missing platform driver). Either way TTS is unavailable.
            _have_pyttsx3 = False
    return _have_pyttsx3


def available() -> bool:
    """True if a text-to-speech backend (``pyttsx3``) is importable.

    Cheap and side-effect-free: it never creates the speech engine or starts the
    worker thread, so UI code can call it freely (e.g. to grey out a menu item).
    """
    return _probe_pyttsx3()


def _worker(q: "queue.Queue") -> None:
    """Background thread: own the pyttsx3 engine and speak queued phrases.

    The engine lives entirely on this thread — it is created here and never
    handed out — so we never drive a pyttsx3/COM object from two threads. If the
    engine can't be created (e.g. no platform voice), we drain the queue quietly
    so callers still don't block; TTS simply stays silent.
    """
    engine = None
    try:
        import pyttsx3  # type: ignore

        engine = pyttsx3.init()
    except Exception:
        # Either pyttsx3 vanished or there's no usable voice backend on this
        # machine (missing driver / no audio device). We deliberately do NOT
        # exit: staying in the loop and quietly discarding phrases means a later
        # speak() enqueues into a live worker instead of orphaning the phrase in
        # a queue nobody is draining. TTS simply stays silent.
        engine = None

    while True:
        item = q.get()
        if item is _STOP:
            if engine is not None:
                try:
                    engine.stop()
                except Exception:
                    pass
            _speaking.clear()
            return
        _speaking.set()
        try:
            if engine is not None:
                engine.say(item)
                engine.runAndWait()
            # else: no backend — swallow the phrase silently.
        except Exception:
            # A single bad phrase (or a transient engine hiccup) must not kill the
            # worker — swallow it and keep serving the queue.
            pass
        finally:
            # Clear only when nothing else is queued, so is_speaking() stays true
            # across a back-to-back burst.
            if q.empty():
                _speaking.clear()


def _drain(q: "queue.Queue") -> None:
    """Discard everything currently queued (used when there's no backend)."""
    _speaking.clear()
    try:
        while True:
            q.get_nowait()
    except queue.Empty:
        pass


def _ensure_worker() -> "queue.Queue | None":
    """Start the worker thread + queue if needed. Returns the queue, or None if
    no backend is available (so the caller no-ops)."""
    global _thread, _queue
    if not _probe_pyttsx3():
        return None
    with _lock:
        if _queue is None:
            _queue = queue.Queue(maxsize=_MAX_PENDING)
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(
                target=_worker, args=(_queue,), name="abax-tts", daemon=True
            )
            _thread.start()
        return _queue


def speak(text: str) -> bool:
    """Speak ``text`` asynchronously; return immediately without blocking.

    A no-op returning ``False`` when no TTS backend is installed, when ``text`` is
    empty/whitespace, or when the worker can't be started — callers never need to
    guard the call. Returns ``True`` when the phrase was accepted onto the speech
    queue.

    Non-blocking: this only enqueues the phrase. If the queue is momentarily full
    (a rapid burst of moves), the oldest pending phrase is dropped so the newest
    still gets through — for speak-on-move the current cell matters, not a stale
    one.
    """
    if not text or not str(text).strip():
        return False
    q = _ensure_worker()
    if q is None:
        return False
    text = str(text)
    try:
        q.put_nowait(text)
        return True
    except queue.Full:
        # Drop the oldest, then retry once so the newest phrase still lands.
        try:
            q.get_nowait()
        except queue.Empty:
            pass
        try:
            q.put_nowait(text)
            return True
        except queue.Full:
            return False


def is_speaking() -> bool:
    """True while a phrase is being spoken *or* still waiting in the queue.

    Reports busy even for work that the worker hasn't picked up yet, so it's a
    reliable "is there speech pending?" signal (not just "mid-utterance").
    """
    if _speaking.is_set():
        return True
    with _lock:
        q = _queue
    return q is not None and not q.empty()


def stop() -> None:
    """Interrupt current/pending speech by draining the queue.

    Safe to call when nothing is speaking or no backend exists. The worker thread
    keeps running (ready for the next :func:`speak`); it just has nothing left to
    say. The phrase already mid-utterance finishes, since pyttsx3 gives us no
    portable way to cut it off from another thread without risking the engine.
    """
    with _lock:
        q = _queue
    if q is not None:
        _drain(q)


def shutdown(timeout: float = 2.0) -> None:
    """Stop speech and tear down the worker thread. Idempotent.

    Intended for app exit (or when the user turns the feature off). After this,
    the next :func:`speak` transparently starts a fresh worker.
    """
    global _thread, _queue
    with _lock:
        q, t = _queue, _thread
        _queue = None
        _thread = None
    if q is not None:
        _drain(q)
        try:
            q.put_nowait(_STOP)
        except queue.Full:
            # Make room for the stop sentinel so the worker actually exits.
            try:
                q.get_nowait()
                q.put_nowait(_STOP)
            except (queue.Empty, queue.Full):
                pass
    if t is not None and t.is_alive():
        t.join(timeout=timeout)
    _speaking.clear()
