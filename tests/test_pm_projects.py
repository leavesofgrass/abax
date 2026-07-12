"""Unit tests for the PM project registry (core/pm/projects.py)."""

from __future__ import annotations

import json

import pytest

from abax.core.pm.projects import (
    CrossProjectLink,
    KeyResult,
    Milestone,
    Objective,
    Project,
    ProjectRegistry,
)


# ---------------------------------------------------------------------------
# Milestone / CrossProjectLink / Objective round-trip
# ---------------------------------------------------------------------------

class TestMilestone:
    def test_roundtrip(self):
        m = Milestone(name="Beta", date="2026-09-01", done=False)
        d = m.to_dict()
        m2 = Milestone.from_dict(d)
        assert m2.name == "Beta"
        assert m2.date == "2026-09-01"
        assert m2.done is False

    def test_defaults(self):
        m = Milestone.from_dict({"name": "GA"})
        assert m.date == ""
        assert m.done is False


class TestCrossProjectLink:
    def test_roundtrip(self):
        link = CrossProjectLink("ProjA", "T3", "ProjB", "T7")
        d = link.to_dict()
        link2 = CrossProjectLink.from_dict(d)
        assert link2.from_project == "ProjA"
        assert link2.from_id == "T3"
        assert link2.to_project == "ProjB"
        assert link2.to_id == "T7"


class TestObjective:
    def test_roundtrip(self):
        obj = Objective(
            objective="Ship PM",
            key_results=[
                KeyResult(name="Views done", target=6, current_formula="=B2"),
                KeyResult(name="Tests pass", target=100),
            ],
        )
        d = obj.to_dict()
        obj2 = Objective.from_dict(d)
        assert obj2.objective == "Ship PM"
        assert len(obj2.key_results) == 2
        assert obj2.key_results[0].target == 6
        assert obj2.key_results[1].current_formula == ""


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

class TestProject:
    def test_roundtrip_explicit_geometry(self):
        p = Project(
            name="Alpha",
            sheet="Tasks",
            header_row=0,
            first_data_row=1,
            last_data_row=50,
            first_col=0,
            last_col=12,
            default_view="gantt",
            milestones=[Milestone("v1", "2026-10-01", False)],
            budget_total=50000,
        )
        d = p.to_dict()
        p2 = Project.from_dict(d)
        assert p2.name == "Alpha"
        assert p2.sheet == "Tasks"
        assert p2.last_data_row == 50
        assert p2.default_view == "gantt"
        assert len(p2.milestones) == 1
        assert p2.budget_total == 50000

    def test_roundtrip_table_ref(self):
        p = Project(name="Beta", table_ref="TaskTable")
        d = p.to_dict()
        assert "table_ref" in d
        assert "sheet" not in d
        p2 = Project.from_dict(d)
        assert p2.table_ref == "TaskTable"

    def test_roundtrip_json(self):
        p = Project(
            name="Gamma",
            sheet="PM",
            objectives=[
                Objective("Launch", [KeyResult("Coverage", 95, "=COVERAGE()")]),
            ],
            cross_links=[CrossProjectLink("Gamma", "T1", "Delta", "T5")],
        )
        raw = json.dumps(p.to_dict())
        p2 = Project.from_dict(json.loads(raw))
        assert p2.objectives[0].key_results[0].name == "Coverage"
        assert p2.cross_links[0].to_project == "Delta"

    def test_shift_rows_insert(self):
        p = Project(name="P", sheet="S", header_row=2, first_data_row=3,
                    last_data_row=10, first_col=0, last_col=5)
        p.shift_rows(at_row=1, delta=3)
        assert p.header_row == 5
        assert p.first_data_row == 6
        assert p.last_data_row == 13

    def test_shift_rows_delete(self):
        p = Project(name="P", sheet="S", header_row=5, first_data_row=6,
                    last_data_row=20, first_col=0, last_col=5)
        p.shift_rows(at_row=0, delta=-2)
        assert p.header_row == 3
        assert p.first_data_row == 4
        assert p.last_data_row == 18

    def test_shift_rows_after_region_no_change(self):
        p = Project(name="P", sheet="S", header_row=2, first_data_row=3,
                    last_data_row=10, first_col=0, last_col=5)
        p.shift_rows(at_row=20, delta=5)
        assert p.header_row == 2
        assert p.last_data_row == 10

    def test_shift_rows_table_ref_noop(self):
        p = Project(name="P", table_ref="T1", header_row=0, first_data_row=1,
                    last_data_row=10)
        p.shift_rows(at_row=0, delta=5)
        assert p.header_row == 0

    def test_shift_cols_insert(self):
        p = Project(name="P", sheet="S", header_row=0, first_col=2,
                    last_col=8)
        p.shift_cols(at_col=1, delta=2)
        assert p.first_col == 4
        assert p.last_col == 10

    def test_shift_cols_delete(self):
        p = Project(name="P", sheet="S", header_row=0, first_col=5,
                    last_col=10)
        p.shift_cols(at_col=0, delta=-2)
        assert p.first_col == 3
        assert p.last_col == 8

    def test_view_configs_roundtrip(self):
        p = Project(name="P", sheet="S", view_configs={
            "kanban": {"column_field": "status"},
            "gantt": {"zoom": "week"},
        })
        d = p.to_dict()
        p2 = Project.from_dict(d)
        assert p2.view_configs["kanban"]["column_field"] == "status"
        assert p2.view_configs["gantt"]["zoom"] == "week"


