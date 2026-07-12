"""Scheduling engine — DAG construction, CPM, critical path, auto-schedule.

Pure stdlib.  Operates on :class:`~abax.core.pm.taskmodel.Task` objects and
produces scheduling artefacts (topological order, early/late dates, slack).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

from abax.core.pm.taskmodel import Task

__all__ = [
    "CpmResult",
    "build_dag",
    "find_cycles",
    "topo_sort",
    "compute_cpm",
    "critical_path",
    "auto_schedule",
]


# ---------------------------------------------------------------------------
# DAG helpers
# ---------------------------------------------------------------------------

def build_dag(tasks: list[Task]) -> dict[str, list[str]]:
    """Map each task ID to the IDs it depends on (filtered to existing IDs)."""
    valid_ids = {t.id for t in tasks}
    return {t.id: [d for d in t.depends if d in valid_ids] for t in tasks}


def find_cycles(dag: dict[str, list[str]]) -> list[list[str]]:
    """Return every elementary cycle found via DFS coloring.

    Uses white (0) / gray (1) / black (2) marking.  When a back-edge is
    detected, the cycle is extracted from the recursion stack.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in dag}
    path: list[str] = []
    cycles: list[list[str]] = []

    def dfs(node: str) -> None:
        color[node] = GRAY
        path.append(node)
        for dep in dag.get(node, []):
            if dep not in color:
                continue
            if color[dep] == GRAY:
                idx = path.index(dep)
                cycles.append(path[idx:] + [dep])
            elif color[dep] == WHITE:
                dfs(dep)
        path.pop()
        color[node] = BLACK

    for node in dag:
        if color[node] == WHITE:
            dfs(node)

    return cycles


def topo_sort(dag: dict[str, list[str]]) -> list[str]:
    """Topological sort — a task appears after all its predecessors.

    Raises ``ValueError`` when the graph contains a cycle.
    """
    cycles = find_cycles(dag)
    if cycles:
        loop = " -> ".join(cycles[0])
        raise ValueError(f"dependency cycle: {loop}")

    # dag[n] = list of predecessors of n, so in-degree = len(predecessors).
    in_degree: dict[str, int] = {n: len(deps) for n, deps in dag.items()}

    # Build a reverse map: node -> list of successors (nodes that depend on it).
    successors: dict[str, list[str]] = {n: [] for n in dag}
    for node, deps in dag.items():
        for d in deps:
            if d in successors:
                successors[d].append(node)

    # Kahn's algorithm — stable via sorted initial queue.
    queue = sorted(n for n, d in in_degree.items() if d == 0)
    order: list[str] = []
    while queue:
        node = queue.pop(0)
        order.append(node)
        for succ in successors[node]:
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                # Insert in sorted position for determinism.
                lo, hi = 0, len(queue)
                while lo < hi:
                    mid = (lo + hi) // 2
                    if queue[mid] < succ:
                        lo = mid + 1
                    else:
                        hi = mid
                queue.insert(lo, succ)
    return order


# ---------------------------------------------------------------------------
# Business-day arithmetic
# ---------------------------------------------------------------------------

def _advance_business_days(start: date, days: int) -> date:
    """Return the date *days* business days after *start*.

    *start* itself counts as day 0.  Weekends (Saturday=5, Sunday=6 in
    ``date.weekday()``) are skipped.  *days* == 0 returns *start* (snapped
    to the next weekday if *start* falls on a weekend).
    """
    current = start
    # Snap to next weekday if starting on a weekend.
    while current.weekday() >= 5:
        current += timedelta(days=1)
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def _business_days_between(a: date, b: date) -> int:
    """Count business days from *a* to *b* (inclusive of *a*, exclusive of *b*)."""
    if b <= a:
        return 0
    count = 0
    cur = a
    while cur < b:
        if cur.weekday() < 5:
            count += 1
        cur += timedelta(days=1)
    return count


# ---------------------------------------------------------------------------
# CPM
# ---------------------------------------------------------------------------

@dataclass
class CpmResult:
    """Per-task result from the Critical Path Method computation."""

    early_start: date
    early_finish: date
    late_start: date
    late_finish: date
    slack_days: float
    critical: bool


