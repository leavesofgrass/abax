"""Tests for qcell.core.science.dxcc (callsign -> DXCC entity lookup)."""

from __future__ import annotations

import pytest

from qcell.core.science.dxcc import PREFIXES, entity_for_call


def test_table_is_nonempty_and_uppercase() -> None:
    assert len(PREFIXES) >= 120
    for prefix, entity in PREFIXES.items():
        assert prefix == prefix.upper()
        assert prefix.isalnum()
        assert entity and isinstance(entity, str)


@pytest.mark.parametrize(
    ("call", "entity"),
    [
        ("W1AW", "United States"),
        ("N7XYZ", "United States"),
        ("KH6AA", "Hawaii"),
        ("KL7RA", "Alaska"),
        ("KP4XX", "Puerto Rico"),
        ("VE3ABC", "Canada"),
        ("G0ABC", "England"),
        ("GM3XXX", "Scotland"),
        ("GW4ABC", "Wales"),
        ("GI6ABC", "Northern Ireland"),
        ("DL1ABC", "Germany"),
        ("F5XXX", "France"),
        ("I2ABC", "Italy"),
        ("EA4XXX", "Spain"),
        ("JA1XYZ", "Japan"),
        ("VK2DEF", "Australia"),
        ("ZL1XX", "New Zealand"),
        ("PY2XX", "Brazil"),
        ("LU5ABC", "Argentina"),
        ("XE1ABC", "Mexico"),
        ("VU2ABC", "India"),
        ("ZS6ABC", "South Africa"),
        ("RA3ABC", "Russia"),
        ("BA4ABC", "China"),
    ],
)
def test_basic_entities(call: str, entity: str) -> None:
    assert entity_for_call(call) == entity


def test_longest_prefix_beats_generic() -> None:
    # KH6 (Hawaii) and KL7 (Alaska) must win over the generic K (United States).
    assert entity_for_call("KH6AA") == "Hawaii"
    assert entity_for_call("KL7RA") == "Alaska"
    assert entity_for_call("KP4XX") == "Puerto Rico"
    # A plain K call still resolves to the US.
    assert entity_for_call("K1ABC") == "United States"


def test_case_and_whitespace_normalisation() -> None:
    assert entity_for_call("  dl1abc  ") == "Germany"
    assert entity_for_call("w1aw") == "United States"


def test_operational_suffixes_are_ignored() -> None:
    assert entity_for_call("DL1ABC/P") == "Germany"
    assert entity_for_call("W1AW/QRP") == "United States"
    assert entity_for_call("VK2DEF/M") == "Australia"
    assert entity_for_call("G0ABC/MM") == "England"
    assert entity_for_call("W1AW/7") == "United States"
    assert entity_for_call("DL1ABC/P/QRP") == "Germany"


def test_relocation_prefix_override() -> None:
    assert entity_for_call("DL/W1AW") == "Germany"
    assert entity_for_call("F/G0ABC") == "France"
    assert entity_for_call("VK/ZL1XX") == "Australia"
    # Combined: re-location prefix plus trailing suffix.
    assert entity_for_call("DL/W1AW/P") == "Germany"


def test_unknown_and_garbage_calls() -> None:
    assert entity_for_call("") is None
    assert entity_for_call("   ") is None
    assert entity_for_call("12345") is None
    assert entity_for_call("QQQ9ZZ") is None
    assert entity_for_call("///") is None
