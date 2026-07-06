"""HP-15C Voyager keypad logic (button presses → RPN state)."""

from __future__ import annotations

from abax.core.calc.voyager import LEGENDS_15C, VoyagerKeypad, grid_pos

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


def test_voyager_hyp_prefix_sinh() -> None:
    import math

    from abax.core.calc.voyager import VoyagerKeypad

    kp = VoyagerKeypad()
    for ch in "1":
        kp._apply(ch)
    kp._apply("HYP")            # arm hyperbolic prefix
    kp._apply("SIN")            # -> sinh(1)
    assert math.isclose(kp.rpn.x, math.sinh(1.0))


def test_voyager_hyp_inverse() -> None:
    import math

    from abax.core.calc.voyager import VoyagerKeypad

    kp = VoyagerKeypad()
    kp._apply("2")
    kp._apply("HYP")
    kp._apply("SIN")            # sinh(2)
    kp._apply("HYP-1")
    kp._apply("SIN")            # asinh(...) -> back to 2
    assert math.isclose(kp.rpn.x, 2.0, abs_tol=1e-12)


def test_voyager_programming_key_message() -> None:
    from abax.core.calc.voyager import VoyagerKeypad

    kp = VoyagerKeypad()
    kp._apply("SOLVE")
    assert "program" in kp.message.lower() or "solver" in kp.message.lower()


# --- HP-15C statistics registers -----------------------------------------

# A small dataset with tidy hand-computed summary statistics.
_STAT_POINTS = [(1.0, 2.0), (2.0, 4.0), (3.0, 5.0), (4.0, 4.0), (5.0, 5.0)]
_EXPECT = {
    "xbar": 3.0, "ybar": 4.0,
    "sx": 1.5811388300841898, "sy": 1.224744871391589,
    "slope": 0.6, "intercept": 2.2, "r": 0.7745966692414834,
}


def _enter_number(kp: VoyagerKeypad, value: float) -> None:
    """Key a (small, non-negative) number one character at a time."""
    for ch in _fmt(value):
        kp._apply(ch)


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _accumulate(kp: VoyagerKeypad, points) -> None:
    """Key each (x, y): y ENTER x Σ+ (the 15C data-point convention)."""
    for x, y in points:
        _enter_number(kp, y)
        kp._apply("ENTER")
        _enter_number(kp, x)
        kp._apply("Sigma+")


def test_voyager_sigma_plus_counts() -> None:
    kp = VoyagerKeypad()
    _accumulate(kp, _STAT_POINTS)
    # Σ+ leaves the running count n in X.
    assert kp.rpn.x == float(len(_STAT_POINTS))
    assert kp.stats.n == len(_STAT_POINTS)


def test_voyager_mean() -> None:
    import math

    kp = VoyagerKeypad()
    _accumulate(kp, _STAT_POINTS)
    kp._apply("mean")
    assert math.isclose(kp.rpn.x, _EXPECT["xbar"], abs_tol=1e-6)   # x̄ in X
    assert math.isclose(kp.rpn.y, _EXPECT["ybar"], abs_tol=1e-6)   # ȳ in Y


def test_voyager_std_dev() -> None:
    import math

    kp = VoyagerKeypad()
    _accumulate(kp, _STAT_POINTS)
    kp._apply("std dev")
    assert math.isclose(kp.rpn.x, _EXPECT["sx"], abs_tol=1e-6)     # sₓ in X
    assert math.isclose(kp.rpn.y, _EXPECT["sy"], abs_tol=1e-6)     # s_y in Y


def test_voyager_linear_regression() -> None:
    import math

    kp = VoyagerKeypad()
    _accumulate(kp, _STAT_POINTS)
    kp._apply("L.R.")
    assert math.isclose(kp.rpn.x, _EXPECT["intercept"], abs_tol=1e-6)  # b in X
    assert math.isclose(kp.rpn.y, _EXPECT["slope"], abs_tol=1e-6)      # m in Y


def test_voyager_lin_est_r() -> None:
    import math

    kp = VoyagerKeypad()
    _accumulate(kp, _STAT_POINTS)
    kp._apply("6")            # forecast at x = 6
    kp._apply("lin est,r")
    expected_yhat = _EXPECT["slope"] * 6.0 + _EXPECT["intercept"]
    assert math.isclose(kp.rpn.x, expected_yhat, abs_tol=1e-6)     # ŷ in X
    assert math.isclose(kp.rpn.y, _EXPECT["r"], abs_tol=1e-6)      # r in Y


