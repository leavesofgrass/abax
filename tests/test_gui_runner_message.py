"""The "you have no Qt binding" message `abax gui` prints when it can't launch.

This is the first thing a new user sees when the GUI won't start, and it drifted
once already (issue #4): it named PyQt6 while pointing at ``abax[gui]``, which
installs PySide6 — and the guard it sits behind (``_runtime._HAS_QT``) doesn't
test a specific binding at all. So these tests pin *properties*, not the wording:

* the guard returns 1 and writes to stderr,
* the diagnosis names the condition (a Qt binding), not one binding,
* every ``abax[...]`` extra it names really exists in pyproject.toml, and really
  installs the binding named beside it,
* both bindings are reachable, and the TUI fallback is still offered.

Needs no Qt binding installed or absent — the guard returns before any Qt import.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

BINDINGS = ("PySide6", "PyQt6")
_EXTRA_RE = re.compile(r"abax\[([A-Za-z0-9._-]+)\]")


@pytest.fixture
def no_qt_launch(monkeypatch, capsys):
    """Run ``run_gui`` with no Qt binding available; return (rc, stdout, stderr)."""
    from abax import _runtime as rt
    from abax.gui.runner import run_gui

    monkeypatch.setattr(rt, "_HAS_QT", False)
    rc = run_gui()
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


def _extras() -> dict[str, list[str]]:
    root = Path(__file__).resolve().parent.parent
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["optional-dependencies"]


def test_guard_fails_with_a_message_on_stderr(no_qt_launch):
    rc, out, err = no_qt_launch
    assert rc == 1
    assert out == ""
    assert err.strip(), "the failed launch must explain itself"


def test_diagnosis_names_the_condition_not_a_binding(no_qt_launch):
    """``_HAS_QT`` is PySide6 *or* PyQt6, so the message may not blame one of them."""
    _, _, err = no_qt_launch
    diagnosis = err.splitlines()[0]
    # \bQt\b so "PyQt6" doesn't satisfy this by accident.
    assert re.search(r"\bQt\b", diagnosis) and "installed" in diagnosis, (
        f"first line should state that no Qt binding is installed: {diagnosis!r}")
    assert not any(b in diagnosis for b in BINDINGS), (
        f"the check is binding-agnostic; the diagnosis must not name one: {diagnosis!r}")
    for line in err.splitlines():
        if "not installed" in line:
            assert not any(b in line for b in BINDINGS), (
                f"claims a specific binding is missing, but that was never tested: {line!r}")


def test_named_extras_exist_and_install_the_binding_beside_them(no_qt_launch):
    """The exact drift from issue #4: extra named, different package installed."""
    _, _, err = no_qt_launch
    extras = _extras()
    named: set[str] = set()
    for line in err.splitlines():
        for extra in _EXTRA_RE.findall(line):
            assert extra in extras, f"abax[{extra}] is not an extra in pyproject.toml"
            named.add(extra)
            deps = " ".join(extras[extra])
            for binding in BINDINGS:
                if binding in line:
                    assert binding in deps, (
                        f"message offers abax[{extra}] for {binding}, but that extra "
                        f"installs {extras[extra]}")
    assert named, "the message must tell the user what to install"


def test_both_bindings_are_reachable_from_the_message(no_qt_launch):
    """A user who wants PySide6 *or* PyQt6 gets a command that installs it."""
    _, _, err = no_qt_launch
    extras = _extras()
    named = set(_EXTRA_RE.findall(err))
    for binding in BINDINGS:
        assert any(
            any(binding in dep for dep in extras[extra])
            for extra in named
            if extra in extras
        ), f"no extra offered by the message installs {binding} (offered: {sorted(named)})"


def test_tui_fallback_is_still_offered(no_qt_launch):
    _, _, err = no_qt_launch
    assert "abax tui" in err
