"""Unit tests for the PM scheduling engine (core/pm/schedule.py)."""

from __future__ import annotations

from datetime import date

import pytest

from abax.core.pm.schedule import (
    auto_schedule,
    build_dag,
    compute_cpm,
    critical_path,
    find_cycles,
    topo_sort,
)
from abax.core.pm.taskmodel import Task

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _task(tid: str, *, depends: list[str] | None = None,
          effort: float | None = None, start: date | None = None) -> Task:
    return Task(
        row=0, id=tid, title=tid, depends=depends or [],
        effort=effort, start=start,
    )


# ---------------------------------------------------------------------------
# build_dag
# ---------------------------------------------------------------------------

class TestBuildDag:
    def test_basic_wiring(self):
        tasks = [_task("A"), _task("B", depends=["A"]), _task("C", depends=["B"])]
        dag = build_dag(tasks)
        assert dag == {"A": [], "B": ["A"], "C": ["B"]}

    def test_missing_dep_filtered(self):
        tasks = [_task("A", depends=["Z"])]
        dag = build_dag(tasks)
        assert dag == {"A": []}

    def test_no_deps_empty_adjacency(self):
        tasks = [_task("X"), _task("Y")]
        dag = build_dag(tasks)
        assert dag == {"X": [], "Y": []}

    def test_multiple_deps(self):
        tasks = [_task("A"), _task("B"), _task("C", depends=["A", "B"])]
        dag = build_dag(tasks)
        assert dag["C"] == ["A", "B"]


# ---------------------------------------------------------------------------
# find_cycles
# ---------------------------------------------------------------------------

class TestFindCycles:
    def test_acyclic(self):
        dag = {"A": [], "B": ["A"], "C": ["B"]}
        assert find_cycles(dag) == []

    def test_simple_cycle(self):
        dag = {"A": ["B"], "B": ["A"]}
        cycles = find_cycles(dag)
        assert len(cycles) >= 1
        flat = {id for cycle in cycles for id in cycle}
        assert "A" in flat and "B" in flat

    def test_longer_cycle(self):
        dag = {"A": ["B"], "B": ["C"], "C": ["A"]}
        cycles = find_cycles(dag)
        assert len(cycles) >= 1
        flat = {id for cycle in cycles for id in cycle}
        assert flat >= {"A", "B", "C"}

    def test_self_loop(self):
        dag = {"A": ["A"]}
        cycles = find_cycles(dag)
        assert len(cycles) >= 1

    def test_multiple_independent_cycles(self):
        dag = {"A": ["B"], "B": ["A"], "C": ["D"], "D": ["C"], "E": []}
        cycles = find_cycles(dag)
        assert len(cycles) >= 2


# ---------------------------------------------------------------------------
# topo_sort
# ---------------------------------------------------------------------------

class TestTopoSort:
    def test_linear_chain(self):
        dag = {"A": [], "B": ["A"], "C": ["B"]}
        order = topo_sort(dag)
        assert order.index("A") < order.index("B") < order.index("C")

    def test_diamond(self):
        dag = {"A": [], "B": ["A"], "C": ["A"], "D": ["B", "C"]}
        order = topo_sort(dag)
        assert order.index("A") < order.index("B")
        assert order.index("A") < order.index("C")
        assert order.index("B") < order.index("D")
        assert order.index("C") < order.index("D")

    def test_raises_on_cycle(self):
        dag = {"A": ["B"], "B": ["A"]}
        with pytest.raises(ValueError, match="dependency cycle"):
            topo_sort(dag)


# ---------------------------------------------------------------------------
# compute_cpm
# ---------------------------------------------------------------------------

