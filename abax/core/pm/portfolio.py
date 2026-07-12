"""Portfolio analytics engine — pure stdlib.

Roll-up computations across registered projects so the GUI dashboard,
HTML reports, and Python console can all consume the same data.

All functions take plain data (lists of Tasks, Projects, CpmResults) —
no sheet or GUI access.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from abax.core.pm.projects import Project
from abax.core.pm.schedule import compute_cpm
from abax.core.pm.taskmodel import Task

if TYPE_CHECKING:
    pass

# ── status helpers ──────────────────────────────────────────────────

_DONE_STATUSES = frozenset({
    "done", "complete", "completed", "closed", "finished",
})


def _is_done(task: Task) -> bool:
    return task.status.lower().strip() in _DONE_STATUSES


def _parse_date(s: str) -> date | None:
    """Parse an ISO date string, returning *None* on failure or empty."""
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


# ── per-project analytics ──────────────────────────────────────────

def project_progress(tasks: list[Task]) -> float:
    """Return 0..100 progress, weighted by effort when present, else by
    task count.

    When every task has a non-``None`` effort value, progress is the
    effort-weighted average of ``percent_done``.  When *any* task lacks
    an effort value, progress is the simple arithmetic mean of
    ``percent_done`` across all tasks.

    Returns 0.0 when the task list is empty.
    """
    if not tasks:
        return 0.0
    all_have_effort = all(t.effort is not None for t in tasks)
    if all_have_effort:
        total_effort = sum(t.effort for t in tasks)  # type: ignore[arg-type]
        if total_effort == 0:
            return 0.0
        return sum(t.percent_done * t.effort for t in tasks) / total_effort  # type: ignore[operator]
    # Unweighted fallback
    return sum(t.percent_done for t in tasks) / len(tasks)


def status_counts(tasks: list[Task]) -> dict[str, int]:
    """Count of tasks per distinct status value (case-preserved)."""
    counts: dict[str, int] = {}
    for t in tasks:
        counts[t.status] = counts.get(t.status, 0) + 1
    return counts


def overdue_tasks(tasks: list[Task], today: date) -> list[Task]:
    """Tasks where *due < today* and status is not done-like.

    Tasks without a due date are never considered overdue.
    """
    result: list[Task] = []
    for t in tasks:
        if _is_done(t):
            continue
        d = _parse_date(t.due)
        if d is not None and d < today:
            result.append(t)
    return result


def at_risk_tasks(
    tasks: list[Task],
    today: date,
    *,
    window_days: int = 7,
) -> list[Task]:
    """Tasks due within *window_days* that are less than 80 % done.

    A task is at risk when:
    - it is not done (status not in done-like set),
    - it has a due date in ``[today, today + window_days)``,
    - ``percent_done < 80``.

    Tasks without a due date are never at risk.
    """
    cutoff = today + timedelta(days=window_days)
    result: list[Task] = []
    for t in tasks:
        if _is_done(t):
            continue
        d = _parse_date(t.due)
        if d is None:
            continue
        if today <= d < cutoff and t.percent_done < 80:
            result.append(t)
    return result


def milestone_schedule(project: Project) -> list[dict]:
    """Return ``[{name, date, done, overdue}]`` for each milestone.

    A milestone is *overdue* when its date is in the past and it is not
    done.  Milestones without a date are never overdue.
    """
    today = date.today()
    result: list[dict] = []
    for m in project.milestones:
        d = _parse_date(m.date)
        overdue = False
        if d is not None and not m.done and d < today:
            overdue = True
        result.append({
            "name": m.name,
            "date": m.date,
            "done": m.done,
            "overdue": overdue,
        })
    return result


def project_health(
    tasks: list[Task],
    project: Project,
    today: date,
) -> str:
    """Compute project health: ``'green'``, ``'amber'``, or ``'red'``.

    Thresholds
    ----------
    **Red** — any of:
      - more than 25 % of tasks are overdue, OR
      - any milestone is overdue (date < today and not done).

    **Amber** — any of:
      - more than 10 % of tasks are overdue, OR
      - any milestone is due within 7 days and not done.

    **Green** — otherwise.

    Tasks without a due date are excluded from the overdue percentage
    calculation (they cannot be overdue).  When there are zero tasks
    with a due date, the percentage-based rule cannot fire.
    """
    n_overdue = len(overdue_tasks(tasks, today))
    n_total = len(tasks)

    # Milestone checks
    any_milestone_overdue = False
    any_milestone_due_soon = False
    for m in project.milestones:
        d = _parse_date(m.date)
        if d is None or m.done:
            continue
        if d < today:
            any_milestone_overdue = True
        elif d <= today + timedelta(days=7):
            any_milestone_due_soon = True

    # Red checks
    if any_milestone_overdue:
        return "red"
    if n_total > 0 and n_overdue / n_total > 0.25:
        return "red"

    # Amber checks
    if any_milestone_due_soon:
        return "amber"
    if n_total > 0 and n_overdue / n_total > 0.10:
        return "amber"

    return "green"


# ── portfolio roll-up ──────────────────────────────────────────────

def portfolio_kpis(
    projects: list[tuple[Project, list[Task]]],
    today: date,
) -> dict:
    """Roll up KPIs across multiple projects.

    Returns a dict with keys:

    - **total_tasks** (int): sum of task counts across all projects.
    - **total_done** (int): tasks whose status is done-like.
    - **overall_progress** (float 0..100): task-count-weighted average of
      per-project progress.
    - **per_project**: ``list[dict]`` each with
      ``{name, progress, health, overdue_count, task_count}``.
    - **overdue_total** (int): total overdue tasks across all projects.
    - **milestones_due_soon**: ``list[dict]`` — milestones due within 14
      days and not done; each dict has ``{project, name, date}``.
    """
    total_tasks = 0
    total_done = 0
    overdue_total = 0
    per_project: list[dict] = []
    milestones_due_soon: list[dict] = []
    weighted_progress_sum = 0.0

    cutoff = today + timedelta(days=14)

    for proj, tasks in projects:
        n = len(tasks)
        total_tasks += n
        done_count = sum(1 for t in tasks if _is_done(t))
        total_done += done_count
        prog = project_progress(tasks)
        od = overdue_tasks(tasks, today)
        overdue_total += len(od)
        health = project_health(tasks, proj, today)
        weighted_progress_sum += prog * n

        per_project.append({
            "name": proj.name,
            "progress": prog,
            "health": health,
            "overdue_count": len(od),
            "task_count": n,
        })

        for m in proj.milestones:
            d = _parse_date(m.date)
            if d is not None and not m.done and today <= d < cutoff:
                milestones_due_soon.append({
                    "project": proj.name,
                    "name": m.name,
                    "date": m.date,
                })

    overall_progress = (
        weighted_progress_sum / total_tasks if total_tasks > 0 else 0.0
    )

    return {
        "total_tasks": total_tasks,
        "total_done": total_done,
        "overall_progress": overall_progress,
        "per_project": per_project,
        "overdue_total": overdue_total,
        "milestones_due_soon": milestones_due_soon,
    }


# ── cross-project dependency & slip impact ─────────────────────────

def resolve_cross_links(
    projects: list[tuple[Project, list[Task]]],
) -> list[dict]:
    """Resolve :class:`CrossProjectLink` instances to actual task pairs.

    Returns ``[{from_project, from_task, to_project, to_task, from_due,
    to_start}]`` where tasks are looked up by id.  Unresolvable links
    (missing project or task id) are silently skipped.
    """
    # Build lookup: project_name -> {task_id -> Task}
    proj_task_map: dict[str, dict[str, Task]] = {}
    proj_map: dict[str, Project] = {}
    for proj, tasks in projects:
        proj_map[proj.name] = proj
        proj_task_map[proj.name] = {t.id: t for t in tasks if t.id}

    result: list[dict] = []
    for proj, _tasks in projects:
        for link in proj.cross_links:
            from_tasks = proj_task_map.get(link.from_project, {})
            to_tasks = proj_task_map.get(link.to_project, {})
            from_task = from_tasks.get(link.from_id)
            to_task = to_tasks.get(link.to_id)
            if from_task is None or to_task is None:
                continue
            result.append({
                "from_project": link.from_project,
                "from_task": from_task,
                "to_project": link.to_project,
                "to_task": to_task,
                "from_due": _parse_date(from_task.due),
                "to_start": _parse_date(to_task.start),
            })
    return result


def slip_impact(
    projects: list[tuple[Project, list[Task]]],
    slipped_project: str,
    slipped_task_id: str,
    slip_days: int,
    *,
    hours_per_day: float = 8.0,
) -> list[dict]:
    """Compute downstream impact of a task slipping by *slip_days*.

    If task X in *slipped_project* slips by *slip_days*, which downstream
    tasks (including cross-project successors) are affected?

    Algorithm:
    1. Run ``compute_cpm`` on the slipped project before and after the
       slip to find intra-project impact.
    2. Walk cross-project links from the slipped project to find tasks
       in other projects whose start depends on the slipped task's
       finish.
    3. For each affected downstream project, re-run ``compute_cpm``
       with the adjusted start and report the delta.

    Returns ``[{project, task_id, task_title, new_finish, old_finish,
    slip}]``.
    """
    # Build lookup structures
    proj_task_map: dict[str, list[Task]] = {}
    proj_map: dict[str, Project] = {}
    for proj, tasks in projects:
        proj_map[proj.name] = proj
        proj_task_map[proj.name] = tasks

    slipped_tasks = proj_task_map.get(slipped_project, [])
    if not slipped_tasks:
        return []

    # Original CPM for the slipped project
    original_cpm = compute_cpm(slipped_tasks, hours_per_day=hours_per_day)
    if slipped_task_id not in original_cpm:
        return []

    # Slip the task: add slip_days to its effort (or due date)
    # We simulate by shifting the start date of the task forward
    import copy
    shifted_tasks = copy.deepcopy(slipped_tasks)
    task_id_map = {t.id: t for t in shifted_tasks}

    slipped_task = task_id_map.get(slipped_task_id)
    if slipped_task is None:
        return []

    # Shift the task's start forward by slip_days
    orig_start = _parse_date(slipped_task.start)
    if orig_start is not None:
        slipped_task.start = (orig_start + timedelta(days=slip_days)).isoformat()
    else:
        # If no start date, add effort to simulate a delay
        if slipped_task.effort is not None:
            slipped_task.effort += slip_days * hours_per_day
        else:
            slipped_task.effort = (1 + slip_days) * hours_per_day

    new_cpm = compute_cpm(shifted_tasks, hours_per_day=hours_per_day)

    result: list[dict] = []

    # Intra-project impact
    for tid, new_res in new_cpm.items():
        if tid == slipped_task_id:
            continue
        old_res = original_cpm.get(tid)
        if old_res is None:
            continue
        if new_res.early_finish > old_res.early_finish:
            orig_task = next((t for t in slipped_tasks if t.id == tid), None)
            if orig_task is None:
                continue
            result.append({
                "project": slipped_project,
                "task_id": tid,
                "task_title": orig_task.title,
                "new_finish": new_res.early_finish,
                "old_finish": old_res.early_finish,
                "slip": (new_res.early_finish - old_res.early_finish).days,
            })

    # Cross-project impact: find links where from_project == slipped_project
    resolved = resolve_cross_links(projects)
    for link_info in resolved:
        if link_info["from_project"] != slipped_project:
            continue
        from_task: Task = link_info["from_task"]
        # Check if the from_task's finish changed
        from_old = original_cpm.get(from_task.id)
        from_new = new_cpm.get(from_task.id)
        if from_old is None or from_new is None:
            continue
        finish_slip = (from_new.early_finish - from_old.early_finish).days
        if finish_slip <= 0:
            # Also check if the slipped task itself is the linked task
            if from_task.id == slipped_task_id:
                old_finish = original_cpm[slipped_task_id].early_finish
                new_finish = new_cpm[slipped_task_id].early_finish
                finish_slip = (new_finish - old_finish).days
                if finish_slip <= 0:
                    continue
            else:
                continue

        # Cascade into the downstream project
        to_project_name = link_info["to_project"]
        to_task: Task = link_info["to_task"]
        downstream_tasks = proj_task_map.get(to_project_name, [])
        if not downstream_tasks:
            continue

        downstream_orig_cpm = compute_cpm(
            downstream_tasks, hours_per_day=hours_per_day,
        )

        # Shift the linked task's start in the downstream project
        shifted_downstream = copy.deepcopy(downstream_tasks)
        ds_id_map = {t.id: t for t in shifted_downstream}
        ds_target = ds_id_map.get(to_task.id)
        if ds_target is None:
            continue
        ds_start = _parse_date(ds_target.start)
        if ds_start is not None:
            ds_target.start = (ds_start + timedelta(days=finish_slip)).isoformat()
        else:
            # Give it a start date based on the upstream finish + slip
            ds_target.start = (from_new.early_finish + timedelta(days=1)).isoformat()

        downstream_new_cpm = compute_cpm(
            shifted_downstream, hours_per_day=hours_per_day,
        )

        for tid, new_res in downstream_new_cpm.items():
            old_res = downstream_orig_cpm.get(tid)
            if old_res is None:
                continue
            if new_res.early_finish > old_res.early_finish:
                orig_task = next(
                    (t for t in downstream_tasks if t.id == tid), None,
                )
                if orig_task is None:
                    continue
                result.append({
                    "project": to_project_name,
                    "task_id": tid,
                    "task_title": orig_task.title,
                    "new_finish": new_res.early_finish,
                    "old_finish": old_res.early_finish,
                    "slip": (new_res.early_finish - old_res.early_finish).days,
                })

    return result


__all__ = [
    "project_progress",
    "status_counts",
    "overdue_tasks",
    "at_risk_tasks",
    "milestone_schedule",
    "project_health",
    "portfolio_kpis",
    "resolve_cross_links",
    "slip_impact",
]
