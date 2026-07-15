"""Session-wide pytest fixtures.

**Keep the suite out of the user's profile.** ``abax_user_dirs`` (autouse) points
every ``abax._runtime`` user-state dir at a per-test temp dir so nothing a
test triggers can touch the real ``%LOCALAPPDATA%/abax`` (or XDG equivalent).

**Keep the suite silent.** Several tests exercise the accessibility text-to-speech
path — speak-on-move in the grid, the TUI screen-reader line, the a11y
preferences — and with ``pyttsx3`` installed those drive the *real* SAPI5 /
NSSpeech voice and speak cell values aloud ("2", "a2 42", …), which is
disruptive to anyone working near the machine running the tests.

Every spoken phrase funnels through the one function ``abax.engine.tts.speak``,
so an autouse fixture no-ops it for the whole suite. The only exception is
``test_tts.py``, which tests the TTS machinery itself and already drives it with
*fake* pyttsx3 engines (no audio) — it must see the real implementation.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def abax_user_dirs(tmp_path_factory, monkeypatch):
    """Redirect every abax user-state dir to a fresh per-test temp dir.

    Plenty of code under test persists for real: ``MainWindow.closeEvent`` and
    the autosave timer, ``DependencyChooser.done()`` (fired by *any* dismissal),
    the Preferences / file-manager dialogs, and the TUI first-run prompt all
    write ``settings.json`` to ``rt.CONFIG_DIR`` — and autodeps drops attempt
    markers under ``rt.CACHE_DIR``. Un-redirected, a test that merely closes its
    window overwrites the developer's real settings with fixture defaults.

    Every consumer resolves these paths through the module attribute at call
    time (``rt.CONFIG_DIR / "settings.json"``), so patching ``abax._runtime``
    is sufficient. The dirs are created eagerly because ``save_settings`` does
    not make parents — but in a private per-test temp dir, *not* inside
    ``tmp_path``: several tests assert on ``tmp_path``'s exact contents
    (test_nbrun, test_fileops) and must not find our scaffolding there.
    Returns the redirect map keyed by attribute name, so a test that asserts
    on persisted files can locate them (e.g.
    ``abax_user_dirs["CONFIG_DIR"] / "settings.json"``). A test needing its own
    layout may still monkeypatch over this — its patch lands later and wins
    (see test_doctor.py).
    """
    import abax._runtime as rt

    base = tmp_path_factory.mktemp("abax-user-dirs")
    dirs = {}
    for name, sub in (
        ("CONFIG_DIR", "config"),
        ("DATA_DIR", "data"),
        ("CACHE_DIR", "cache"),
        ("LOG_DIR", "log"),
        ("EXCHANGE_DIR", "data/exchange"),
    ):
        d = base / sub
        d.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(rt, name, d)
        dirs[name] = d
    return dirs


@pytest.fixture(autouse=True)
def _silence_tts(request, monkeypatch):
    # test_tts.py exercises speak() directly against fake engines (silent) and
    # needs the genuine implementation; leave it untouched.
    if request.module.__name__.endswith("test_tts"):
        yield
        return
    # Replace the single TTS entry point with a silent no-op. Callers import it
    # lazily (`tts.speak(...)` / `from ...engine.tts import speak`) at call time,
    # so they pick up the patched attribute.
    monkeypatch.setattr("abax.engine.tts.speak", lambda *a, **k: False, raising=False)
    yield
