"""Roll-up report renderer — sheet data and standalone HTML.

Pure stdlib (except sibling ``pmsvg`` which is also core). Produces:

* **Sheet data** for the Profile-sheet pattern: headers + rows, one per
  project plus a totals row.
* **HTML report** — a self-contained page with per-project summary table,
  embedded Gantt SVGs, milestone list, and inline CSS.
"""

from __future__ import annotations

from datetime import date
from xml.sax.saxutils import escape

from abax.core.pm.projects import Project
from abax.core.pm.taskmodel import Task

__all__ = [
    "report_sheet_data",
    "report_html",
    "report_markdown",
]


# ---------------------------------------------------------------------------
# Private analytics helpers (lightweight; portfolio.py has the canonical
# versions — the integrator will wire those later)
# ---------------------------------------------------------------------------

_DONE_STATUSES = frozenset({"done", "complete", "completed", "closed"})


def _is_done(task: Task) -> bool:
    return task.status.lower() in _DONE_STATUSES or task.percent_done >= 100.0


def _progress(tasks: list[Task]) -> float:
    """Effort-weighted progress, falling back to simple average."""
    weighted = [(t.effort or 1.0, t.percent_done) for t in tasks]
    total_effort = sum(w for w, _ in weighted)
    if total_effort <= 0:
        return 0.0
    return sum(w * p for w, p in weighted) / total_effort


def _overdue_tasks(tasks: list[Task], today: date) -> list[Task]:
    return [
        t for t in tasks
        if t.due is not None and t.due < today and not _is_done(t)
    ]


def _health(tasks: list[Task], today: date) -> str:
    """Green / Amber / Red based on overdue ratio."""
    if not tasks:
        return "Green"
    overdue = len(_overdue_tasks(tasks, today))
    ratio = overdue / len(tasks)
    if ratio > 0.25:
        return "Red"
    if ratio > 0.10:
        return "Amber"
    return "Green"


def _milestone_summary(project: Project) -> str:
    if not project.milestones:
        return ""
    total = len(project.milestones)
    done = sum(1 for m in project.milestones if m.done)
    return f"{done}/{total}"


# ---------------------------------------------------------------------------
# Sheet data
# ---------------------------------------------------------------------------

_HEADERS = [
    "Project",
    "Progress %",
    "Tasks",
    "Done",
    "Overdue",
    "Health",
    "Milestones",
]


def report_sheet_data(
    projects: list[tuple[Project, list[Task]]],
    today: date,
) -> tuple[list[str], list[list[str]]]:
    """Return ``(headers, rows)`` for a report sheet.

    One row per project, plus a totals row at the bottom.
    """
    rows: list[list[str]] = []

    total_tasks = 0
    total_done = 0
    total_overdue = 0
    all_tasks: list[Task] = []
    total_milestones = 0
    total_milestones_done = 0

    for proj, tasks in projects:
        done_count = sum(1 for t in tasks if _is_done(t))
        overdue_count = len(_overdue_tasks(tasks, today))
        pct = _progress(tasks) if tasks else 0.0

        rows.append([
            proj.name,
            f"{pct:.1f}",
            str(len(tasks)),
            str(done_count),
            str(overdue_count),
            _health(tasks, today),
            _milestone_summary(proj),
        ])

        total_tasks += len(tasks)
        total_done += done_count
        total_overdue += overdue_count
        all_tasks.extend(tasks)
        total_milestones += len(proj.milestones)
        total_milestones_done += sum(1 for m in proj.milestones if m.done)

    # Totals row
    overall_pct = _progress(all_tasks) if all_tasks else 0.0
    ms_summary = f"{total_milestones_done}/{total_milestones}" if total_milestones else ""
    rows.append([
        "TOTAL",
        f"{overall_pct:.1f}",
        str(total_tasks),
        str(total_done),
        str(total_overdue),
        _health(all_tasks, today),
        ms_summary,
    ])

    return list(_HEADERS), rows


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------

_CSS = """\
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
       Helvetica, Arial, sans-serif; margin: 2em; color: #222; }
h1 { margin-bottom: 0.2em; }
.subtitle { color: #666; margin-bottom: 1.5em; }
table { border-collapse: collapse; width: 100%; margin-bottom: 2em; }
th, td { border: 1px solid #ccc; padding: 6px 10px; text-align: left; }
th { background: #f5f5f5; }
tr:nth-child(even) { background: #fafafa; }
tr.totals { font-weight: bold; background: #eee; }
.health-green { color: #2e7d32; }
.health-amber { color: #ef6c00; }
.health-red   { color: #c62828; }
.project-section { margin-bottom: 2em; }
.milestone-list { list-style: none; padding: 0; }
.milestone-list li { padding: 2px 0; }
.milestone-list li.done { text-decoration: line-through; color: #999; }
svg { max-width: 100%; height: auto; }
"""


