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

**No gate.** ``sandbox_e2e`` marks the eight tests that launch a real
AppContainer-confined child. It *selects* the tier (``-m sandbox_e2e``) and
skips nothing, anywhere.

**Give the confinement's session-scoped ACL grants back before pytest exits.**
``sandbox_windows`` holds the shared read grants for the life of the process and
sweeps them from an ``atexit`` hook (issue #11); in a test run "the process" is
pytest, so without ``sandbox_session_grants_swept`` that sweep lands ~20 s of
DACL walking *after* the summary line, where it reads as a hang.
"""

from __future__ import annotations

import sys

import pytest

# --- the Windows AppContainer end-to-end tier ---------------------------------
#
# Eight tests launch a REAL AppContainer-confined child: the seven ``test_e2e_*``
# in ``test_sandbox_windows.py``, which call ``sandbox_windows.custom_spawn``
# directly, and ``test_sandbox.py::test_windows_strict_worker_runs_and_confines``,
# which reaches the same confinement through ``ConsoleBridge``. All eight carry
# ``@pytest.mark.sandbox_e2e``, and it skips nothing — the marker exists so the
# tier can be selected (``-m sandbox_e2e``), not so it can be turned off.
#
# There was a gate here, and its history is the reason this comment is long.
# The tier was skipped on GitHub Actions on the claim that a hosted Windows
# runner cannot launch an AppContainer-confined child. A probe workflow tested
# that claim and disproved it (#3): the five direct-launcher tests passed there,
# twice, in about four seconds. The gate then narrowed to the ConsoleBridge test
# alone — until the diagnostics showed *why* that one failed (#6): the confined
# worker could not open ``nul``, which it did at startup to keep stray prints out
# of the frame stream. One mundane device restriction, generalised into a claim
# about the platform, suppressing six security tests for months.
#
# With that fixed, those six pass on a hosted runner and the gate has nothing
# left to gate. abax's Windows confinement guarantee — confined code may write its
# scratch dir, and may not write beside it or open a socket — is now verified on
# every push by ci.yml's ``check`` matrix on its four windows-latest cells.
#
# If you are about to re-introduce a skip here: that is what the last one did,
# and it cost months of unverified security behaviour. Reproduce first.

#: Selection only: "this test launches a real OS-confined child". Never skipped.
SANDBOX_E2E_MARKER = "sandbox_e2e"


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        f"{SANDBOX_E2E_MARKER}: launches a real OS-confined child process. "
        "Selection only -- this marker never skips anything.",
    )


@pytest.fixture(scope="session", autouse=True)
def sandbox_session_grants_swept():
    """Run the Windows confinement's exit sweep when the *test* session ends.

    ``abax.sandbox_windows`` grants ALL APPLICATION PACKAGES read+execute on the
    interpreter prefix and every ``sys.path`` directory once per process and
    revokes them once, at process exit, from an ``atexit`` hook — the design that
    closes issue #11's window (see the note above ``_hold_session_grant``).

    Here the process is pytest, and any strict-mode test leaves those grants
    standing for the rest of the run. That is correct and deliberate; what is
    unhelpful is *when* the hook then collects them. An ``atexit`` sweep of the
    real prefix is ~20 s of DACL walking that happens after pytest has printed
    its summary and settled its exit code, so it looks exactly like a hang. Doing
    it here makes it part of the run.

    Not a substitute for the hook and not a check of it: this calls the same
    production function, and leaves it registered and holding nothing. The
    hook's own behaviour is tested in ``test_sandbox_windows.py``.

    **The sweep is machine-wide, not suite-wide.** The ACE names ALL APPLICATION
    PACKAGES, so this removes it for every process on the box — including a real
    abax running strict mode beside the suite, whose live worker loses its stdlib
    the moment this fires. Running the tests and the app at the same time on one
    machine is asking for exactly issue #9. Same hazard as any second abax
    exiting; it is just easier to hit here because a test run ends often.
    """
    yield
    if sys.platform != "win32":
        return
    try:
        from abax.sandbox_windows import _revoke_session_grants

        _revoke_session_grants()
    except Exception:          # never let cleanup fail a green run
        pass


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
