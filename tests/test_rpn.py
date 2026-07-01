"""The pure-Python HP-style RPN calculator engine (abax.core.calc.rpn)."""

from __future__ import annotations

import math

import pytest

from abax.core.calc.rpn import RPN, RPNError


def test_always_lift_interleaved():
    assert RPN().eval_line("3 4 + 5 *") == pytest.approx(35.0)


def test_simple_add():
    assert RPN().eval_line("3 4 +") == pytest.approx(7.0)


def test_subtraction_order():
    # Binary minus is Y - X.
    assert RPN().eval_line("10 3 -") == pytest.approx(7.0)


def test_division_order():
    # Binary divide is Y / X.
    assert RPN().eval_line("12 4 /") == pytest.approx(3.0)


def test_divide_by_zero_raises():
    with pytest.raises(RPNError):
        RPN().eval_line("1 0 /")


def test_power():
    assert RPN().eval_line("2 10 ^") == pytest.approx(1024.0)
    assert RPN().eval_line("2 10 pow") == pytest.approx(1024.0)


def test_sqrt_and_negative_sqrt_error():
    assert RPN().eval_line("9 sqrt") == pytest.approx(3.0)
    with pytest.raises(RPNError):
        RPN().eval_line("-1 sqrt")


def test_inv_and_zero_error():
    assert RPN().eval_line("4 1/x") == pytest.approx(0.25)
    assert RPN().eval_line("4 inv") == pytest.approx(0.25)
    with pytest.raises(RPNError):
        RPN().eval_line("0 1/x")


def test_chs():
    assert RPN().eval_line("5 chs") == pytest.approx(-5.0)


def test_swap():
    r = RPN()
    r.eval_line("3 4 swap")
    assert r.x == pytest.approx(3.0)
    assert r.y == pytest.approx(4.0)


def test_rolldown():
    r = RPN()
    # Stack becomes X=4, Y=3, Z=2, T=1.
    r.eval_line("1 2 3 4")
    r.feed("rdn")
    assert r.x == pytest.approx(3.0)
    assert r.y == pytest.approx(2.0)
    assert r.z == pytest.approx(1.0)
    assert r.t == pytest.approx(4.0)


def test_lastx():
    r = RPN()
    r.eval_line("8 2 /")  # X=4, last_x=2
    assert r.x == pytest.approx(4.0)
    r.feed("lastx")
    assert r.x == pytest.approx(2.0)
    assert r.y == pytest.approx(4.0)


def test_sin_degrees():
    assert RPN().eval_line("90 sin") == pytest.approx(1.0)


def test_sin_radians():
    r = RPN()
    r.feed("rad")
    assert r.eval_line(f"{math.pi / 2} sin") == pytest.approx(1.0)


def test_inverse_trig_degrees():
    assert RPN().eval_line("1 asin") == pytest.approx(90.0)


def test_pi():
    assert RPN().eval_line("pi") == pytest.approx(math.pi)


def test_e_constant():
    assert RPN().eval_line("e") == pytest.approx(math.e)


def test_sto_rcl():
    assert RPN().eval_line("5 sto 0 clx rcl 0") == pytest.approx(5.0)


def test_sto_rcl_single_token():
    r = RPN()
    r.eval_line("7 sto0 clx")
    assert r.x == pytest.approx(0.0)
    r.feed("rcl0")
    assert r.x == pytest.approx(7.0)


def test_rcl_unknown_register_is_zero():
    assert RPN().eval_line("rcl 9") == pytest.approx(0.0)


def test_to_dict_load_dict_roundtrip():
    r = RPN()
    r.eval_line("1 2 3 4")
    r.eval_line("5 sto 0")
    r.feed("rad")
    d = r.to_dict()
    assert d["stack"][0] == pytest.approx(r.x)
    assert d["registers"]["R0"] == pytest.approx(5.0)

    r2 = RPN()
    r2.load_dict(d)
    assert r2.stack == pytest.approx(r.stack)
    assert r2.regs == r.regs
    assert r2.angle == r.angle
    assert r2.last_x == pytest.approx(r.last_x)


def test_load_dict_tolerates_missing_and_short_stack():
    r = RPN()
    r.load_dict({"stack": [1.0, 2.0]})  # short stack, no registers/angle/last_x
    assert r.stack == pytest.approx([1.0, 2.0, 0.0, 0.0])
    assert r.regs == {}
    assert r.angle == "DEG"
    assert r.last_x == pytest.approx(0.0)


def test_load_dict_truncates_long_stack():
    r = RPN()
    r.load_dict({"stack": [1.0, 2.0, 3.0, 4.0, 5.0]})
    assert r.stack == pytest.approx([1.0, 2.0, 3.0, 4.0])


def test_factorial():
    assert RPN().eval_line("5 fact") == pytest.approx(120.0)
    assert RPN().eval_line("5 !") == pytest.approx(120.0)
    with pytest.raises(RPNError):
        RPN().eval_line("-1 fact")
    with pytest.raises(RPNError):
        RPN().eval_line("2.5 fact")


def test_percent():
    r = RPN()
    r.eval_line("200 10 %")  # Y=200, X=10 -> 20, Y unchanged
    assert r.x == pytest.approx(20.0)
    assert r.y == pytest.approx(200.0)


def test_unknown_token_raises():
    with pytest.raises(RPNError):
        RPN().eval_line("3 bogus")


def test_reset():
    r = RPN()
    r.eval_line("1 2 3 sto 0")
    r.feed("rad")
    r.reset()
    assert r.stack == [0.0, 0.0, 0.0, 0.0]
    assert r.regs == {}
    assert r.angle == "DEG"
    assert r.last_x == 0.0