def _health_class(h: str) -> str:
    return f"health-{h.lower()}"


def report_html(
    projects: list[tuple[Project, list[Task]]],
    today: date,
    *,
    title: str = "Project Report",
) -> str:
    """Return a self-contained HTML string with summary table and Gantt charts."""
    # Lazy import to keep module-level clean (pmsvg is also core).
    from abax.core.pm.pmsvg import gantt_svg

    headers, rows = report_sheet_data(projects, today)
    parts: list[str] = []

    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en"><head><meta charset="utf-8">')
    parts.append(f"<title>{escape(title)}</title>")
    parts.append(f"<style>{_CSS}</style>")
    parts.append("</head><body>")
    parts.append(f"<h1>{escape(title)}</h1>")
    parts.append(f'<p class="subtitle">Generated {today.isoformat()}</p>')

    # Summary table
    parts.append("<table>")
    parts.append("<thead><tr>")
    for h in headers:
        parts.append(f"<th>{escape(h)}</th>")
    parts.append("</tr></thead><tbody>")

    for i, row in enumerate(rows):
        is_totals = i == len(rows) - 1
        cls = ' class="totals"' if is_totals else ""
        parts.append(f"<tr{cls}>")
        for j, cell in enumerate(row):
            # Colour the Health column
            if j == 5:  # noqa: PLR2004 — Health column index
                hcls = _health_class(cell)
                parts.append(f'<td class="{hcls}">{escape(cell)}</td>')
            else:
                parts.append(f"<td>{escape(cell)}</td>")
        parts.append("</tr>")

    parts.append("</tbody></table>")

    # Per-project Gantt + milestones
    for proj, tasks in projects:
        parts.append('<div class="project-section">')
        parts.append(f"<h2>{escape(proj.name)}</h2>")

        # Embedded Gantt SVG
        if tasks:
            svg = gantt_svg(
                tasks,
                today=today,
                milestones=proj.milestones,
                title=proj.name,
            )
            parts.append(svg)

        # Milestone list
        if proj.milestones:
            parts.append("<h3>Milestones</h3>")
            parts.append('<ul class="milestone-list">')
            for ms in proj.milestones:
                cls = ' class="done"' if ms.done else ""
                label = escape(ms.name)
                if ms.date:
                    label += f" ({escape(ms.date)})"
                parts.append(f"<li{cls}>{label}</li>")
            parts.append("</ul>")

        parts.append("</div>")

    parts.append("</body></html>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def report_markdown(
    projects: list[tuple[Project, list[Task]]],
    today: date,
    *,
    title: str = "Project Report",
) -> str:
    """Return a Markdown string with summary table and per-project details."""
    headers, rows = report_sheet_data(projects, today)
    lines: list[str] = []

    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"*Generated {today.isoformat()}*")
    lines.append("")

    # Summary table
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for i, row in enumerate(rows):
        prefix = "**" if i == len(rows) - 1 else ""
        suffix = "**" if i == len(rows) - 1 else ""
        cells = [f"{prefix}{cell}{suffix}" for cell in row]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    # Per-project details
    for proj, tasks in projects:
        lines.append(f"## {proj.name}")
        lines.append("")

        done_count = sum(1 for t in tasks if _is_done(t))
        overdue = _overdue_tasks(tasks, today)
        pct = _progress(tasks) if tasks else 0.0
        health = _health(tasks, today)

        lines.append(f"- **Progress:** {pct:.0f}%")
        lines.append(f"- **Tasks:** {len(tasks)} ({done_count} done)")
        lines.append(f"- **Overdue:** {len(overdue)}")
        lines.append(f"- **Health:** {health}")
        lines.append("")

        if overdue:
            lines.append("### Overdue tasks")
            lines.append("")
            for t in overdue:
                due_str = t.due.isoformat() if t.due else "?"
                lines.append(f"- {t.title or t.id} (due {due_str})")
            lines.append("")

        if proj.milestones:
            lines.append("### Milestones")
            lines.append("")
            for ms in proj.milestones:
                mark = "x" if ms.done else " "
                date_str = f" ({ms.date})" if ms.date else ""
                lines.append(f"- [{mark}] {ms.name}{date_str}")
            lines.append("")

    return "\n".join(lines)
