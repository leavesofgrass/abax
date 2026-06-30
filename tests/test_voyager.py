"""HP-15C Voyager keypad logic (button presses → RPN state)."""

from __future__ import annotations

from qcell.core.calc.voyager import LEGENDS_15C, VoyagerKeypad, grid_pos

# Button numbers for the keys used below (from LEGENDS_15C primaries).
B = {"7": 17, "8": 18, "9": 19, "4": 27, "5": 28, "6": 29, "1": 37, "2": 38,
     "3": 39, "0": 47, "ENTER": 36, "+": 40, "-": 30, "*": 20, "/": 10,
     "sqrt": 11, "CHS": 16, "STO": 44, "RCL": 45, "f": 42, "g": 43,
     "backspace": 35}


def press(kp: VoyagerKeypad, *buttons: int) -> None:
    for b in buttons:
        kp.press(b)


def test_basic_arithmetic():
    kp = VoyagerKeypad()
    press(kp, B["7"], B["ENTER"], B["8"], B["+"])
    assert kp.rpn.x == 15.0


def test_chained_expression():
    kp = VoyagerKeypad()
    press(kp, B["3"], B["ENTER"], B["4"], B["+"], B["5"], B["*"])
    assert kp.rpn.x == 35.0


def test_primary_sqrt():
    kp = VoyagerKeypad()
    press(kp, B["9"], B["sqrt"])
    assert kp.rpn.x == 3.0


def test_blue_shift_square():
    kp = VoyagerKeypad()
    # g + button 11 (blue legend "x^2") squares X
    press(kp, B["3"], B["g"], 11)
    assert kp.rpn.x == 9.0


def test_gold_shift_factorial():
    kp = VoyagerKeypad()
    # f + button 47 (gold legend "x!") -> factorial
    press(kp, B["5"], B["f"], 47)
    assert kp.rpn.x == 120.0


def test_sto_rcl():
    kp = VoyagerKeypad()
    press(kp, B["7"], B["STO"], B["0"])     # R0 = 7
    press(kp, B["g"], B["backspace"])        # blue of 35 = CLx -> clear X
    assert kp.rpn.x == 0.0
    press(kp, B["RCL"], B["0"])              # recall R0
    assert kp.rpn.x == 7.0


def test_display_reflects_entry_then_value():
    kp = VoyagerKeypad()
    press(kp, B["4"], B["2"])
    assert kp.display() == "42"
    press(kp, B["ENTER"])
    assert kp.display() == "42"


def test_chs_during_entry():
    kp = VoyagerKeypad()
    press(kp, B["5"], B["CHS"])
    # CHS as a token negates X after committing entry
    assert kp.rpn.x == -5.0


def test_grid_positions():
    assert grid_pos(17) == (0, 6)   # "7" key, top row
    assert grid_pos(47) == (3, 6)   # "0" key, bottom row
    assert grid_pos(10) == (0, 9)   # divide, top-right
    assert 36 in LEGENDS_15C and LEGENDS_15C[36][0] == "ENTER"
