"""Tests for the `abax tasks` CLI subcommand (task listing + validation gate)."""

from __future__ import annotations

from abax.core.pm.projects import Project
from abax.core.workbook import Workbook
from abax.engine.document import Document

_HEADERS = ["ID", "Title", "Status", "Start", "Due", "Assignee", "Depends"]


def _fill(sheet, rows):
    for c, h in enumerate(_HEADERS):
        sheet.set_cell(0, c, h)
    for r, row in enumerate(rows, start=1):
        for c, val in enumerate(row):
            sheet.set_cell(r, c, val)


def _write_book(tmp_path, *, problems: bool = False):
    """A tiny .json workbook with one project.

    The clean variant has every date filled and only valid dependencies; its
    one past-due task is Done, which must NOT count as overdue.  The problem
    variant plants exactly one of each validation failure: an overdue task, a
    task missing both dates, and a dependency on an id that does not exist.
    """
    wb = Workbook()
    sh = wb.sheet  # "Sheet1"
    if problems:
        rows = [
            ["T1", "Design", "In progress", "2020-01-01", "2020-01-05", "alice", ""],
            ["T2", "Implement", "Todo", "", "", "bob", "T1"],
            ["T3", "Test", "Todo", "2099-01-01", "2099-01-05", "carol", "T9"],
        ]
    else:
        rows = [
            ["T1", "Design", "Done", "2020-01-01", "2020-01-05", "alice", ""],
            ["T2", "Implement", "In progress", "2099-01-01", "2099-01-10", "bob", "T1"],
            ["T3", "Test", "Todo", "2099-01-11", "2099-01-20", "carol", "T2"],
        ]
    _fill(sh, rows)
    wb.projects.add(Project(name="Alpha", sheet="Sheet1", header_row=0,
                            first_data_row=1, last_data_row=-1,
                            first_col=0, last_col=-1))
    path = tmp_path / ("problem.json" if problems else "clean.json")
    Document(wb).save(str(path))
    return str(path)


def test_cli_tasks_clean_book_exits_zero(tmp_path, capsys):
    from abax.app import main

    rc = main(["tasks", _write_book(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Alpha (3 task(s))" in out
    # Every task line carries id, title, status, dates, and assignee.
    for tid, title, who in (("T1", "Design", "alice"),
                            ("T2", "Implement", "bob"),
                            ("T3", "Test", "carol")):
        assert tid in out
        assert title in out
        assert who in out
    assert "2099-01-10" in out
    assert "validation: ok" in out
    # The Done task's past due date is not overdue (done-detection).
    assert "overdue" not in out


def test_cli_tasks_problem_book_exits_one(tmp_path, capsys):
    from abax.app import main

    rc = main(["tasks", _write_book(tmp_path, problems=True)])
    out = capsys.readouterr().out
    assert rc == 1
    # The listing is still printed in full before the validation section.
    assert "Alpha (3 task(s))" in out
    assert "3 problem(s):" in out
    assert "overdue: T1 (Design) was due 2020-01-05" in out
    assert "missing start and due: T2 (Implement)" in out
    assert "unknown dependency: T3 (Test) depends on 'T9'" in out


def test_cli_tasks_project_filter(tmp_path, capsys):
    from abax.app import main

    wb = Workbook()
    _fill(wb.sheet, [["A1", "Alpha work", "Todo", "", "", "", ""]])
    beta = wb.add_sheet("Beta")
    _fill(beta, [["B1", "Beta work", "Todo", "2099-01-01", "2099-01-05", "dan", ""]])
    for name, sheet in (("Alpha", "Sheet1"), ("Beta", "Beta")):
        wb.projects.add(Project(name=name, sheet=sheet, header_row=0,
                                first_data_row=1, last_data_row=-1,
                                first_col=0, last_col=-1))
    path = tmp_path / "two.json"
    Document(wb).save(str(path))

    # --project restricts the listing (and the gate) to the named project.
    rc = main(["tasks", str(path), "--project", "Beta"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Beta (1 task(s))" in out
    assert "Alpha" not in out

    # Without the filter, Alpha's missing dates make the gate fail.
    rc = main(["tasks", str(path)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "Alpha (1 task(s))" in out
    assert "Beta (1 task(s))" in out
    assert "missing start and due: A1 (Alpha work)" in out


def test_cli_tasks_unknown_project_errors(tmp_path, capsys):
    from abax.app import main

    rc = main(["tasks", _write_book(tmp_path), "--project", "Nope"])
    assert rc == 2
    assert "no such project" in capsys.readouterr().err


def test_cli_tasks_no_projects_errors(tmp_path, capsys):
    from abax.app import main

    wb = Workbook()
    wb.sheet.set_cell(0, 0, "hello")
    path = tmp_path / "plain.json"
    Document(wb).save(str(path))

    rc = main(["tasks", str(path)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "no projects" in err


def test_cli_tasks_missing_file_errors(capsys):
    from abax.app import main

    rc = main(["tasks", "does_not_exist.abax"])
    assert rc == 2
    assert "cannot open" in capsys.readouterr().err
