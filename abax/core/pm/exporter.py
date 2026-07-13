"""Export PM views to SVG files and optionally to PDF-ready HTML.

Pure stdlib.  Wraps :func:`gantt_svg` and :func:`timeline_svg` from
:mod:`abax.core.pm.pmsvg`, adds legend rendering, multi-project stacking,
and a lightweight HTML wrapper for browser-based PDF printing.
"""

from __future__ import annotations

import pathlib
from datetime import date
from xml.sax.saxutils import escape

from abax.core.pm.pmsvg import gantt_svg, timeline_svg
from abax.core.pm.projects import Project
from abax.core.pm.taskmodel import Task

__all__ = [
    "export_gantt_svg",
    "export_timeline_svg",
    "export_gantt_pdf",
    "export_report_svg",
]

# Colour constants — kept in sync with pmsvg defaults.
_BAR = "#1565c0"
_BAR_DONE = "#0d47a1"
_CRITICAL = "#c62828"
_TODAY = "#ef6c00"
_MILESTONE_FILL = "#f9a825"
_IN_PROGRESS = "#42a5f5"
_TEXT = "#333333"
_BG = "white"
_FONT = "sans-serif"


# -------------------------------------------------------------------
# Legend
# -------------------------------------------------------------------

def _legend_svg(width: int = 800) -> str:
    """Return a small ``<svg>`` block explaining the colour key."""
    items: list[tuple[str, str, str]] = [
        ("rect", _BAR, "Scheduled"),
        ("rect", _BAR_DONE, "Done"),
        ("rect", _CRITICAL, "Critical path"),
        ("rect", _IN_PROGRESS, "In progress"),
        ("diamond", _MILESTONE_FILL, "Milestone"),
        ("line", _TODAY, "Today"),
    ]

    row_h = 20
    col_w = 130
    cols = min(len(items), max(1, width // col_w))
    rows = (len(items) + cols - 1) // cols
    legend_h = rows * row_h + 10
    legend_w = width

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {legend_w} {legend_h}" '
        f'width="{legend_w}" height="{legend_h}">',
        f'<rect width="{legend_w}" height="{legend_h}" fill="{_BG}"/>',
    ]

    for i, (kind, colour, label) in enumerate(items):
        col = i % cols
        row = i // cols
        x = 10 + col * col_w
        y = 6 + row * row_h

        if kind == "rect":
            parts.append(
                f'<rect x="{x}" y="{y}" width="14" height="12" rx="2" '
                f'fill="{colour}"/>'
            )
        elif kind == "diamond":
            cx = x + 7
            cy = y + 6
            parts.append(
                f'<path d="M{cx},{cy - 5} L{cx + 5},{cy} '
                f'L{cx},{cy + 5} L{cx - 5},{cy} Z" '
                f'fill="{colour}" stroke="{_TEXT}" stroke-width="0.5"/>'
            )
        elif kind == "line":
            parts.append(
                f'<line x1="{x}" y1="{y + 6}" x2="{x + 14}" y2="{y + 6}" '
                f'stroke="{colour}" stroke-width="2" stroke-dasharray="4,2"/>'
            )

        parts.append(
            f'<text x="{x + 18}" y="{y + 10}" font-family="{_FONT}" '
            f'font-size="10" fill="{_TEXT}">{escape(label)}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def _combine_svgs(*svgs: str, width: int = 800) -> str:
    """Stack multiple ``<svg>`` strings vertically into one SVG document.

    Each child SVG is embedded as a ``<g>`` with a translate transform.
    Heights are extracted from the ``viewBox`` or ``height`` attribute.
    """
    import re

    blocks: list[tuple[str, int]] = []  # (svg_content, height)
    for svg in svgs:
        # Extract height from viewBox="0 0 W H" or height="H"
        m = re.search(r'viewBox="[^"]*\s(\d+)"', svg)
        if m:
            h = int(m.group(1))
        else:
            m = re.search(r'height="(\d+)"', svg)
            h = int(m.group(1)) if m else 100
        blocks.append((svg, h))

    total_h = sum(h for _, h in blocks)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {total_h}" '
        f'width="{width}" height="{total_h}">',
        f'<rect width="{width}" height="{total_h}" fill="{_BG}"/>',
    ]

    y_offset = 0
    for svg_str, h in blocks:
        # Strip the outer <svg> and </svg> tags, embed as a <g>.
        inner = re.sub(r"<svg[^>]*>", "", svg_str, count=1)
        inner = re.sub(r"</svg>\s*$", "", inner)
        parts.append(f'<g transform="translate(0,{y_offset})">')
        parts.append(inner)
        parts.append("</g>")
        y_offset += h

    parts.append("</svg>")
    return "\n".join(parts)


# -------------------------------------------------------------------
# Gantt SVG export
# -------------------------------------------------------------------

def export_gantt_svg(
    tasks: list[Task],
    path: str | pathlib.Path,
    *,
    critical: set[str] | None = None,
    today: date | None = None,
    milestones: list | None = None,
    width: int = 800,
    row_height: int = 28,
    title: str = "",
    show_legend: bool = True,
) -> None:
    """Export a Gantt chart to an SVG file.

    Generates the chart via :func:`~abax.core.pm.pmsvg.gantt_svg` and
    writes the result to *path*.  When *show_legend* is ``True`` a colour
    key is appended below the chart.

    Parameters
    ----------
    tasks : list[Task]
        Task objects; only those with ``start`` and ``due`` are drawn.
    path : str | Path
        Destination file path.
    critical, today, milestones, width, row_height, title :
        Forwarded to :func:`gantt_svg`.
    show_legend : bool
        Append a legend explaining the colour coding (default ``True``).
    """
    svg = gantt_svg(
        tasks,
        critical=critical,
        today=today,
        milestones=milestones,
        width=width,
        row_height=row_height,
        title=title,
    )

    if show_legend:
        legend = _legend_svg(width=width)
        svg = _combine_svgs(svg, legend, width=width)

    pathlib.Path(path).write_text(svg, encoding="utf-8")


# -------------------------------------------------------------------
# Timeline SVG export
# -------------------------------------------------------------------

def export_timeline_svg(
    tasks: list[Task],
    path: str | pathlib.Path,
    *,
    width: int = 800,
    lane_height: int = 32,
    title: str = "",
    lanes: list[str] | None = None,
) -> None:
    """Export a timeline chart to an SVG file.

    Converts :class:`Task` objects into the ``dict`` items expected by
    :func:`~abax.core.pm.pmsvg.timeline_svg`, using the assignee as the
    lane and ``start``/``due`` as the time span.

    Parameters
    ----------
    tasks : list[Task]
        Task objects; those missing ``start`` or ``due`` are skipped.
    path : str | Path
        Destination file path.
    width, lane_height, title, lanes :
        Forwarded to :func:`timeline_svg`.
    """
    items: list[dict] = []
    for t in tasks:
        if t.start is not None and t.due is not None:
            items.append({
                "name": t.title,
                "start": t.start,
                "end": t.due,
                "lane": t.assignee or "",
            })

    svg = timeline_svg(
        items,
        width=width,
        lane_height=lane_height,
        title=title,
        lanes=lanes,
    )
    pathlib.Path(path).write_text(svg, encoding="utf-8")


# -------------------------------------------------------------------
# PDF wrapper (HTML-based)
# -------------------------------------------------------------------

def _svg_to_html(svg: str, *, title: str = "Gantt Chart") -> str:
    """Wrap an SVG string in a minimal HTML page for browser-based PDF printing."""
    return (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head>\n"
        f"<title>{escape(title)}</title>\n"
        "<style>\n"
        "  @page { size: landscape; margin: 1cm; }\n"
        "  body { margin: 0; display: flex; justify-content: center; }\n"
        "  svg { max-width: 100%; height: auto; }\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        f"{svg}\n"
        "</body>\n"
        "</html>\n"
    )


def export_gantt_pdf(
    tasks: list[Task],
    path: str | pathlib.Path,
    *,
    critical: set[str] | None = None,
    today: date | None = None,
    milestones: list | None = None,
    width: int = 800,
    row_height: int = 28,
    title: str = "",
    show_legend: bool = True,
) -> None:
    """Export a Gantt chart as an HTML file suitable for PDF conversion.

    Generates the SVG via :func:`gantt_svg`, wraps it in a minimal HTML
    page with print-friendly CSS, and writes to *path*.

    For high-fidelity PDF output the GUI layer should use Qt's
    ``QWebEnginePage.printToPdf`` (or ``QPrinter``) on this HTML.  In a
    headless/core context, the caller can open the file in a browser and
    use the browser's print-to-PDF.

    The file is saved with an ``.html`` extension regardless of the
    extension in *path* — rename it afterwards if needed.
    """
    svg = gantt_svg(
        tasks,
        critical=critical,
        today=today,
        milestones=milestones,
        width=width,
        row_height=row_height,
        title=title,
    )

    if show_legend:
        legend = _legend_svg(width=width)
        svg = _combine_svgs(svg, legend, width=width)

    html = _svg_to_html(svg, title=title or "Gantt Chart")
    pathlib.Path(path).write_text(html, encoding="utf-8")


# -------------------------------------------------------------------
# Multi-project report
# -------------------------------------------------------------------

def export_report_svg(
    projects: list[tuple[Project, list[Task]]],
    path: str | pathlib.Path,
    *,
    today: date | None = None,
    width: int = 800,
    row_height: int = 28,
) -> None:
    """Export a stacked multi-project Gantt report to a single SVG file.

    Each ``(project, tasks)`` pair gets its own Gantt chart with the
    project name as the title.  The charts are stacked vertically with
    a small gap between them.

    Parameters
    ----------
    projects : list[tuple[Project, list[Task]]]
        One entry per project; the format matches what
        ``portfolio.dashboard`` produces.
    path : str | Path
        Destination SVG file.
    today : date | None
        Passed through to each Gantt chart.
    width : int
        Chart width (shared across all projects).
    row_height : int
        Row height per task row.
    """
    if not projects:
        # Write a minimal empty SVG.
        empty = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {width} 60" width="{width}" height="60">'
            f'<rect width="{width}" height="60" fill="{_BG}"/>'
            f'<text x="{width / 2.0:.1f}" y="30" text-anchor="middle" '
            f'font-family="{_FONT}" font-size="12" '
            f'fill="{_TEXT}">No projects</text>'
            "</svg>"
        )
        pathlib.Path(path).write_text(empty, encoding="utf-8")
        return

    chart_svgs: list[str] = []
    for project, tasks in projects:
        svg = gantt_svg(
            tasks,
            today=today,
            width=width,
            row_height=row_height,
            title=project.name,
        )
        chart_svgs.append(svg)

    combined = _combine_svgs(*chart_svgs, width=width)
    pathlib.Path(path).write_text(combined, encoding="utf-8")
