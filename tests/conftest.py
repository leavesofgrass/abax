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

**One gate for the sandbox end-to-end tier.** The ``sandbox_e2e`` marker below is
the single place deciding whether the real-AppContainer tests run; see
:func:`sandbox_e2e_skip_reason`.
"""

from __future__ import annotations

import os

import pytest

# --- the Windows AppContainer end-to-end tier ---------------------------------
#
# Two files carry tests that launch a REAL AppContainer-confined child process:
# ``test_sandbox.py::test_windows_strict_worker_runs_and_confines`` and the five
# ``test_e2e_*`` tests in ``test_sandbox_windows.py``. They used to hold two
# hand-copied ``skipif(GITHUB_ACTIONS)`` decorators with two hand-copied reasons,
# which is exactly the kind of duplicated reasoning that drifts. Both now apply
# ``@pytest.mark.sandbox_e2e`` and this module decides — once — what that means.
#
# A marker plus a collection hook (rather than a shared ``skipif`` object the two
# modules import) is deliberate: nothing under ``tests/`` has to import anything
# else under ``tests/``, so the gate does not depend on the test directory being
# importable, and ``-m sandbox_e2e`` / ``-m "not sandbox_e2e"`` selects the tier
# from the command line for free.

#: Opt-in switch. ``ABAX_SANDBOX_E2E=1`` runs the tier wherever it is otherwise
#: gated off — the ``sandbox-e2e`` job in ``.github/workflows/ci.yml``, a
#: scheduled run, or a developer reproducing a CI failure locally.
SANDBOX_E2E_ENV = "ABAX_SANDBOX_E2E"

# Deliberately ASCII: unlike the comments around it this string is *printed*, by
# `pytest -rs`, and a Windows console in the OEM codepage mojibakes a UTF-8 em
# dash into a replacement character mid-sentence.
_SANDBOX_E2E_SKIP_REASON = (
    "AppContainer end-to-end confinement is gated off on GitHub-HOSTED runners. "
    "The standing claim is that a hosted Windows runner cannot launch an "
    "AppContainer-confined child (it exits immediately) -- that claim predates the "
    "diagnostics in test_sandbox_windows.py (_diag) and has never actually been "
    "verified against a hosted runner, so treat it as unverified, not as "
    f"established fact. Set {SANDBOX_E2E_ENV}=1 to run the tier here anyway "
    "(.github/workflows/sandbox-e2e.yml does exactly that, to capture the error "
    "text). Only GitHub-hosted runners are gated: developer machines and "
    "self-hosted runners run the tier unconditionally."
)


def _env_truthy(name: str) -> bool:
    """abax's usual env-flag reading (matches ``abax.sandbox.strict_requested``)."""
    val = os.environ.get(name)
    return val is not None and val not in ("", "0", "false", "False")


def hosted_github_runner() -> bool:
    """True only on a GitHub-*hosted* Actions runner.

    ``GITHUB_ACTIONS`` alone is set on every runner, self-hosted ones included,
    and gating on it alone excluded the machines most likely to be *able* to run
    this. ``RUNNER_ENVIRONMENT`` (``github-hosted`` / ``self-hosted``) is what
    distinguishes them, so require both. Whether a given self-hosted runner can
    actually launch an AppContainer is untested — it could equally be a
    locked-down container — but leaving it ungated produces evidence instead of
    assuming an answer.

    An unset ``RUNNER_ENVIRONMENT`` reads as "not hosted" and the tier runs: fail
    loud rather than silently skip. Worth knowing where that lands — GitHub has
    set the variable since runner ~2.294 (2022), but if it ever stops, this tier
    starts running in ci.yml's ``check`` matrix on all four Windows cells and, if
    the standing claim holds, reddens the job that gates everything rather than
    the probe that is allowed to fail. That is the intended loud failure; this is
    the note that explains it to whoever is staring at a red Windows cell.
    """
    return (os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted")


def sandbox_e2e_skip_reason() -> "str | None":
    """The reason to skip the AppContainer end-to-end tier, or ``None`` to run it."""
    if _env_truthy(SANDBOX_E2E_ENV):
        return None
    if hosted_github_runner():
        return _SANDBOX_E2E_SKIP_REASON
    return None


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "sandbox_e2e: launches a real OS-confined child process; gated on "
        f"GitHub-hosted runners unless {SANDBOX_E2E_ENV}=1 (see conftest.py).",
    )


def pytest_collection_modifyitems(config, items):
    reason = sandbox_e2e_skip_reason()
    if reason is None:
        return
    skip = pytest.mark.skip(reason=reason)
    for item in items:
        if item.get_closest_marker("sandbox_e2e") is not None:
            item.add_marker(skip)


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
