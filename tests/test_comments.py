"""Cell comments/notes — core set/get, envelope round-trip, structural shifting."""

from __future__ import annotations

from abax.core.reference import parse_a1
from abax.core.sheet import Sheet
from abax.core.workbook import Workbook

# --- set / get --------------------------------------------------------------

def test_set_and_get_comment():
    s = Sheet()
    r, c = parse_a1("B2")
    assert s.get_comment(r, c) is None
    s.set_comment(r, c, "hello note")
    assert s.get_comment(r, c) == "hello note"


def test_empty_text_removes_comment():
    s = Sheet()
    r, c = parse_a1("B2")
    s.set_comment(r, c, "note")
    s.set_comment(r, c, "")
    assert s.get_comment(r, c) is None
    # Whitespace-only is treated as empty too.
    s.set_comment(r, c, "note")
    s.set_comment(r, c, "   \n\t ")
    assert s.get_comment(r, c) is None


def test_comment_is_not_a_value():
    """A comment must not touch the cell's value/formula machinery."""
    s = Sheet()
    r, c = parse_a1("A1")
    s.set_cell(r, c, "=1+1")
    s.set_comment(r, c, "just a note")
    assert s.get_value(r, c) == 2
    assert s.get_comment(r, c) == "just a note"


# --- envelope round-trip ----------------------------------------------------

def test_envelope_round_trip_lossless():
    wb = Workbook()
    sheet = wb.sheet
    r1, c1 = parse_a1("A1")
    r2, c2 = parse_a1("C7")
    sheet.set_cell(r1, c1, "42")
    sheet.set_comment(r1, c1, "the answer")
    sheet.set_comment(r2, c2, "multi\nline\ncomment")

    env = wb.to_envelope()
    # Comments live A1-keyed in the sheet payload, mirroring formats.
    payload = env["data"]["sheets"][0]
    assert payload["comments"] == {"A1": "the answer", "C7": "multi\nline\ncomment"}

    wb2 = Workbook.from_envelope(env)
    s2 = wb2.sheet
    assert s2.get_comment(r1, c1) == "the answer"
    assert s2.get_comment(r2, c2) == "multi\nline\ncomment"
    assert s2.get_comment(*parse_a1("B2")) is None


def test_legacy_envelope_without_comments_loads():
    """Older files predate the 'comments' key — they must still load fine."""
    wb = Workbook()
    env = wb.to_envelope()
    for sheet_payload in env["data"]["sheets"]:
        sheet_payload.pop("comments", None)
    wb2 = Workbook.from_envelope(env)
    assert wb2.sheet.cell_comments == {}


# --- structural shifting ----------------------------------------------------

def test_insert_rows_shifts_comment_down():
    s = Sheet()
    r, c = parse_a1("A3")
    s.set_comment(r, c, "note")
    s.insert_rows(at=0, count=2)  # push everything down by 2
    assert s.get_comment(r, c) is None
    assert s.get_comment(*parse_a1("A5")) == "note"


def test_delete_rows_shifts_comment_up():
    s = Sheet()
    r, c = parse_a1("A5")
    s.set_comment(r, c, "note")
    s.delete_rows(at=0, count=2)  # pull everything up by 2
    assert s.get_comment(*parse_a1("A3")) == "note"


def test_delete_rows_removes_comment_in_deleted_range():
    s = Sheet()
    s.set_comment(*parse_a1("A2"), "gone")
    s.set_comment(*parse_a1("A5"), "kept")
    s.delete_rows(at=1, count=2)  # deletes rows 2-3 (0-based 1-2)
    assert s.get_comment(*parse_a1("A2")) is None  # A2 was deleted
    assert s.get_comment(*parse_a1("A3")) == "kept"  # A5 -> A3


def test_insert_cols_shifts_comment_right():
    s = Sheet()
    r, c = parse_a1("B1")
    s.set_comment(r, c, "note")
    s.insert_cols(at=0, count=1)
    assert s.get_comment(*parse_a1("C1")) == "note"


def test_delete_cols_shifts_comment_left():
    s = Sheet()
    r, c = parse_a1("C1")
    s.set_comment(r, c, "note")
    s.delete_cols(at=0, count=1)
    assert s.get_comment(*parse_a1("B1")) == "note"


def test_delete_cols_removes_comment_in_deleted_range():
    s = Sheet()
    s.set_comment(*parse_a1("B1"), "gone")
    s.set_comment(*parse_a1("E1"), "kept")
    s.delete_cols(at=1, count=2)  # deletes cols B,C
    assert s.get_comment(*parse_a1("B1")) is None
    assert s.get_comment(*parse_a1("C1")) == "kept"  # E1 -> C1
