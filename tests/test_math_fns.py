"""Oracle tests for abax.core.math_fns.

Every function is asserted against a documented Excel result. Transcendental
results use rel_tol=1e-6; exact algebra uses rel_tol=1e-9.
"""

from __future__ import annotations

import math

from abax.core import math_fns as M
from abax.core.errors import CellError
from abax.core.math_fns import SIGNATURES, register

ALG = dict(rel_tol=1e-9)
TRANS = dict(rel_tol=1e-6)


# --- hyperbolic & inverse --------------------------------------------------


def test_hyperbolic():
    assert math.isclose(M._sinh([1]), 1.1752011936, **TRANS)
    assert math.isclose(M._cosh([1]), 1.5430806348, **TRANS)
    assert math.isclose(M._tanh([1]), 0.7615941559, **TRANS)
    assert math.isclose(M._asinh([1]), 0.8813735870, **TRANS)
    assert math.isclose(M._acosh([2]), 1.3169578969, **TRANS)
    assert math.isclose(M._atanh([0.5]), 0.5493061443, **TRANS)


def test_hyperbolic_domain():
    assert M._acosh([0.5]) == CellError(CellError.NUM)
    assert M._atanh([1]) == CellError(CellError.NUM)
    assert M._atanh([-1]) == CellError(CellError.NUM)


# --- reciprocal trig -------------------------------------------------------


def test_reciprocal_trig():
    assert math.isclose(M._sec([0]), 1.0, **ALG)
    assert math.isclose(M._csc([math.pi / 2]), 1.0, **TRANS)
    assert math.isclose(M._cot([math.pi / 4]), 1.0, **TRANS)
    assert math.isclose(M._sech([0]), 1.0, **ALG)
    assert math.isclose(M._csch([1]), 0.8509181282, **TRANS)
    assert math.isclose(M._coth([1]), 1.3130352855, **TRANS)
    assert math.isclose(M._acot([1]), math.pi / 4, **TRANS)


def test_reciprocal_trig_div0():
    assert M._csc([0]) == CellError(CellError.DIV0)
    assert M._cot([0]) == CellError(CellError.DIV0)
    assert M._csch([0]) == CellError(CellError.DIV0)


# --- rounding / int --------------------------------------------------------


def test_even_odd():
    assert M._even([3]) == 4.0
    assert M._even([1.5]) == 2.0
    assert M._even([-1]) == -2.0
    assert M._even([0]) == 0.0
    assert M._odd([2]) == 3.0
    assert M._odd([1.5]) == 3.0
    assert M._odd([-1]) == -1.0
    assert M._odd([0]) == 1.0


def test_mround():
    assert M._mround([10, 3]) == 9.0
    assert math.isclose(M._mround([1.3, 0.2]), 1.4, **TRANS)
    assert M._mround([-10, 3]) == CellError(CellError.NUM)


def test_quotient():
    assert M._quotient([7, 2]) == 3.0
    assert M._quotient([-7, 2]) == -3.0
    assert M._quotient([5, 0]) == CellError(CellError.DIV0)


def test_sqrtpi():
    assert math.isclose(M._sqrtpi([1]), math.sqrt(math.pi), **TRANS)
    assert math.isclose(M._sqrtpi([2]), math.sqrt(2 * math.pi), **TRANS)


def test_iso_ceiling():
    assert M._iso_ceiling([4.3]) == 5.0
    assert M._iso_ceiling([-4.3]) == -4.0
    assert math.isclose(M._iso_ceiling([4.3, 0.5]), 4.5, **TRANS)


# --- combinatorics ---------------------------------------------------------


def test_factdouble():
    assert M._factdouble([7]) == 105.0  # 7*5*3*1
    assert M._factdouble([6]) == 48.0  # 6*4*2
    assert M._factdouble([0]) == 1.0
    assert M._factdouble([-1]) == 1.0
    assert M._factdouble([-2]) == CellError(CellError.NUM)


def test_combin():
    assert M._combin([8, 2]) == 28.0
    assert M._combin([5, 0]) == 1.0
    assert M._combin([2, 5]) == CellError(CellError.NUM)


def test_combina():
    assert M._combina([4, 3]) == 20.0  # C(6,3)
    assert M._combina([0, 0]) == 1.0


def test_permut():
    assert M._permut([5, 2]) == 20.0
    assert M._permut([3, 4]) == CellError(CellError.NUM)


def test_permutationa():
    assert M._permutationa([3, 2]) == 9.0
    assert M._permutationa([2, 3]) == 8.0


