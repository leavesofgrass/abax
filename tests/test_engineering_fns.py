"""Tests for abax.core.engineering_fns (base conversions, bitwise, special,
Bessel, and database D-functions)."""

from __future__ import annotations

import math

import pytest

from abax.core.engineering_fns import SIGNATURES, register
from abax.core.errors import CellError
from abax.core.values import RangeValue


@pytest.fixture(scope="module")
def fns():
    table: dict = {}
    register(table)
    return table


def call(fns, name, *args):
    return fns[name]([*args])


# --- number-base conversions -----------------------------------------------


def test_dec2bin(fns):
    assert call(fns, "DEC2BIN", 9) == "1001"


def test_dec2bin_negative(fns):
    assert call(fns, "DEC2BIN", -1) == "1111111111"


def test_bin2dec_negative(fns):
    assert call(fns, "BIN2DEC", "1111111111") == -1


def test_dec2hex(fns):
    assert call(fns, "DEC2HEX", 255) == "FF"


def test_hex2dec(fns):
    assert call(fns, "HEX2DEC", "FF") == 255


def test_dec2oct(fns):
    assert call(fns, "DEC2OCT", 8) == "10"


def test_oct2dec(fns):
    assert call(fns, "OCT2DEC", "10") == 8


def test_dec2bin_places(fns):
    assert call(fns, "DEC2BIN", 4, 6) == "000100"


def test_dec2bin_out_of_range(fns):
    assert call(fns, "DEC2BIN", 512) == CellError(CellError.NUM)


def test_places_too_small(fns):
    # 3 binary digits cannot fit in 2 places
    assert call(fns, "DEC2BIN", 4, 2) == CellError(CellError.NUM)


def test_cross_base_roundtrip(fns):
    assert call(fns, "HEX2BIN", "F") == "1111"
    assert call(fns, "BIN2HEX", "1111") == "F"
    assert call(fns, "OCT2HEX", "17") == "F"


# --- bitwise ---------------------------------------------------------------


def test_bitand(fns):
    assert call(fns, "BITAND", 6, 10) == 2


def test_bitor(fns):
    assert call(fns, "BITOR", 6, 10) == 14


def test_bitxor(fns):
    assert call(fns, "BITXOR", 6, 10) == 12


def test_bitlshift(fns):
    assert call(fns, "BITLSHIFT", 4, 2) == 16


def test_bitrshift(fns):
    assert call(fns, "BITRSHIFT", 16, 2) == 4


def test_bitlshift_negative_is_right(fns):
    assert call(fns, "BITLSHIFT", 16, -2) == 4


def test_bit_negative_operand(fns):
    assert call(fns, "BITAND", -1, 2) == CellError(CellError.NUM)


# --- step / compare / special ----------------------------------------------


def test_delta(fns):
    assert call(fns, "DELTA", 5, 5) == 1
    assert call(fns, "DELTA", 5, 4) == 0


def test_gestep(fns):
    assert call(fns, "GESTEP", 5, 4) == 1
    assert call(fns, "GESTEP", 3, 4) == 0


def test_erf(fns):
    assert call(fns, "ERF", 1) == pytest.approx(0.842701, abs=1e-6)


def test_erfc(fns):
    assert call(fns, "ERFC", 1) == pytest.approx(0.157299, abs=1e-6)


def test_erf_two_limits(fns):
    assert call(fns, "ERF", 0, 1) == pytest.approx(0.842701, abs=1e-6)


def test_erf_precise(fns):
    assert call(fns, "ERF.PRECISE", 1) == pytest.approx(math.erf(1), abs=1e-12)


# --- Bessel ----------------------------------------------------------------


def test_besselj(fns):
    assert call(fns, "BESSELJ", 1, 0) == pytest.approx(0.765198, rel=1e-4)


def test_besseli(fns):
    assert call(fns, "BESSELI", 1, 0) == pytest.approx(1.266066, rel=1e-4)


def test_bessely(fns):
    # Y_0(1) ~ 0.088257
    assert call(fns, "BESSELY", 1, 0) == pytest.approx(0.088257, rel=1e-4)


def test_besselk(fns):
    # K_0(1) ~ 0.421024
    assert call(fns, "BESSELK", 1, 0) == pytest.approx(0.421024, rel=1e-4)


def test_bessel_negative_order(fns):
    assert call(fns, "BESSELJ", 1, -1) == CellError(CellError.NUM)


# --- database D-functions --------------------------------------------------


@pytest.fixture
def db():
    return RangeValue([["Tree", "Height"], ["Apple", 18], ["Pear", 12], ["Apple", 21]])


@pytest.fixture
def crit():
    return RangeValue([["Tree"], ["Apple"]])


def test_dsum(fns, db, crit):
    assert call(fns, "DSUM", db, "Height", crit) == 39


def test_dcount(fns, db, crit):
    assert call(fns, "DCOUNT", db, "Height", crit) == 2


def test_daverage(fns, db, crit):
    assert call(fns, "DAVERAGE", db, "Height", crit) == 19.5


def test_dmax(fns, db, crit):
    assert call(fns, "DMAX", db, "Height", crit) == 21


def test_dmin(fns, db, crit):
    assert call(fns, "DMIN", db, "Height", crit) == 18


def test_dcounta(fns, db, crit):
    assert call(fns, "DCOUNTA", db, "Tree", crit) == 2


def test_dproduct(fns, db, crit):
    assert call(fns, "DPRODUCT", db, "Height", crit) == 18 * 21


def test_dget_single_match(fns, db):
    crit = RangeValue([["Tree"], ["Pear"]])
    assert call(fns, "DGET", db, "Height", crit) == 12


def test_dget_multiple_match_is_num(fns, db, crit):
    assert call(fns, "DGET", db, "Height", crit) == CellError(CellError.NUM)


def test_dget_no_match_is_value(fns, db):
    crit = RangeValue([["Tree"], ["Cherry"]])
    assert call(fns, "DGET", db, "Height", crit) == CellError(CellError.VALUE)


def test_field_by_index(fns, db, crit):
    # Height is column 2 (1-based)
    assert call(fns, "DSUM", db, 2, crit) == 39


def test_dstdev(fns, db, crit):
    # sample stdev of [18, 21]
    assert call(fns, "DSTDEV", db, "Height", crit) == pytest.approx(
        math.sqrt(((18 - 19.5) ** 2 + (21 - 19.5) ** 2) / 1), rel=1e-9
    )


def test_dstdevp(fns, db, crit):
    assert call(fns, "DSTDEVP", db, "Height", crit) == pytest.approx(
        math.sqrt(((18 - 19.5) ** 2 + (21 - 19.5) ** 2) / 2), rel=1e-9
    )


def test_dvar(fns, db, crit):
    assert call(fns, "DVAR", db, "Height", crit) == pytest.approx(4.5, rel=1e-9)


def test_dvarp(fns, db, crit):
    assert call(fns, "DVARP", db, "Height", crit) == pytest.approx(2.25, rel=1e-9)


def test_criteria_numeric_comparison(fns, db):
    crit = RangeValue([["Height"], [">15"]])
    assert call(fns, "DSUM", db, "Height", crit) == 18 + 21


# --- registration surface --------------------------------------------------


def test_register_adds_exactly_signatures_count():
    table: dict = {}
    register(table)
    assert len(table) == len(SIGNATURES)


def test_every_name_has_signature(fns):
    for name in fns:
        assert name in SIGNATURES, f"missing signature for {name}"
    assert set(fns) == set(SIGNATURES)
