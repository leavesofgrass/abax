"""Oracle-pinned tests for the REGEX text family (REGEXTEST / REGEXEXTRACT /
REGEXREPLACE). Values are checked against Python's ``re`` (the oracle) and the
Excel-2024 semantics abax mirrors."""

from __future__ import annotations

import re

from abax.core.errors import CellError
from abax.core.regex_fns import _regexextract, _regexreplace, _regextest
from abax.core.sheet import Sheet

# --- REGEXTEST -------------------------------------------------------------


def test_regextest_true():
    assert _regextest(["abc123", r"\d+"]) is True
    # Oracle cross-check.
    assert (re.search(r"\d+", "abc123") is not None) is True


def test_regextest_false():
    assert _regextest(["abcdef", r"\d+"]) is False


def test_regextest_case_sensitivity():
    # Default (0) is case-sensitive: uppercase pattern does not match lowercase.
    assert _regextest(["hello", "HELLO"]) is False
    # case_sensitivity == 1 -> case-insensitive.
    assert _regextest(["hello", "HELLO", 1]) is True


# --- REGEXEXTRACT ----------------------------------------------------------


def test_regexextract_mode0_first_match():
    # Default return_mode 0 -> first whole match.
    assert _regexextract(["a1b2c3", r"\d"]) == "1"
    assert _regexextract(["phone: 555-1234", r"\d{3}-\d{4}"]) == "555-1234"


def test_regexextract_mode1_all_matches_spills():
    # return_mode 1 -> a Python list (spills).
    out = _regexextract(["a1b2c3", r"\d", 1])
    assert out == ["1", "2", "3"]
    assert isinstance(out, list)


def test_regexextract_mode2_capture_groups():
    # return_mode 2 -> capture groups of the first match (a list).
    out = _regexextract(["2026-07-02", r"(\d{4})-(\d{2})-(\d{2})", 2])
    assert out == ["2026", "07", "02"]


def test_regexextract_mode2_no_groups_falls_back_to_whole_match():
    out = _regexextract(["abc", r"a.c", 2])
    assert out == ["abc"]


def test_regexextract_no_match_is_na():
    err = _regexextract(["abcdef", r"\d+"])
    assert isinstance(err, CellError) and err.code == CellError.NA
    # Modes 1 and 2 also yield #N/A when nothing matches.
    assert _regexextract(["abcdef", r"\d+", 1]).code == CellError.NA
    assert _regexextract(["abcdef", r"\d+", 2]).code == CellError.NA


def test_regexextract_case_insensitive():
    assert _regexextract(["Hello", "hello", 0, 1]) == "Hello"


# --- REGEXREPLACE ----------------------------------------------------------


def test_regexreplace_global():
    assert _regexreplace(["a1b2c3", r"\d", "#"]) == "a#b#c#"
    # Oracle cross-check.
    assert re.sub(r"\d", "#", "a1b2c3") == "a#b#c#"


def test_regexreplace_with_backreference():
    assert _regexreplace(["John Smith", r"(\w+) (\w+)", r"\2 \1"]) == "Smith John"


def test_regexreplace_case_insensitive():
    assert _regexreplace(["aAaA", "a", "x", 1]) == "xxxx"


def test_regexreplace_no_match_is_identity():
    assert _regexreplace(["abc", r"\d", "#"]) == "abc"


# --- error handling --------------------------------------------------------


def test_bad_pattern_is_value_error():
    err = _regextest(["abc", "("])  # unbalanced group
    assert isinstance(err, CellError) and err.code == CellError.VALUE
    assert _regexextract(["abc", "("]).code == CellError.VALUE
    assert _regexreplace(["abc", "(", "x"]).code == CellError.VALUE


def test_bad_case_sensitivity_is_value_error():
    err = _regextest(["abc", "a", 2])
    assert isinstance(err, CellError) and err.code == CellError.VALUE


def test_bad_return_mode_is_value_error():
    err = _regexextract(["abc", "a", 5])
    assert isinstance(err, CellError) and err.code == CellError.VALUE


# --- end-to-end through the formula engine ---------------------------------


def test_regex_functions_evaluate_in_sheet():
    s = Sheet()
    s.set("A1", '=REGEXTEST("abc123","\\d+")')
    assert s.get("A1") is True
    s.set("A2", '=REGEXEXTRACT("a1b2c3","\\d")')
    assert s.get("A2") == "1"
    s.set("A3", '=REGEXREPLACE("a1b2","\\d","#")')
    assert s.get("A3") == "a#b#"


def test_regexextract_mode1_spills_in_sheet():
    s = Sheet()
    s.set("A1", '=REGEXEXTRACT("a1b2c3","\\d",1)')
    assert [s.get("A1"), s.get("A2"), s.get("A3")] == ["1", "2", "3"]


def test_regexextract_no_match_is_na_in_sheet():
    s = Sheet()
    s.set("A1", '=REGEXEXTRACT("abc","\\d")')
    val = s.get("A1")
    assert isinstance(val, CellError) and val.code == CellError.NA


# --- caching sanity --------------------------------------------------------


def test_compile_cache_reuses_pattern():
    from abax.core.regex_fns import _compile

    _compile.cache_clear()
    _regextest(["abc", r"\d"])
    _regextest(["xyz", r"\d"])  # same pattern + flags -> a cache hit
    info = _compile.cache_info()
    assert info.hits >= 1
