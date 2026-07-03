"""Copy / paste / fill / sort operations."""

from __future__ import annotations

from abax.core import Sheet
from abax.core.fill import (
    Clip,
    clip_from_tsv,
    copy_region,
    fill_down,
    fill_right,
    fill_series,
    fill_series_from,
    paste_clip,
    region_to_tsv,
    sort_region,
)


def _grid(rows):
    s = Sheet()
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            if v != "":
                s.set(f"{chr(ord('A') + c)}{r + 1}", str(v))
    return s


def test_copy_and_paste_relative():
    s = _grid([[1, "=A1*2"]])
    clip = copy_region(s, "A1:B1")
    paste_clip(s, clip, "A3")  # shift +2 rows
    assert s.get("A3") == 1
    assert s.get_raw(2, 1) == "=A3*2"  # =A1*2 -> =A3*2
    assert s.get("B3") == 2


def test_paste_absolute_mode():
    s = _grid([["=A1*2"]])
    s.set("A1", "5")
    clip = copy_region(s, "A1:A1")
    paste_clip(s, clip, "C1", mode="absolute")
    assert s.get_raw(0, 2) == "5"


def test_fill_down_shifts_refs():
    s = Sheet()
    s.set("A1", "10")
    s.set("B1", "=A1*2")
    fill_down(s, "B1:B4")
    assert s.get_raw(1, 1) == "=A2*2"
    assert s.get_raw(3, 1) == "=A4*2"


def test_fill_right_shifts_refs():
    s = Sheet()
    s.set("A1", "3")
    s.set("A2", "=A1+1")
    fill_right(s, "A2:D2")
    assert s.get_raw(1, 1) == "=B1+1"
    assert s.get_raw(1, 3) == "=D1+1"


def test_fill_series_numeric_column():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    fill_series(s, "A1:A6")
    assert [s.get(f"A{i}") for i in range(1, 7)] == [1, 2, 3, 4, 5, 6]


def test_fill_series_weekday_row():
    s = Sheet()
    s.set("A1", "Mon")
    fill_series(s, "A1:E1")
    assert [s.get_raw(0, c) for c in range(5)] == ["Mon", "Tue", "Wed", "Thu", "Fri"]


def test_fill_series_from_down_and_right():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    fill_series_from(s, (0, 0, 1, 0), (0, 0, 4, 0))  # drag handle down A2 -> A5
    assert [s.get(f"A{i}") for i in range(1, 6)] == [1, 2, 3, 4, 5]

    s = Sheet()
    s.set("A1", "10")
    s.set("B1", "20")
    fill_series_from(s, (0, 0, 0, 1), (0, 0, 0, 4))  # drag right B1 -> E1
    assert [s.get_raw(0, c) for c in range(5)] == ["10", "20", "30", "40", "50"]


def test_fill_series_from_up_and_left():
    # Drag the handle UP: seeds at the bottom extend the series backwards.
    s = Sheet()
    s.set("A4", "4")
    s.set("A5", "5")
    fill_series_from(s, (3, 0, 4, 0), (0, 0, 4, 0))
    assert [s.get_raw(r, 0) for r in range(5)] == ["1", "2", "3", "4", "5"]

    # Drag the handle LEFT.
    s = Sheet()
    s.set("D1", "40")
    s.set("E1", "50")
    fill_series_from(s, (0, 3, 0, 4), (0, 0, 0, 4))
    assert [s.get_raw(0, c) for c in range(5)] == ["10", "20", "30", "40", "50"]


def test_fill_series_from_backward_dates():
    s = Sheet()
    s.set("A4", "2020-01-04")
    s.set("A5", "2020-01-05")
    fill_series_from(s, (3, 0, 4, 0), (0, 0, 4, 0))
    assert s.get_raw(0, 0) == "2020-01-01"
    assert s.get_raw(2, 0) == "2020-01-03"


def test_sort_region_ascending_and_descending():
    s = _grid([[3, "c"], [1, "a"], [2, "b"]])
    sort_region(s, "A1:B3")  # key col A
    assert [s.get(f"A{i}") for i in range(1, 4)] == [1, 2, 3]
    assert [s.get(f"B{i}") for i in range(1, 4)] == ["a", "b", "c"]
    sort_region(s, "A1:B3", descending=True)
    assert [s.get(f"A{i}") for i in range(1, 4)] == [3, 2, 1]


def test_on_set_callback_records():
    s = Sheet()
    s.set("A1", "1")
    seen = []
    fill_down(s, "A1:A3", on_set=lambda ref, raw: seen.append((ref, raw)))
    assert ("A2", "1") in seen and ("A3", "1") in seen


def test_tsv_roundtrip():
    s = _grid([[1, 2], [3, 4]])
    tsv = region_to_tsv(s, "A1:B2")
    assert tsv == "1\t2\n3\t4"
    clip = clip_from_tsv(tsv)
    assert isinstance(clip, Clip)
    paste_clip(s, clip, "A4", mode="absolute")
    assert s.get("A4") == 1
    assert s.get("B5") == 4
