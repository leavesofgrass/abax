"""The Qt vector faceplate constructs and drives the keypad offscreen."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.core.calc.voyager import LEGENDS_15C, VoyagerKeypad  # noqa: E402
from abax.gui._qtcompat import QApplication  # noqa: E402
from abax.gui.calc.faceplate import VoyagerFaceplate  # noqa: E402

# Reverse-lookup: primary legend -> button number (for readable presses).
_BY_PRIMARY = {legends[0]: n for n, legends in LEGENDS_15C.items()}

DIGIT = {str(d): _BY_PRIMARY[str(d)] for d in range(10)}
ENTER = _BY_PRIMARY["ENTER"]
ADD = _BY_PRIMARY["add"]
MUL = _BY_PRIMARY["multiply"]


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def test_constructs_offscreen(app):
    fp = VoyagerFaceplate(VoyagerKeypad())
    assert fp.display() == "0"
    # The widget is built but never shown — no visible window required.
    assert not fp.isVisible()


def test_seven_enter_eight_add(app):
    fp = VoyagerFaceplate(VoyagerKeypad())
    for number in (DIGIT["7"], ENTER, DIGIT["8"], ADD):
        fp._press(number)
    assert fp.keypad.rpn.x == pytest.approx(15.0)
    assert fp.display() == "15"


def test_seventy_seven_enter_then_add(app):
    # Multi-digit live entry: 7 7 ENTER 8 + -> 85.
    fp = VoyagerFaceplate(VoyagerKeypad())
    for number in (DIGIT["7"], DIGIT["7"], ENTER, DIGIT["8"], ADD):
        fp._press(number)
    assert fp.keypad.rpn.x == pytest.approx(85.0)
    assert fp.display() == "85"


def test_interleaved_multiply(app):
    # 3 ENTER 4 + 5 * -> 35 (automatic stack lift).
    fp = VoyagerFaceplate(VoyagerKeypad())
    for number in (DIGIT["3"], ENTER, DIGIT["4"], ADD, DIGIT["5"], MUL):
        fp._press(number)
    assert fp.keypad.rpn.x == pytest.approx(35.0)


def test_display_updates_during_entry(app):
    fp = VoyagerFaceplate(VoyagerKeypad())
    fp._press(DIGIT["4"])
    fp._press(DIGIT["2"])
    assert fp.display() == "42"
    assert fp._lcd.text() == "42"
