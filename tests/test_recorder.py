"""Macro recording: capture, replay, .py emission, JSON round-trip."""

from __future__ import annotations

from abax.core.workbook import Workbook
from abax.macros import load_macro_file, run_macro
from abax.recorder import Action, MacroRecorder


def _recording() -> MacroRecorder:
    rec = MacroRecorder()
    rec.start("demo")
    rec.record_set("A1", "10")
    rec.record_set("A2", "=A1*2")
    rec.record_set("A2", "=A1*3")  # collapses with previous (same ref)
    rec.record_clear("B1")
    rec.stop()
    return rec


def test_capture_collapses_repeated_sets():
    rec = _recording()
    sets = [a for a in rec.actions if a.kind == "set"]
    assert [a.ref for a in sets] == ["A1", "A2"]
    assert sets[1].raw == "=A1*3"  # last write wins
    assert rec.actions[-1] == Action("clear", ref="B1")


def test_not_recording_captures_nothing():
    rec = MacroRecorder()
    rec.record_set("A1", "x")  # recording is False
    assert rec.count == 0


def test_toggle():
    rec = MacroRecorder()
    assert rec.toggle() is True
    assert rec.recording is True
    assert rec.toggle() is False


def test_replay_reproduces_state():
    rec = _recording()
    wb = Workbook()
    rec.replay(wb)
    assert wb.sheet.get("A1") == 10
    assert wb.sheet.get("A2") == 30
    assert wb.sheet.get("B1") is None  # cleared


def test_to_macro_source_is_valid_runnable_macro(tmp_path):
    rec = _recording()
    path = rec.save_macro(tmp_path / "rec.py", "myrec")
    src = path.read_text()
    assert '@macro("myrec")' in src
    assert 'ctx.set(\'A2\', \'=A1*3\')' in src

    # Load it through the real macro machinery and run it.
    reg = load_macro_file(path)
    assert "myrec" in reg.macros
    wb = Workbook()
    run_macro(reg, "myrec", wb)
    assert wb.sheet.get("A2") == 30


def test_empty_recording_emits_pass(tmp_path):
    rec = MacroRecorder()
    rec.start("empty")
    rec.stop()
    src = rec.to_macro_source()
    assert "pass" in src
    # still loadable
    path = rec.save_macro(tmp_path / "e.py", "empty")
    reg = load_macro_file(path)
    assert "empty" in reg.macros


def test_json_roundtrip(tmp_path):
    rec = _recording()
    path = rec.save_json(tmp_path / "rec.json", "demo")
    env = __import__("json").loads(path.read_text())
    assert env["app"] == "abax"
    assert env["kind"] == "macro-recording"
    assert env["schema_version"] == 1

    rec2 = MacroRecorder.load_json(path)
    wb = Workbook()
    rec2.replay(wb)
    assert wb.sheet.get("A2") == 30


def _relative_recording() -> MacroRecorder:
    rec = MacroRecorder()
    rec.start("pattern", relative=True)
    # anchor is B2 (the first edited cell)
    rec.record_set("B2", "label")
    rec.record_set("C2", "=B2")  # relative ref one cell left
    rec.stop()
    return rec


def test_relative_anchor_is_first_cell():
    rec = _relative_recording()
    assert rec.relative is True
    assert rec.anchor == (1, 1)  # B2


def test_relative_replay_at_offset():
    rec = _relative_recording()
    wb = Workbook()
    # replay anchored at E5 (row 4, col 4) -> shift by (+3, +3)
    rec.replay(wb, at=(4, 4))
    assert wb.sheet.get("E5") == "label"  # B2 -> E5
    assert wb.sheet.get_raw(4, 5) == "=E5"  # C2 "=B2" -> F5 "=E5"
    assert wb.sheet.get("F5") == "label"


def test_relative_replay_without_at_reproduces_in_place():
    rec = _relative_recording()
    wb = Workbook()
    rec.replay(wb)  # no shift
    assert wb.sheet.get("B2") == "label"
    assert wb.sheet.get_raw(1, 2) == "=B2"


def test_relative_macro_source_runs_headless_and_offset(tmp_path):
    rec = _relative_recording()
    path = rec.save_macro(tmp_path / "rel.py", "pattern")
    src = path.read_text()
    assert "ctx.set_rc" in src
    assert "shift_refs" in src

    reg = load_macro_file(path)

    # headless (cursor=None) reproduces at the recorded anchor
    wb1 = Workbook()
    run_macro(reg, "pattern", wb1)
    assert wb1.sheet.get("B2") == "label"
    assert wb1.sheet.get_raw(1, 2) == "=B2"

    # invoked at E5 replays the whole pattern there
    wb2 = Workbook()
    run_macro(reg, "pattern", wb2, cursor=(4, 4))
    assert wb2.sheet.get("E5") == "label"
    assert wb2.sheet.get_raw(4, 5) == "=E5"


def test_relative_survives_json_roundtrip(tmp_path):
    rec = _relative_recording()
    path = rec.save_json(tmp_path / "rel.json")
    rec2 = MacroRecorder.load_json(path)
    assert rec2.relative is True
    assert rec2.anchor == (1, 1)
    wb = Workbook()
    rec2.replay(wb, at=(4, 4))
    assert wb.sheet.get("E5") == "label"


def test_sanitize_bad_macro_name(tmp_path):
    rec = MacroRecorder()
    rec.start()
    rec.record_set("A1", "1")
    rec.stop()
    src = rec.to_macro_source("123 weird-name!")
    # def line must be a valid identifier
    def_line = [ln for ln in src.splitlines() if ln.startswith("def ")][0]
    name = def_line[len("def "):].split("(")[0]
    assert name.isidentifier()
