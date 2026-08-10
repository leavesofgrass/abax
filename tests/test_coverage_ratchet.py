"""Tests for the coverage ratchet gate (scripts/coverage_ratchet.py).

The point of that script is a failure path that ``--fail-under`` does not have:
it goes red when coverage drifts *above* the floor and the floor was never
raised. That branch had never fired in production when it was written — both
abax gates were 3 and 6 points stale — so it is exactly the kind of check that
can ship unable to fail and look fine for months.

``check()`` is pure for this reason: the verdict is testable without staging a
coverage run, so every branch here is exercised for real rather than asserted
about from a distance. Nothing below reads a coverage data file.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# Load scripts/coverage_ratchet.py as a module (scripts/ is not a package).
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "coverage_ratchet.py"
_spec = importlib.util.spec_from_file_location("coverage_ratchet", _SCRIPT)
assert _spec and _spec.loader
ratchet = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ratchet)


def test_healthy_coverage_passes():
    code, msg = ratchet.check(measured=84.2, floor=83, slack=3)
    assert code == ratchet.EXIT_OK
    assert "OK" in msg


def test_below_the_floor_is_a_regression():
    code, msg = ratchet.check(measured=80.9, floor=83, slack=3)
    assert code == ratchet.EXIT_REGRESSED
    assert "REGRESSED" in msg


def test_exactly_at_the_floor_passes():
    """``--fail-under`` treats == floor as passing; so must this, or a gate set
    to the measured value fails the build that set it."""
    code, _ = ratchet.check(measured=83.0, floor=83, slack=3)
    assert code == ratchet.EXIT_OK


def test_drift_beyond_slack_demands_the_floor_be_raised():
    """The branch that makes this a ratchet rather than a floor.

    Uses abax/engine's real numbers on the day the gate was written — measured
    63%, floor 57 — which passed ``--fail-under=57`` while permitting a 6-point
    regression.
    """
    code, msg = ratchet.check(measured=63.0, floor=57, slack=3)
    assert code == ratchet.EXIT_STALE
    assert "STALE RATCHET" in msg
    assert "raise the floor to 63" in msg


def test_drift_exactly_at_slack_still_passes():
    """Slack is a tolerance, not a target: at the boundary the build stays
    green, so a floor set one slack-width down does not immediately nag."""
    code, _ = ratchet.check(measured=86.0, floor=83, slack=3)
    assert code == ratchet.EXIT_OK


def test_the_two_failure_modes_have_distinct_exit_codes():
    """A CI log must be able to say which direction failed without parsing
    prose — and neither may collide with success."""
    regressed, _ = ratchet.check(measured=10.0, floor=83, slack=3)
    stale, _ = ratchet.check(measured=99.0, floor=83, slack=3)
    assert regressed != stale
    assert ratchet.EXIT_OK not in (regressed, stale)


@pytest.mark.parametrize("measured,expected", [
    (84.99, 84),      # rounds DOWN, never up: the floor keeps a sub-point buffer
    (83.0, 83),
    (63.51, 63),
])
def test_suggested_floor_rounds_down(measured, expected):
    assert ratchet.suggested_floor(measured) == expected


def test_missing_coverage_data_fails_rather_than_passing_silently():
    """Fail closed. A gate that cannot read its input must not report success —
    that is how a green build comes to mean nothing at all.
    """
    code = ratchet.main([
        "--include", "abax/core/*",
        "--floor", "83",
        "--data-file", str(Path(__file__).parent / "no-such-coverage-data"),
    ])
    assert code != ratchet.EXIT_OK


def test_the_ci_workflow_uses_this_gate_for_both_packages():
    """Pins the wiring, not the tool.

    The script passing its own unit tests proves nothing if ci.yml still calls
    bare ``coverage report --fail-under``: the ratchet would be dead code and
    the floors would go stale again exactly as before.
    """
    ci = (Path(__file__).resolve().parent.parent
          / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    # Count invocations, not mentions — the surrounding comment names the
    # script too, and matching that would pass on a workflow that only talks
    # about the gate without running it.
    assert ci.count("python scripts/coverage_ratchet.py") == 2, (
        "ci.yml should RUN the ratchet for abax/core and abax/engine")
    for package in ("abax/core/*", "abax/engine/*"):
        assert f'--include "{package}"' in ci, f"{package} is not gated"
    assert "--fail-under" not in ci, (
        "a bare --fail-under floor is back in ci.yml; it cannot ratchet — see "
        "scripts/coverage_ratchet.py")
