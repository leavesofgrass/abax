"""Golden table of formula -> Excel/gnumeric error code.

Guards #NUM! vs #VALUE! fidelity. The evaluator's generic handler used to map
*every* ``OverflowError`` to #VALUE!, but Excel and gnumeric report #NUM! when a
numeric result overflows (e.g. ``FACT(171)`` exceeds float64). The
integer-combinatorial builtins (FACT/FACTDOUBLE/MULTINOMIAL and the
COMBIN/COMBINA/PERMUT/PERMUTATIONA family) plus POWER and the ``^`` operator now
return #NUM! on overflow; the ``_OVERFLOW_IS_NUM`` allowlist in the evaluator
keeps every *other* function's OverflowError at #VALUE!.

Each case is driven through a real :class:`~abax.core.Sheet` cell so the whole
parse -> evaluate -> error-propagation path (including the generic handler that
was fixed) is exercised, not just a bare function call. Error codes are checked,
not values, because these inputs deliberately fail.

Codes are the documented spreadsheet behaviour, not values derived from abax's
own implementation, so this file is a genuine oracle for the error surface.
"""

from __future__ import annotations

import pytest

from abax.core import Sheet
from abax.core.errors import CellError


def code(formula: str) -> str:
    """Set ``formula`` into a fresh cell and return the resulting error code
    (or ``VALUE:<repr>`` if the cell did *not* evaluate to an error)."""
    s = Sheet()
    s.set("A1", formula)
    result = s.get("A1")
    if isinstance(result, CellError):
        return result.code
    return f"VALUE:{result!r}"


# --- overflow must be #NUM!, not #VALUE! ----------------------------------
#
# These integer-combinatorial builtins compute an exact (astronomically large)
# Python int, then fail only at the final ``float(...)`` cast. Excel/gnumeric:
# #NUM!. Before the fix the evaluator's generic OverflowError net gave #VALUE!.

OVERFLOW_NUM = [
    "=FACT(171)",                 # 170! is the last factorial that fits float64
    "=FACT(1000)",
    "=FACTDOUBLE(600)",           # 600!! overflows float64
    "=FACTDOUBLE(320)",           # 300!! fits (~8e307), 320!! does not
    "=FACTDOUBLE(400)",
    "=MULTINOMIAL(400,400,400)",  # 1200! / (400!)^3 overflows
    "=COMBIN(2000,1000)",         # central binomial ~2e600
    "=COMBINA(2000,1000)",
    "=PERMUT(500,250)",
    "=PERMUTATIONA(1000,200)",    # 1000**200 overflows
    "=POWER(10,400)",             # already handled inside POWER, pinned here
    "=10^400",                    # the ``^`` operator path
    "=POWER(10,309)",             # just past the ~1.8e308 ceiling
]


@pytest.mark.parametrize("formula", OVERFLOW_NUM)
def test_overflow_is_num(formula):
    assert code(formula) == CellError.NUM, formula


# --- domain errors: #NUM! (a valid #NUM! for a different reason) ----------
#
# Not overflow — the *argument domain* is wrong. Excel returns #NUM! for these
# too, and abax already did; pinned so the overflow fix did not disturb them.

DOMAIN_NUM = [
    "=FACT(-1)",              # factorial of a negative
    "=COMBIN(5, 9)",          # number_chosen > number
    "=COMBIN(-1, 2)",         # negative n
    "=PERMUT(2, 5)",          # number_chosen > number
    "=FACTDOUBLE(-3)",        # < -1
    "=SQRT(-1)",              # negative radicand
    "=LN(0)",                 # log of zero
    "=LN(-1)",                # log of a negative
    "=LOG(10, 1)",            # base 1
    "=POWER(-1, 0.5)",        # negative base, fractional exponent
]


@pytest.mark.parametrize("formula", DOMAIN_NUM)
def test_domain_errors_are_num(formula):
    assert code(formula) == CellError.NUM, formula


# --- regressions that MUST stay #VALUE! -----------------------------------
#
# Non-numeric operands are a *type* failure, not a numeric one: Excel says
# #VALUE!. The overflow fix narrowed only the OverflowError branch, so these are
# untouched — this is the "do not broaden" guard.

STAY_VALUE = [
    '=ABS("x")',
    '=SQRT("x")',
    '=SIN("x")',
    '=EXP("x")',
    '=INT("x")',
    '="x"+1',            # string in an arithmetic operator
    '=1*"abc"',
    '=-"z"',             # unary minus on text
]


@pytest.mark.parametrize("formula", STAY_VALUE)
def test_type_errors_stay_value(formula):
    assert code(formula) == CellError.VALUE, formula


# --- regressions that MUST stay #DIV/0! -----------------------------------

STAY_DIV0 = [
    "=1/0",
    "=MOD(1, 0)",
    "=10%0",
    "=SUM(1,2)/0",
]


@pytest.mark.parametrize("formula", STAY_DIV0)
def test_div_by_zero_stays_div0(formula):
    assert code(formula) == CellError.DIV0, formula


# --- regressions: other codes unaffected ----------------------------------


def test_unknown_name_stays_name():
    assert code("=NOTAFUNCTION(1)") == CellError.NAME


def test_na_stays_na():
    assert code("=NA()") == CellError.NA


# --- sanity: near-ceiling inputs still return a finite number -------------
#
# The overflow boundary must not fire early — values that *do* fit float64 must
# still compute, so #NUM! is reserved for true overflow.

FINITE_OK = [
    "=FACT(170)",
    "=FACT(0)",
    "=FACTDOUBLE(300)",
    "=COMBIN(100, 50)",
    "=PERMUT(50, 10)",
    "=PERMUTATIONA(3, 2)",
    "=MULTINOMIAL(2, 3, 4)",
    "=POWER(10, 308)",
    "=2^1000",
]


@pytest.mark.parametrize("formula", FINITE_OK)
def test_near_ceiling_is_finite(formula):
    result = code(formula)
    assert not result.startswith("#"), f"{formula} -> {result}"
    assert result.startswith("VALUE:"), formula
