"""Macro manager panel (offscreen).

Drives the dialog through its testable seams (``_macro_names`` /
``run_selected``) against a lightweight stub window, so no real MainWindow or
worker process is needed. Covers: both sources appear in the list, running a
registry row calls ``_run_macro``, construction never raises, and the
empty-registry path is handled (Run disabled).
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.gui._qtcompat import QApplication, QWidget  # noqa: E402
from abax.macros import MacroRegistry  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _MenuEntry:
    """Tiny stand-in for abax.userconfig.MacroEntry (name/desc/action)."""

    def __init__(self, name, desc, action):
        self.name = name
        self.desc = desc
        self.action = action


class _UserConfig:
    def __init__(self, macro_menu):
        self.macro_menu = macro_menu


def _make_window(*, with_registry=True, with_menu=True):
    """A QWidget-based stub window with just what the dialog reads."""
    win = QWidget()
    win._run_calls = []
    win._entry_calls = []
    win._load_calls = []

    if with_registry:
        registry = MacroRegistry()

        @registry.macro("alpha")
        def _alpha(ctx):  # noqa: ANN001
            """Alpha macro — first line of doc.

            Second line, ignored by the description box.
            """

        @registry.macro("beta")
        def _beta(ctx):  # noqa: ANN001
            """Beta macro."""

        win._macro_registry = registry
    else:
        win._macro_registry = None

    if with_menu:
        entry = _MenuEntry(
            "init-hello",
            "Say hello from init.py",
            lambda w: w._entry_calls.append("init-hello"),
        )
        win.user_config = _UserConfig([entry])

    win._run_macro = lambda name: win._run_calls.append(name)
    win.load_macros = lambda: win._load_calls.append(True)
    return win


def test_lists_registry_and_initpy_macros(app):
    from abax.gui.dialogs.macro_manager_dialog import MacroManagerDialog

    win = _make_window()
    dlg = MacroManagerDialog(win)

    names = dlg._macro_names()
    assert ("alpha", "macro") in names
    assert ("beta", "macro") in names
    assert ("init-hello", "init.py") in names
    assert len(names) == 3
    assert dlg._run_btn.isEnabled()


def test_run_selected_registry_calls_run_macro(app):
    from abax.gui.dialogs.macro_manager_dialog import MacroManagerDialog

    win = _make_window()
    dlg = MacroManagerDialog(win)

    # Registry macros are listed first (sorted); row 0 is "alpha".
    dlg._list.setCurrentRow(0)
    dlg.run_selected()
    assert win._run_calls == ["alpha"]
    assert win._entry_calls == []


def test_run_selected_initpy_calls_entry_action(app):
    from abax.gui.dialogs.macro_manager_dialog import MacroManagerDialog

    win = _make_window()
    dlg = MacroManagerDialog(win)

    names = dlg._macro_names()
    row = names.index(("init-hello", "init.py"))
    dlg._list.setCurrentRow(row)
    dlg.run_selected()
    assert win._entry_calls == ["init-hello"]
    assert win._run_calls == []


def test_construction_does_not_raise_and_shows_description(app):
    from abax.gui.dialogs.macro_manager_dialog import MacroManagerDialog

    win = _make_window()
    dlg = MacroManagerDialog(win)
    # Selecting the first (alpha) row shows the first doc line only.
    dlg._list.setCurrentRow(0)
    assert dlg._desc.toPlainText() == "Alpha macro — first line of doc."


def test_empty_registry_no_menu_disables_run(app):
    from abax.gui.dialogs.macro_manager_dialog import MacroManagerDialog

    win = _make_window(with_registry=False, with_menu=False)
    dlg = MacroManagerDialog(win)
    assert dlg._macro_names() == []
    assert not dlg._run_btn.isEnabled()
    # Running with nothing selected is a no-op, not a crash.
    dlg.run_selected()


def test_raising_macro_is_caught(app):
    from abax.gui.dialogs.macro_manager_dialog import MacroManagerDialog

    win = _make_window()

    def _boom(name):
        raise RuntimeError("kaboom")

    win._run_macro = _boom
    dlg = MacroManagerDialog(win)
    dlg._list.setCurrentRow(0)
    dlg.run_selected()  # must not raise
    assert "kaboom" in dlg._status.text()


def test_load_file_delegates_to_window(app):
    from abax.gui.dialogs.macro_manager_dialog import MacroManagerDialog

    win = _make_window()
    dlg = MacroManagerDialog(win)
    dlg._load_file()
    assert win._load_calls == [True]