def test_voyager_sigma_minus_removes_point() -> None:
    import math

    kp = VoyagerKeypad()
    _accumulate(kp, _STAT_POINTS)
    # Remove the last point (5, 5): y ENTER x Σ-.
    kp._apply("5")
    kp._apply("ENTER")
    kp._apply("5")
    kp._apply("Sigma-")
    assert kp.rpn.x == 4.0
    assert kp.stats.n == 4
    # The mean of the remaining four points {(1,2),(2,4),(3,5),(4,4)}.
    kp._apply("mean")
    assert math.isclose(kp.rpn.x, 2.5, abs_tol=1e-6)   # x̄ = (1+2+3+4)/4
    assert math.isclose(kp.rpn.y, 3.75, abs_tol=1e-6)  # ȳ = (2+4+5+4)/4


def test_voyager_stat_keys_via_full_keypress() -> None:
    import math

    # Exercise the real f/g shift mapping: mean is the blue (g) legend of key 47.
    kp = VoyagerKeypad()
    _accumulate(kp, _STAT_POINTS)
    press(kp, B["g"], 47)     # g + button 47 -> "mean"
    assert math.isclose(kp.rpn.x, _EXPECT["xbar"], abs_tol=1e-6)
    assert math.isclose(kp.rpn.y, _EXPECT["ybar"], abs_tol=1e-6)


def test_voyager_stat_keys_no_longer_program_keys() -> None:
    from abax.core.calc.voyager import _PROGRAM_KEYS

    for label in ("Sigma+", "Sigma-", "mean", "std dev", "L.R.", "lin est,r"):
        assert label not in _PROGRAM_KEYS
    # Genuine program keys remain rejected.
    assert "GTO" in _PROGRAM_KEYS and "SOLVE" in _PROGRAM_KEYS


# --- SOLVE / INTEGRATE engine API -----------------------------------------

def test_voyager_solve_bracket_pushes_root() -> None:
    import math

    kp = VoyagerKeypad()
    root = kp.solve(lambda x: x * x - 2, 0, 2)
    assert math.isclose(root, math.sqrt(2), abs_tol=1e-6)
    # Root lands in X; f(root) is left in Y (classic HP SOLVE convention).
    assert math.isclose(kp.rpn.x, math.sqrt(2), abs_tol=1e-6)
    assert math.isclose(kp.rpn.y, 0.0, abs_tol=1e-6)


def test_voyager_solve_cos_minus_x() -> None:
    import math

    kp = VoyagerKeypad()
    root = kp.solve(lambda x: math.cos(x) - x, 0, 1)
    assert math.isclose(root, 0.7390851, abs_tol=1e-6)


def test_voyager_solve_single_guess() -> None:
    import math

    kp = VoyagerKeypad()
    root = kp.solve(lambda x: x * x - 2, 1.0)
    assert math.isclose(root, math.sqrt(2), abs_tol=1e-6)


def test_voyager_solve_lifts_stack() -> None:
    # A pending entry is committed and the result lifts the stack.
    kp = VoyagerKeypad()
    for ch in "9":
        kp._apply(ch)          # digit entry pending
    kp.solve(lambda x: x - 3, 0, 10)   # root = 3
    assert kp.rpn.x == 3.0
    # 9 was committed then pushed up through Y (froot) into Z.
    assert kp.rpn.z == 9.0


def test_voyager_integrate_sin() -> None:
    import math

    kp = VoyagerKeypad()
    result = kp.integrate(math.sin, 0, math.pi)
    assert math.isclose(result, 2.0, abs_tol=1e-6)
    assert math.isclose(kp.rpn.x, 2.0, abs_tol=1e-6)


def test_voyager_integrate_exp() -> None:
    import math

    kp = VoyagerKeypad()
    result = kp.integrate(math.exp, 0, 1)
    assert math.isclose(result, math.e - 1.0, abs_tol=1e-6)


def test_voyager_integrate_xsquared() -> None:
    kp = VoyagerKeypad()
    result = kp.integrate(lambda x: x * x, 0, 1)
    assert abs(result - 1.0 / 3.0) < 1e-6


def test_voyager_solve_no_bracket_raises() -> None:
    import pytest

    from abax.core.science.numeric import NumericError

    kp = VoyagerKeypad()
    with pytest.raises(NumericError):
        kp.solve(lambda x: x * x + 1, -1, 1)
    assert kp.message  # error text recorded
