"""The ``restricted`` code-isolation tier: AST allowlist blocks OS access while
safe math still runs, plus the RestrictedPython-guarded path when installed.

These exercise :mod:`abax.restricted` directly, the worker wiring in
:mod:`abax.console_worker`, and the bridge/factory selection. The
RestrictedPython-specific case is guarded with ``importorskip`` so the thin CI
env (no RestrictedPython) skips it rather than failing.
"""

from __future__ import annotations

import pytest

from abax import restricted, sandbox
from abax.console_worker import Worker
from abax.core.workbook import Workbook

# --- the executor: blocks OS, allows safe math -------------------------------


def test_restricted_blocks_filesystem_write():
    # open() is a forbidden builtin call AND absent from safe_builtins.
    result = restricted.run_restricted("open('/tmp/abax_probe', 'w').write('x')")
    assert result["error"] is not None
    assert "open" in result["error"]


def test_restricted_blocks_import_os():
    result = restricted.run_restricted("import os\nos.system('echo hi')")
    assert result["error"] is not None
    # The static AST check rejects the import before anything executes.
    assert "os" in result["error"]
    assert "not allowed" in result["error"]


def test_restricted_blocks_subprocess_and_dunder_reflection():
    # The classic reflection escape uses a dunder attribute -> rejected.
    src = "().__class__.__bases__[0].__subclasses__()"
    result = restricted.run_restricted(src)
    assert result["error"] is not None
    assert "dunder" in result["error"]


def test_restricted_allows_safe_math():
    result = restricted.run_restricted(
        "import math\nprint(round(math.sqrt(144)))\nresult = 6 * 7"
    )
    assert result["error"] is None
    assert "12" in result["output"]
    assert result["namespace"]["result"] == 42


def test_restricted_allows_statistics_stdlib():
    result = restricted.run_restricted(
        "import statistics\nprint(statistics.mean([1, 2, 3, 4]))"
    )
    assert result["error"] is None
    assert "2.5" in result["output"]


def test_restrictedpython_available_never_raises():
    # Pure predicate; must return a bool whether or not the package is present.
    assert isinstance(restricted.restrictedpython_available(), bool)


def test_force_stdlib_path_when_rp_absent_still_blocks():
    # use_restrictedpython=False forces the pure fallback; the allowlist must
    # still block os regardless of the optional package.
    result = restricted.run_restricted("import os", use_restrictedpython=False)
    assert result["error"] is not None and "not allowed" in result["error"]


# --- the optional RestrictedPython-guarded compile path ----------------------


def test_restrictedpython_guarded_path_runs_math():
    pytest.importorskip("RestrictedPython")
    # With RestrictedPython present and forced on, safe math still works and the
    # compile guards are injected without breaking anything.
    result = restricted.run_restricted(
        "print(sum([1, 2, 3]))", use_restrictedpython=True
    )
    assert result["error"] is None
    assert "6" in result["output"]


def test_restrictedpython_guarded_path_still_blocks_os():
    pytest.importorskip("RestrictedPython")
    result = restricted.run_restricted("import os", use_restrictedpython=True)
    assert result["error"] is not None
    assert "not allowed" in result["error"]


# --- the sandbox restricted-tier hook ----------------------------------------


def test_restricted_requested_env(monkeypatch):
    monkeypatch.delenv(sandbox.RESTRICTED_ENV, raising=False)
    assert sandbox.restricted_requested() is False
    monkeypatch.setenv(sandbox.RESTRICTED_ENV, "1")
    assert sandbox.restricted_requested() is True
    monkeypatch.setenv(sandbox.RESTRICTED_ENV, "0")
    assert sandbox.restricted_requested() is False


def test_restricted_tier_is_always_available():
    assert sandbox.restricted_available() is True
    assert isinstance(sandbox.restricted_describe(), str)


# --- worker wiring: the exec/script paths honour the tier --------------------


def test_worker_exec_restricted_blocks_os(monkeypatch):
    monkeypatch.setenv(sandbox.RESTRICTED_ENV, "1")
    w = Worker()
    resp = w.handle("import os", Workbook().to_envelope())
    assert resp["error"] is not None
    assert "not allowed" in resp["error"]


def test_worker_exec_restricted_allows_math_and_persists(monkeypatch):
    monkeypatch.setenv(sandbox.RESTRICTED_ENV, "1")
    w = Worker()
    env = Workbook().to_envelope()
    resp = w.handle("x = 21", env)
    assert resp["error"] is None
    resp2 = w.handle("print(x * 2)", env)
    assert resp2["error"] is None and "42" in resp2["output"]


def test_worker_script_restricted_blocks_open(monkeypatch):
    monkeypatch.setenv(sandbox.RESTRICTED_ENV, "1")
    w = Worker()
    resp = w.handle_script("open('x', 'w')", "s.py", Workbook().to_envelope())
    assert resp["error"] is not None
    assert "open" in resp["error"]


def test_worker_exec_unrestricted_allows_os(monkeypatch):
    # Without the flag, the normal (unrestricted) interpreter path runs — os is
    # importable there. Proves the tier is genuinely gated on the env var.
    monkeypatch.delenv(sandbox.RESTRICTED_ENV, raising=False)
    w = Worker()
    resp = w.handle("import os; print(bool(os.getpid()))", Workbook().to_envelope())
    assert "True" in resp["output"]


# --- factory / bridge selection ----------------------------------------------


def test_factory_restricted_sets_flag():
    from abax.gui.console.console_bridge import ConsoleBridge, make_exec_bridge

    b = make_exec_bridge("restricted")
    try:
        assert isinstance(b, ConsoleBridge)
        assert b._restricted is True
        assert b._strict is False
    finally:
        b.close()


def test_restricted_bridge_end_to_end_blocks_os():
    # Full subprocess round-trip: the restricted worker rejects `import os`.
    from abax.gui.console.console_bridge import ConsoleBridge

    b = ConsoleBridge(restricted=True)
    try:
        r = b.execute("import os", Workbook().to_envelope())
        assert r.get("error") is not None
        assert "not allowed" in r["error"]
    finally:
        b.close()


def test_restricted_bridge_end_to_end_allows_math():
    from abax.gui.console.console_bridge import ConsoleBridge

    b = ConsoleBridge(restricted=True)
    try:
        r = b.execute("print(6 * 7)", Workbook().to_envelope())
        assert r.get("error") is None
        assert "42" in r["output"]
    finally:
        b.close()
