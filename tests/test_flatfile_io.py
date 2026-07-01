"""Tests for flat-file (JSON Lines and fixed-width) Sheet I/O."""

from __future__ import annotations

from abax.core.io.flatfile_io import (
    dumps_fixed,
    dumps_jsonl,
    load_fixed,
    load_jsonl,
    loads_fixed,
    loads_jsonl,
    save_fixed,
    save_jsonl,
)
from abax.core.sheet import Sheet

# --- JSON Lines -----------------------------------------------------------


def _records_sheet() -> Sheet:
    s = Sheet()
    s.set_cell(0, 0, "name")
    s.set_cell(0, 1, "age")
    s.set_cell(1, 0, "Alice")
    s.set_cell(1, 1, "30")
    s.set_cell(2, 0, "Bob")
    s.set_cell(2, 1, "25")
    return s


def test_jsonl_round_trip_preserves_header_and_values():
    s = _records_sheet()
    text = dumps_jsonl(s)
    out = loads_jsonl(text)

    assert out.get_raw(0, 0) == "name"
    assert out.get_raw(0, 1) == "age"
    assert out.get_raw(1, 0) == "Alice"
    assert out.get_raw(1, 1) == "30"
    assert out.get_raw(2, 0) == "Bob"
    assert out.get_raw(2, 1) == "25"
    assert out.used_bounds() == (3, 2)


def test_jsonl_differing_keys_produce_union_header():
    text = "\n".join(
        [
            '{"name": "Alice", "age": "30"}',
            '{"name": "Bob", "city": "NYC"}',
        ]
    )
    s = loads_jsonl(text)
    # Union, first-seen order: name, age, city.
    assert s.get_raw(0, 0) == "name"
    assert s.get_raw(0, 1) == "age"
    assert s.get_raw(0, 2) == "city"
    # Row 1: Alice has no city.
    assert s.get_raw(1, 0) == "Alice"
    assert s.get_raw(1, 1) == "30"
    assert s.get_raw(1, 2) == ""
    # Row 2: Bob has no age (missing-key cell becomes "").
    assert s.get_raw(2, 0) == "Bob"
    assert s.get_raw(2, 1) == ""
    assert s.get_raw(2, 2) == "NYC"


def test_jsonl_missing_key_cells_round_trip_empty():
    text = "\n".join(
        [
            '{"a": "1", "b": "2"}',
            '{"a": "3"}',
        ]
    )
    s = loads_jsonl(text)
    out = loads_jsonl(dumps_jsonl(s))
    assert out.get_raw(2, 0) == "3"
    assert out.get_raw(2, 1) == ""


def test_jsonl_save_and_load_file(tmp_path):
    s = _records_sheet()
    path = tmp_path / "people.jsonl"
    save_jsonl(s, path)
    out = load_jsonl(path)
    assert out.get_raw(0, 0) == "name"
    assert out.get_raw(1, 0) == "Alice"
    assert out.name == "people"


# --- Fixed-width ----------------------------------------------------------


def test_loads_fixed_splits_on_2plus_spaces():
    text = "name   age   city\n" "Alice  30    NYC\n" "Bob    25    LA"
    s = loads_fixed(text)
    assert s.get_raw(0, 0) == "name"
    assert s.get_raw(0, 1) == "age"
    assert s.get_raw(0, 2) == "city"
    assert s.get_raw(1, 0) == "Alice"
    assert s.get_raw(1, 2) == "NYC"
    assert s.get_raw(2, 1) == "25"
    assert s.used_bounds() == (3, 3)


def test_dumps_fixed_pads_columns():
    s = _records_sheet()
    text = dumps_fixed(s, gap=2)
    lines = text.splitlines()
    # "name" is 4 wide, "Alice" is 5 wide -> column 0 width = 5 + gap(2) = 7.
    assert lines[0] == "name   age"
    assert lines[1] == "Alice  30"
    assert lines[2] == "Bob    25"


def test_fixed_round_trip():
    s = _records_sheet()
    out = loads_fixed(dumps_fixed(s))
    assert out.get_raw(0, 0) == "name"
    assert out.get_raw(1, 0) == "Alice"
    assert out.get_raw(1, 1) == "30"
    assert out.get_raw(2, 0) == "Bob"
    assert out.get_raw(2, 1) == "25"
    assert out.used_bounds() == s.used_bounds()


def test_loads_fixed_explicit_widths():
    text = "Alice30NYC\n" "Bob  25LA "
    s = loads_fixed(text, widths=[5, 2, 3])
    assert s.get_raw(0, 0) == "Alice"
    assert s.get_raw(0, 1) == "30"
    assert s.get_raw(0, 2) == "NYC"
    assert s.get_raw(1, 0) == "Bob"
    assert s.get_raw(1, 1) == "25"
    assert s.get_raw(1, 2) == "LA"


def test_fixed_save_and_load_file(tmp_path):
    s = _records_sheet()
    path = tmp_path / "people.txt"
    save_fixed(s, path)
    out = load_fixed(path)
    assert out.get_raw(0, 0) == "name"
    assert out.get_raw(2, 0) == "Bob"
    assert out.name == "people"
