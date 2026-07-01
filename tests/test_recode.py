"""Tests for the column recode / clean engine (``abax.core.recode``)."""

from __future__ import annotations

import pytest

from abax.core import recode
from abax.core.recode import RecodeError


# --------------------------------------------------------------------------- #
# retype                                                                       #
# --------------------------------------------------------------------------- #
def test_retype_int_passthrough_unparseable():
    assert recode.retype(["1", "2", "x"], "int") == ["1", "2", "x"]


def test_retype_float_to_int_truncates_whole():
    # Documented behaviour: "1.0" -> "1"; "2.5" is not whole so stays unchanged.
    assert recode.retype(["1.0", "2.5"], "int") == ["1", "2.5"]


def test_retype_float_canonical():
    assert recode.retype(["1", "3.14", "x"], "float") == ["1", "3.14", "x"]


def test_retype_bool():
    assert recode.retype(["true", "no", "x"], "bool") == ["True", "False", "x"]


def test_retype_date_iso():
    assert recode.retype(["2020-01-02", "nope"], "date") == ["2020-01-02", "nope"]


def test_retype_text_identity():
    assert recode.retype(["a", "1", ""], "text") == ["a", "1", ""]


def test_retype_blanks_preserved():
    assert recode.retype(["1", "", "3"], "int") == ["1", "", "3"]


def test_retype_unknown_target_raises():
    with pytest.raises(RecodeError):
        recode.retype(["1"], "complex")


# --------------------------------------------------------------------------- #
# fill_missing                                                                 #
# --------------------------------------------------------------------------- #
def test_fill_value():
    assert recode.fill_missing(["a", "", "b"], "value", "Z") == ["a", "Z", "b"]


def test_fill_zero():
    assert recode.fill_missing(["1", "", "3"], "zero") == ["1", "0", "3"]


def test_fill_ffill():
    assert recode.fill_missing(["1", "", "3"], "ffill") == ["1", "1", "3"]


def test_fill_ffill_leading_blank():
    assert recode.fill_missing(["", "2", ""], "ffill") == ["", "2", "2"]


def test_fill_bfill():
    assert recode.fill_missing(["1", "", "3"], "bfill") == ["1", "3", "3"]


def test_fill_bfill_trailing_blank():
    assert recode.fill_missing(["1", "", ""], "bfill") == ["1", "", ""]


def test_fill_mean():
    assert recode.fill_missing(["2", "", "4"], "mean") == ["2", "3", "4"]


def test_fill_median():
    assert recode.fill_missing(["1", "", "2", "4"], "median") == ["1", "2", "2", "4"]


def test_fill_mean_non_numeric_raises():
    with pytest.raises(RecodeError):
        recode.fill_missing(["a", "", "b"], "mean")


def test_fill_unknown_method_raises():
    with pytest.raises(RecodeError):
        recode.fill_missing(["1"], "bogus")


# --------------------------------------------------------------------------- #
# strip_whitespace / to_case                                                   #
# --------------------------------------------------------------------------- #
def test_strip_whitespace():
    assert recode.strip_whitespace([" a ", "b "]) == ["a", "b"]


def test_strip_whitespace_blank_preserved():
    assert recode.strip_whitespace(["", "   "]) == ["", ""]


def test_to_case_upper():
    assert recode.to_case(["aa", "bb"], "upper") == ["AA", "BB"]


def test_to_case_lower():
    assert recode.to_case(["AA", "Bb"], "lower") == ["aa", "bb"]


def test_to_case_title():
    assert recode.to_case(["hello world", "foo"], "title") == ["Hello World", "Foo"]


def test_to_case_unknown_raises():
    with pytest.raises(RecodeError):
        recode.to_case(["a"], "sentence")


# --------------------------------------------------------------------------- #
# standardize_dates                                                            #
# --------------------------------------------------------------------------- #
def test_standardize_dates_us_slash():
    assert recode.standardize_dates(["01/02/2020"]) == ["2020-01-02"]


