"""Task-sheet convention — parse ordinary sheet rows into typed Task objects.

A *task sheet* is any sheet (or Table region) whose first row contains
recognizable column headers.  Headers are matched case-insensitively with
aliases so users can label columns however they like (``Due``, ``Deadline``,
``Finish`` all map to the due-date field).

This module is pure stdlib.  Views and engines import it to read/write task
data without knowing about the GUI or TUI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable

__all__ = [
    "Task",
    "parse_tasks",
    "write_task",
    "STATUS_ORDER",
    "detect_columns",
]

# ---------------------------------------------------------------------------
# Header aliases — case-insensitive, first match wins
# ---------------------------------------------------------------------------

_ALIASES: dict[str, tuple[str, ...]] = {
    "title":        ("title", "task", "name", "summary", "subject"),
    "status":       ("status", "state", "stage"),
    "start":        ("start", "begin"),
    "due":          ("due", "end", "finish", "deadline"),
    "assignee":     ("assignee", "owner", "who", "assigned", "resource"),
    "priority":     ("priority", "prio", "pri"),
    "percent_done": ("%done", "progress", "percent", "complete", "%complete",
                     "pct", "pctdone", "percentdone", "percent_done"),
    "depends":      ("depends", "dependson", "blocked by", "predecessors",
                     "blockedby", "deps"),
    "milestone":    ("milestone", "ms"),
    "effort":       ("effort", "hours", "estimate", "duration", "work"),
    "cost":         ("cost", "budget"),
    "tags":         ("tags", "labels", "tag", "label", "category"),
    "id":           ("id", "key", "taskid", "task_id", "uid"),
}

_ALIAS_LOOKUP: dict[str, str] = {}
for _field, _names in _ALIASES.items():
    for _name in _names:
        _ALIAS_LOOKUP[_name] = _field


def _normalize_header(text: str) -> str:
    """Strip whitespace, lower-case, remove all spaces for matching."""
    return re.sub(r"\s+", "", str(text).strip().lower())


def detect_columns(
    headers: list[str],
) -> dict[str, int]:
    """Map recognised field names to column indices (0-based within *headers*).

    Unrecognised headers are silently skipped — they end up in ``Task.extra``.
    """
    mapping: dict[str, int] = {}
    for i, raw in enumerate(headers):
        key = _normalize_header(raw)
        # Try exact alias match first.
        field_name = _ALIAS_LOOKUP.get(key)
        # Fall back to prefix match (e.g. "% Done (approx)" → "%done").
        if field_name is None:
            for alias, fname in _ALIAS_LOOKUP.items():
                if key.startswith(alias):
                    field_name = fname
                    break
        if field_name is not None and field_name not in mapping:
            mapping[field_name] = i
    return mapping


# ---------------------------------------------------------------------------
# Date parsing — ISO first, then spreadsheet-ish formats
# ---------------------------------------------------------------------------

_DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%d-%b-%Y",
    "%d-%b-%y",
    "%d %b %Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d/%m/%Y",
    "%Y.%m.%d",
    "%d.%m.%Y",
)


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    s = str(value).strip()
    if not s:
        return None
    # ISO fast path.
    try:
        return date.fromisoformat(s[:10] if len(s) >= 10 else s)
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except (TypeError, ValueError):
            continue
    return None


def _parse_float(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        s = value.strip().rstrip("%")
        try:
            return float(s)
        except (TypeError, ValueError):
            return None
    return None


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1", "x", "y")
    return False


def _parse_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        parts = re.split(r"[,;|]+", value)
        return [p.strip() for p in parts if p.strip()]
    return []


# ---------------------------------------------------------------------------
# Task dataclass
# ---------------------------------------------------------------------------


@dataclass
class Task:
    """One task parsed from a sheet row."""

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

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"T{self.row}"


# ---------------------------------------------------------------------------
# Parse tasks from a sheet
# ---------------------------------------------------------------------------

def _read_row(
    sheet: Any,
    row: int,
    first_col: int,
    ncols: int,
) -> list[Any]:
    """Read *ncols* values starting at *(row, first_col)* from a Sheet."""
    return [sheet.get_value(row, first_col + c) for c in range(ncols)]


def parse_tasks(
    sheet: Any,
    *,
    header_row: int = 0,
    first_col: int = 0,
    last_col: int | None = None,
    first_data_row: int | None = None,
    last_data_row: int | None = None,
) -> list[Task]:
    """Parse task rows from *sheet* into :class:`Task` objects.

    Parameters match the geometry of a :class:`~abax.core.tables.Table` so a
    caller can pass ``table.header_row``, ``table.first_col``, etc. directly.

    Tolerant: missing columns yield defaults; bad dates yield ``None``; nothing
    raises on user data.
    """
    if last_col is None:
        nrows, ncols = sheet.used_bounds()
        last_col = ncols - 1
    width = last_col - first_col + 1
    if width <= 0:
        return []

    # Read headers and detect columns.
    headers = [
        str(v) if v is not None else ""
        for v in _read_row(sheet, header_row, first_col, width)
    ]
    col_map = detect_columns(headers)
    if "title" not in col_map:
        return []

    if first_data_row is None:
        first_data_row = header_row + 1
    if last_data_row is None:
        nrows, _ = sheet.used_bounds()
        last_data_row = nrows - 1

    # Build the reverse map: column index → header label (for extra fields).
    recognised_cols = set(col_map.values())
    extra_headers: dict[int, str] = {}
    for i, h in enumerate(headers):
        if i not in recognised_cols and h.strip():
            extra_headers[i] = h.strip()

    tasks: list[Task] = []
    for r in range(first_data_row, last_data_row + 1):
        vals = _read_row(sheet, r, first_col, width)

        def _val(field_name: str) -> Any:
            idx = col_map.get(field_name)
            if idx is None:
                return None
            return vals[idx]

        title_raw = _val("title")
        if title_raw is None or str(title_raw).strip() == "":
            continue

        extra: dict[str, Any] = {}
        for ci, label in extra_headers.items():
            v = vals[ci]
            if v is not None and str(v).strip():
                extra[label] = v

        pct = _parse_float(_val("percent_done"))

        task = Task(
            row=r,
            title=str(title_raw).strip(),
            status=str(_val("status") or "").strip(),
            start=_parse_date(_val("start")),
            due=_parse_date(_val("due")),
            assignee=str(_val("assignee") or "").strip(),
            priority=str(_val("priority") or "").strip(),
            percent_done=max(0.0, min(100.0, pct)) if pct is not None else 0.0,
            depends=_parse_list(_val("depends")),
            milestone=_parse_bool(_val("milestone")),
            effort=_parse_float(_val("effort")),
            cost=_parse_float(_val("cost")),
            tags=_parse_list(_val("tags")),
            id=str(_val("id") or "").strip() or f"T{r}",
            extra=extra,
        )
        tasks.append(task)

    return tasks


# ---------------------------------------------------------------------------
# Write-back — single-cell mutation through the caller's commit path
# ---------------------------------------------------------------------------

# Field → serializer for write-back.
_SERIALIZERS: dict[str, Callable[[Any], Any]] = {
    "title":        str,
    "status":       str,
    "start":        lambda v: v.isoformat() if isinstance(v, date) else str(v),
    "due":          lambda v: v.isoformat() if isinstance(v, date) else str(v),
    "assignee":     str,
    "priority":     str,
    "percent_done": lambda v: round(float(v), 1),
    "depends":      lambda v: ", ".join(v) if isinstance(v, list) else str(v),
    "milestone":    lambda v: "TRUE" if v else "FALSE",
    "effort":       lambda v: round(float(v), 2) if v is not None else "",
    "cost":         lambda v: round(float(v), 2) if v is not None else "",
    "tags":         lambda v: ", ".join(v) if isinstance(v, list) else str(v),
    "id":           str,
}


def write_task(
    sheet: Any,
    task: Task,
    field_name: str,
    value: Any,
    *,
    col_map: dict[str, int],
    first_col: int = 0,
    on_set: Callable[[Any, int, int, Any], None] | None = None,
) -> None:
    """Write ONE cell — the intersection of *task.row* and *field_name*'s column.

    *on_set* is called as ``on_set(sheet, row, col, cell_value)`` so the GUI's
    undo/recording hooks fire.  Views never write cells any other way.

    If *on_set* is ``None``, the sheet's ``set_raw`` is used directly (useful
    for headless / test scenarios).
    """
    col_idx = col_map.get(field_name)
    if col_idx is None:
        raise KeyError(f"no column mapped for field {field_name!r}")

    serializer = _SERIALIZERS.get(field_name, str)
    cell_value = serializer(value)
    abs_col = first_col + col_idx

    if on_set is not None:
        on_set(sheet, task.row, abs_col, cell_value)
    else:
        sheet.set_cell(task.row, abs_col, str(cell_value))


# ---------------------------------------------------------------------------
# STATUS_ORDER — distinct statuses in first-appearance order
# ---------------------------------------------------------------------------

def STATUS_ORDER(
    tasks: list[Task],
    *,
    override: list[str] | None = None,
) -> list[str]:
    """Return the distinct statuses in first-appearance order.

    If *override* is given, those statuses come first (in the given order),
    followed by any remaining statuses from the tasks that weren't listed.
    """
    if override:
        seen = set()
        order: list[str] = []
        for s in override:
            if s not in seen:
                order.append(s)
                seen.add(s)
        for t in tasks:
            if t.status and t.status not in seen:
                order.append(t.status)
                seen.add(t.status)
        return order

    seen: set[str] = set()
    order: list[str] = []
    for t in tasks:
        if t.status and t.status not in seen:
            order.append(t.status)
            seen.add(t.status)
    return order
