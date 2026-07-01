"""Tests for the workbook named-range registry (``abax.core.names``)."""

from __future__ import annotations

import pytest

from abax.core.names import (
    NameError,
    NameRegistry,
    is_valid_name,
    normalize_target,
)

# --- is_valid_name ---------------------------------------------------------


def test_is_valid_name_accepts_plain():
    assert is_valid_name("Sales")


def test_is_valid_name_rejects_cell_ref():
    assert not is_valid_name("A1")
    assert not is_valid_name("$B$2")


def test_is_valid_name_rejects_leading_digit():
    assert not is_valid_name("1abc")


def test_is_valid_name_rejects_reserved():
    assert not is_valid_name("TRUE")
    assert not is_valid_name("false")
    assert not is_valid_name("R")
    assert not is_valid_name("c")


def test_is_valid_name_allows_dots_and_underscores():
    assert is_valid_name("tax_rate.2")
    assert is_valid_name("_hidden")


def test_is_valid_name_length_bounds():
    assert not is_valid_name("")
    assert is_valid_name("a" * 255)
    assert not is_valid_name("a" * 256)


# --- normalize_target ------------------------------------------------------


def test_normalize_target_range():
    assert normalize_target("A1:C3") == "A1:C3"


def test_normalize_target_absolute_cell():
    assert normalize_target("$B$2") == "$B$2"


def test_normalize_target_trims():
    assert normalize_target("  A1  ") == "A1"


def test_normalize_target_keeps_qualifier():
    assert normalize_target("Sheet1!A1:B2") == "Sheet1!A1:B2"
    assert normalize_target("Sheet1!B2") == "Sheet1!B2"


def test_normalize_target_rejects_garbage():
    with pytest.raises(NameError):
        normalize_target("not a ref")


def test_normalize_target_rejects_empty():
    with pytest.raises(NameError):
        normalize_target("   ")


# --- define / lookup -------------------------------------------------------


def test_define_and_lookup_case_insensitive():
    reg = NameRegistry()
    reg.define("Sales", "A1:A10")
    assert reg.lookup("sales") == "A1:A10"
    assert reg.lookup("SALES") == "A1:A10"


def test_lookup_missing_returns_none():
    reg = NameRegistry()
    assert reg.lookup("nope") is None


def test_redefining_overwrites_and_preserves_case():
    reg = NameRegistry()
    reg.define("Sales", "A1:A10")
    reg.define("SALES", "B1:B5")
    assert reg.lookup("sales") == "B1:B5"
    # Display case is the most recent definition.
    assert reg.names() == [("SALES", "B1:B5")]


def test_define_invalid_name_raises():
    reg = NameRegistry()
    with pytest.raises(NameError):
        reg.define("A1", "B2")


def test_define_invalid_target_raises():
    reg = NameRegistry()
    with pytest.raises(NameError):
        reg.define("Sales", "not a ref")


# --- has / rename / remove -------------------------------------------------


def test_has():
    reg = NameRegistry()
    reg.define("Sales", "A1:A10")
    assert reg.has("SALES")
    assert not reg.has("Costs")


def test_rename():
    reg = NameRegistry()
    reg.define("Sales", "A1:A10")
    reg.rename("Sales", "Revenue")
    assert not reg.has("Sales")
    assert reg.lookup("revenue") == "A1:A10"


def test_rename_missing_raises():
    reg = NameRegistry()
    with pytest.raises(NameError):
        reg.rename("Ghost", "Revenue")


def test_rename_to_taken_raises():
    reg = NameRegistry()
    reg.define("Sales", "A1:A10")
    reg.define("Costs", "B1:B10")
    with pytest.raises(NameError):
        reg.rename("Sales", "Costs")


def test_rename_to_invalid_raises():
    reg = NameRegistry()
    reg.define("Sales", "A1:A10")
    with pytest.raises(NameError):
        reg.rename("Sales", "A1")


def test_rename_same_name_different_case_ok():
    reg = NameRegistry()
    reg.define("Sales", "A1:A10")
    reg.rename("Sales", "SALES")
    assert reg.lookup("sales") == "A1:A10"
    assert reg.names() == [("SALES", "A1:A10")]


def test_remove():
    reg = NameRegistry()
    reg.define("Sales", "A1:A10")
    reg.remove("sales")
    assert not reg.has("Sales")


def test_remove_missing_raises():
    reg = NameRegistry()
    with pytest.raises(NameError):
        reg.remove("Ghost")


# --- names / to_dict / from_dict ------------------------------------------


def test_names_sorted_case_insensitive():
    reg = NameRegistry()
    reg.define("zebra", "A1")
    reg.define("Apple", "B2")
    reg.define("mango", "C3")
    assert reg.names() == [("Apple", "B2"), ("mango", "C3"), ("zebra", "A1")]


def test_to_dict_from_dict_round_trip():
    reg = NameRegistry()
    reg.define("Sales", "A1:A10")
    reg.define("Tax", "$B$2")
    d = reg.to_dict()
    assert d == {"Sales": "A1:A10", "Tax": "$B$2"}
    reg2 = NameRegistry.from_dict(d)
    assert reg2.to_dict() == d


# --- version / len (resolved-AST cache invalidation) -----------------------


def test_version_bumps_on_mutation():
    reg = NameRegistry()
    v0 = reg.version
    reg.define("Sales", "A1:A10")
    v1 = reg.version
    assert v1 > v0
    reg.rename("Sales", "Revenue")
    v2 = reg.version
    assert v2 > v1
    reg.remove("Revenue")
    assert reg.version > v2


def test_len_and_truthiness():
    reg = NameRegistry()
    assert len(reg) == 0
    assert not reg
    reg.define("Sales", "A1:A10")
    assert len(reg) == 1
    assert reg


def test_from_dict_skips_invalid_entries():
    reg = NameRegistry.from_dict(
        {
            "Sales": "A1:A10",
            "A1": "B2",          # invalid name
            "Bad": "not a ref",  # invalid target
            "Tax": "$B$2",
        }
    )
    assert reg.has("Sales")
    assert reg.has("Tax")
    assert not reg.has("A1")
    assert not reg.has("Bad")
    assert len(reg.names()) == 2
