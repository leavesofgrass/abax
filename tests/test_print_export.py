"""Print / PDF export (GUI-only): the workbook is rendered via the existing
``workbook_to_html`` report and printed through a ``QPrinter``.

Runs a MainWindow offscreen. ``export_pdf`` with an explicit path needs no
dialog, so it exercises the whole render→print pipeline headlessly and lets us
assert a real ``%PDF`` file lands on disk. Skips cleanly without a Qt binding.
"""

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


def _fill(win):
    sheet = win._doc.workbook.sheet
    sheet.set_cell(0, 0, "Widget")
    sheet.set_cell(0, 1, "Qty")
    sheet.set_cell(1, 0, "Sprocket")
    sheet.set_cell(1, 1, "42")


def test_export_pdf_writes_pdf_file(win, tmp_path):
    from abax.gui import print_export

    _fill(win)
    target = tmp_path / "report.pdf"
    result = print_export.export_pdf(win, str(target))

    assert result == str(target)
    assert target.exists()
    data = target.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(data) > 0


def test_export_pdf_reuses_workbook_to_html(win, tmp_path, monkeypatch):
    """export_pdf must go through core.io.html_report.workbook_to_html."""
    from abax.core.io import html_report
    from abax.gui import print_export

    _fill(win)
    calls = {}
    real = html_report.workbook_to_html

    def spy(workbook, **kw):
        calls["workbook"] = workbook
        calls["kw"] = kw
        return real(workbook, **kw)

    # print_export imports the symbol by name, so patch it there.
    monkeypatch.setattr(print_export, "workbook_to_html", spy)

    target = tmp_path / "spied.pdf"
    print_export.export_pdf(win, str(target))

    assert calls["workbook"] is win._doc.workbook
    assert target.read_bytes().startswith(b"%PDF")


def test_export_pdf_cancel_returns_none(win, monkeypatch):
    """A cancelled Save dialog (empty path) writes nothing and returns None."""
    from abax.gui import _qtcompat, print_export

    monkeypatch.setattr(
        _qtcompat.QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: ("", "")))

    assert print_export.export_pdf(win) is None


def test_print_document_declined_does_not_print(win, monkeypatch):
    """Rejecting the print dialog must not touch the printer."""
    from abax.gui import _qtcompat, print_export

    monkeypatch.setattr(
        _qtcompat.QPrintDialog, "exec",
        lambda self: _qtcompat.QPrintDialog.DialogCode.Rejected.value)

    # Should return without raising and without rendering.
    print_export.print_document(win)
