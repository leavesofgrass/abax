"""Wave I — modern-Excel completeness functions (excel_modern pack)."""

from __future__ import annotations

import math

from abax.core.errors import CellError
from abax.core.functions import FUNCTIONS
from abax.core.values import RangeValue
from abax.core.workbook import Workbook


def v(name, *a):
    return FUNCTIONS[name](list(a))


def _sheet_val(formula):
    wb = Workbook()
    s = wb.sheets[0]
    s.set("A1", formula)
    return s.get("A1")


def test_all_registered():
    for name in ("TEXTSPLIT", "ARRAYTOTEXT", "VALUETOTEXT", "XMATCH", "LOOKUP",
                 "CEILING.MATH", "FLOOR.MATH", "SUBTOTAL", "AGGREGATE",
                 "WORKDAY.INTL", "NETWORKDAYS.INTL",
                 "IMTAN", "IMCOT", "IMSEC", "IMCSC", "IMSINH", "IMCOSH",
                 "IMTANH", "IMSECH", "IMCSCH", "IMLOG2", "IMLOG10"):
        assert name in FUNCTIONS, name


# --- TEXTSPLIT ---------------------------------------------------------------


def test_textsplit_row():
    assert v("TEXTSPLIT", "a,b,c", ",") == [["a", "b", "c"]]


def test_textsplit_grid():
    assert v("TEXTSPLIT", "a,b;c,d", ",", ";") == [["a", "b"], ["c", "d"]]


def test_textsplit_ignore_empty_and_pad():
    assert v("TEXTSPLIT", "a,,b", ",", None, True) == [["a", "b"]]
    # Ragged rows pad with #N/A by default.
    out = v("TEXTSPLIT", "a,b;c", ",", ";")
    assert out[0] == ["a", "b"]
    assert out[1][0] == "c"
    assert isinstance(out[1][1], CellError) and str(out[1][1]) == "#N/A"


def test_textsplit_case_insensitive_and_errors():
    assert v("TEXTSPLIT", "1x2X3", "x", None, False, 1) == [["1", "2", "3"]]
    assert isinstance(v("TEXTSPLIT", "abc", ""), CellError)


def test_textsplit_spills_in_sheet():
    wb = Workbook()
    s = wb.sheets[0]
    s.set("A1", '=TEXTSPLIT("x;y",";")')
    assert s.get("A1") == "x"
    assert s.get("B1") == "y"


# --- ARRAYTOTEXT / VALUETOTEXT ----------------------------------------------


def test_arraytotext():
    rv = RangeValue([[1.0, "a"], [True, 2.5]])
    assert v("ARRAYTOTEXT", rv) == "1, a, TRUE, 2.5"
    assert v("ARRAYTOTEXT", rv, 1) == '{1,"a";TRUE,2.5}'


def test_valuetotext():
    assert v("VALUETOTEXT", "hi") == "hi"
    assert v("VALUETOTEXT", "hi", 1) == '"hi"'
    assert v("VALUETOTEXT", 3.0) == "3"


# --- XMATCH / LOOKUP ---------------------------------------------------------


def test_xmatch_exact_and_reverse():
    hay = RangeValue([["apple"], ["banana"], ["cherry"], ["banana"]])
    assert v("XMATCH", "banana", hay) == 2
    assert v("XMATCH", "banana", hay, 0, -1) == 4
    assert isinstance(v("XMATCH", "kiwi", hay), CellError)


def test_xmatch_nearest():
    hay = RangeValue([[10.0], [20.0], [30.0]])
    assert v("XMATCH", 25, hay, -1) == 2   # next smaller: 20
    assert v("XMATCH", 25, hay, 1) == 3    # next larger: 30
    assert isinstance(v("XMATCH", 5, hay, -1), CellError)
    assert isinstance(v("XMATCH", 35, hay, 1), CellError)


def test_xmatch_wildcard():
    hay = RangeValue([["grape"], ["pear"], ["apple"]])
    assert v("XMATCH", "ap*", hay, 2) == 3
    assert v("XMATCH", "p?ar", hay, 2) == 2


def test_lookup_vector():
    lk = RangeValue([[4.14], [4.19], [5.17], [5.77], [6.39]])
    rs = RangeValue([["red"], ["orange"], ["yellow"], ["green"], ["blue"]])
    assert v("LOOKUP", 4.19, lk, rs) == "orange"     # Excel doc example
    assert v("LOOKUP", 5.75, lk, rs) == "yellow"     # largest <= 5.75 is 5.17
    assert isinstance(v("LOOKUP", 0, lk, rs), CellError)