def test_standardize_dates_iso_passthrough():
    assert recode.standardize_dates(["2020-01-02"]) == ["2020-01-02"]


def test_standardize_dates_mon_name():
    assert recode.standardize_dates(["02-Jan-2020"]) == ["2020-01-02"]


def test_standardize_dates_short_year():
    assert recode.standardize_dates(["1/2/20"]) == ["2020-01-02"]


def test_standardize_dates_unparseable_stays():
    assert recode.standardize_dates(["not a date"]) == ["not a date"]


def test_standardize_dates_blank_preserved():
    assert recode.standardize_dates(["", "01/02/2020"]) == ["", "2020-01-02"]


def test_standardize_dates_custom_format():
    assert recode.standardize_dates(["2020-01-02"], "%m/%d/%Y") == ["01/02/2020"]


# --------------------------------------------------------------------------- #
# map_values                                                                   #
# --------------------------------------------------------------------------- #
def test_map_values_basic():
    out = recode.map_values(["M", "F", "M"], {"M": "male", "F": "female"})
    assert out == ["male", "female", "male"]


def test_map_values_unmapped_keeps_original():
    out = recode.map_values(["M", "X"], {"M": "male"})
    assert out == ["male", "X"]


def test_map_values_default():
    out = recode.map_values(["M", "X"], {"M": "male"}, default="?")
    assert out == ["male", "?"]


# --------------------------------------------------------------------------- #
# normalize                                                                    #
# --------------------------------------------------------------------------- #
def test_normalize_minmax():
    assert recode.normalize(["0", "5", "10"], "minmax") == ["0", "0.5", "1"]


def test_normalize_minmax_blank_preserved():
    out = recode.normalize(["0", "", "10"], "minmax")
    assert out == ["0", "", "1"]


def test_normalize_minmax_constant_column():
    assert recode.normalize(["5", "5", "5"], "minmax") == ["0", "0", "0"]


def test_normalize_zscore_mean_zero():
    out = recode.normalize(["1", "2", "3", "4", "5"], "zscore")
    vals = [float(x) for x in out]
    assert abs(sum(vals) / len(vals)) < 1e-9


def test_normalize_non_numeric_raises():
    with pytest.raises(RecodeError):
        recode.normalize(["a", "b"], "minmax")


def test_normalize_unknown_method_raises():
    with pytest.raises(RecodeError):
        recode.normalize(["1", "2"], "bogus")


# --------------------------------------------------------------------------- #
# clip                                                                         #
# --------------------------------------------------------------------------- #
def test_clip_both_bounds():
    assert recode.clip(["1", "5", "10"], low=2, high=8) == ["2", "5", "8"]


def test_clip_low_only():
    assert recode.clip(["1", "5", "10"], low=3) == ["3", "5", "10"]


def test_clip_high_only():
    assert recode.clip(["1", "5", "10"], high=4) == ["1", "4", "4"]


def test_clip_blank_and_non_numeric_passthrough():
    assert recode.clip(["1", "", "x", "10"], low=2, high=8) == ["2", "", "x", "8"]


# --------------------------------------------------------------------------- #
# OPERATIONS registry                                                          #
# --------------------------------------------------------------------------- #
def test_operations_has_entry_per_op():
    expected = {
        "retype",
        "fill_missing",
        "strip_whitespace",
        "to_case",
        "standardize_dates",
        "map_values",
        "normalize",
        "clip",
    }
    assert expected <= set(recode.OPERATIONS)


def test_operations_entries_well_formed():
    for name, meta in recode.OPERATIONS.items():
        assert {"label", "doc", "needs_arg"} <= set(meta)
        assert isinstance(meta["label"], str) and meta["label"]
        assert isinstance(meta["doc"], str) and meta["doc"]
        assert isinstance(meta["needs_arg"], bool)
