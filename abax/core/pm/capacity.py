"""Capacity planning — workload aggregation and resource rebalancing.

Pure-stdlib module.  No imports from the engine or gui layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Sequence

# ---------------------------------------------------------------------------
# Task dataclass (frozen contract — duplicated here so this module is
# self-contained and does not depend on taskmodel.py at import time)
# ---------------------------------------------------------------------------

@dataclass
class Task:
    row: int
    title: str = ""
    status: str = ""
    start: date | None = None
    due: date | None = None
    assignee: str = ""
    priority: str = ""
    percent_done: float = 0.0
    depends: list[str] = field(default_factory=list)
    milestone: bool = False
    effort: float | None = None
    cost: float | None = None
    tags: list[str] = field(default_factory=list)
    id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Supporting dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Person:
    name: str
    weekly_capacity: float = 40.0
    skills: list[str] = field(default_factory=list)


@dataclass
class Overallocation:
    assignee: str
    week: str
    allocated: float
    capacity: float
    excess: float


@dataclass
class Suggestion:
    task: Task
    from_assignee: str
    to_assignee: str
    reason: str


# ---------------------------------------------------------------------------
# Business-day helpers
# ---------------------------------------------------------------------------

def _is_business_day(d: date) -> bool:
    return d.weekday() < 5  # Mon–Fri


def _business_days_between(a: date, b: date) -> int:
    """Count business days in [a, b] inclusive."""
    if b < a:
        return 0
    count = 0
    cur = a
    while cur <= b:
        if _is_business_day(cur):
            count += 1
        cur += timedelta(days=1)
    return count


def _monday_of(d: date) -> date:
    """Return the Monday of the ISO week containing *d*."""
    return d - timedelta(days=d.weekday())


# ---------------------------------------------------------------------------
# 1. workload_by_week
# ---------------------------------------------------------------------------

def workload_by_week(
    tasks: Sequence[Task],
    start_date: date,
    end_date: date,
    hours_per_day: float = 8.0,
) -> dict[str, dict[str, float]]:
    """Per-assignee per-week effort within *[start_date, end_date]*.

    For each task that has both ``start`` and ``due``, its effort is spread
    evenly across the business days in ``[task.start, task.due]``.  If
    ``task.effort`` is *None*, effort defaults to
    ``hours_per_day * business_days(task.start, task.due)``.

    Returns ``{assignee: {week_start_iso: hours}}``.
    Week start is the Monday of each ISO week.
    Tasks with no assignee are skipped.
    """
    result: dict[str, dict[str, float]] = {}

    for task in tasks:
        if not task.assignee or task.start is None or task.due is None:
            continue

        bdays = _business_days_between(task.start, task.due)
        if bdays == 0:
            continue

        total_effort = task.effort if task.effort is not None else hours_per_day * bdays
        daily = total_effort / bdays

        cur = task.start
        while cur <= task.due:
            if _is_business_day(cur) and start_date <= cur <= end_date:
                week_key = _monday_of(cur).isoformat()
                assignee_weeks = result.setdefault(task.assignee, {})
                assignee_weeks[week_key] = assignee_weeks.get(week_key, 0.0) + daily
            cur += timedelta(days=1)

    return result


# ---------------------------------------------------------------------------
# 2. detect_people
# ---------------------------------------------------------------------------

_NAME_ALIASES = {"name", "person", "resource", "who"}
_CAPACITY_ALIASES = {"capacity", "hours", "availability", "weekly"}
_SKILLS_ALIASES = {"skills", "skill", "tags", "expertise"}


def detect_people(
    sheet: Sequence[Sequence[Any]],
    header_row: int = 0,
    first_col: int = 0,
    last_col: int | None = None,
) -> list[Person]:
    """Detect a "People sheet" by column-header convention.

    Looks for columns matching name/capacity/skills aliases (case-insensitive).
    Returns a list of :class:`Person` dataclasses.
    """
    if not sheet or header_row >= len(sheet):
        return []

    headers_raw = sheet[header_row]
    end = last_col + 1 if last_col is not None else len(headers_raw)
    headers = [
        str(h).strip().lower() for h in headers_raw[first_col:end]
    ]

    name_col: int | None = None
    cap_col: int | None = None
    skills_col: int | None = None

    for i, h in enumerate(headers):
        if h in _NAME_ALIASES:
            name_col = i + first_col
        elif h in _CAPACITY_ALIASES:
            cap_col = i + first_col
        elif h in _SKILLS_ALIASES:
            skills_col = i + first_col

    if name_col is None:
        return []

    people: list[Person] = []
    for r in range(header_row + 1, len(sheet)):
        row = sheet[r]
        if name_col >= len(row):
            continue
        name = str(row[name_col]).strip()
        if not name:
            continue

        cap = 40.0
        if cap_col is not None and cap_col < len(row):
            try:
                cap = float(row[cap_col])
            except (ValueError, TypeError):
                pass

        skills: list[str] = []
        if skills_col is not None and skills_col < len(row):
            raw = str(row[skills_col]).strip()
            if raw:
                skills = [s.strip() for s in raw.split(",") if s.strip()]

        people.append(Person(name=name, weekly_capacity=cap, skills=skills))

    return people


# ---------------------------------------------------------------------------
# 3. overallocation
# ---------------------------------------------------------------------------

def overallocation(
    workload: dict[str, dict[str, float]],
    people: list[Person] | None = None,
    default_capacity: float = 40.0,
) -> list[Overallocation]:
    """Return weeks where an assignee is allocated above capacity."""
    cap_map: dict[str, float] = {}
    if people:
        for p in people:
            cap_map[p.name] = p.weekly_capacity

    result: list[Overallocation] = []
    for assignee, weeks in sorted(workload.items()):
        cap = cap_map.get(assignee, default_capacity)
        for week, hours in sorted(weeks.items()):
            if hours > cap:
                result.append(Overallocation(
                    assignee=assignee,
                    week=week,
                    allocated=hours,
                    capacity=cap,
                    excess=hours - cap,
                ))
    return result


# ---------------------------------------------------------------------------
# 4. suggest_reassignment
# ---------------------------------------------------------------------------

def suggest_reassignment(
    tasks: Sequence[Task],
    overloaded_assignee: str,
    week: str,
    people: list[Person],
    workload: dict[str, dict[str, float]] | None = None,
) -> list[Suggestion]:
    """Suggest moving a task from *overloaded_assignee* to someone with capacity.

    **Greedy heuristic**: picks the task in *week* with the smallest effort
    (least disruption), then finds candidates from *people* who have spare
    capacity that week and whose skills overlap with the task's tags.

    If *workload* is not supplied, candidates are assumed to have full capacity.
    """
    week_monday = date.fromisoformat(week)
    week_friday = week_monday + timedelta(days=4)

    # Collect tasks assigned to overloaded_assignee that overlap this week.
    candidate_tasks: list[Task] = []
    for t in tasks:
        if t.assignee != overloaded_assignee:
            continue
        if t.start is None or t.due is None:
            continue
        # Task overlaps the week if task.start <= friday and task.due >= monday
        if t.start <= week_friday and t.due >= week_monday:
            candidate_tasks.append(t)

    if not candidate_tasks:
        return []

    # Sort by effort (ascending) — smallest first for least disruption.
    def _task_effort(t: Task) -> float:
        if t.effort is not None:
            return t.effort
        bdays = _business_days_between(t.start, t.due)  # type: ignore[arg-type]
        return 8.0 * bdays if bdays > 0 else 0.0

    candidate_tasks.sort(key=_task_effort)

    # Build capacity map for candidate people.
    cap_map: dict[str, float] = {p.name: p.weekly_capacity for p in people}
    alloc_map: dict[str, float] = {}
    if workload:
        for name in cap_map:
            alloc_map[name] = workload.get(name, {}).get(week, 0.0)

    suggestions: list[Suggestion] = []
    for t in candidate_tasks:
        task_eff = _task_effort(t)
        matches = skill_match(t.tags, people)
        for person, overlap in matches:
            if person.name == overloaded_assignee:
                continue
            available = cap_map[person.name] - alloc_map.get(person.name, 0.0)
            if available >= task_eff:
                reason = (
                    f"Move '{t.title}' ({task_eff:.1f}h) to {person.name} "
                    f"— {overlap} skill overlap, {available:.1f}h available"
                )
                suggestions.append(Suggestion(
                    task=t,
                    from_assignee=overloaded_assignee,
                    to_assignee=person.name,
                    reason=reason,
                ))
                break  # one suggestion per task

    return suggestions


# ---------------------------------------------------------------------------
# 5. skill_match
# ---------------------------------------------------------------------------

def skill_match(
    task_tags: Sequence[str],
    people: list[Person],
) -> list[tuple[Person, int]]:
    """Rank *people* by skill overlap with *task_tags*.

    Sorted by overlap count descending, then by name ascending (tiebreak).
    Returns ``[(person, overlap_count), ...]``.
    """
    tag_set = set(task_tags)
    scored: list[tuple[Person, int]] = []
    for p in people:
        overlap = len(tag_set & set(p.skills))
        scored.append((p, overlap))
    scored.sort(key=lambda x: (-x[1], x[0].name))
    return scored


# ---------------------------------------------------------------------------
# 6. rebalance
# ---------------------------------------------------------------------------

def rebalance(
    tasks: Sequence[Task],
    people: list[Person],
    default_capacity: float = 40.0,
    hours_per_day: float = 8.0,
) -> list[Suggestion]:
    """Run overallocation detection, then suggest reassignments.

    **Greedy heuristic** — iterates over overloaded (assignee, week) pairs
    in sorted order and tries :func:`suggest_reassignment` for each.  Does
    not re-compute workload after each suggestion, so results are advisory.
    """
    if not tasks or not people:
        return []

    # Determine date range from tasks.
    starts = [t.start for t in tasks if t.start is not None]
    dues = [t.due for t in tasks if t.due is not None]
    if not starts or not dues:
        return []

    start_date = min(starts)
    end_date = max(dues)

    wl = workload_by_week(tasks, start_date, end_date, hours_per_day=hours_per_day)
    issues = overallocation(wl, people, default_capacity=default_capacity)

    suggestions: list[Suggestion] = []
    for issue in issues:
        s = suggest_reassignment(
            tasks, issue.assignee, issue.week, people, workload=wl,
        )
        suggestions.extend(s)

    return suggestions