def test_lookup_array_form():
    table = RangeValue([[1.0, "a"], [2.0, "b"], [3.0, "c"]])
    assert v("LOOKUP", 2, table) == "b"
    assert v("LOOKUP", 2.9, table) == "b"


# --- CEILING.MATH / FLOOR.MATH ----------------------------------------------


def test_ceiling_math():
    assert v("CEILING.MATH", 24.3, 5) == 25          # Excel doc example
    assert v("CEILING.MATH", 6.7) == 7               # Excel doc example
    assert v("CEILING.MATH", -8.1, 2) == -8          # Excel doc example
    assert v("CEILING.MATH", -5.5, 2, -1) == -6      # Excel doc example (away from 0)


def test_floor_math():
    assert v("FLOOR.MATH", 24.3, 5) == 20            # Excel doc example
    assert v("FLOOR.MATH", 6.7) == 6                 # Excel doc example
    assert v("FLOOR.MATH", -8.1, 2) == -10           # Excel doc example
    assert v("FLOOR.MATH", -5.5, 2, -1) == -4        # Excel doc example (toward 0)


# --- SUBTOTAL / AGGREGATE ----------------------------------------------------


def test_subtotal():
    rng = RangeValue([[120.0], [10.0], [150.0], [23.0]])
    assert v("SUBTOTAL", 9, rng) == 303              # Excel doc example (SUM)
    assert v("SUBTOTAL", 109, rng) == 303            # 1xx behaves the same here
    assert v("SUBTOTAL", 1, rng) == 75.75            # AVERAGE
    assert v("SUBTOTAL", 4, rng) == 150              # MAX
    assert isinstance(v("SUBTOTAL", 12, rng), CellError)


def test_subtotal_propagates_errors():
    rng = RangeValue([[1.0], [CellError(CellError.DIV0)], [3.0]])
    out = v("SUBTOTAL", 9, rng)
    assert isinstance(out, CellError) and str(out) == "#DIV/0!"


def test_aggregate_ignore_errors():
    rng = RangeValue([[6.0], [CellError(CellError.DIV0)], [4.0], [12.0]])
    assert v("AGGREGATE", 4, 6, rng) == 12           # MAX ignoring errors
    assert v("AGGREGATE", 9, 6, rng) == 22           # SUM ignoring errors
    out = v("AGGREGATE", 9, 4, rng)                  # option 4 propagates
    assert isinstance(out, CellError)


def test_aggregate_k_functions():
    rng = RangeValue([[1.0], [CellError(CellError.NUM)], [3.0], [5.0], [7.0]])
    assert v("AGGREGATE", 14, 6, rng, 2) == 5        # 2nd-largest ignoring errors
    assert v("AGGREGATE", 15, 6, rng, 1) == 1        # smallest
    assert v("AGGREGATE", 12, 6, rng) == 4           # MEDIAN of 1,3,5,7
    assert math.isclose(v("AGGREGATE", 16, 6, rng, 0.5), 4.0)


# --- WORKDAY.INTL / NETWORKDAYS.INTL ------------------------------------------


def test_workday_intl():
    # 2026-01-01 is a Thursday. Default weekend (Sat/Sun): +5 workdays = Jan 8.
    assert v("WORKDAY.INTL", "2026-01-01", 5) == "2026-01-08"
    # Sunday-only weekend (11): +5 workdays = Jan 7 (skips Jan 4, a Sunday).
    assert v("WORKDAY.INTL", "2026-01-01", 5, 11) == "2026-01-07"
    # Mask string: weekend = Thu+Fri ("0001100").
    assert v("WORKDAY.INTL", "2026-01-01", 1, "0001100") == "2026-01-03"
    # All-weekend mask is invalid.
    assert isinstance(v("WORKDAY.INTL", "2026-01-01", 1, "1111111"), CellError)


def test_workday_intl_holidays_and_negative():
    assert v("WORKDAY.INTL", "2026-01-01", 5, 1, "2026-01-05") == "2026-01-09"
    assert v("WORKDAY.INTL", "2026-01-08", -5) == "2026-01-01"


def test_networkdays_intl():
    # January 2026: 22 Mon-Fri weekdays.
    assert v("NETWORKDAYS.INTL", "2026-01-01", "2026-01-31") == 22
    # Sunday-only weekend: 31 - 4 Sundays = 27.
    assert v("NETWORKDAYS.INTL", "2026-01-01", "2026-01-31", 11) == 27
    # Reversed order counts negative.
    assert v("NETWORKDAYS.INTL", "2026-01-31", "2026-01-01") == -22
    # Agrees with plain NETWORKDAYS on the default weekend.
    assert v("NETWORKDAYS", "2026-01-01", "2026-01-31") == 22


