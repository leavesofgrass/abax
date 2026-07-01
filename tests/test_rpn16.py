"""Tests for the HP-16C integer RPN engine (:mod:`abax.core.calc.rpn16`)."""

from __future__ import annotations

import pytest

from abax.core.calc.rpn16 import RPN16, RPN16Error, Voyager16Keypad


def test_hex_and() -> None:
    r = RPN16(base=16)
    assert r.eval_line("FF AA AND") == 0xAA


def test_hex_math_lift() -> None:
    # Always-lift model: FF AA OR.
    r = RPN16(base=16)
    assert r.eval_line("F0 0F OR") == 0xFF


def test_integer_arithmetic() -> None:
    r = RPN16(base=10)
    assert r.eval_line("3 4 +") == 7
    r.reset()
    assert r.eval_line("10 3 -") == 7
    r.reset()
    assert r.eval_line("6 7 *") == 42


def test_integer_division() -> None:
    r = RPN16(base=10)
    assert r.eval_line("17 5 /") == 3


def test_divide_by_zero() -> None:
    r = RPN16(base=10)
    with pytest.raises(RPN16Error):
        r.eval_line("5 0 /")


def test_not() -> None:
    r = RPN16(word_size=8, base=10)
    r.eval_line("0 NOT")
    assert r.x == 0xFF


def test_xor() -> None:
    r = RPN16(base=16)
    assert r.eval_line("FF 0F XOR") == 0xF0


def test_or() -> None:
    r = RPN16(base=16)
    assert r.eval_line("F0 0F OR") == 0xFF


def test_shift_left() -> None:
    r = RPN16(base=10)
    assert r.eval_line("1 SL") == 2


def test_shift_right() -> None:
    r = RPN16(base=10)
    assert r.eval_line("4 SR") == 2


def test_rotate_left() -> None:
    r = RPN16(word_size=8, base=16)
    # 0x80 rotate-left in 8 bits -> 0x01.
    assert r.eval_line("80 RL") == 0x01


def test_rotate_right() -> None:
    r = RPN16(word_size=8, base=16)
    # 0x01 rotate-right in 8 bits -> 0x80.
    assert r.eval_line("1 RR") == 0x80


def test_chs_twos_complement() -> None:
    r = RPN16(word_size=8, base=10, signed=True)
    r.eval_line("1 CHS")
    assert r.x == 0xFF  # -1 stored unsigned in 8 bits


def test_signed_display() -> None:
    r = RPN16(word_size=8, base=16, signed=True)
    r.eval_line("1 CHS")
    assert r.display() == "FF h"
    r.base = 10
    assert r.display() == "-1 d"


def test_unsigned_display() -> None:
    r = RPN16(word_size=8, base=16, signed=False)
    r.eval_line("1 CHS")
    assert r.display() == "FF h"
    r.base = 10
    assert r.display() == "255 d"


def test_base_switch_display() -> None:
    r = RPN16(word_size=8, base=16, signed=True)
    r.eval_line("FF")
    assert r.display() == "FF h"  # hex shows the raw bit pattern
    r2 = RPN16(word_size=8, base=10, signed=False)
    r2.eval_line("255")
    assert r2.display() == "255 d"
    r2.feed("oct")
    assert r2.display() == "377 o"
    r2.feed("bin")
    assert r2.display() == "11111111 b"


def test_word_size_wrap() -> None:
    r = RPN16(word_size=8, base=16)
    assert r.eval_line("FF 1 +") == 0


def test_wsize_token_remasks() -> None:
    r = RPN16(word_size=16, base=16)
    r.eval_line("FFFF")
    assert r.x == 0xFFFF
    r.eval_line("wsize 8")
    assert r.x == 0xFF


def test_swap_and_stack() -> None:
    r = RPN16(base=10)
    r.eval_line("1 2 3")
    r.feed("swap")
    assert r.x == 2 and r.y == 3
    r.feed("rdn")
    assert r.x == 3


def test_clx_lastx() -> None:
    r = RPN16(base=10)
    r.eval_line("9 3 /")  # last_x becomes 3
    assert r.x == 3
    r.feed("clx")
    assert r.x == 0
    r.feed("lastx")
    assert r.x == 3


def test_sto_rcl() -> None:
    r = RPN16(base=10)
    r.eval_line("42 sto 0")
    r.eval_line("clx")
    r.eval_line("rcl 0")
    assert r.x == 42


def test_to_dict_roundtrip() -> None:
    r = RPN16(word_size=8, base=8, signed=False)
    r.eval_line("200 100")
    r.regs["R5"] = 7
    d = r.to_dict()
    r2 = RPN16()
    r2.load_dict(d)
    assert r2.to_dict() == d
    assert r2.stack == r.stack
    assert r2.word_size == 8 and r2.base == 8 and r2.signed is False


def test_unknown_token() -> None:
    r = RPN16(base=10)
    with pytest.raises(RPN16Error):
        r.feed("frobnicate")


def test_invalid_digit_for_base() -> None:
    # 'F' is not a valid digit in base 10, so it is an unknown token.
    r = RPN16(base=10)
    with pytest.raises(RPN16Error):
        r.feed("FF")


# -- keypad ----------------------------------------------------------------


def test_keypad_hex_digits_and_and() -> None:
    # Default RPN16 base is 16. Press: F, ENTER, F, AND.
    kp = Voyager16Keypad()
    kp.press(16)  # F
    kp.press(36)  # ENTER
    kp.press(16)  # F
    # gold AND lives on button 20 (multiply).
    kp.press(42)  # f shift
    kp.press(20)  # AND
    assert kp.rpn.x == 0xF


def test_keypad_ff_and_0f() -> None:
    # FF ENTER 0F AND -> 0x0F.
    kp = Voyager16Keypad()
    kp.press(16)  # F
    kp.press(16)  # F -> entry "FF"
    kp.press(36)  # ENTER -> push 0xFF
    kp.press(47)  # 0
    kp.press(16)  # F -> entry "0F"
    kp.press(42)  # f shift
    kp.press(20)  # gold AND
    assert kp.rpn.x == 0x0F


def test_keypad_base_switch() -> None:
    kp = Voyager16Keypad()
    kp.press(16)  # F
    kp.press(16)  # F -> entry "FF"
    kp.press(24)  # DEC -> commits entry then switches base
    assert kp.rpn.base == 10
    assert kp.rpn.x == 0xFF
    assert kp.display() == "255 d"


def test_keypad_not_implemented() -> None:
    kp = Voyager16Keypad()
    kp.press(43)  # g shift
    kp.press(25)  # blue 'sqrt' -> not implemented
    assert "not implemented" in kp.message


def test_keypad_chs() -> None:
    kp = Voyager16Keypad()
    kp.rpn.set_word_size(8)
    kp.press(16)  # F
    kp.press(16)  # FF
    kp.press(36)  # ENTER -> 0xFF
    kp.press(49)  # CHS
    # -(-1) interpreted signed... 0xFF is -1 signed, CHS -> 1
    assert kp.rpn.x == 1
