"""Tests for the algebraic (infix) calculator engine (``qcell/core/algebraic.py``)."""

from __future__ import annotations

import math

import pytest

from qcell.core.calc.algebraic import (
    SAFE_CONSTS,
    SAFE_FUNCTIONS,
    AlgebraicCalc,
    AlgebraicError,
    evaluate,
)

# -- evaluate: arithmetic -------------------------------------------------


def test_precedence():
    assert evaluate("2+3*4") == pytest.approx(14)


def test_parentheses():
    assert evaluate("(2+3)*4") == pytest.approx(20)


def test_power_right_assoc():
    assert evaluate("2^10") == pytest.approx(1024)
    # right-associative: 2^(3^2) == 2^9 == 512
    assert evaluate("2^3^2") == pytest.approx(512)


def test_double_star_power():
    assert evaluate("2**8") == pytest.approx(256)


def test_unary_minus():
    assert evaluate("-3+5") == pytest.approx(2)
    assert evaluate("-2^2") == pytest.approx(-4)  # -(2^2)
    assert evaluate("(-2)^2") == pytest.approx(4)


def test_unary_plus():
    assert evaluate("+3") == pytest.approx(3)


def test_modulo():
    assert evaluate("10%3") == pytest.approx(1)
    assert evaluate("10 % 4") == pytest.approx(2)


def test_division():
    assert evaluate("7/2") == pytest.approx(3.5)


def test_float_and_exponent_literals():
    assert evaluate("1.5e3") == pytest.approx(1500)
    assert evaluate("2.5+0.5") == pytest.approx(3.0)
    assert evaluate("1.5E-1") == pytest.approx(0.15)


def test_whitespace_ignored():
    assert evaluate("  2  +   3 ") == pytest.approx(5)


# -- evaluate: functions and constants ------------------------------------


def test_sqrt():
    assert evaluate("sqrt(16)") == pytest.approx(4)


def test_sin_radians():
    assert evaluate("sin(0)") == pytest.approx(0)


def test_sin_degrees():
    assert evaluate("sin(90)", degrees=True) == pytest.approx(1)
    assert evaluate("cos(0)", degrees=True) == pytest.approx(1)
    assert evaluate("tan(45)", degrees=True) == pytest.approx(1)


def test_inverse_trig_degrees():
    assert evaluate("asin(1)", degrees=True) == pytest.approx(90)
    assert evaluate("atan(1)", degrees=True) == pytest.approx(45)


def test_ln_and_log():
    assert evaluate("ln(e)") == pytest.approx(1)
    assert evaluate("log(1000)") == pytest.approx(3)  # log base 10
    assert evaluate("log2(8)") == pytest.approx(3)


def test_fact():
    assert evaluate("fact(5)") == pytest.approx(120)
    assert evaluate("fact(0)") == pytest.approx(1)


def test_misc_functions():
    assert evaluate("exp(0)") == pytest.approx(1)
    assert evaluate("abs(-4)") == pytest.approx(4)
    assert evaluate("floor(3.7)") == pytest.approx(3)
    assert evaluate("ceil(3.2)") == pytest.approx(4)
    assert evaluate("round(2.5)") == pytest.approx(2)  # banker's rounding
    assert evaluate("cbrt(27)") == pytest.approx(3)
    assert evaluate("cbrt(-8)") == pytest.approx(-2)


def test_constants():
    assert evaluate("pi") == pytest.approx(math.pi)
    assert evaluate("e") == pytest.approx(math.e)
    assert evaluate("tau") == pytest.approx(math.tau)
    assert evaluate("2*pi") == pytest.approx(2 * math.pi)


def test_nested_functions():
    assert evaluate("sqrt(sqrt(16))") == pytest.approx(2)
    assert evaluate("sqrt(9)+abs(-1)") == pytest.approx(4)


# -- evaluate: Ans / M ----------------------------------------------------


def test_ans():
    assert evaluate("Ans*2", ans=21) == pytest.approx(42)


def test_memory():
    assert evaluate("M+1", memory=9) == pytest.approx(10)


def test_ans_and_memory_together():
    assert evaluate("Ans+M", ans=5, memory=3) == pytest.approx(8)


# -- evaluate: errors -----------------------------------------------------


def test_trailing_operator_error():
    with pytest.raises(AlgebraicError):
        evaluate("2+")


def test_unknown_function_error():
    with pytest.raises(AlgebraicError):
        evaluate("foo(2)")


def test_unknown_name_error():
    with pytest.raises(AlgebraicError):
        evaluate("xyz")


def test_juxtaposition_error():
    with pytest.raises(AlgebraicError):
        evaluate("2 3")


def test_empty_error():
    with pytest.raises(AlgebraicError):
        evaluate("")
    with pytest.raises(AlgebraicError):
        evaluate("   ")


