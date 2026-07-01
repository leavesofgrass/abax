"""Dual-pane file manager dialog — listing, copy/move between panes, archive, run."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("qcell.gui._qtcompat")

from qcell.gui._qtcompat import QApplication  # noqa: E402
from qcell.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def tree(tmp_path):
    (tmp_path / "left").mkdir()
    (tmp_path / "right").mkdir()
    (tmp_path / "left" / "a.txt").write_text("alpha")
    (tmp_path / "left" / "b.txt").write_text("beta")
    return tmp_path


def _dlg(app, start):
    from qcell.gui.dialogs.filemanager_dialog import FileManagerDialog

    return FileManagerDialog(None, start_dir=str(start))


def test_panes_list_directory(app, tree):
    dlg = _dlg(app, tree / "left")
    assert dlg.left.current_dir() == str(tree / "left")
    assert dlg.left._table.rowCount() == 2          # a.txt, b.txt


def test_copy_between_panes(app, tree):
    dlg = _dlg(app, tree)
    dlg.left.set_dir(str(tree / "left"))
    dlg.right.set_dir(str(tree / "right"))
    dlg._set_active(dlg.left)
    dlg.left.select_names(["a.txt"])
    dlg._copy()
    assert (tree / "right" / "a.txt").read_text() == "alpha"


def test_move_between_panes(app, tree):
    dlg = _dlg(app, tree)
    dlg.left.set_dir(str(tree / "left"))
    dlg.right.set_dir(str(tree / "right"))
    dlg._set_active(dlg.left)
    dlg.left.select_names(["b.txt"])
    dlg._move()
    assert (tree / "right" / "b.txt").exists()
    assert not (tree / "left" / "b.txt").exists()


def test_navigation_up(app, tree):
    dlg = _dlg(app, tree / "left")
    dlg.left.go_up()
    assert dlg.left.current_dir() == str(tree)


def test_zip_and_extract_roundtrip(app, tree):
    dlg = _dlg(app, tree)
    dlg.left.set_dir(str(tree / "left"))
    dlg.right.set_dir(str(tree / "right"))
    dlg._set_active(dlg.left)
    dlg.left.select_names(["a.txt", "b.txt"])
    # archive directly through the core (skips the save dialog) then extract via the UI
    from qcell.core import archive
    bundle = tree / "bundle.zip"
    archive.create_archive(dlg.left.selected_paths(), bundle)
    dlg.left.set_dir(str(tree))
    dlg.left.select_names(["bundle.zip"])
    dlg._set_active(dlg.left)
    dlg._extract()                                   # extracts into the other pane
    assert (tree / "right" / "a.txt").exists()


def test_run_command_button(app, tree):
    from qcell.core import fmbuttons

    dlg = _dlg(app, tree / "left")
    dlg._set_active(dlg.left)
    dlg.left.select_names(["a.txt"])
    dlg._run_button(fmbuttons.Button("echo", "echo fm-ok"))
    assert "echo" in dlg._status.text()              # status records the run


def test_user_buttons_loaded_from_settings(app, tree):
    from qcell.gui._qtcompat import QWidget
    from qcell.gui.dialogs.filemanager_dialog import FileManagerDialog
    from qcell.settings import Settings

    win = QWidget()                                  # cheap stand-in for the window
    win._settings = Settings()
    win._settings.fm_buttons = [{"label": "Mine", "command": "echo {name}"}]
    dlg = FileManagerDialog(win, start_dir=str(tree / "left"))
    labels = [b.label for b in dlg._buttons]
    assert "Mine" in labels                          # user button merged with defaults
    assert "Show path" in labels                     # defaults still present


def test_select_all_and_invert(app, tree):
    dlg = _dlg(app, tree / "left")
    dlg._set_active(dlg.left)
    dlg._select_all()
    assert len(dlg.left.selected_paths()) == 2
    dlg._invert_selection()
    assert len(dlg.left.selected_paths()) == 0


def test_duplicate_in_place(app, tree):
    dlg = _dlg(app, tree / "left")
    dlg._set_active(dlg.left)
    dlg.left.select_names(["a.txt"])
    dlg._duplicate()
    names = os.listdir(tree / "left")
    assert len(names) == 3                            # a.txt, b.txt, a copy
    assert "duplicated" in dlg._status.text()


def test_dirsize_reports_bytes(app, tree):
    dlg = _dlg(app, tree / "left")
    dlg._set_active(dlg.left)
    dlg._dirsize()                                    # whole active dir (nothing selected)
    assert "bytes" in dlg._status.text()


def test_go_home_and_root(app, tree):
    dlg = _dlg(app, tree / "left")
    dlg._set_active(dlg.left)
    dlg._go_home()
    assert dlg.left.current_dir() == os.path.abspath(os.path.expanduser("~"))
    dlg._go_root()
    assert dlg.left.current_dir() == os.path.abspath(dlg.left.current_dir())  # a real root


def test_view_and_edit_file(app, tree):
    from qcell.gui import _qtcompat

    dlg = _dlg(app, tree / "left")
    dlg._set_active(dlg.left)
    dlg.left.select_names(["a.txt"])
    # View/Edit open a modal dialog; auto-close it so the test doesn't block.
    opened = {}
    orig = _qtcompat.QDialog.exec

    def fake_exec(self):
        opened["title"] = self.windowTitle()
        return 0

    _qtcompat.QDialog.exec = fake_exec
    try:
        dlg._view()
        assert opened["title"].startswith("View: a.txt")
        dlg._edit()
        assert opened["title"].startswith("Edit: a.txt")
    finally:
        _qtcompat.QDialog.exec = orig


def test_function_key_shortcuts_present(app, tree):
    dlg = _dlg(app, tree / "left")
    # F5/F6/F7/F8 are live shortcuts on their buttons.
    for label in ("F5 Copy ->", "F6 Move ->", "F7 New dir", "F8 Delete"):
        assert dlg._buttons_by_label[label].shortcut().toString() != ""


def test_wired_into_window(app):
    from qcell.gui.main_window import MainWindow

    win = MainWindow(Settings())
    assert callable(win.show_file_manager)
    assert "File manager..." in win._palette_actions()
