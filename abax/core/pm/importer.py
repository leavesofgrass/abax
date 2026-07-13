"""CSV and MS Project XML task import/export.

Pure-stdlib module — no third-party dependencies.
"""

from __future__ import annotations

import csv
import io
import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import Any

from abax.core.pm.taskmodel import Task, detect_columns

__all__ = ["import_csv", "import_mpp_xml", "tasks_to_csv"]

# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

_DATE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # ISO: 2024-03-15 or 2024/03/15
    (re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$"), "YMD"),
    # US: 03/15/2024 or 03-15-2024
    (re.compile(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$"), "MDY"),
    # EU: 15.03.2024
    (re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$"), "DMY"),
    # ISO datetime: 2024-03-15T00:00:00
    (re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})[T ]"), "YMD_DT"),
]


def _parse_date(text: str) -> date | None:
    """Parse a date string in ISO, US, or EU format.  Returns None on failure."""
    text = text.strip()
    if not text:
        return None
    for pat, fmt in _DATE_PATTERNS:
        m = pat.match(text)
        if m:
            g = m.groups()
            try:
                if fmt in ("YMD", "YMD_DT"):
                    return date(int(g[0]), int(g[1]), int(g[2]))
                if fmt == "MDY":
                    return date(int(g[2]), int(g[0]), int(g[1]))
                if fmt == "DMY":
                    return date(int(g[2]), int(g[1]), int(g[0]))
            except ValueError:
                return None
    return None


# ---------------------------------------------------------------------------
# CSV import
# ---------------------------------------------------------------------------

PathOrFile = str | Path | io.TextIOBase | io.StringIO


def _open_text(source: PathOrFile) -> tuple[io.StringIO, bool]:
    """Return a StringIO ready for csv.reader and whether we opened it."""
    if isinstance(source, (str, Path)):
        raw = Path(source).read_bytes()
        # Strip UTF-8 BOM if present
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        text = raw.decode("utf-8")
        return io.StringIO(text), False
    # file-like object — read its content
    content = source.read()
    if isinstance(content, bytes):
        if content.startswith(b"\xef\xbb\xbf"):
            content = content[3:]
        content = content.decode("utf-8")
    return io.StringIO(content), False


def _detect_delimiter(sample: str) -> str:
    """Detect CSV delimiter using csv.Sniffer, default to comma."""
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        return ","


def _parse_float(text: str) -> float | None:
    """Parse a float, returning None on failure."""
    text = text.strip()
    if not text:
        return None
    # Handle percentage strings like "50%"
    if text.endswith("%"):
        try:
            return float(text[:-1])
        except ValueError:
            return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_bool(text: str) -> bool:
    """Parse a boolean string."""
    return text.strip().lower() in ("true", "yes", "1", "x")


def import_csv(source: PathOrFile) -> list[Task]:
    """Import tasks from a CSV file or file-like object.

    The first row must be column headers.  Headers are mapped to Task fields
    using :func:`detect_columns` (alias-aware).  Unrecognised columns go into
    ``Task.extra``.
    """
    sio, _ = _open_text(source)
    content = sio.getvalue()

    if not content.strip():
        return []

    delimiter = _detect_delimiter(content)
    sio.seek(0)
    reader = csv.reader(sio, delimiter=delimiter)

    try:
        raw_headers = next(reader)
    except StopIteration:
        return []

    headers = [h.strip() for h in raw_headers]
    col_map = detect_columns(headers)

    # Build reverse map: column index -> field name (for mapped cols)
    idx_to_field: dict[int, str] = {v: k for k, v in col_map.items()}
    # Extra columns: indices not in idx_to_field
    extra_cols: dict[int, str] = {}
    for i, h in enumerate(headers):
        if i not in idx_to_field:
            extra_cols[i] = h

    tasks: list[Task] = []
    for row_idx, row in enumerate(reader, start=1):
        # Skip empty rows
        if not any(cell.strip() for cell in row):
            continue

        kwargs: dict[str, Any] = {"row": row_idx}
        extra: dict[str, Any] = {}

        for i, cell in enumerate(row):
            cell = cell.strip()
            if i in idx_to_field:
                fld = idx_to_field[i]
                if fld in ("start", "due"):
                    kwargs[fld] = _parse_date(cell)
                elif fld == "percent_done":
                    kwargs[fld] = _parse_float(cell) or 0.0
                elif fld == "milestone":
                    kwargs[fld] = _parse_bool(cell)
                elif fld in ("effort", "cost"):
                    kwargs[fld] = _parse_float(cell)
                elif fld == "depends":
                    kwargs[fld] = [d.strip() for d in cell.split(",") if d.strip()] if cell else []
                elif fld == "tags":
                    kwargs[fld] = [t.strip() for t in cell.split(";") if t.strip()] if cell else []
                else:
                    kwargs[fld] = cell
            elif i in extra_cols:
                if cell:
                    extra[extra_cols[i]] = cell

        if extra:
            kwargs["extra"] = extra

        tasks.append(Task(**kwargs))

    return tasks


# ---------------------------------------------------------------------------
# MS Project XML import
# ---------------------------------------------------------------------------

_MSP_NS = "http://schemas.microsoft.com/project"


def _ns(tag: str) -> str:
    """Return a namespace-qualified tag name for MS Project XML."""
    return f"{{{_MSP_NS}}}{tag}"


def _get_text(elem: ET.Element, tag: str) -> str:
    """Get text content of a child element, or empty string."""
    child = elem.find(_ns(tag))
    if child is not None and child.text:
        return child.text.strip()
    return ""


def _parse_iso_date(text: str) -> date | None:
    """Parse ISO datetime from MS Project (e.g. '2024-03-15T08:00:00')."""
    if not text:
        return None
    return _parse_date(text)


def _parse_duration_hours(text: str) -> float | None:
    """Parse an ISO 8601 duration (PT8H0M0S or P5D) to hours.

    MS Project uses formats like PT8H0M0S, PT16H0M0S, P5DT0H0M0S, etc.
    """
    if not text:
        return None
    m = re.match(
        r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$",
        text,
    )
    if not m:
        return None
    days = int(m.group(1) or 0)
    hours = int(m.group(2) or 0)
    minutes = int(m.group(3) or 0)
    seconds = int(m.group(4) or 0)
    return days * 8.0 + hours + minutes / 60.0 + seconds / 3600.0


def _status_from_pct(pct: float) -> str:
    """Map percent-complete to a status string."""
    if pct >= 100.0:
        return "Done"
    if pct > 0.0:
        return "In Progress"
    return "To Do"


def import_mpp_xml(source: PathOrFile) -> list[Task]:
    """Import tasks from an MS Project XML file.

    Parses the standard ``xmlns="http://schemas.microsoft.com/project"``
    format exported by Microsoft Project.

    Raises :class:`ValueError` for files that are not valid MS Project XML.
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        raw = path.read_bytes()
        content = raw.decode("utf-8")
    else:
        content = source.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8")

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f"Not valid XML: {exc}") from exc

    # Verify this is an MS Project file
    root_tag = root.tag
    if root_tag != _ns("Project") and root_tag != "Project":
        raise ValueError(
            f"Not an MS Project XML file: root element is <{root_tag}>, "
            f"expected <Project> with namespace {_MSP_NS}"
        )

    tasks_elem = root.find(_ns("Tasks"))
    if tasks_elem is None:
        # Try without namespace
        tasks_elem = root.find("Tasks")
    if tasks_elem is None:
        return []

    ns_task = _ns("Task")
    tasks: list[Task] = []
    row = 0

    for task_elem in tasks_elem:
        if task_elem.tag not in (ns_task, "Task"):
            continue

        name = _get_text(task_elem, "Name")
        uid = _get_text(task_elem, "UID")
        start_text = _get_text(task_elem, "Start")
        finish_text = _get_text(task_elem, "Finish")
        pct_text = _get_text(task_elem, "PercentComplete")
        duration_text = _get_text(task_elem, "Duration")
        milestone_text = _get_text(task_elem, "Milestone")

        # Skip the project summary task (UID=0 with no name) if present
        if uid == "0" and not name:
            continue

        row += 1
        pct = float(pct_text) if pct_text else 0.0

        # Parse predecessors
        depends: list[str] = []
        for pred_elem in task_elem.findall(_ns("PredecessorLink")):
            pred_uid = _get_text(pred_elem, "PredecessorUID")
            if pred_uid:
                depends.append(pred_uid)
        # Also try without namespace
        if not depends:
            for pred_elem in task_elem.findall("PredecessorLink"):
                pred_uid_elem = pred_elem.find("PredecessorUID")
                if pred_uid_elem is not None and pred_uid_elem.text:
                    depends.append(pred_uid_elem.text.strip())

        tasks.append(Task(
            row=row,
            title=name,
            id=uid,
            start=_parse_iso_date(start_text),
            due=_parse_iso_date(finish_text),
            percent_done=pct,
            status=_status_from_pct(pct),
            effort=_parse_duration_hours(duration_text),
            depends=depends,
            milestone=milestone_text.lower() in ("1", "true") if milestone_text else False,
        ))

    return tasks


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

_DEFAULT_FIELDS = [
    "id", "title", "status", "start", "due", "assignee",
    "priority", "percent_done", "effort", "cost", "tags",
]

# Map internal field names to CSV-header strings that detect_columns can
# round-trip.  Fields whose name already appears as an alias key (lowercase)
# in taskmodel._ALIASES are left as-is.
_HEADER_DISPLAY: dict[str, str] = {
    "percent_done": "% Done",
}


def tasks_to_csv(
    tasks: list[Task],
    dest: PathOrFile,
    fields: list[str] | None = None,
) -> None:
    """Write *tasks* to a CSV file or file-like object.

    *fields* selects and orders columns; defaults to :data:`_DEFAULT_FIELDS`.
    Dates are serialised as ISO strings, tags as semicolon-joined.
    """
    fields = fields or list(_DEFAULT_FIELDS)
    headers = [_HEADER_DISPLAY.get(f, f) for f in fields]

    if isinstance(dest, (str, Path)):
        fh = open(dest, "w", newline="", encoding="utf-8")  # noqa: SIM115
        should_close = True
    else:
        fh = dest
        should_close = False

    try:
        writer = csv.writer(fh)
        writer.writerow(headers)

        for task in tasks:
            row: list[str] = []
            for f in fields:
                val = getattr(task, f, None)
                if val is None:
                    row.append("")
                elif isinstance(val, date):
                    row.append(val.isoformat())
                elif isinstance(val, list):
                    row.append(";".join(str(v) for v in val))
                elif isinstance(val, bool):
                    row.append("true" if val else "false")
                elif isinstance(val, float):
                    # Format cleanly: no trailing zeros for whole numbers
                    row.append(str(int(val)) if val == int(val) else str(val))
                else:
                    row.append(str(val))
            writer.writerow(row)
    finally:
        if should_close:
            fh.close()