# --- IM* tail ----------------------------------------------------------------


def _cplx(s):
    from abax.core.science.complexnum import parse
    return parse(s)


def test_im_trig():
    import cmath
    z = 1 + 1j
    assert cmath.isclose(_cplx(v("IMTAN", "1+i")), cmath.tan(z))
    assert cmath.isclose(_cplx(v("IMSEC", "1+i")), 1 / cmath.cos(z))
    assert cmath.isclose(_cplx(v("IMCSC", "1+i")), 1 / cmath.sin(z))
    assert cmath.isclose(_cplx(v("IMCOT", "1+i")), 1 / cmath.tan(z))


def test_im_hyperbolic():
    import cmath
    z = 1 + 1j
    assert cmath.isclose(_cplx(v("IMSINH", "1+i")), cmath.sinh(z))
    assert cmath.isclose(_cplx(v("IMCOSH", "1+i")), cmath.cosh(z))
    assert cmath.isclose(_cplx(v("IMTANH", "1+i")), cmath.tanh(z))
    assert cmath.isclose(_cplx(v("IMSECH", "1+i")), 1 / cmath.cosh(z))
    assert cmath.isclose(_cplx(v("IMCSCH", "1+i")), 1 / cmath.sinh(z))


def test_im_logs():
    import cmath
    # IMLOG2("3+4i"): real = log2(|3+4i|) = log2(5), imag = arg(3+4i)/ln 2.
    got = _cplx(v("IMLOG2", "3+4i"))
    assert cmath.isclose(got, cmath.log(3 + 4j) / math.log(2))
    assert math.isclose(got.real, 2.321928094887362, rel_tol=1e-12)
    assert math.isclose(got.imag, math.atan2(4, 3) / math.log(2), rel_tol=1e-12)
    got10 = _cplx(v("IMLOG10", "3+4i"))
    assert math.isclose(got10.real, 0.698970004336019, rel_tol=1e-12)


def test_im_suffix_and_errors():
    assert v("IMTAN", "j").endswith("j")     # preserves the j suffix
    assert isinstance(v("IMCOT", 0), CellError)
    assert isinstance(v("IMLOG2", 0), CellError)
    assert isinstance(v("IMTAN", "not complex"), CellError)


def test_sheet_integration():
    assert _sheet_val("=SUBTOTAL(9,{1,2,3,4})") == 10
    assert _sheet_val('=XMATCH(25,{10,20,30},1)') == 3
    assert _sheet_val('=CEILING.MATH(-8.1,2)') == -8


# --- ENCODEURL / HYPERLINK ----------------------------------------------------


def test_encodeurl_microsoft_example():
    # Microsoft's worked example: the URL is escaped as a component — every
    # reserved character (:, /, space) is percent-encoded.
    assert (v("ENCODEURL", "http://contoso.sharepoint.com/Finance/Profit and Loss Statement.xlsx")
            == "http%3A%2F%2Fcontoso.sharepoint.com%2FFinance%2FProfit%20and%20Loss%20Statement.xlsx")


def test_encodeurl_unreserved_utf8_and_coercion():
    assert v("ENCODEURL", "AZaz09-_.~") == "AZaz09-_.~"    # unreserved set passes through
    assert v("ENCODEURL", "a b&c=d") == "a%20b%26c%3Dd"
    assert v("ENCODEURL", "café") == "caf%C3%A9"           # UTF-8 bytes, then escaped
    assert v("ENCODEURL", 42) == "42"                      # numbers coerce to text
    err = CellError(CellError.NA)
    assert v("ENCODEURL", err) is err                      # errors propagate


def test_hyperlink_display_value():
    assert v("HYPERLINK", "https://example.org") == "https://example.org"
    assert v("HYPERLINK", "https://example.org", "Example") == "Example"
    assert v("HYPERLINK", "https://example.org", 42) == 42  # friendly name kept verbatim
    err = CellError(CellError.NA)
    assert v("HYPERLINK", err) is err
    assert v("HYPERLINK", "u", err) is err


def test_hyperlink_encodeurl_sheet_integration():
    assert _sheet_val('=HYPERLINK("https://example.org","abax")') == "abax"
    assert _sheet_val('=ENCODEURL("a b")') == "a%20b"