def _duration_days(task: Task, hours_per_day: float) -> int:
    """Task duration in whole business days (ceil), minimum 1."""
    if task.effort is None:
        return 1
    return max(1, math.ceil(task.effort / hours_per_day))


def compute_cpm(
    tasks: list[Task],
    *,
    hours_per_day: float = 8.0,
) -> dict[str, CpmResult]:
    """Compute Critical Path Method dates for a list of tasks.

    Raises ``ValueError`` if the dependency graph contains a cycle.
    """
    dag = build_dag(tasks)
    order = topo_sort(dag)
    task_map: dict[str, Task] = {t.id: t for t in tasks}

    today = date.today()
    durations: dict[str, int] = {
        tid: _duration_days(task_map[tid], hours_per_day) for tid in order
    }

    # Forward pass — earliest start / finish.
    early_start: dict[str, date] = {}
    early_finish: dict[str, date] = {}

    for tid in order:
        t = task_map[tid]
        predecessors = dag[tid]
        if predecessors:
            es = max(early_finish[p] for p in predecessors)
            # Snap to next weekday.
            while es.weekday() >= 5:
                es += timedelta(days=1)
        else:
            es = t.start if t.start is not None else today
            while es.weekday() >= 5:
                es += timedelta(days=1)
        early_start[tid] = es
        early_finish[tid] = _advance_business_days(es, durations[tid])

    # Backward pass — latest start / finish.
    project_end = max(early_finish.values())
    late_finish: dict[str, date] = {}
    late_start: dict[str, date] = {}

    # Reverse of the successors map for the backward pass.
    successors: dict[str, list[str]] = {tid: [] for tid in order}
    for tid, deps in dag.items():
        for d in deps:
            if d in successors:
                successors[d].append(tid)

    for tid in reversed(order):
        succs = successors[tid]
        if succs:
            lf = min(late_start[s] for s in succs)
        else:
            lf = project_end
        late_finish[tid] = lf
        # Walk backward from lf by duration business days.
        ls = lf
        remaining = durations[tid]
        while remaining > 0:
            ls -= timedelta(days=1)
            if ls.weekday() < 5:
                remaining -= 1
        # Snap to weekday.
        while ls.weekday() >= 5:
            ls += timedelta(days=1)
        late_start[tid] = ls

    results: dict[str, CpmResult] = {}
    for tid in order:
        slack = float(_business_days_between(early_start[tid], late_start[tid]))
        results[tid] = CpmResult(
            early_start=early_start[tid],
            early_finish=early_finish[tid],
            late_start=late_start[tid],
            late_finish=late_finish[tid],
            slack_days=slack,
            critical=(slack == 0),
        )

    return results


def critical_path(cpm: dict[str, CpmResult]) -> list[str]:
    """Return IDs on the critical path (slack == 0), in dependency order.

    Preserves the insertion order from :func:`compute_cpm` which already
    follows the topological sort.
    """
    return [tid for tid, r in cpm.items() if r.critical]


def auto_schedule(
    tasks: list[Task],
    *,
    start_date: date | None = None,
    hours_per_day: float = 8.0,
) -> list[tuple[str, date, date]]:
    """Propose ``(task_id, suggested_start, suggested_finish)`` tuples.

    If *start_date* is given, tasks without an explicit start use it as a
    baseline (overriding ``today``).
    """
    if start_date is not None:
        adjusted = []
        for t in tasks:
            if t.start is None:
                patched = Task(
                    row=t.row, title=t.title, status=t.status,
                    start=start_date, due=t.due, assignee=t.assignee,
                    priority=t.priority, percent_done=t.percent_done,
                    depends=list(t.depends), milestone=t.milestone,
                    effort=t.effort, cost=t.cost, tags=list(t.tags),
                    id=t.id, extra=dict(t.extra),
                )
                adjusted.append(patched)
            else:
                adjusted.append(t)
        tasks = adjusted

    cpm = compute_cpm(tasks, hours_per_day=hours_per_day)
    return [(tid, r.early_start, r.early_finish) for tid, r in cpm.items()]
