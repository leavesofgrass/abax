"""GUI terminal drop-to-shell selection context ($ABAX_* env)."""

from __future__ import annotations

import os


def test_shellsession_passes_env_to_run(monkeypatch):
    from abax.core import shell

    captured = {}

    def fake_run(command, cwd=None, timeout=30.0, env=None):
        captured["env"] = env
        return shell.Result(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(shell, "run", fake_run)
    session = shell.ShellSession(env={"ABAX_ACTIVE_CELL": "B2"})
    session.execute("echo hi")
    assert captured["env"] == {"ABAX_ACTIVE_CELL": "B2"}


def test_shellsession_default_env_is_none(monkeypatch):
    from abax.core import shell

    captured = {}
    monkeypatch.setattr(shell, "run",
                        lambda command, cwd=None, timeout=30.0, env=None: captured.update(env=env)
                        or shell.Result(stdout="", stderr="", returncode=0))
    shell.ShellSession().execute("echo hi")
    assert captured["env"] is None   # inherit os.environ


def test_window_selection_env_exports_active_cell():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import pytest
    pytest.importorskip("PySide6")
    from abax.gui._qtcompat import QApplication
    from abax.gui.main_window import MainWindow
    from abax.settings import Settings

    _ = QApplication.instance() or QApplication([])
    win = MainWindow(Settings())
    sheet = win._doc.workbook.sheet
    sheet.set_cell(1, 1, "42")        # B2
    win.refresh_table()
    win._table.setCurrentCell(1, 1)

    env = win._selection_env()
    assert env is not None
    assert env["ABAX_ACTIVE_CELL"] == "B2"
    assert "ABAX_SELECTION_RANGE" in env
    assert "ABAX_SELECTION_JSON" in env
    assert "ABAX_SELECTION_TSV" in env
