"""Tests for :mod:`abax.core.science.complexnum`."""

from __future__ import annotations

import cmath

import pytest

from abax.core.science.complexnum import (
    ComplexError,
    complexnum,
    fmt,
    im_abs,
    im_argument,
    im_conjugate,
    im_cos,
    im_div,
    im_exp,
    im_imaginary,
    im_ln,
    im_power,
    im_product,
    im_real,
    im_sin,
    im_sqrt,
    im_sub,
    im_sum,
    parse,
)

# --- parse ------------------------------------------------------------------


def test_parse_full():
    assert parse("3+4i") == complex(3, 4)


def test_parse_full_j():
    assert parse("3+4j") == complex(3, 4)


def test_parse_negative_parts():
    assert parse("-2.5-1.5i") == complex(-2.5, -1.5)


def test_parse_pure_imaginary():
    assert parse("2i") == 2j


def test_parse_unit_imaginary():
    assert parse("i") == 1j
    assert parse("-i") == -1j
    assert parse("+i") == 1j


def test_parse_pure_real():
    assert parse("5") == 5 + 0j


def test_parse_spaces():
    assert parse(" 3 + 4 i ") == complex(3, 4)


def test_parse_numeric_types():
    assert parse(7) == 7 + 0j
    assert parse(2.5) == 2.5 + 0j
    assert parse(complex(1, 2)) == complex(1, 2)


def test_parse_scientific():
    assert parse("1e3+2i") == complex(1000, 2)


@pytest.mark.parametrize("bad", ["", "abc", "3+4k", "++3", "3+4", None, [1], True])
def test_parse_bad_raises(bad):
    with pytest.raises(ComplexError):
        parse(bad)


# --- fmt --------------------------------------------------------------------


def test_fmt_negative_imag():
    assert fmt(complex(3, -4)) == "3-4i"


def test_fmt_real_only():
    assert fmt(complex(3, 0)) == "3"


def test_fmt_imag_only():
    assert fmt(complex(0, 2)) == "2i"


def test_fmt_unit_imag():
    assert fmt(complex(0, 1)) == "i"
    assert fmt(complex(0, -1)) == "-i"
    assert fmt(complex(2, 1)) == "2+i"
    assert fmt(complex(2, -1)) == "2-i"


def test_fmt_suffix():
    assert fmt(complex(3, 4), "j") == "3+4j"


def test_fmt_trims_trailing_zero():
    assert fmt(complex(3.0, 4.0)) == "3+4i"


# --- round trip -------------------------------------------------------------


@pytest.mark.parametrize(
    "z",
    [
        complex(3, 4),
        complex(-2.5, -1.5),
        complex(0, 2),
        complex(5, 0),
        complex(0, -1),
        complex(1.25, -3.75),
        complex(-7, 0.5),
    ],
)
def test_round_trip(z):
    assert parse(fmt(z)) == pytest.approx(z)
    assert parse(fmt(z, "j")) == pytest.approx(z)


# --- arithmetic -------------------------------------------------------------


def test_im_sum():
    assert im_sum("3+4i", "1-2i") == "4+2i"


def test_im_sum_many():
    assert im_sum("1", "2i", "3+4i") == "4+6i"


def test_im_sub():
    assert im_sub("3+4i", "1-2i") == "2+6i"


def test_im_product():
    assert im_product("2i", "2i") == "-4"


def test_im_product_many():
    assert parse(im_product("2", "3", "1i")) == 6j


def test_im_div():
    assert parse(im_div("4+2i", "2")) == complex(2, 1)


def test_im_div_by_zero():
    with pytest.raises(ComplexError):
        im_div("3+4i", "0")


# --- scalar results ---------------------------------------------------------


def test_im_abs():
    assert im_abs("3+4i") == 5


def test_im_real():
    assert im_real("3+4i") == 3


def test_im_imaginary():
    assert im_imaginary("3+4i") == 4


def test_im_conjugate():
    assert im_conjugate("3+4i") == "3-4i"


def test_im_argument():
    assert im_argument("0+1i") == pytest.approx(cmath.pi / 2)


# --- transcendental ---------------------------------------------------------


def test_im_sqrt_of_minus_one():
    assert parse(im_sqrt("-1")) == pytest.approx(1j)


def test_im_sqrt_value():
    assert parse(im_sqrt("3+4i")) == pytest.approx(complex(2, 1))


def test_im_exp():
    assert parse(im_exp("0")) == pytest.approx(1 + 0j)


def test_im_ln():
    assert parse(im_ln("1")) == pytest.approx(0 + 0j)


def test_im_ln_zero():
    with pytest.raises(ComplexError):
        im_ln("0")


def test_im_power():
    assert parse(im_power("2i", "2")) == pytest.approx(-4 + 0j)


def test_im_sin():
    assert parse(im_sin("0")) == pytest.approx(0 + 0j)


def test_im_cos():
    assert parse(im_cos("0")) == pytest.approx(1 + 0j)


# --- builder ----------------------------------------------------------------


def test_complexnum():
    assert complexnum(3, 4) == "3+4i"
    assert complexnum(0, 1, "j") == "j"
    assert complexnum(5, 0) == "5"


def test_complexnum_bad_suffix():
    with pytest.raises(ComplexError):
        complexnum(1, 1, "k")