def test_multinomial():
    assert M._multinomial([2, 3, 4]) == 1260.0  # 9!/(2!3!4!)
    assert M._multinomial([1, 1]) == 2.0


# --- sum families ----------------------------------------------------------


def test_sum_families():
    assert M._sumx2my2([[1, 2], [3, 4]]) == (1 - 9) + (4 - 16)  # -20
    assert M._sumx2py2([[1, 2], [3, 4]]) == (1 + 9) + (4 + 16)  # 30
    assert M._sumxmy2([[1, 2], [3, 4]]) == (1 - 3) ** 2 + (2 - 4) ** 2  # 8


def test_seriessum():
    # SERIESSUM(2,1,0,{1,1,1}) = 1*2^1 + 1*2^1 + 1*2^1 = 6
    assert math.isclose(M._seriessum([2, 1, 0, [1, 1, 1]]), 6.0, **ALG)
    # SERIESSUM(1,0,1,{1,2,3}) = 1 + 2 + 3 = 6
    assert math.isclose(M._seriessum([1, 0, 1, [1, 2, 3]]), 6.0, **ALG)


# --- numerals --------------------------------------------------------------


def test_roman():
    assert M._roman([1994]) == "MCMXCIV"
    assert M._roman([2024]) == "MMXXIV"
    assert M._roman([4]) == "IV"
    assert M._roman([4000]) == CellError(CellError.NUM)
    assert M._roman([0]) == CellError(CellError.NUM)


def test_arabic():
    assert M._arabic(["MCMXCIV"]) == 1994.0
    assert M._arabic(["LVII"]) == 57.0
    assert M._arabic([""]) == 0.0


def test_base():
    assert M._base([15, 2]) == "1111"
    assert M._base([255, 16]) == "FF"
    assert M._base([7, 2, 8]) == "00000111"
    assert M._base([0, 10]) == "0"


def test_decimal():
    assert M._decimal(["FF", 16]) == 255.0
    assert M._decimal(["1111", 2]) == 15.0
    assert M._decimal(["ZZ", 36]) == 1295.0


# --- gamma -----------------------------------------------------------------


def test_gamma():
    assert math.isclose(M._gamma([5]), 24.0, **TRANS)
    assert math.isclose(M._gamma([0.5]), math.sqrt(math.pi), **TRANS)
    assert M._gamma([0]) == CellError(CellError.NUM)
    assert M._gamma([-1]) == CellError(CellError.NUM)


def test_gammaln():
    assert math.isclose(M._gammaln([5]), math.log(24.0), **TRANS)
    assert math.isclose(M._gammaln([1]), 0.0, abs_tol=1e-9)


# --- information -----------------------------------------------------------


def test_iseven_isodd():
    assert M._iseven([4]) is True
    assert M._iseven([3]) is False
    assert M._isodd([3]) is True
    assert M._isodd([4]) is False
    assert M._iseven(["x"]) == CellError(CellError.VALUE)


def test_iserr_isna():
    assert M._iserr([CellError(CellError.DIV0)]) is True
    assert M._iserr([CellError(CellError.NA)]) is False
    assert M._iserr([5]) is False
    assert M._isna([CellError(CellError.NA)]) is True
    assert M._isna([CellError(CellError.DIV0)]) is False


def test_isnontext():
    assert M._isnontext([5]) is True
    assert M._isnontext(["hi"]) is False


def test_n():
    assert M._n([7]) == 7.0
    assert M._n([True]) == 1.0
    assert M._n([False]) == 0.0
    assert M._n(["hi"]) == 0.0
    assert M._n([CellError(CellError.NA)]) == CellError(CellError.NA)


def test_type():
    assert M._type([5]) == 1.0
    assert M._type(["hi"]) == 2.0
    assert M._type([True]) == 4.0
    assert M._type([CellError(CellError.DIV0)]) == 16.0


def test_error_type():
    assert M._error_type([CellError(CellError.DIV0)]) == 2.0
    assert M._error_type([CellError(CellError.VALUE)]) == 3.0
    assert M._error_type([CellError(CellError.REF)]) == 4.0
    assert M._error_type([CellError(CellError.NAME)]) == 5.0
    assert M._error_type([CellError(CellError.NUM)]) == 6.0
    assert M._error_type([CellError(CellError.NA)]) == 7.0
    assert M._error_type([5]) == CellError(CellError.NA)


# --- registration ----------------------------------------------------------


def test_register_adds_all_signatures():
    functions: dict = {}
    register(functions)
    assert len(functions) == len(SIGNATURES)
    for name in functions:
        assert name in SIGNATURES
    for name in SIGNATURES:
        assert name in functions
