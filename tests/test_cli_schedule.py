"""Tests for the `abax schedule` CLI subcommand (headless CPM report)."""

from __future__ import annotations

from abax.core.pm.projects import Project
from abax.core.workbook import Workbook
from abax.engine.document import Document


def _write_book(tmp_path, *, cyclic: bool = False):
    """A tiny .json workbook with one project whose tasks form a dependency
    chain (T1 -> T2 -> T3).  With *cyclic* the chain is turned into a cycle."""
    wb = Workbook()
    sh = wb.sheet  # "Sheet1"
    headers = ["ID", "Title", "Depends", "Effort"]
    for c, h in enumerate(headers):
        sh.set_cell(0, c, h)
    rows = [
        ["T1", "Design", "T2" if cyclic else "", "8"],
        ["T2", "Implement", "T1", "16"],
        ["T3", "Test", "T2", "8"],
    ]
    for r, row in enumerate(rows, start=1):
        for c, val in enumerate(row):
            sh.set_cell(r, c, val)

    wb.projects.add(Project(name="Alpha", sheet="Sheet1", header_row=0,
                            first_data_row=1, last_data_row=-1,
                            first_col=0, last_col=-1))
    path = tmp_path / "book.json"
    Document(wb).save(str(path))
    return str(path)


def test_cli_schedule_reports_critical_path(tmp_path, capsys):
    from abax.app import main

    rc = main(["schedule", _write_book(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    # Project header names the project and its task count.
    assert "Alpha (3 task(s))" in out
    # A linear dependency chain puts every task on the critical path.
    assert "critical path:" in out
    for tid, title in (("T1", "Design"), ("T2", "Implement"), ("T3", "Test")):
        assert tid in out
        assert title in out


def test_cli_schedule_detects_cycle(tmp_path, capsys):
    from abax.app import main

    rc = main(["schedule", _write_book(tmp_path, cyclic=True)])
    captured = capsys.readouterr()
    # A dependency cycle is reported to stderr and yields a non-zero exit.
    assert rc == 1
    assert "cycle" in captured.err
    # The project header is still printed to stdout.
    assert "Alpha" in captured.out


def test_cli_schedule_no_projects_errors(tmp_path, capsys):
    from abax.app import main

    wb = Workbook()
    wb.sheet.set_cell(0, 0, "hello")
    path = tmp_path / "plain.json"
    Document(wb).save(str(path))

    rc = main(["schedule", str(path)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "no projects" in err


def test_cli_schedule_missing_file_errors(capsys):
    from abax.app import main

    rc = main(["schedule", "does_not_exist.abax"])
    assert rc == 2
    assert "cannot open" in capsys.readouterr().err
