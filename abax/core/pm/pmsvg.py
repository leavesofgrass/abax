"""PM-layer SVG renderers — Gantt chart, timeline, and calendar month.

Pure stdlib. Each public function returns a complete ``<svg>`` string with
inline styles, viewBox-based sizing, and no external dependencies — the same
idiom as :mod:`abax.core.science.chartsvg`.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from xml.sax.saxutils import escape

__all__ = ["gantt_svg", "timeline_svg", "calendar_month_svg"]

# Default colours.
_BAR = "#1565c0"
_BAR_DONE = "#0d47a1"
_CRITICAL = "#c62828"
_CRITICAL_DONE = "#8e0000"
_GRID = "#cccccc"
_TODAY = "#ef6c00"
_MILESTONE_FILL = "#f9a825"
_TEXT = "#333333"
_BG = "white"
_FONT = "sans-serif"
_ARROW = "#555555"


def _date_x(d: date, d_min: date, d_max: date, x0: float, pw: float) -> float:
    span = (d_max - d_min).days
    if span <= 0:
        return x0
    return x0 + (d - d_min).days / span * pw


def _clamp_text(text: str, max_chars: int = 24) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


# -------------------------------------------------------------------
# Gantt chart
# -------------------------------------------------------------------

def gantt_svg(
    tasks,
    *,
    critical: set[str] | None = None,
    today: date | None = None,
    milestones: list | None = None,
    width: int = 800,
    row_height: int = 28,
    title: str = "",
) -> str:
    """Gantt chart SVG for a list of :class:`Task` objects.

    Parameters
    ----------
    tasks : list[Task]
        Only tasks with both ``start`` and ``due`` are drawn.
    critical : set[str] | None
        Task IDs on the critical path — drawn in a red tone.
    today : date | None
        If set, a vertical dashed line marks today.
    milestones : list[Milestone] | None
        Diamond markers along the header at their dates.
    width : int
        ViewBox width; height is computed from content.
    row_height : int
        Pixel height per task row.
    title : str
        Chart title drawn at the top.

    Colors: ``_BAR`` (default bar), ``_CRITICAL`` (critical-path bar),
    ``_BAR_DONE`` / ``_CRITICAL_DONE`` (percent-done overlay),
    ``_TODAY`` (today line), ``_MILESTONE_FILL`` (milestone diamond).
    """
    crit = critical or set()

    dated = [t for t in tasks if t.start is not None and t.due is not None]

    ms_dates: list[date] = []
    if milestones:
        for m in milestones:
            try:
                ms_dates.append(
                    date.fromisoformat(m.date) if isinstance(m.date, str) else m.date
                )
            except (ValueError, TypeError):
                ms_dates.append(None)  # type: ignore[arg-type]

    all_dates: list[date] = []
    for t in dated:
        all_dates.append(t.start)  # type: ignore[arg-type]
        all_dates.append(t.due)  # type: ignore[arg-type]
    for d in ms_dates:
        if d is not None:
            all_dates.append(d)
    if today is not None:
        all_dates.append(today)

    if not all_dates:
        h = 60
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {width} {h}" width="{width}" height="{h}">',
            f'<rect width="{width}" height="{h}" fill="{_BG}"/>',
        ]
        if title:
            parts.append(
                f'<text x="{width / 2.0:.1f}" y="16" text-anchor="middle" '
                f'font-family="{_FONT}" font-size="13" '
                f'font-weight="bold" fill="{_TEXT}">{escape(title)}</text>'
            )
        parts.append("</svg>")
        return "\n".join(parts)

    d_min = min(all_dates) - timedelta(days=1)
    d_max = max(all_dates) + timedelta(days=1)

    margin_l = 150
    margin_r = 16
    header_h = 40 + (20 if title else 0)
    ms_row_h = 24 if milestones else 0
    body_h = len(dated) * row_height
    height = int(header_h + ms_row_h + body_h + 10)
    pw = width - margin_l - margin_r
    x0 = margin_l
    y_header = 20 if title else 0

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
        f'<rect width="{width}" height="{height}" fill="{_BG}"/>',
    ]

    if title:
        parts.append(
            f'<text x="{width / 2.0:.1f}" y="16" text-anchor="middle" '
            f'font-family="{_FONT}" font-size="13" '
            f'font-weight="bold" fill="{_TEXT}">{escape(title)}</text>'
        )

    # Date axis labels (months).
    _gantt_date_axis(parts, d_min, d_max, x0, pw, y_header + 8)

    # Milestone diamonds in a row below the axis.
    if milestones:
        my = y_header + 34
        for i, m in enumerate(milestones):
            md = ms_dates[i] if i < len(ms_dates) else None
            if md is None:
                continue
            mx = _date_x(md, d_min, d_max, x0, pw)
            diamond = (
                f"M{mx:.1f},{my - 6:.1f} "
                f"L{mx + 6:.1f},{my:.1f} "
                f"L{mx:.1f},{my + 6:.1f} "
                f"L{mx - 6:.1f},{my:.1f} Z"
            )
            parts.append(
                f'<path d="{diamond}" fill="{_MILESTONE_FILL}" '
                f'stroke="{_TEXT}" stroke-width="0.75"/>'
            )
            parts.append(
                f'<text x="{mx:.1f}" y="{my + 18:.1f}" text-anchor="middle" '
                f'font-family="{_FONT}" font-size="9" '
                f'fill="{_TEXT}">{escape(_clamp_text(m.name, 16))}</text>'
            )

    body_y0 = header_h + ms_row_h
    id_to_row: dict[str, int] = {}
    for idx, t in enumerate(dated):
        if t.id:
            id_to_row[t.id] = idx

    for idx, t in enumerate(dated):
        y = body_y0 + idx * row_height
        is_crit = t.id in crit

        # Row background grid line.
        parts.append(
            f'<line x1="{x0}" y1="{y + row_height:.1f}" '
            f'x2="{x0 + pw:.1f}" y2="{y + row_height:.1f}" '
            f'stroke="{_GRID}" stroke-width="0.5"/>'
        )

        # Task title label (left of bars).
        parts.append(
            f'<text x="{x0 - 6:.1f}" y="{y + row_height / 2.0 + 4:.1f}" '
            f'text-anchor="end" font-family="{_FONT}" font-size="11" '
            f'fill="{_TEXT}">{escape(_clamp_text(t.title))}</text>'
        )

        bar_x = _date_x(t.start, d_min, d_max, x0, pw)  # type: ignore[arg-type]
        bar_x2 = _date_x(t.due, d_min, d_max, x0, pw)  # type: ignore[arg-type]
        bar_w = max(bar_x2 - bar_x, 2.0)
        bar_y = y + 4
        bar_h = row_height - 8
        fill = _CRITICAL if is_crit else _BAR

        parts.append(
            f'<rect x="{bar_x:.1f}" y="{bar_y:.1f}" '
            f'width="{bar_w:.1f}" height="{bar_h:.1f}" rx="3" '
            f'fill="{fill}" fill-opacity="0.8"/>'
        )

        # Percent-done overlay.
        pct = max(0.0, min(1.0, t.percent_done))
        if pct > 0:
            done_fill = _CRITICAL_DONE if is_crit else _BAR_DONE
            parts.append(
                f'<rect x="{bar_x:.1f}" y="{bar_y:.1f}" '
                f'width="{bar_w * pct:.1f}" height="{bar_h:.1f}" rx="3" '
                f'fill="{done_fill}"/>'
            )

    # Dependency arrows.
    for idx, t in enumerate(dated):
        if not t.depends:
            continue
        for dep_id in t.depends:
            if dep_id not in id_to_row:
                continue
            pred_idx = id_to_row[dep_id]
            pred = dated[pred_idx]
            if pred.due is None or t.start is None:
                continue
            sx = _date_x(pred.due, d_min, d_max, x0, pw)  # type: ignore[arg-type]
            sy = body_y0 + pred_idx * row_height + row_height / 2.0
            ex = _date_x(t.start, d_min, d_max, x0, pw)  # type: ignore[arg-type]
            ey = body_y0 + idx * row_height + row_height / 2.0
            mid_x = sx + 8
            path_d = (
                f"M{sx:.1f},{sy:.1f} "
                f"L{mid_x:.1f},{sy:.1f} "
                f"L{mid_x:.1f},{ey:.1f} "
                f"L{ex:.1f},{ey:.1f}"
            )
            parts.append(
                f'<path d="{path_d}" fill="none" '
                f'stroke="{_ARROW}" stroke-width="1.2" '
                f'marker-end="url(#arrowhead)"/>'
            )

    # Define arrowhead marker if there are any dependency arrows.
    has_deps = any(
        dep_id in id_to_row
        for t in dated
        for dep_id in t.depends
    )
    if has_deps:
        parts.insert(
            1,
            '<defs><marker id="arrowhead" markerWidth="8" markerHeight="6" '
            'refX="8" refY="3" orient="auto">'
            f'<path d="M0,0 L8,3 L0,6 Z" fill="{_ARROW}"/>'
            "</marker></defs>",
        )

    # Today line.
    if today is not None:
        tx = _date_x(today, d_min, d_max, x0, pw)
        parts.append(
            f'<line x1="{tx:.1f}" y1="{y_header + 20:.1f}" '
            f'x2="{tx:.1f}" y2="{height - 4:.1f}" '
            f'stroke="{_TODAY}" stroke-width="1.5" '
            f'stroke-dasharray="6,3"/>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def _gantt_date_axis(
    parts: list[str],
    d_min: date,
    d_max: date,
    x0: float,
    pw: float,
    y: float,
) -> None:
    """Draw month/week tick labels across the date range."""
    span = (d_max - d_min).days
    if span <= 0:
        return

    # Always draw month boundaries.
    cur = d_min.replace(day=1)
    while cur <= d_max:
        if cur >= d_min:
            mx = _date_x(cur, d_min, d_max, x0, pw)
            parts.append(
                f'<line x1="{mx:.1f}" y1="{y:.1f}" '
                f'x2="{mx:.1f}" y2="{y + 14:.1f}" '
                f'stroke="{_GRID}" stroke-width="0.5"/>'
            )
            label = cur.strftime("%b %Y") if span > 60 else cur.strftime("%b %d")
            parts.append(
                f'<text x="{mx + 3:.1f}" y="{y + 12:.1f}" '
                f'font-family="{_FONT}" font-size="9" '
                f'fill="{_TEXT}">{escape(label)}</text>'
            )
        # Advance to next month.
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)


# -------------------------------------------------------------------
# Timeline
# -------------------------------------------------------------------

def timeline_svg(
    items: list[dict],
    *,
    lanes: list[str] | None = None,
    width: int = 800,
    lane_height: int = 32,
    title: str = "",
) -> str:
    """Timeline SVG showing items as horizontal bars on a date axis.

    Parameters
    ----------
    items : list[dict]
        Each dict: ``name`` (str), ``start`` (date), ``end`` (date),
        ``lane`` (str, optional).
    lanes : list[str] | None
        Explicit lane names for multi-lane mode.  When *None*, all items
        share a single lane.
    width, lane_height, title :
        Layout controls.

    Colors: ``_BAR`` for item bars, ``_GRID`` for grid lines.
    """
    valid = [
        it for it in items
        if isinstance(it.get("start"), date) and isinstance(it.get("end"), date)
    ]

    all_dates: list[date] = []
    for it in valid:
        all_dates.append(it["start"])
        all_dates.append(it["end"])

    if not all_dates:
        h = 60
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {width} {h}" width="{width}" height="{h}">',
            f'<rect width="{width}" height="{h}" fill="{_BG}"/>',
        ]
        if title:
            parts.append(
                f'<text x="{width / 2.0:.1f}" y="16" text-anchor="middle" '
                f'font-family="{_FONT}" font-size="13" '
                f'font-weight="bold" fill="{_TEXT}">{escape(title)}</text>'
            )
        parts.append("</svg>")
        return "\n".join(parts)

    d_min = min(all_dates) - timedelta(days=1)
    d_max = max(all_dates) + timedelta(days=1)

    # Determine lanes.
    if lanes is not None:
        lane_names = list(lanes)
    else:
        seen_lanes: set[str] = set()
        for it in valid:
            lane = it.get("lane", "")
            if lane and lane not in seen_lanes:
                seen_lanes.add(lane)
        if seen_lanes:
            lane_names = sorted(seen_lanes)
        else:
            lane_names = [""]

    margin_l = 120
    margin_r = 16
    header_h = 32 + (20 if title else 0)
    body_h = len(lane_names) * lane_height
    height = int(header_h + body_h + 10)
    pw = width - margin_l - margin_r
    x0 = margin_l
    y_header = 20 if title else 0

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
        f'<rect width="{width}" height="{height}" fill="{_BG}"/>',
    ]

    if title:
        parts.append(
            f'<text x="{width / 2.0:.1f}" y="16" text-anchor="middle" '
            f'font-family="{_FONT}" font-size="13" '
            f'font-weight="bold" fill="{_TEXT}">{escape(title)}</text>'
        )

    _gantt_date_axis(parts, d_min, d_max, x0, pw, y_header + 8)

    palette = (
        "#1565c0", "#c62828", "#2e7d32", "#f9a825",
        "#6a1b9a", "#00838f", "#ef6c00", "#4e342e",
    )

    body_y0 = header_h
    lane_idx = {name: i for i, name in enumerate(lane_names)}

    for li, lane_name in enumerate(lane_names):
        row_y = body_y0 + li * lane_height
        parts.append(
            f'<line x1="{x0}" y1="{row_y + lane_height:.1f}" '
            f'x2="{x0 + pw:.1f}" y2="{row_y + lane_height:.1f}" '
            f'stroke="{_GRID}" stroke-width="0.5"/>'
        )
        if lane_name:
            parts.append(
                f'<text x="{x0 - 6:.1f}" y="{row_y + lane_height / 2.0 + 4:.1f}" '
                f'text-anchor="end" font-family="{_FONT}" font-size="10" '
                f'fill="{_TEXT}">{escape(_clamp_text(lane_name, 16))}</text>'
            )

    for ci, it in enumerate(valid):
        lane = it.get("lane", "")
        li = lane_idx.get(lane, 0)
        row_y = body_y0 + li * lane_height

        bx1 = _date_x(it["start"], d_min, d_max, x0, pw)
        bx2 = _date_x(it["end"], d_min, d_max, x0, pw)
        bw = max(bx2 - bx1, 2.0)
        bar_y = row_y + 4
        bar_h = lane_height - 8
        colour = palette[ci % len(palette)]

        parts.append(
            f'<rect x="{bx1:.1f}" y="{bar_y:.1f}" '
            f'width="{bw:.1f}" height="{bar_h:.1f}" rx="3" '
            f'fill="{colour}" fill-opacity="0.8"/>'
        )
        name = it.get("name", "")
        if name and bw > 20:
            parts.append(
                f'<text x="{bx1 + 4:.1f}" y="{bar_y + bar_h / 2.0 + 4:.1f}" '
                f'font-family="{_FONT}" font-size="9" '
                f'fill="white">{escape(_clamp_text(name, 20))}</text>'
            )

    parts.append("</svg>")
    return "\n".join(parts)


# -------------------------------------------------------------------
# Calendar month
# -------------------------------------------------------------------

def calendar_month_svg(
    year: int,
    month: int,
    tasks,
    *,
    width: int = 700,
    cell_size: int = 90,
    title: str = "",
) -> str:
    """Month calendar grid SVG with task due dates and spans.

    Parameters
    ----------
    year, month : int
        The calendar month to render.
    tasks : list[Task]
        Tasks whose ``due`` falls in a day cell are listed; tasks whose
        ``start``--``due`` span covers a day get a subtle background tint.
    width : int
        ViewBox width (columns are ``cell_size`` wide, auto-centered).
    cell_size : int
        Width and height of each day cell.
    title : str
        Overrides the default "Month YYYY" header.

    Colors: ``_BAR`` for span background tint, ``_MILESTONE_FILL`` for
    milestone diamonds.
    """
    cal = calendar.Calendar(firstweekday=0)  # Mon = 0
    weeks = cal.monthdayscalendar(year, month)
    n_weeks = len(weeks)
    cols = 7

    grid_w = cols * cell_size
    header_h = 40 + (20 if title else 0)
    day_label_h = 20
    grid_h = n_weeks * cell_size
    total_h = header_h + day_label_h + grid_h + 10
    total_w = max(width, grid_w + 20)
    gx0 = (total_w - grid_w) / 2.0
    gy0 = header_h + day_label_h

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {total_w} {total_h}" '
        f'width="{total_w}" height="{total_h}">',
        f'<rect width="{total_w}" height="{total_h}" fill="{_BG}"/>',
    ]

    display_title = title or f"{calendar.month_name[month]} {year}"
    parts.append(
        f'<text x="{total_w / 2.0:.1f}" y="{20 if not title else 16:.1f}" '
        f'text-anchor="middle" font-family="{_FONT}" font-size="14" '
        f'font-weight="bold" fill="{_TEXT}">{escape(display_title)}</text>'
    )

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for ci, dn in enumerate(day_names):
        cx = gx0 + ci * cell_size + cell_size / 2.0
        parts.append(
            f'<text x="{cx:.1f}" y="{header_h + 14:.1f}" '
            f'text-anchor="middle" font-family="{_FONT}" font-size="11" '
            f'font-weight="bold" fill="{_TEXT}">{escape(dn)}</text>'
        )

    # Pre-compute task lookups.
    due_by_day: dict[int, list] = {}
    span_days: set[int] = set()
    milestone_days: set[int] = set()
    for t in tasks:
        if t.due is not None and t.due.year == year and t.due.month == month:
            due_by_day.setdefault(t.due.day, []).append(t)
        if t.milestone and t.due is not None and t.due.year == year and t.due.month == month:
            milestone_days.add(t.due.day)
        if t.start is not None and t.due is not None:
            d = t.start
            while d <= t.due:
                if d.year == year and d.month == month:
                    span_days.add(d.day)
                d += timedelta(days=1)

    today = date.today()
    is_current_month = today.year == year and today.month == month

    for wi, week in enumerate(weeks):
        for ci, day in enumerate(week):
            cx = gx0 + ci * cell_size
            cy = gy0 + wi * cell_size

            if day == 0:
                parts.append(
                    f'<rect x="{cx:.1f}" y="{cy:.1f}" '
                    f'width="{cell_size}" height="{cell_size}" '
                    f'fill="#f5f5f5" stroke="{_GRID}" stroke-width="0.5"/>'
                )
                continue

            # Span background tint.
            bg = _BG
            if day in span_days:
                bg = "#e3f2fd"
            # Today highlight.
            if is_current_month and day == today.day:
                bg = "#fff3e0"

            parts.append(
                f'<rect x="{cx:.1f}" y="{cy:.1f}" '
                f'width="{cell_size}" height="{cell_size}" '
                f'fill="{bg}" stroke="{_GRID}" stroke-width="0.5"/>'
            )

            # Day number.
            parts.append(
                f'<text x="{cx + 4:.1f}" y="{cy + 14:.1f}" '
                f'font-family="{_FONT}" font-size="11" '
                f'font-weight="bold" fill="{_TEXT}">{day}</text>'
            )

            # Milestone diamond.
            if day in milestone_days:
                dx = cx + cell_size - 12
                dy = cy + 10
                diamond = (
                    f"M{dx:.1f},{dy - 5:.1f} "
                    f"L{dx + 5:.1f},{dy:.1f} "
                    f"L{dx:.1f},{dy + 5:.1f} "
                    f"L{dx - 5:.1f},{dy:.1f} Z"
                )
                parts.append(
                    f'<path d="{diamond}" fill="{_MILESTONE_FILL}" '
                    f'stroke="{_TEXT}" stroke-width="0.5"/>'
                )

            # Task titles in cell.
            cell_tasks = due_by_day.get(day, [])
            max_show = (cell_size - 20) // 12
            for ti, t in enumerate(cell_tasks[:max_show]):
                ty = cy + 26 + ti * 12
                parts.append(
                    f'<text x="{cx + 4:.1f}" y="{ty:.1f}" '
                    f'font-family="{_FONT}" font-size="9" '
                    f'fill="{_TEXT}">{escape(_clamp_text(t.title, 12))}</text>'
                )
            if len(cell_tasks) > max_show:
                ty = cy + 26 + max_show * 12
                parts.append(
                    f'<text x="{cx + 4:.1f}" y="{ty:.1f}" '
                    f'font-family="{_FONT}" font-size="8" '
                    f'fill="{_TEXT}">+{len(cell_tasks) - max_show} more</text>'
                )

    parts.append("</svg>")
    return "\n".join(parts)
