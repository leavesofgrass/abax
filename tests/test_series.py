"""Autofill series detection (the gnumeric fill-series feature)."""

from __future__ import annotations

from abax.core.series import extend_series


def test_numeric_progression():
    assert extend_series(["1", "2"], 3) == ["3", "4", "5"]
    assert extend_series(["10", "20"], 2) == ["30", "40"]
    assert extend_series(["5"], 3) == ["6", "7", "8"]  # single seed -> +1


def test_numeric_negative_step():
    assert extend_series(["10", "8"], 3) == ["6", "4", "2"]


def test_weekday_cycle():
    assert extend_series(["Mon", "Tue"], 3) == ["Wed", "Thu", "Fri"]
    assert extend_series(["Saturday"], 2) == ["Sunday", "Monday"]


def test_month_cycle_case_preserved():
    assert extend_series(["Jan", "Feb"], 2) == ["Mar", "Apr"]
    assert extend_series(["JAN"], 1) == ["FEB"]  # upper preserved


def test_date_progression():
    assert extend_series(["2026-01-01", "2026-01-02"], 2) == ["2026-01-03", "2026-01-04"]
    assert extend_series(["2026-01-01"], 1) == ["2026-01-02"]


def test_text_with_number():
    assert extend_series(["Item 1"], 2) == ["Item 2", "Item 3"]
    assert extend_series(["Q1", "Q3"], 2) == ["Q5", "Q7"]  # step 2


def test_fallback_repeats():
    assert extend_series(["a", "b"], 3) == ["a", "b", "a"]
