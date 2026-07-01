"""The shared Excel-criteria engine (core/criteria.py)."""

from __future__ import annotations

from abax.core.criteria import make_predicate


def test_numeric_comparisons():
    assert make_predicate(">10")(11)
    assert not make_predicate(">10")(10)
    assert make_predicate(">=10")(10)
    assert make_predicate("<>0")(5)
    assert not make_predicate("<>0")(0)
    assert make_predicate("100")(100.0)


def test_text_equality_case_insensitive():
    p = make_predicate("Apple")
    assert p("apple")
    assert p("APPLE")
    assert not p("banana")


def test_wildcards():
    assert make_predicate("a*")("apple")
    assert not make_predicate("a*")("banana")
    assert make_predicate("?at")("cat")
    assert not make_predicate("?at")("coat")


def test_not_equal_text():
    p = make_predicate("<>apple")
    assert p("banana")
    assert not p("Apple")


def test_number_criterion_ignores_text_cells():
    p = make_predicate(10)
    assert p(10)
    assert not p("10")  # text 10 does not match a numeric criterion
