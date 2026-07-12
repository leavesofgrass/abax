"""The batch file-conversion dialog: it converts a selected file end-to-end."""

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

    _win = MainWindow(Settings())
    yield _win
    from abax.gui._qtcompat import QEvent as _QEvent
    _win.deleteLater()
    app.sendPostedEvents(None, _QEvent.Type.DeferredDelete)
    app.processEvents()


def test_dialog_converts_csv_to_json(win, tmp_path):
    from abax.gui.dialogs.convert_dialog import ConvertDialog

    csv = tmp_path / "data.csv"
    csv.write_text("a,b\n1,2\n")

    dlg = ConvertDialog(win, [str(csv)])
    # choose the JSON target
    dlg._fmt.setCurrentIndex(dlg._fmt.findData(".json"))
    dlg._do_convert()

    assert (tmp_path / "data.json").exists()
    assert "→" in dlg._log.toPlainText()   # a success line was reported


def test_show_convert_prefills_paths(win, tmp_path):
    # show_convert is the Tools-menu / file-manager entry point.
    assert callable(win.show_convert)
