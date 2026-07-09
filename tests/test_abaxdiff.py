"""Cell-level workbook diff engine — added/removed/changed cells, whole sheets.

Envelopes are built through the real :class:`Workbook` (set cells, then
``to_envelope()``) so the test exercises the exact schema the diff engine reads,
not a hand-rolled approximation of it.
"""

from __future__ import annotations

import json

import pytest

from abax.core.abaxdiff import (
    DiffError,
    diff_envelopes,
    diff_files,
    render_text,
)
from abax.core.workbook import Workbook


def _old_env() -> dict:
    """Baseline workbook: A1 formula, B1 value, C1 value (to be removed)."""
    wb = Workbook()
    sh = wb.sheets[0]  # "Sheet1"
    sh.set("A1", "=B1+C1")
    sh.set("B1", "10")
    sh.set("C1", "old")
    return wb.to_envelope()


def _new_env() -> dict:
    """Edited workbook: A1 formula changed, C1 removed, B5 added, whole Sheet2 added."""
    wb = Workbook()
    sh = wb.sheets[0]  # "Sheet1"
    sh.set("A1", "=B1*C1")  # changed
    sh.set("B1", "10")      # unchanged
    sh.set("B5", "42")      # added
    # C1 intentionally absent -> removed
    sh2 = wb.add_sheet("Sheet2")  # whole-sheet add
    sh2.set("A1", "new")
    return wb.to_envelope()


def test_cell_level_added_removed_changed():
    diff = diff_envelopes(_old_env(), _new_env())
    s1 = next(s for s in diff.sheets if s.name == "Sheet1")

    assert s1.added == {"B5": "42"}
    assert s1.removed == {"C1": "old"}
    assert s1.changed == {"A1": ("=B1+C1", "=B1*C1")}
    assert s1.only_in is None
    assert not s1.is_empty


def test_whole_sheet_add():
    diff = diff_envelopes(_old_env(), _new_env())
    s2 = next(s for s in diff.sheets if s.name == "Sheet2")

    assert s2.only_in == "new"
    assert s2.added == {"A1": "new"}
    assert s2.removed == {}
    assert s2.changed == {}


def test_rollup_counts():
    diff = diff_envelopes(_old_env(), _new_env())
    # Sheet1: 1 added (B5), 1 removed (C1), 1 changed (A1); Sheet2: 1 added (A1).
    assert diff.added == 2
    assert diff.removed == 1
    assert diff.changed == 1
    assert not diff.is_empty


def test_render_text_has_marker_lines():
    diff = diff_envelopes(_old_env(), _new_env())
    report = render_text(diff)

    assert "+B5: 42" in report
    assert "-C1: old" in report
    assert "~A1: =B1+C1 -> =B1*C1" in report
    assert "Sheet2" in report
    assert "(added sheet)" in report


def test_render_text_color_wraps_ansi():
    diff = diff_envelopes(_old_env(), _new_env())
    report = render_text(diff, color=True)

    assert "\x1b[32m" in report  # green (added)
    assert "\x1b[31m" in report  # red (removed)
    assert "\x1b[33m" in report  # yellow (changed)
    assert "\x1b[0m" in report   # reset


def test_identical_is_empty():
    env = _old_env()
    diff = diff_envelopes(env, json.loads(json.dumps(env)))  # deep copy

    assert diff.is_empty
    assert diff.added == diff.removed == diff.changed == 0
    assert render_text(diff) == ""
    assert render_text(diff, color=True) == ""


def test_removed_sheet_tagged():
    # Reverse direction: Sheet2 present in "old" but not "new" -> removed sheet.
    diff = diff_envelopes(_new_env(), _old_env())
    s2 = next(s for s in diff.sheets if s.name == "Sheet2")

    assert s2.only_in == "old"
    assert s2.removed == {"A1": "new"}
    assert "(removed sheet)" in render_text(diff)


def test_diff_files_roundtrip(tmp_path):
    old_p = tmp_path / "old.abax"
    new_p = tmp_path / "new.abax"
    old_p.write_text(json.dumps(_old_env()), encoding="utf-8")
    new_p.write_text(json.dumps(_new_env()), encoding="utf-8")

    diff = diff_files(str(old_p), str(new_p))
    assert diff.added == 2
    assert diff.changed == 1


def test_malformed_file_raises_diff_error(tmp_path):
    bad = tmp_path / "bad.abax"
    bad.write_text("{ not json", encoding="utf-8")
    with pytest.raises(DiffError):
        diff_files(str(bad), str(bad))


def test_malformed_envelope_raises_diff_error():
    with pytest.raises(DiffError):
        diff_envelopes({"data": {"sheets": "not-a-list"}}, _new_env())
