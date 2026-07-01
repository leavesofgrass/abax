"""Consent gate for code-execution surfaces (console / terminal / scripts / macros)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.gui._qtcompat import QApplication  # noqa: E402
from abax.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    from abax.gui.main_window import MainWindow

    return MainWindow(Settings())


def test_consent_fast_path_when_already_granted(win):
    win._settings.code_consent = True
    assert win._require_code_consent("anything") is True   # no dialog shown


def test_declined_gate_blocks_every_entry_point(win, monkeypatch):
    win._settings.code_consent = False
    asked: list[str] = []
    # Stand in for the modal dialog: record the prompt and decline.
    monkeypatch.setattr(type(win), "_require_code_consent",
                        lambda self, what="?": (asked.append(what) or False))

    win.show_pyconsole()
    win.show_terminal()
    win.run_script()
    win.load_macros()

    assert len(asked) == 4                                  # all four gated
    assert getattr(win, "_pyconsole_dock", None) is None    # console never opened
    assert win._settings.code_consent is False              # declining doesn't grant
