"""The sandbox end-to-end gate itself (``tests/conftest.py``).

Without this file the gate is the one piece of the suite whose failure mode is
silence. It decides whether tests that verify a *security* promise run at all;
widen its condition back to the whole ``sandbox_e2e`` tier — or invert a boolean
— and nothing goes red anywhere. The tests simply stop running, and the suite
still reports success. That is precisely the shape this project keeps getting
caught by, so the gate gets tests like anything else.

Two invariants live here, and the second one is new:

* ``console_bridge_e2e_skip_reason()`` returning ``None`` means *run it*. Those
  cases are about the decision, not the thing decided — nothing here launches a
  confined child.
* The five ``test_e2e_*`` tests are never skipped by the gate, under any
  environment. They were suppressed for a long time by a claim about hosted
  runners that turned out to be false (see conftest.py), and re-widening the
  gate is exactly the regression that would undo the fix.
"""

from __future__ import annotations

import ast
import pathlib
import sys

import pytest

# The collection hook is reached through the module (``gate.pytest_...``) on
# purpose: binding a name that starts with ``pytest_`` at test-module scope is
# how you accidentally grow a second hook implementation.
from tests import conftest as gate
from tests.conftest import (
    CONSOLE_BRIDGE_E2E_MARKER,
    SANDBOX_E2E_ENV,
    SANDBOX_E2E_MARKER,
    console_bridge_e2e_skip_reason,
    hosted_github_runner,
)

_CI = "GITHUB_ACTIONS"
_ENVIRONMENT = "RUNNER_ENVIRONMENT"

#: Every environment shape the gate can see, as (ci, runner-environment, opt-in).
_ALL_ENVS = [
    (None, None, None),                        # a developer desktop
    ("true", "github-hosted", None),           # the only gated combination
    ("true", "github-hosted", "1"),
    ("true", "self-hosted", None),
    ("true", None, None),
    (None, "github-hosted", None),
    ("false", "github-hosted", None),
]


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


def test_a_developer_machine_runs_everything(monkeypatch):
    """No CI variables at all. This is where the ConsoleBridge path is actually
    exercised today, so a change that silences it here is the worst possible
    outcome of touching the gate."""
    assert console_bridge_e2e_skip_reason() is None


# --- hosted runners: the only place anything is gated off --------------------


def test_a_hosted_runner_skips_the_console_bridge_test(monkeypatch):
    _set(monkeypatch, ci="true", environment="github-hosted")
    reason = console_bridge_e2e_skip_reason()
    assert reason is not None
    # The reason has to carry the opt-in, or a reader who hits the skip has no
    # way to run the thing they wanted.
    assert SANDBOX_E2E_ENV in reason


def test_the_skip_reason_blames_console_bridge_and_not_appcontainer(monkeypatch):
    """The reason is evidence, not a hunch, and the distinction is the entire
    point of this change: AppContainer confinement demonstrably works on a hosted
    runner. A reason that goes back to claiming otherwise would re-license
    skipping the five test_e2e_* tests."""
    _set(monkeypatch, ci="true", environment="github-hosted")
    reason = console_bridge_e2e_skip_reason()
    assert "ConsoleBridge" in reason
    assert "test_e2e_" in reason                    # names the counter-evidence
    assert "sandbox-e2e.yml" in reason              # and where it was measured
    # Printed by `pytest -rs` into a Windows OEM console, which mangles non-ASCII.
    reason.encode("ascii")
    # One skipped test, one paragraph. The reason this replaced ran to ~700
    # characters, which nobody reads twice.
    assert len(reason) < 450, len(reason)


def test_a_hosted_runner_runs_it_when_opted_in(monkeypatch):
    _set(monkeypatch, ci="true", environment="github-hosted", optin="1")
    assert console_bridge_e2e_skip_reason() is None


# --- everything that is NOT a hosted runner ----------------------------------


def test_a_self_hosted_runner_runs_everything(monkeypatch):
    """GITHUB_ACTIONS alone is set on self-hosted runners too. Gating on it
    excluded the machines most likely to be able to run this."""
    _set(monkeypatch, ci="true", environment="self-hosted")
    assert console_bridge_e2e_skip_reason() is None


