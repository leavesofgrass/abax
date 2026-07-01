"""Tests for the data-validation rule model (``abax.core.validation``)."""

from __future__ import annotations

import pytest

from abax.core.validation import (
    KINDS,
    OPS,
    ValidationRule,
    list_rule,
    number_rule,
    validate,
)

# --- list rules -----------------------------------------------------------


def test_list_rule_accepts_member():
    r = list_rule(["a", "b", "c"])
    assert validate("a", r) == (True, "")


def test_list_rule_rejects_nonmember_with_options_in_message():
    r = list_rule(["a", "b", "c"])
    ok, msg = validate("z", r)
    assert ok is False
    assert "a" in msg and "b" in msg and "c" in msg


def test_list_rule_blank_ignore_blank_true_ok():
    r = list_rule(["a", "b", "c"])
    assert validate("", r) == (True, "")


def test_list_rule_blank_ignore_blank_false_not_ok():
    r = list_rule(["a", "b", "c"], ignore_blank=False)
    ok, _ = validate("", r)
    assert ok is False


# --- whole rules ----------------------------------------------------------


def test_whole_between_ok():
    r = number_rule("whole", "between", "1", "10")
    assert validate("5", r) == (True, "")


def test_whole_between_above_range_not_ok():
    r = number_rule("whole", "between", "1", "10")
    ok, _ = validate("11", r)
    assert ok is False


def test_whole_rejects_decimal_value():
    r = number_rule("whole", "between", "1", "10")
    ok, msg = validate("1.5", r)
    assert ok is False
    assert "whole" in msg.lower()


def test_whole_rejects_nonnumeric():
    r = number_rule("whole", "between", "1", "10")
    ok, _ = validate("abc", r)
    assert ok is False


# --- decimal rules --------------------------------------------------------


def test_decimal_gt_ok():
    r = number_rule("decimal", "gt", "0")
    assert validate("0.5", r) == (True, "")


def test_decimal_gt_not_ok():
    r = number_rule("decimal", "gt", "0")
    ok, _ = validate("-1", r)
    assert ok is False


# --- textlen rules --------------------------------------------------------


def test_textlen_le_ok():
    r = ValidationRule(kind="textlen", op="le", p1="3")
    assert validate("abc", r) == (True, "")


def test_textlen_le_not_ok():
    r = ValidationRule(kind="textlen", op="le", p1="3")
    ok, _ = validate("abcd", r)
    assert ok is False


# --- custom message -------------------------------------------------------


def test_custom_message_returned_on_failure():
    r = number_rule("whole", "between", "1", "10")
    r = ValidationRule(
        kind=r.kind, op=r.op, p1=r.p1, p2=r.p2, message="pick 1-10"
    )
    ok, msg = validate("99", r)
    assert ok is False
    assert msg == "pick 1-10"


# --- round-trips ----------------------------------------------------------


def test_list_rule_to_dict_is_compact():
    r = list_rule(["a", "b"])
    d = r.to_dict()
    assert d == {"kind": "list", "values": ["a", "b"]}


def test_list_rule_round_trip():
    r = list_rule(["a", "b", "c"])
    assert ValidationRule.from_dict(r.to_dict()) == r


def test_number_rule_round_trip():
    r = number_rule("whole", "between", "1", "10")
    restored = ValidationRule.from_dict(r.to_dict())
    assert restored == r
    assert isinstance(restored.values, tuple)


# --- errors ---------------------------------------------------------------


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        validate("x", ValidationRule(kind="bogus"))


def test_unknown_op_raises_in_validate():
    with pytest.raises(ValueError):
        validate("5", ValidationRule(kind="whole", op="bogus"))


def test_number_rule_rejects_bad_kind():
    with pytest.raises(ValueError):
        number_rule("list", "between", "1", "10")


def test_number_rule_rejects_bad_op():
    with pytest.raises(ValueError):
        number_rule("whole", "bogus", "1", "10")


def test_kinds_and_ops_constants():
    assert KINDS == ("list", "whole", "decimal", "textlen")
    assert OPS == ("between", "notbetween", "eq", "ne", "gt", "lt", "ge", "le")
