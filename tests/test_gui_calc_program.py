"""The keystroke-program run/step panel (abax.gui.calc.program_panel).

Headless Qt (offscreen). Drives the panel against a real Voyager faceplate:
record captures presses, Run executes the recorded program through the keypad,
and the infinite-loop guard surfaces as a status message rather than hanging.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.gui._qtcompat import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _faceplate():
    from abax.gui.calc.faceplate import VoyagerFaceplate

    return VoyagerFaceplate()


def test_record_run_through_panel(app):
    from abax.gui.calc.program_panel import ProgramPanel

    fp = _faceplate()
    panel = ProgramPanel(fp)
    # Arm recording and press 7 ENTER 8 + on the faceplate's keypad.
    panel._toggle_record(True)
    for b in (17, 36, 18, 40):
        fp.keypad.press(b)
    panel._toggle_record(False)
    assert len(panel.program) == 4
    assert fp.keypad.rpn.x == pytest.approx(15.0)

    # Clear the live stack, then Run replays the recorded program to reach 15.
    fp.keypad.rpn.reset()
    panel._run()
    assert fp.keypad.rpn.x == pytest.approx(15.0)
    panel.deleteLater()
    fp.deleteLater()


def test_single_step_button_advances(app):
    from abax.core.calc.program import Step
    from abax.gui.calc.program_panel import ProgramPanel

    fp = _faceplate()
    panel = ProgramPanel(fp)
    panel.append_step(Step.feed("6"))
    panel.append_step(Step.feed("7"))
    panel.append_step(Step.feed("*"))
    panel._single_step()          # feed 6
    assert fp.keypad.rpn.x == pytest.approx(6.0)
    panel._single_step()          # feed 7
    panel._single_step()          # *
    assert fp.keypad.rpn.x == pytest.approx(42.0)
    panel.deleteLater()
    fp.deleteLater()


def test_infinite_loop_reports_not_hangs(app):
    from abax.core.calc.program import Step
    from abax.gui.calc.program_panel import ProgramPanel

    fp = _faceplate()
    panel = ProgramPanel(fp, step_cap=200)
    panel.append_step(Step.lbl("a"))
    panel.append_step(Step.gto("a"))
    panel._run()                  # must return quickly, not hang
    assert "step cap" in panel._status.text().lower()
    panel.deleteLater()
    fp.deleteLater()


def test_empty_program_is_guarded(app):
    from abax.gui.calc.program_panel import ProgramPanel

    fp = _faceplate()
    panel = ProgramPanel(fp)
    panel._run()
    assert "empty" in panel._status.text().lower()
    panel.deleteLater()
    fp.deleteLater()


# --- wiring: the panel is reachable from the calculator window ----------------


@pytest.fixture()
def win(app):
    from abax.settings import Settings
    from abax.gui.main_window import MainWindow

    _win = MainWindow(Settings())
    yield _win
    from abax.gui._qtcompat import QEvent as _QEvent
    _win.deleteLater()
    app.sendPostedEvents(None, _QEvent.Type.DeferredDelete)
    app.processEvents()


def test_show_program_panel_wires_faceplate(win):
    # The palette action opens the calculator and shows the program panel,
    # pointed at the live HP faceplate (default model is an HP).
    win.show_program_panel()
    calc = win._calc_panel()
    assert calc is not None and calc._kind == "hp"
    assert calc._prog_panel is not None
    assert calc._prog_panel.isVisible()
    assert calc._prog_panel._keypad() is not None          # recorder is armed-able
    assert calc._prog_btn.isChecked()
    # Toggling off hides it but keeps the recorded program.
    calc.toggle_program_panel(False)
    assert not calc._prog_panel.isVisible()
    assert not calc._prog_btn.isChecked()


def test_program_panel_hides_for_non_rpn_models(win):
    win.show_program_panel()
    calc = win._calc_panel()
    assert calc._prog_panel.isVisible()
    # Switch to a TI model: the program panel and its toggle disappear, and the
    # panel is detached from the (now-deleted) HP faceplate.
    ti_ix = next(i for i in range(calc._model_box.count())
                 if calc._model_box.itemData(i)[0] == "ti")
    calc._model_box.setCurrentIndex(ti_ix)
    assert calc._kind == "ti"
    assert not calc._prog_panel.isVisible()
    assert not calc._prog_btn.isVisible()
    assert calc._prog_panel._keypad() is None
    # Back to an HP model: the toggle returns and reattaches to the new keypad.
    hp_ix = next(i for i in range(calc._model_box.count())
                 if calc._model_box.itemData(i)[0] == "hp")
    calc._model_box.setCurrentIndex(hp_ix)
    assert calc._prog_btn.isVisible()
    calc.toggle_program_panel(True)
    assert calc._prog_panel.isVisible()
    assert calc._prog_panel._keypad() is not None


def test_palette_lists_program_memory(win):
    actions = win._palette_actions()
    assert "Calculator program memory (record / run)..." in actions
