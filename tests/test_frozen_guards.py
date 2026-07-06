"""Frozen-app (PyInstaller) guards: in a bundled build sys.executable is the
abax exe itself, so "python -c/-m" spawns would relaunch the app, and pip can't
add modules to the bundle. These guards keep the console worker, auto-install,
and the CLI entry point correct when ``sys.frozen`` is set."""

from __future__ import annotations

import subprocess
import sys

import pytest

from abax import autodeps


@pytest.fixture()
def frozen(monkeypatch):
    """Simulate a PyInstaller bundle (sys.frozen truthy)."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    yield
    # monkeypatch restores/removes the attribute on teardown


def test_autodeps_disabled_when_frozen(frozen):
    # Force-disabled even when a caller explicitly enables auto-install.
    autodeps.set_enabled(True)
    try:
        assert autodeps.enabled() is False
    finally:
        autodeps.set_enabled(None)


def test_autodeps_enabled_unfrozen_baseline(monkeypatch):
    monkeypatch.delenv("ABAX_NO_AUTOINSTALL", raising=False)
    autodeps.set_enabled(True)
    try:
        assert autodeps.enabled() is True
    finally:
        autodeps.set_enabled(None)


def test_pip_install_fail_closed_when_frozen(frozen, monkeypatch):
    # Never even attempts a subprocess: "abax.exe -m pip" would relaunch the app.
    def _boom(*a, **k):  # pragma: no cover — the guard must prevent the call
        raise AssertionError("pip subprocess must not be spawned in a frozen app")

    monkeypatch.setattr(subprocess, "run", _boom)
    assert autodeps._pip_install("msgspec") is False


def test_entry_point_worker_escape_hatch(monkeypatch):
    # ``abax --run-console-worker`` becomes the isolated worker and nothing
    # else — no argparse, no Qt. (This is what a frozen bridge spawns.)
    import abax.console_worker as cw
    from abax.app import main

    called = {}
    monkeypatch.setattr(cw, "main", lambda: called.setdefault("worker", True))
    rc = main(["--run-console-worker"])
    assert rc == 0
    assert called == {"worker": True}


def test_entry_point_normal_cli_unaffected(capsys):
    from abax.app import main

    assert main(["--version"]) == 0
    from abax import __version__

    assert __version__ in capsys.readouterr().out
