"""TUI read-only PM commands: :tasks and :critpath.

Drives the headless TuiEditor directly — no real terminal (spec §12).
"""

from __future__ import annotations

from abax.core.pm.projects import Project
from abax.engine.document import Document
from abax.tui import TuiEditor

_HEADERS = ["ID", "Title", "Status", "Due", "Depends", "Effort"]


def _fill(sheet, rows):
    for c, h in enumerate(_HEADERS):
        sheet.set_cell(0, c, h)
    for r, row in enumerate(rows, start=1):
        for c, val in enumerate(row):
            sheet.set_cell(r, c, val)


def _pm_document(*, cyclic: bool = False) -> Document:
    """A document whose active sheet holds one project: a T1 -> T2 -> T3
    dependency chain (turned into a cycle with *cyclic*)."""
    doc = Document()
    _fill(doc.workbook.sheet, [
        ["T1", "Design", "Done", "2099-01-05", "T2" if cyclic else "", "8"],
        ["T2", "Implement", "In progress", "2099-01-10", "T1", "16"],
        ["T3", "Test", "Todo", "", "T2", "8"],
    ])
    doc.workbook.projects.add(Project(name="Alpha", sheet="Sheet1", header_row=0,
                                      first_data_row=1, last_data_row=-1,
                                      first_col=0, last_col=-1))
    return doc


def _run(ed: TuiEditor, line: str) -> None:
    ed.command_buf = line
    ed.run_command()


# --- :tasks ---------------------------------------------------------------

def test_tasks_opens_readonly_overlay():
    ed = TuiEditor(_pm_document())
    _run(ed, ":tasks")
    assert ed.mode == "describe"
    assert "Alpha" in ed.describe_title
    body = "\n".join(lbl for lbl, _ in ed.describe_lines)
    for tid, title in (("T1", "Design"), ("T2", "Implement"), ("T3", "Test")):
        assert tid in body
        assert title in body
    assert "In progress" in body
    assert "due 2099-01-10" in body
    assert "due -" in body  # T3 has no due date
    # Strictly read-only: no writes, no checkpoints.
    assert ed.doc.dirty is False
    assert ed.doc.can_undo is False


def test_tasks_overlay_scrolls_and_closes_like_describe():
    from abax.tui.keys import _handle_key

    ed = TuiEditor(_pm_document())
    _run(ed, ":tasks")
    assert ed.describe_idx == 0
    _handle_key(ed, "j")
    assert ed.describe_idx == 1
    _handle_key(ed, "q")
    assert ed.mode == "normal"


def test_tasks_prefers_project_on_active_sheet():
    doc = _pm_document()  # "Alpha" on Sheet1
    pm = doc.workbook.add_sheet("PM")
    _fill(pm, [["B1", "Beta work", "Todo", "2099-02-01", "", "4"]])
    doc.workbook.projects.add(Project(name="Beta", sheet="PM", header_row=0,
                                      first_data_row=1, last_data_row=-1,
                                      first_col=0, last_col=-1))
    ed = TuiEditor(doc)
    _run(ed, ":sheet PM")
    _run(ed, ":tasks")
    assert "Beta" in ed.describe_title
    body = "\n".join(lbl for lbl, _ in ed.describe_lines)
    assert "Beta work" in body
    assert "Design" not in body  # Alpha's tasks are not shown


def test_tasks_without_projects_is_a_status_message():
    ed = TuiEditor(Document())
    _run(ed, ":tasks")
    assert ed.mode == "normal"  # no overlay, no traceback
    assert "no projects" in ed.message


# --- :critpath -------------------------------------------------------------

def test_critpath_shows_zero_slack_chain():
    ed = TuiEditor(_pm_document())
    _run(ed, ":critpath")
    assert ed.mode == "describe"
    assert "Critical path" in ed.describe_title
    assert "Alpha" in ed.describe_title
    # A linear chain puts every task on the critical path, in dependency order.
    labels = [lbl for lbl, _ in ed.describe_lines]
    assert labels == ["T1  Design", "T2  Implement", "T3  Test"]
    assert ed.doc.dirty is False
    assert ed.doc.can_undo is False


def test_critpath_cycle_reports_not_raises():
    ed = TuiEditor(_pm_document(cyclic=True))
    _run(ed, ":critpath")
    assert ed.mode == "normal"
    assert "cycle" in ed.message


def test_critpath_without_projects_is_a_status_message():
    ed = TuiEditor(Document())
    _run(ed, ":critpath")
    assert ed.mode == "normal"
    assert "no projects" in ed.message


def test_pm_commands_are_in_the_help_overlay():
    from abax.tui.editor import HELP_ENTRIES

    keys = [k for k, _ in HELP_ENTRIES]
    assert ":tasks" in keys
    assert ":critpath" in keys
