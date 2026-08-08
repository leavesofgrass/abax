"""The AppContainer end-to-end gate itself (``tests/conftest.py``).

Without this file the gate is the one piece of the suite whose failure mode is
silence. It decides whether six tests that verify a *security* promise run at
all; collapse its condition back to a bare ``GITHUB_ACTIONS`` check — or invert
a boolean — and nothing goes red anywhere. The tier simply stops running, on
developer machines too, and the suite still reports success. That is precisely
the shape this project keeps getting caught by, so the gate gets tests like
anything else.

Note what is asserted: ``sandbox_e2e_skip_reason()`` returning ``None`` means
*run the tier*. These tests never launch a confined child themselves — they are
about the decision, not the thing decided.
"""

from __future__ import annotations

import pytest

from tests.conftest import (
    SANDBOX_E2E_ENV,
    hosted_github_runner,
    sandbox_e2e_skip_reason,
)

_CI = "GITHUB_ACTIONS"
_ENVIRONMENT = "RUNNER_ENVIRONMENT"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Start every case from a bare machine, whatever the host really is.

    Without this the tests would pass or fail depending on where they run, which
    is the exact class of bug the gate exists to avoid.
    """
    for name in (_CI, _ENVIRONMENT, SANDBOX_E2E_ENV):
        monkeypatch.delenv(name, raising=False)


def _set(monkeypatch, ci=None, environment=None, optin=None):
    for name, val in ((_CI, ci), (_ENVIRONMENT, environment),
                      (SANDBOX_E2E_ENV, optin)):
        if val is not None:
            monkeypatch.setenv(name, val)


# --- the case that must never break ------------------------------------------


def test_a_developer_machine_runs_the_tier(monkeypatch):
    """No CI variables at all. This is where the confinement promise is actually
    verified today, so a change that silences the tier here is the worst
    possible outcome of touching the gate."""
    assert sandbox_e2e_skip_reason() is None


# --- hosted runners: the only place the tier is gated off --------------------


def test_a_hosted_runner_skips_the_tier(monkeypatch):
    _set(monkeypatch, ci="true", environment="github-hosted")
    reason = sandbox_e2e_skip_reason()
    assert reason is not None
    # The reason has to carry the opt-in, or a reader who hits the skip has no
    # way to run the thing they wanted.
    assert SANDBOX_E2E_ENV in reason


def test_a_hosted_runner_runs_the_tier_when_opted_in(monkeypatch):
    _set(monkeypatch, ci="true", environment="github-hosted", optin="1")
    assert sandbox_e2e_skip_reason() is None


# --- everything that is NOT a hosted runner ----------------------------------


def test_a_self_hosted_runner_runs_the_tier(monkeypatch):
    """GITHUB_ACTIONS alone is set on self-hosted runners too. Gating on it
    excluded the machines most likely to be able to run this."""
    _set(monkeypatch, ci="true", environment="self-hosted")
    assert sandbox_e2e_skip_reason() is None


def test_an_unset_runner_environment_fails_open(monkeypatch):
    """Deliberate: an unrecognised environment runs the tier rather than
    silently skipping it. See the note in hosted_github_runner()."""
    _set(monkeypatch, ci="true")
    assert sandbox_e2e_skip_reason() is None


def test_the_environment_alone_is_not_enough(monkeypatch):
    _set(monkeypatch, environment="github-hosted")
    assert sandbox_e2e_skip_reason() is None


# --- the opt-in flag's own parsing -------------------------------------------


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "anything"])
def test_truthy_optin_values_run_the_tier(monkeypatch, value):
    _set(monkeypatch, ci="true", environment="github-hosted", optin=value)
    assert sandbox_e2e_skip_reason() is None


@pytest.mark.parametrize("value", ["", "0", "false", "False"])
def test_falsey_optin_values_leave_the_gate_closed(monkeypatch, value):
    """Matches abax.sandbox.strict_requested's convention, so an operator who
    sets ABAX_SANDBOX_E2E=0 to mean "off" is not surprised by it meaning "on"."""
    _set(monkeypatch, ci="true", environment="github-hosted", optin=value)
    assert sandbox_e2e_skip_reason() is not None


# --- the predicate underneath -------------------------------------------------


@pytest.mark.parametrize(
    ("ci", "environment", "expected"),
    [
        ("true", "github-hosted", True),
        ("true", "self-hosted", False),
        ("true", None, False),
        (None, "github-hosted", False),
        (None, None, False),
        ("false", "github-hosted", False),
    ],
)
def test_hosted_github_runner_predicate(monkeypatch, ci, environment, expected):
    _set(monkeypatch, ci=ci, environment=environment)
    assert hosted_github_runner() is expected


# --- the marker is actually wired to the gate ---------------------------------


def test_the_tier_is_marked_and_the_marker_is_registered(pytestconfig):
    """A gate nothing is marked with would be a no-op that still passes every
    test above. Pin both halves: the marker exists, and the six tier members
    carry it."""
    # conftest registers it with addinivalue_line, which appends to the ini
    # value, so getini sees it at runtime. An unregistered marker would only
    # warn, and warnings are not errors here — hence an explicit assertion.
    known = "\n".join(pytestconfig.getini("markers"))
    assert "sandbox_e2e" in known, (
        "the sandbox_e2e marker is no longer registered in conftest.pytest_configure")

    import pathlib
    root = pathlib.Path(__file__).parent
    for src in (root / "test_sandbox.py", root / "test_sandbox_windows.py"):
        assert "sandbox_e2e" in src.read_text(encoding="utf-8"), (
            f"{src.name} no longer applies the sandbox_e2e marker, so the gate "
            f"cannot reach its tests")