def test_mismatched_parens_error():
    with pytest.raises(AlgebraicError):
        evaluate("(2+3")
    with pytest.raises(AlgebraicError):
        evaluate("2+3)")


def test_division_by_zero_error():
    with pytest.raises(AlgebraicError):
        evaluate("1/0")


def test_bad_character_error():
    with pytest.raises(AlgebraicError):
        evaluate("2 @ 3")


def test_fact_domain_error():
    with pytest.raises(AlgebraicError):
        evaluate("fact(-1)")
    with pytest.raises(AlgebraicError):
        evaluate("fact(2.5)")


def test_no_eval_injection():
    # Names outside the safe set must not resolve to builtins / attributes.
    with pytest.raises(AlgebraicError):
        evaluate("__import__")
    with pytest.raises(AlgebraicError):
        evaluate("pi.real")


# -- module surface -------------------------------------------------------


def test_safe_consts_values():
    assert SAFE_CONSTS == {"pi": math.pi, "e": math.e, "tau": math.tau}


def test_safe_functions_complete():
    expected = {
        "sin", "cos", "tan", "asin", "acos", "atan",
        "sinh", "cosh", "tanh", "ln", "log", "log2",
        "sqrt", "cbrt", "exp", "abs", "floor", "ceil", "round", "fact",
    }
    assert expected <= set(SAFE_FUNCTIONS)


# -- AlgebraicCalc --------------------------------------------------------


def test_calc_basic_equals():
    c = AlgebraicCalc()
    c.input("2")
    c.input("+")
    c.input("3")
    assert c.expression == "2+3"
    assert c.equals() == "5"
    assert c.ans == pytest.approx(5)
    assert c.display == "5"


def test_calc_uses_ans_after_equals():
    c = AlgebraicCalc()
    c.input("2")
    c.input("+")
    c.input("3")
    c.equals()  # ans == 5
    # An operator continues from the previous answer.
    c.input("*")
    c.input("2")
    assert c.equals() == "10"
    assert c.ans == pytest.approx(10)


def test_calc_digit_after_equals_starts_fresh():
    c = AlgebraicCalc()
    c.input("7")
    c.equals()
    c.input("9")
    assert c.expression == "9"
    assert c.equals() == "9"


def test_calc_display_default_zero():
    c = AlgebraicCalc()
    assert c.display == "0"


def test_calc_display_is_expression_before_equals():
    c = AlgebraicCalc()
    c.input("1")
    c.input("2")
    assert c.display == "12"


def test_calc_backspace():
    c = AlgebraicCalc()
    c.input("1")
    c.input("2")
    c.input("3")
    c.backspace()
    assert c.expression == "12"
    assert c.equals() == "12"


def test_calc_backspace_clears_result():
    c = AlgebraicCalc()
    c.input("5")
    c.equals()
    c.backspace()
    assert c.display == "5"  # result cleared, expression intact


def test_calc_clear():
    c = AlgebraicCalc()
    c.input("9")
    c.input("9")
    c.equals()
    c.clear()
    assert c.expression == ""
    assert c.display == "0"


def test_calc_error_does_not_raise():
    c = AlgebraicCalc()
    c.input("2")
    c.input("+")
    assert c.equals() == "Error"


def test_calc_error_leaves_ans_unchanged():
    c = AlgebraicCalc()
    c.input("4")
    c.equals()
    assert c.ans == pytest.approx(4)
    c.input("+")  # operator -> continues from Ans
    c.input("(")  # now expression is "Ans+(" -> error
    assert c.equals() == "Error"
    assert c.ans == pytest.approx(4)  # unchanged


def test_calc_degrees_toggle():
    c = AlgebraicCalc(degrees=False)
    assert c.degrees is False
    c.set_degrees(True)
    assert c.degrees is True
    c.input("sin(")
    c.input("90")
    c.input(")")
    assert c.equals() == "1"


def test_calc_memory_store_recall():
    c = AlgebraicCalc()
    c.input("4")
    c.input("2")
    c.equals()  # 42
    c.memory_store()
    assert c.memory == pytest.approx(42)
    c.clear()
    c.memory_recall()
    assert c.expression == "M"
    assert c.equals() == "42"


def test_calc_memory_add_and_clear():
    c = AlgebraicCalc()
    c.input("1")
    c.input("0")
    c.equals()
    c.memory_store()
    c.clear()
    c.input("5")
    c.equals()
    c.memory_add()
    assert c.memory == pytest.approx(15)
    c.memory_clear()
    assert c.memory == pytest.approx(0)


def test_calc_memory_store_from_expression():
    c = AlgebraicCalc()
    c.input("3")
    c.input("*")
    c.input("4")
    c.memory_store()  # evaluates the in-progress expression
    assert c.memory == pytest.approx(12)


def test_calc_pi_constant_input():
    c = AlgebraicCalc()
    c.input("pi")
    assert c.equals() == repr(math.pi)