def test_an_unset_runner_environment_fails_open(monkeypatch):
    """Deliberate: an unrecognised environment runs the test rather than
    silently skipping it. See the note in hosted_github_runner()."""
    _set(monkeypatch, ci="true")
    assert console_bridge_e2e_skip_reason() is None


def test_the_environment_alone_is_not_enough(monkeypatch):
    _set(monkeypatch, environment="github-hosted")
    assert console_bridge_e2e_skip_reason() is None


# --- the opt-in flag's own parsing -------------------------------------------


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "anything"])
def test_truthy_optin_values_open_the_gate(monkeypatch, value):
    _set(monkeypatch, ci="true", environment="github-hosted", optin=value)
    assert console_bridge_e2e_skip_reason() is None


@pytest.mark.parametrize("value", ["", "0", "false", "False"])
def test_falsey_optin_values_leave_the_gate_closed(monkeypatch, value):
    """Matches abax.sandbox.strict_requested's convention, so an operator who
    sets ABAX_SANDBOX_E2E=0 to mean "off" is not surprised by it meaning "on"."""
    _set(monkeypatch, ci="true", environment="github-hosted", optin=value)
    assert console_bridge_e2e_skip_reason() is not None


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


# --- the collection hook: what it actually skips ------------------------------


class _FakeItem:
    """The slice of a pytest item the collection hook touches."""

    def __init__(self, name, *markers):
        self.name = name
        self.markers = set(markers)
        self.added = []

    def get_closest_marker(self, name):
        return name if name in self.markers else None

    def add_marker(self, marker):
        self.added.append(marker)


def _run_hook():
    items = [
        _FakeItem("test_e2e_confined_child_runs_to_completion", SANDBOX_E2E_MARKER),
        _FakeItem("test_windows_strict_worker_runs_and_confines",
                  SANDBOX_E2E_MARKER, CONSOLE_BRIDGE_E2E_MARKER),
        _FakeItem("test_wrap_argv_is_the_identity"),
    ]
    gate.pytest_collection_modifyitems(config=None, items=items)
    return items


@pytest.mark.parametrize(("ci", "environment", "optin"), _ALL_ENVS)
def test_the_direct_launcher_tier_is_never_skipped(monkeypatch, ci, environment, optin):
    """THE regression guard. Under every environment the gate can observe, a test
    marked ``sandbox_e2e`` and nothing else keeps running. This is what the five
    test_e2e_* tests rely on: they verify the confinement promise on every push,
    including on the hosted runners that used to skip them."""
    _set(monkeypatch, ci=ci, environment=environment, optin=optin)
    e2e, _bridge, _plain = _run_hook()
    assert e2e.added == [], (
        f"the gate skipped {e2e.name} with GITHUB_ACTIONS={ci!r} "
        f"RUNNER_ENVIRONMENT={environment!r} {SANDBOX_E2E_ENV}={optin!r}")


def test_the_hook_skips_the_console_bridge_test_on_a_hosted_runner(monkeypatch):
    _set(monkeypatch, ci="true", environment="github-hosted")
    _e2e, bridge, plain = _run_hook()
    (mark,) = bridge.added
    assert mark.name == "skip"
    assert SANDBOX_E2E_ENV in mark.kwargs["reason"]
    assert plain.added == []       # unmarked tests are never touched


def test_the_hook_is_inert_off_a_hosted_runner(monkeypatch):
    assert all(item.added == [] for item in _run_hook())


# --- the markers are actually wired to the gate -------------------------------


_ROOT = pathlib.Path(__file__).parent


def _marker_names(func: ast.FunctionDef) -> "set[str]":
    """The ``pytest.mark.<name>`` decorators on *func*, by name."""
    names = set()
    for dec in func.decorator_list:
        node = dec.func if isinstance(dec, ast.Call) else dec
        if (isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "mark"):
            names.add(node.attr)
    return names


def _functions(filename: str) -> "dict[str, set[str]]":
    tree = ast.parse((_ROOT / filename).read_text(encoding="utf-8"))
    return {node.name: _marker_names(node) for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)}


