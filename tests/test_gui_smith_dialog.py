"""Smith chart dialog — complex-load matching, drawn match paths, accessibility."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.gui._qtcompat import QApplication, Qt  # noqa: E402
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


def test_analyse_uses_the_reactance():
    from abax.core.science import rf
    from abax.gui.dialogs.smith_dialog import analyse

    res = analyse(75, 25, 50, 14.2e6)
    assert len(res["solutions"]) >= 2
    for sol, path in zip(res["solutions"], res["paths"]):
        zin = rf.match_input_impedance(complex(75, 25), sol["topology"],
                                       sol["series_x"], sol["shunt_b"])
        assert abs(zin - 50) < 1e-6                     # matches the COMPLEX load
        assert abs(path[-1]) < 1e-6
    assert "VSWR = 1.77:1" in res["lines"]
    assert "upper (inductive)" in res["description"]
    assert "lower (capacitive)" in analyse(30, -20, 50, 7e6)["description"]


def test_dialog_draws_selected_match_and_describes_it(win):
    from abax.gui.dialogs.smith_dialog import SmithDialog

    dlg = SmithDialog(win)
    chart = dlg._chart
    assert chart.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert chart.accessibleName() == "Smith chart"
    assert dlg._solution.count() >= 3                   # "None" + ≥2 matches
    assert dlg._solution.currentIndex() == 1 and chart._path
    desc = chart.accessibleDescription()
    assert desc == dlg._summary.text() and "path of match 1" in desc
    dlg._solution.setCurrentIndex(0)                    # "None": no path drawn
    assert not chart._path and "path of match" not in chart.accessibleDescription()
    dlg._solution.setCurrentIndex(2)
    assert "path of match 2" in chart.accessibleDescription()
    dlg._x.setText("-40")
    dlg._plot()
    assert "capacitive" in chart.accessibleDescription()
    dlg._r.setText("abc")
    dlg._plot()
    assert "Enter numeric" in dlg._readout.toPlainText()
    dlg.close()


def test_matched_load_and_render(win):
    from abax.gui.dialogs.smith_dialog import SmithDialog

    dlg = SmithDialog(win)
    dlg._r.setText("50")
    dlg._x.setText("0")
    dlg._plot()
    assert "Already matched" in dlg._readout.toPlainText()
    assert dlg._solution.count() == 1
    dlg._r.setText("75")
    dlg._x.setText("25")
    dlg._plot()
    dlg.resize(760, 480)
    dlg.show()
    QApplication.processEvents()
    img = dlg._chart.grab()
    assert not img.isNull()
    out = os.environ.get("ABAX_SNAPSHOT_DIR")
    if out:
        img.save(os.path.join(out, "smith.png"))
    dlg.close()