# ---------------------------------------------------------------------------
# ProjectRegistry
# ---------------------------------------------------------------------------

class TestProjectRegistry:
    def test_add_get(self):
        reg = ProjectRegistry()
        p = Project(name="Alpha", sheet="S1")
        reg.add(p)
        assert reg.get("Alpha") is p
        assert reg.get("ALPHA") is p
        assert reg.get("alpha") is p

    def test_has_contains(self):
        reg = ProjectRegistry()
        reg.add(Project(name="Proj"))
        assert reg.has("Proj")
        assert "Proj" in reg
        assert not reg.has("Other")

    def test_remove(self):
        reg = ProjectRegistry()
        reg.add(Project(name="Proj"))
        reg.remove("Proj")
        assert not reg.has("Proj")

    def test_remove_missing_raises(self):
        reg = ProjectRegistry()
        with pytest.raises(KeyError):
            reg.remove("Missing")

    def test_rename(self):
        reg = ProjectRegistry()
        reg.add(Project(name="Old"))
        reg.rename("Old", "New")
        assert reg.has("New")
        assert not reg.has("Old")
        assert reg.get("New").name == "New"

    def test_rename_collision_raises(self):
        reg = ProjectRegistry()
        reg.add(Project(name="A"))
        reg.add(Project(name="B"))
        with pytest.raises(KeyError):
            reg.rename("A", "B")

    def test_rename_missing_raises(self):
        reg = ProjectRegistry()
        with pytest.raises(KeyError):
            reg.rename("Missing", "New")

    def test_names_sorted(self):
        reg = ProjectRegistry()
        reg.add(Project(name="Charlie"))
        reg.add(Project(name="Alpha"))
        reg.add(Project(name="bravo"))
        assert reg.names() == ["Alpha", "bravo", "Charlie"]

    def test_iter_len(self):
        reg = ProjectRegistry()
        reg.add(Project(name="A"))
        reg.add(Project(name="B"))
        assert len(reg) == 2
        assert {p.name for p in reg} == {"A", "B"}

    def test_for_sheet(self):
        reg = ProjectRegistry()
        reg.add(Project(name="P1", sheet="S1"))
        reg.add(Project(name="P2", sheet="S2"))
        reg.add(Project(name="P3", sheet="S1"))
        assert len(reg.for_sheet("S1")) == 2

    def test_version_bumps(self):
        reg = ProjectRegistry()
        v0 = reg.version
        reg.add(Project(name="P"))
        assert reg.version > v0
        v1 = reg.version
        reg.rename("P", "Q")
        assert reg.version > v1
        v2 = reg.version
        reg.remove("Q")
        assert reg.version > v2

    def test_shift_rows_propagates(self):
        reg = ProjectRegistry()
        reg.add(Project(name="P1", sheet="S1", header_row=0,
                        first_data_row=1, last_data_row=10))
        reg.add(Project(name="P2", sheet="S2", header_row=0,
                        first_data_row=1, last_data_row=5))
        reg.shift_rows("S1", at_row=0, delta=3)
        assert reg.get("P1").header_row == 3
        assert reg.get("P2").header_row == 0  # different sheet, untouched

    def test_shift_cols_propagates(self):
        reg = ProjectRegistry()
        reg.add(Project(name="P1", sheet="S1", first_col=2, last_col=8))
        reg.shift_cols("S1", at_col=0, delta=1)
        assert reg.get("P1").first_col == 3
        assert reg.get("P1").last_col == 9

    def test_roundtrip_dict(self):
        reg = ProjectRegistry()
        reg.add(Project(
            name="Alpha",
            sheet="Tasks",
            header_row=0,
            first_data_row=1,
            last_data_row=50,
            first_col=0,
            last_col=12,
            milestones=[Milestone("v1", "2026-10-01", False)],
            objectives=[Objective("Ship", [KeyResult("Tests", 100)])],
            cross_links=[CrossProjectLink("Alpha", "T1", "Beta", "T5")],
            budget_total=25000,
        ))
        reg.add(Project(name="Beta", table_ref="BetaTable"))

        d = reg.to_dict()
        raw = json.dumps(d)
        reg2 = ProjectRegistry.from_dict(json.loads(raw))

        assert len(reg2) == 2
        alpha = reg2.get("Alpha")
        assert alpha.last_data_row == 50
        assert alpha.milestones[0].name == "v1"
        assert alpha.objectives[0].key_results[0].target == 100
        assert alpha.cross_links[0].to_project == "Beta"
        assert alpha.budget_total == 25000

        beta = reg2.get("Beta")
        assert beta.table_ref == "BetaTable"

    def test_roundtrip_json_serializable(self):
        reg = ProjectRegistry()
        reg.add(Project(name="P", sheet="S"))
        json.dumps(reg.to_dict())

    def test_empty_roundtrip(self):
        reg = ProjectRegistry()
        d = reg.to_dict()
        reg2 = ProjectRegistry.from_dict(d)
        assert len(reg2) == 0