def test_both_markers_are_registered(pytestconfig):
    """A marker nothing registers only warns, and warnings are not errors here —
    hence an explicit assertion. conftest registers them with addinivalue_line,
    which appends to the ini value, so getini sees them at runtime."""
    known = "\n".join(pytestconfig.getini("markers"))
    for marker in (SANDBOX_E2E_MARKER, CONSOLE_BRIDGE_E2E_MARKER):
        assert marker in known, (
            f"the {marker} marker is no longer registered in "
            f"conftest.pytest_configure")


def test_the_five_e2e_tests_are_marked_for_selection_only():
    """The invariant this whole change exists to create, pinned at the source.

    Applying ``console_bridge_e2e`` to one of these — the obvious way to
    're-gate the sandbox tier' — puts the confinement promise back to being
    verified only when someone remembers to run the suite on a desktop.
    """
    funcs = {name: marks for name, marks in
             _functions("test_sandbox_windows.py").items()
             if name.startswith("test_e2e_")}
    assert len(funcs) == 5, sorted(funcs)
    for name, marks in funcs.items():
        assert SANDBOX_E2E_MARKER in marks, f"{name} lost its selection marker"
        assert CONSOLE_BRIDGE_E2E_MARKER not in marks, (
            f"{name} was gated behind the ConsoleBridge marker; it launches the "
            f"confined child directly and passes on hosted runners")


def test_the_console_bridge_test_carries_both_markers():
    """A gate nothing is marked with would be a no-op that still passes every
    test above."""
    marks = _functions("test_sandbox.py")["test_windows_strict_worker_runs_and_confines"]
    assert SANDBOX_E2E_MARKER in marks       # still part of the selectable tier
    assert CONSOLE_BRIDGE_E2E_MARKER in marks


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="test_sandbox_windows.py is Windows-only (its own module-level "
           "pytestmark), so elsewhere the five report as skipped for a reason "
           "that has nothing to do with the gate under test",
)
def test_a_real_collection_on_a_hosted_runner_keeps_the_five(tmp_path):
    """The same invariant, but measured by pytest instead of by reading source.

    Everything above inspects decorators (via ast) or drives the hook with
    hand-built items. Both share a blind spot: a module-level
    ``pytestmark = pytest.mark.console_bridge_e2e`` would gate all five without
    touching a single decorator, and every other test here would stay green
    while the confinement tier silently stopped running on CI. Since that is the
    exact failure mode this file exists to prevent, one case has to ask the real
    collector.

    Subprocess rather than in-process: the gate reads the environment at
    collection time, and this process has already collected.
    """
    import os
    import subprocess
    import sys

    env = dict(os.environ)
    env.update(GITHUB_ACTIONS="true", RUNNER_ENVIRONMENT="github-hosted",
               QT_QPA_PLATFORM="offscreen")
    env.pop(SANDBOX_E2E_ENV, None)           # gate closed, as on a real hosted run

    root = pathlib.Path(__file__).resolve().parent.parent
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_sandbox_windows.py",
         "-m", SANDBOX_E2E_MARKER, "--collect-only", "-q", "--no-header"],
        capture_output=True, text=True, timeout=300, cwd=str(root), env=env,
    )
    assert r.returncode == 0, r.stdout + r.stderr

    collected = [ln for ln in r.stdout.splitlines() if "::test_e2e_" in ln]
    assert len(collected) == 5, (
        f"expected the five direct-launcher tests to collect on a hosted runner, "
        f"got {len(collected)}:\n{r.stdout}")
    # --collect-only reports deselection, not skips; the hook adds skip marks at
    # collection, so a gated item would still be listed. Run them for real and
    # assert nothing was skipped.
    r2 = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_sandbox_windows.py",
         "-m", SANDBOX_E2E_MARKER, "-rs", "--no-header", "-q"],
        capture_output=True, text=True, timeout=600, cwd=str(root), env=env,
    )
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "skipped" not in r2.stdout.splitlines()[-1], (
        f"a hosted runner skipped part of the direct-launcher tier:\n{r2.stdout}")
