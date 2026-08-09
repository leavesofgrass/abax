"""Nothing may skip the AppContainer confinement tier.

There is no gate any more, and this file exists to keep it that way.

Eight tests verify abax's Windows security promise: confined code may write its
scratch dir, may not write beside it or open a socket, two confinements in
one process stay two containers (#10), and a live worker keeps the grants it
shares with a sibling that tore down (#11). They were skipped on
GitHub Actions for months on a claim about hosted runners that turned out to be
false (#3), and then on a narrower claim that turned out to be one mundane
device restriction (#6 — the confined worker could not open ``nul``). For that
whole period the guarantee held only as long as someone remembered to run the
suite on a Windows desktop, and nothing anywhere went red to say otherwise.

That is the failure mode being guarded: a skip is silent. Re-widen a condition,
invert a boolean, or add a module-level ``pytestmark``, and eight security tests
stop running while the suite still reports success. So the *absence* of a gate
gets tests, exactly as the gate itself did.

These never launch a confined child — they are about whether the tier would run,
not about what it proves.
"""

from __future__ import annotations

import ast
import pathlib
import sys

import pytest

from tests import conftest as gate
from tests.conftest import SANDBOX_E2E_MARKER

_TESTS = pathlib.Path(__file__).parent

#: The tier, by file and count. Spelled out so losing a member is a failure
#: rather than a silently smaller run.
_TIER = {"test_sandbox.py": 1, "test_sandbox_windows.py": 7}


def _marked_functions(filename: str) -> "set[str]":
    """Names of test functions in *filename* carrying the tier marker."""
    tree = ast.parse((_TESTS / filename).read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            target = dec.func if isinstance(dec, ast.Call) else dec
            if (isinstance(target, ast.Attribute)
                    and target.attr == SANDBOX_E2E_MARKER):
                found.add(node.name)
    return found


def test_the_tier_is_marked_and_intact():
    for filename, count in _TIER.items():
        marked = _marked_functions(filename)
        assert len(marked) == count, (
            f"{filename} should carry {count} {SANDBOX_E2E_MARKER} tests, "
            f"found {len(marked)}: {sorted(marked)}")


def test_the_marker_is_registered(pytestconfig):
    """An unregistered marker only warns, and warnings are not errors here."""
    assert SANDBOX_E2E_MARKER in "\n".join(pytestconfig.getini("markers"))


def test_conftest_has_no_collection_hook():
    """The gate was a ``pytest_collection_modifyitems`` hook. Its absence is the
    thing being asserted — a hook here could skip the tier for any reason at
    all, including a good-looking one."""
    assert not hasattr(gate, "pytest_collection_modifyitems"), (
        "tests/conftest.py grew a collection hook again — if it skips the "
        "sandbox tier, see this module's docstring before keeping it")


def test_no_environment_gating_helpers_survive():
    """The old gate keyed on CI environment variables. Nothing should read them
    to decide whether the confinement tier runs."""
    for name in ("hosted_github_runner", "sandbox_e2e_skip_reason",
                 "console_bridge_e2e_skip_reason", "SANDBOX_E2E_ENV",
                 "CONSOLE_BRIDGE_E2E_MARKER"):
        assert not hasattr(gate, name), f"tests/conftest.py:{name} is back"


def test_neither_sandbox_module_carries_a_module_level_skip():
    """A module-level ``pytestmark`` would gate every test in the file without
    touching a decorator — the blind spot that defeated the previous version of
    this file's checks.

    ``test_sandbox_windows.py`` legitimately has one: it is Windows-only. That
    is allowed; a *conditional on anything else* is not.
    """
    for filename in _TIER:
        tree = ast.parse((_TESTS / filename).read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if not any(getattr(t, "id", None) == "pytestmark" for t in node.targets):
                continue
            src = ast.unparse(node)
            assert "sys.platform" in src, (
                f"{filename} has a module-level pytestmark that is not the "
                f"platform guard: {src}")


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="test_sandbox_windows.py is Windows-only, so elsewhere the tier "
           "reports as skipped for a reason unrelated to gating",
)
def test_a_real_collection_runs_the_whole_tier(tmp_path):
    """Measured by pytest rather than by reading source.

    Everything above inspects decorators or module attributes. A real collection
    is what catches a gate arriving by some route none of them model — and the
    environment is set to what used to trigger the skip, so a resurrected gate
    shows up here first.
    """
    import os
    import subprocess

    env = dict(os.environ)
    env.update(GITHUB_ACTIONS="true", RUNNER_ENVIRONMENT="github-hosted",
               QT_QPA_PLATFORM="offscreen")
    env.pop("ABAX_SANDBOX_E2E", None)          # the old opt-in must be irrelevant

    root = _TESTS.parent
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_sandbox_windows.py",
         "-m", SANDBOX_E2E_MARKER, "-rs", "--no-header", "-q"],
        capture_output=True, text=True, timeout=600, cwd=str(root), env=env,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "skipped" not in r.stdout.splitlines()[-1], (
        f"something skipped part of the confinement tier:\n{r.stdout}")