class TestComputeCpm:
    def test_simple_chain(self):
        """A(16h) -> B(8h) -> C(24h), start Monday 2026-08-03."""
        monday = date(2026, 8, 3)
        tasks = [
            _task("A", effort=16, start=monday),
            _task("B", effort=8, depends=["A"]),
            _task("C", effort=24, depends=["B"]),
        ]
        cpm = compute_cpm(tasks)

        # A: 16h / 8h = 2 days.  Mon Aug 3 -> Wed Aug 5.
        assert cpm["A"].early_start == date(2026, 8, 3)
        assert cpm["A"].early_finish == date(2026, 8, 5)

        # B: 8h = 1 day.  Wed Aug 5 -> Thu Aug 6.
        assert cpm["B"].early_start == date(2026, 8, 5)
        assert cpm["B"].early_finish == date(2026, 8, 6)

        # C: 24h / 8h = 3 days.  Thu Aug 6 -> Tue Aug 11 (skip weekend).
        assert cpm["C"].early_start == date(2026, 8, 6)
        assert cpm["C"].early_finish == date(2026, 8, 11)

        # Single chain — all critical.
        assert all(cpm[t].critical for t in ("A", "B", "C"))
        assert all(cpm[t].slack_days == 0 for t in ("A", "B", "C"))

    def test_parallel_paths(self):
        """Two parallel paths with different durations.

        A(24h) -> C vs B(8h) -> C.  A-path is longer, so it's critical.
        """
        monday = date(2026, 8, 3)
        tasks = [
            _task("A", effort=24, start=monday),
            _task("B", effort=8, start=monday),
            _task("C", effort=8, depends=["A", "B"]),
        ]
        cpm = compute_cpm(tasks)

        assert cpm["A"].critical is True
        assert cpm["C"].critical is True
        assert cpm["B"].critical is False
        assert cpm["B"].slack_days > 0

    def test_weekend_skipping(self):
        """A 3-day task starting Friday should finish Wednesday."""
        friday = date(2026, 8, 7)
        tasks = [_task("X", effort=24, start=friday)]  # 24h / 8h = 3 days
        cpm = compute_cpm(tasks)

        assert cpm["X"].early_start == friday
        # Fri -> Mon -> Tue -> Wed (skip Sat+Sun).
        assert cpm["X"].early_finish == date(2026, 8, 12)

    def test_no_effort_defaults_to_one_day(self):
        monday = date(2026, 8, 3)
        tasks = [_task("A", start=monday)]
        cpm = compute_cpm(tasks)

        assert cpm["A"].early_start == date(2026, 8, 3)
        assert cpm["A"].early_finish == date(2026, 8, 4)

    def test_explicit_start_date(self):
        wed = date(2026, 8, 5)
        tasks = [_task("A", effort=8, start=wed)]
        cpm = compute_cpm(tasks)
        assert cpm["A"].early_start == wed

    def test_late_dates_single_task(self):
        monday = date(2026, 8, 3)
        tasks = [_task("A", effort=16, start=monday)]
        cpm = compute_cpm(tasks)

        assert cpm["A"].late_start == cpm["A"].early_start
        assert cpm["A"].late_finish == cpm["A"].early_finish


# ---------------------------------------------------------------------------
# critical_path
# ---------------------------------------------------------------------------

class TestCriticalPath:
    def test_returns_zero_slack_in_order(self):
        monday = date(2026, 8, 3)
        tasks = [
            _task("A", effort=24, start=monday),
            _task("B", effort=8, start=monday),
            _task("C", effort=8, depends=["A", "B"]),
        ]
        cpm = compute_cpm(tasks)
        cp = critical_path(cpm)
        assert "A" in cp
        assert "C" in cp
        assert "B" not in cp
        assert cp.index("A") < cp.index("C")

    def test_full_chain_critical(self):
        monday = date(2026, 8, 3)
        tasks = [
            _task("A", effort=8, start=monday),
            _task("B", effort=8, depends=["A"]),
        ]
        cpm = compute_cpm(tasks)
        cp = critical_path(cpm)
        assert cp == ["A", "B"]


# ---------------------------------------------------------------------------
# auto_schedule
# ---------------------------------------------------------------------------

class TestAutoSchedule:
    def test_returns_tuples(self):
        monday = date(2026, 8, 3)
        tasks = [
            _task("A", effort=16, start=monday),
            _task("B", effort=8, depends=["A"]),
        ]
        result = auto_schedule(tasks)
        assert len(result) == 2
        for tid, s, f in result:
            assert isinstance(tid, str)
            assert isinstance(s, date)
            assert isinstance(f, date)
            assert f >= s

    def test_start_date_override(self):
        monday = date(2026, 8, 3)
        tasks = [_task("A", effort=8), _task("B", effort=8, depends=["A"])]
        result = auto_schedule(tasks, start_date=monday)
        starts = {tid: s for tid, s, _ in result}
        assert starts["A"] == monday

    def test_dependency_order(self):
        monday = date(2026, 8, 3)
        tasks = [
            _task("A", effort=8, start=monday),
            _task("B", effort=8, depends=["A"]),
            _task("C", effort=8, depends=["B"]),
        ]
        result = auto_schedule(tasks)
        dates = {tid: (s, f) for tid, s, f in result}
        assert dates["B"][0] >= dates["A"][1]
        assert dates["C"][0] >= dates["B"][1]
