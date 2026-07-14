"""Soak test: every PM view tab materializes and feeds against real data.

The 0.1.13 OKRs bug (a tab that materialized but was never fed, so it shipped
permanently empty) was found by reading, not by tests — this file is the
guard. It builds a populated two-project workbook (dependencies, milestones,
objectives, budget, cross-links), cycles the view host through ALL ten tabs,
and asserts each one actually materialized and survives a refresh.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("abax.gui._qtcompat")

from abax.core.pm.projects import (  # noqa: E402
    CrossProjectLink,
    KeyResult,
    Milestone,
    Objective,
    Project,
)
from abax.gui._qtcompat import QApplication, QEvent, QLabel  # noqa: E402
from abax.settings import Settings  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(app):
    from abax.gui.main_window import MainWindow

    _win = MainWindow(Settings())
    yield _win
    _win.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


_HEADERS = ["ID", "Title", "Status", "Start", "Due", "Assignee",
            "Effort", "Cost", "% Done", "Depends", "Tags"]

_ALPHA_TASKS = [
    ["A1", "Design", "Done", "2026-07-01", "2026-07-03", "Ann",
     "16", "800", "100", "", "okr:ship_alpha"],
    ["A2", "Build", "In Progress", "2026-07-04", "2026-07-10", "Bob",
     "40", "2000", "50", "A1", "okr:ship_alpha"],
    ["A3", "Test", "To Do", "2026-07-11", "2026-07-15", "Ann",
     "24", "1200", "0", "A2", ""],
]

_BETA_TASKS = [
    ["B1", "Spec", "Done", "2026-07-02", "2026-07-05", "Cara",
     "8", "400", "100", "", ""],
    ["B2", "Implement", "To Do", "2026-07-06", "2026-07-20", "Cara",
     "60", "3000", "0", "B1", ""],
]


def _fill(sheet, rows):
    for c, h in enumerate(_HEADERS):
        sheet.set_cell(0, c, h)
    for r, row in enumerate(rows, start=1):
        for c, v in enumerate(row):
            sheet.set_cell(r, c, v)


def _build_portfolio(win):
    wb = win._doc.workbook
    alpha_sheet = wb.sheet
    _fill(alpha_sheet, _ALPHA_TASKS)
    beta_sheet = wb.add_sheet("BetaSheet")
    _fill(beta_sheet, _BETA_TASKS)

    alpha = Project(
        name="Alpha", sheet=alpha_sheet.name, header_row=0,
        first_col=0, last_col=len(_HEADERS) - 1,
        first_data_row=1, last_data_row=len(_ALPHA_TASKS),
        budget_total=6000.0,
        milestones=[Milestone(name="Alpha GA", date="2026-07-15", done=False)],
        objectives=[Objective(objective="Ship Alpha", key_results=[
            KeyResult(name="Tasks done", target=3, current_formula="1"),
        ])],
        cross_links=[CrossProjectLink(
            from_project="Alpha", from_id="A3", to_project="Beta", to_id="B2",
        )],
    )
    beta = Project(
        name="Beta", sheet=beta_sheet.name, header_row=0,
        first_col=0, last_col=len(_HEADERS) - 1,
        first_data_row=1, last_data_row=len(_BETA_TASKS),
        budget_total=4000.0,
        milestones=[Milestone(name="Beta done", date="2026-07-21", done=False)],
    )
    wb.projects.add(alpha)
    wb.projects.add(beta)
    return alpha, beta


class TestAllTabsMaterializeAndFeed:
    def test_every_tab_materializes_against_real_data(self, win):
        from abax.gui.pm.view_host import _VIEW_DEFS

        _build_portfolio(win)
        win._pm_ensure_host()
        host = win._pm_host
        host.reload_projects()
        host.select_project("Alpha")

        # Cycle through every tab: each switch materializes the view lazily.
        for idx, (key, _label) in enumerate(_VIEW_DEFS):
            host._tabs.setCurrentIndex(idx)
            assert key in host._views, f"tab {key!r} did not materialize"
            widget = host._tabs.widget(idx)
            assert not isinstance(widget, QLabel), (
                f"tab {key!r} is still the placeholder label"
            )

        assert len(host._views) == len(_VIEW_DEFS) == 10

        # A refresh over all materialized views must not raise.
        host._refresh_views()

        # Spot checks that data actually arrived (the OKR-bug class):
        okr = host._views["okr"]
        assert okr._table.rowCount() >= 2          # objective + KR rows
        finance = host._views["finance"]
        assert finance._tiles                       # EVM tiles built

        win._doc.workbook.projects.remove("Alpha")
        win._doc.workbook.projects.remove("Beta")

    def test_switching_projects_refeeds_views(self, win):
        _build_portfolio(win)
        win._pm_ensure_host()
        host = win._pm_host
        host.reload_projects()
        host.select_project("Alpha")
        # Materialize one editable view, then switch projects and refresh.
        from abax.gui.pm.view_host import _VIEW_DEFS

        keys = [k for k, _ in _VIEW_DEFS]
        host._tabs.setCurrentIndex(keys.index("kanban"))
        host.select_project("Beta")
        host._refresh_views()                       # must not raise
        assert host._project is not None and host._project.name == "Beta"

        win._doc.workbook.projects.remove("Alpha")
        win._doc.workbook.projects.remove("Beta")
