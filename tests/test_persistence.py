"""Settings round-trip + migration, workbook JSON envelope, state journal."""

from __future__ import annotations

import json

from abax.core.workbook import Workbook
from abax.settings import Settings, _migrate_settings, load_settings, save_settings
from abax.state import StateManager


def test_settings_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    s = Settings()
    s.theme = "high_contrast"
    s.vim_mode = False
    save_settings(s, path)
    loaded = load_settings(path)
    assert loaded.theme == "high_contrast"
    assert loaded.vim_mode is False


def test_settings_migration_v0_to_v1():
    data = {"color_scheme": "nord"}  # v0 shape, no schema_version
    migrated = _migrate_settings(data)
    assert migrated["theme"] == "nord"          # v0 -> v1 theme rename still applies
    assert migrated["schema_version"] == 2      # then chains through v1 -> v2


def test_save_json_is_atomic_and_roundtrips(tmp_path):
    wb = Workbook()
    wb.sheet.set("A1", "=1+2")
    path = tmp_path / "book.abax"
    wb.save_json(path)
    assert path.exists()
    # the temp file used for the atomic replace must not linger
    assert not (tmp_path / "book.abax.tmp").exists()
    assert Workbook.load_json(path).sheet.get_value(0, 0) == 3.0


def test_load_skips_malformed_validation(tmp_path):
    # A corrupt/old envelope with a validation missing its rule "kind" must
    # degrade gracefully (skip the entry), not crash the whole workbook load.
    wb = Workbook()
    wb.sheet.set("A1", "1")
    env = wb.to_envelope()
    env["data"]["sheets"][0]["validations"] = [
        {"range": "A1:A1"},                                  # no "rule" -> skip
        {"range": "B1:B1", "rule": {}},                      # empty rule -> skip
        {"range": "C1:C1", "rule": {"kind": "whole", "op": "ge", "p1": "0"}},  # valid
    ]
    wb2 = Workbook.from_envelope(env)
    assert wb2.sheet.get_raw(0, 0) == "1"
    assert len(wb2.sheet.validations) == 1  # only the well-formed rule survives


def test_workbook_envelope_is_self_describing(tmp_path):
    wb = Workbook()
    wb.sheet.set("A1", "1")
    wb.sheet.set("A2", "=A1+1")
    path = tmp_path / "book.abax"
    wb.save_json(path)
    env = json.loads(path.read_text())
    assert env["app"] == "abax"
    assert env["schema_version"] == 1
    assert "written_at" in env
    assert "sheets" in env["data"]


def test_workbook_json_roundtrip(tmp_path):
    wb = Workbook()
    wb.sheet.set("A1", "10")
    wb.sheet.set("B1", "=A1*3")
    wb.add_sheet("Second")
    wb.get_sheet("Second").set("A1", "hi")
    path = tmp_path / "book.abax"
    wb.save_json(path)

    wb2 = Workbook.load_json(path)
    assert wb2.sheet.get("B1") == 30
    assert wb2.get_sheet("Second").get("A1") == "hi"
    assert len(wb2.sheets) == 2


def test_state_journal_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    mgr = StateManager.load(path)
    mgr.set("last_file", "/tmp/foo.csv")
    mgr.flush()
    assert path.exists()

    mgr2 = StateManager.load(path)
    assert mgr2.get("last_file") == "/tmp/foo.csv"


def test_state_journal_replay(tmp_path):
    path = tmp_path / "state.json"
    journal = path.with_suffix(".journal")
    # Simulate a crash mid-write: a journal exists but state file does not.
    journal.write_text(json.dumps({"key": "pending", "value": 7}))
    mgr = StateManager.load(path)
    assert mgr.get("pending") == 7
    assert not journal.exists()  # replayed and cleaned up
