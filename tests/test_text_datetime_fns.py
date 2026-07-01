"""Tests for the extended text and date/time functions."""

from __future__ import annotations

from abax.core.errors import CellError
from abax.core.text_datetime_fns import (
    SIGNATURES,
    _clean,
    _datevalue,
    _days360,
    _dollar,
    _eomonth,
    _fixed,
    _isoweeknum,
    _networkdays,
    _numbervalue,
    _textafter,
    _textbefore,
    _textjoin,
    _time,
    _timevalue,
    _unichar,
    _unicode,
    _weeknum,
    _workday,
    _yearfrac,
    register,
)

NA = CellError(CellError.NA)
VALUE = CellError(CellError.VALUE)


# --- text ------------------------------------------------------------------


def test_textjoin_ignore_empty():
    assert _textjoin(["-", True, "a", "", "b"]) == "a-b"


def test_textjoin_keep_empty():
    assert _textjoin([",", False, "a", "", "b"]) == "a,,b"


def test_textbefore_first():
    assert _textbefore(["a.b.c", "."]) == "a"


def test_textbefore_second_instance():
    assert _textbefore(["a.b.c", ".", 2]) == "a.b"


def test_textbefore_not_found():
    assert _textbefore(["abc", "."]) == NA


def test_textbefore_negative_instance():
    assert _textbefore(["a.b.c", ".", -1]) == "a.b"


def test_textafter_first():
    assert _textafter(["a.b.c", "."]) == "b.c"


def test_textafter_not_found():
    assert _textafter(["abc", "."]) == NA


def test_unichar():
    assert _unichar([65]) == "A"


def test_unichar_nonpositive():
    assert _unichar([0]) == VALUE


def test_unicode():
    assert _unicode(["A"]) == 65


def test_unicode_empty():
    assert _unicode([""]) == VALUE


def test_clean():
    assert _clean(["a\x07b"]) == "ab"


def test_fixed_default():
    assert _fixed([1234.567, 1]) == "1,234.6"


def test_fixed_no_commas():
    assert _fixed([1234.567, 1, True]) == "1234.6"


def test_dollar():
    assert _dollar([1234.567]) == "$1,234.57"


def test_dollar_negative():
    assert _dollar([-1234.567]) == "($1,234.57)"


def test_numbervalue():
    assert _numbervalue(["1,234.5"]) == 1234.5


# --- date / time -----------------------------------------------------------


def test_time_noon():
    assert _time([12, 0, 0]) == 0.5


def test_timevalue():
    assert _timevalue(["18:00"]) == 0.75


def test_timevalue_ampm():
    assert _timevalue(["6:00 PM"]) == 0.75


def test_datevalue_iso():
    assert _datevalue(["2026-06-30"]) == "2026-06-30"


def test_datevalue_us_format():
    assert _datevalue(["06/30/2026"]) == "2026-06-30"


def test_datevalue_bad():
    assert _datevalue(["not a date"]) == VALUE


def test_eomonth_jan():
    assert _eomonth(["2026-01-15", 1]) == "2026-02-28"


def test_eomonth_leap():
    assert _eomonth(["2024-01-31", 1]) == "2024-02-29"


def test_workday():
    assert _workday(["2026-06-30", 3]) == "2026-07-03"


def test_workday_holidays():
    # 2026-07-03 is a Friday; skip it as a holiday -> next workday Monday.
    assert _workday(["2026-06-30", 3, ["2026-07-03"]]) == "2026-07-06"


def test_networkdays_full_week():
    assert _networkdays(["2026-06-01", "2026-06-05"]) == 5


def test_networkdays_with_weekend():
    assert _networkdays(["2026-06-01", "2026-06-07"]) == 5


def test_isoweeknum():
    assert _isoweeknum(["2026-01-01"]) == 1


def test_weeknum_type1():
    assert _weeknum(["2026-01-01", 1]) == 1


def test_yearfrac_half():
    assert abs(_yearfrac(["2026-01-01", "2026-07-01", 0]) - 0.5) < 1e-9


def test_days360():
    assert _days360(["2026-01-01", "2026-02-01"]) == 30


# --- registration ----------------------------------------------------------


def test_register_adds_all():
    funcs: dict = {}
    register(funcs)
    assert len(funcs) == len(SIGNATURES)


def test_every_name_has_signature():
    funcs: dict = {}
    register(funcs)
    for name in funcs:
        assert name in SIGNATURES
    for name in SIGNATURES:
        assert name in funcs
