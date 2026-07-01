"""ADIF import/export — stdlib only, so it lives in core.

ADIF (Amateur Data Interchange Format) is the ham-radio logbook interchange
format. A logbook is text with fields written as ``<FIELDNAME:LENGTH>value`` or
``<FIELDNAME:LENGTH:TYPE>value``, where ``LENGTH`` is the byte length of
``value``. An optional header ends at ``<EOH>``; each QSO record ends at
``<EOR>`` (both case-insensitive). Field names are case-insensitive and stored
uppercase; whitespace between tags is insignificant.
"""

from __future__ import annotations

import re

_TAG_RE = re.compile(rb"<([^:>]+)(?::(\d+))?(?::[^>]*)?>", re.IGNORECASE)


def parse_adif(text: str) -> list[dict]:
    """Parse ADIF ``text`` into one dict per QSO record ``{FIELD_UPPER: value}``.

    Skips everything up to and including ``<EOH>`` if a header is present;
    otherwise parses records from the start. Field lengths are honoured so
    values containing ``<`` or ``>`` survive intact. Records are separated by
    ``<EOR>``.
    """
    # Work in bytes: ADIF LENGTH is the UTF-8 byte length of the value, so a
    # value with multi-byte characters would be mis-sliced by character index.
    data = text.encode("utf-8")
    header_match = re.search(rb"<eoh>", data, re.IGNORECASE)
    pos = header_match.end() if header_match else 0

    records: list[dict] = []
    record: dict[str, str] = {}
    while True:
        match = _TAG_RE.search(data, pos)
        if match is None:
            break
        name = match.group(1).strip().upper().decode("ascii")
        pos = match.end()
        if name == "EOR":
            if record:
                records.append(record)
            record = {}
            continue
        if name == "EOH":
            continue
        length_str = match.group(2)
        if length_str is None:
            # A control tag without a length and not EOR/EOH; nothing to read.
            continue
        length = int(length_str)
        value = data[pos:pos + length].decode("utf-8")
        pos += length
        record[name] = value

    if record:
        records.append(record)
    return records


def to_adif(records: list[dict], *, header: str = "qcell ADIF export") -> str:
    """Emit ``records`` as an ADIF document with a header.

    The header is written as a comment line followed by ``<ADIF_VER:5>3.1.4``,
    ``<PROGRAMID:5>qcell`` and ``<EOH>``. Each record's fields are emitted as
    ``<NAME:LEN>value`` (``LEN`` in UTF-8 bytes) preserving insertion order,
    and each record ends with ``<EOR>`` on its own line.
    """
    lines: list[str] = []
    lines.append(header)
    lines.append("<ADIF_VER:5>3.1.4")
    lines.append("<PROGRAMID:5>qcell")
    lines.append("<EOH>")
    for record in records:
        parts: list[str] = []
        for name, value in record.items():
            value = "" if value is None else str(value)
            length = len(value.encode("utf-8"))
            parts.append(f"<{name.upper()}:{length}>{value}")
        parts.append("<EOR>")
        lines.append("".join(parts))
    return "\n".join(lines) + "\n"


def records_to_grid(
    records: list[dict], fields: list[str] | None = None
) -> tuple[list[str], list[list[str]]]:
    """Return ``(headers, rows)`` tabulating ``records``.

    ``headers`` is ``fields`` if given, else the union of all field names in
    first-seen order. One row per record; missing fields become ``""``.
    """
    if fields is None:
        headers: list[str] = []
        seen: set[str] = set()
        for record in records:
            for name in record:
                if name not in seen:
                    seen.add(name)
                    headers.append(name)
    else:
        headers = list(fields)

    rows = [[record.get(name, "") for name in headers] for record in records]
    return headers, rows


def grid_to_records(headers: list[str], rows: list[list[str]]) -> list[dict]:
    """Inverse of :func:`records_to_grid`; empty cells are skipped."""
    records: list[dict] = []
    for row in rows:
        record: dict[str, str] = {}
        for name, value in zip(headers, row):
            if value != "":
                record[name] = value
        records.append(record)
    return records


def load_adif(path):
    """Read an ADIF file into a :class:`~qcell.core.sheet.Sheet` named "Log"
    (header row = field names, one row per QSO)."""
    from pathlib import Path

    from ..sheet import Sheet

    records = parse_adif(Path(path).read_text(encoding="utf-8", errors="replace"))
    headers, rows = records_to_grid(records)
    sheet = Sheet("Log")
    for c, name in enumerate(headers):
        sheet.set_cell(0, c, name)
    for r, row in enumerate(rows, start=1):
        for c, value in enumerate(row):
            if value:
                sheet.set_cell(r, c, value)
    return sheet


def save_adif(sheet, path) -> None:
    """Write a sheet (header row + rows) to an ADIF file."""
    from pathlib import Path

    nr, nc = sheet.used_bounds()
    headers = [str(sheet.get_value(0, c) or "") for c in range(nc)]
    rows = [[str(sheet.get_value(r, c) or "") for c in range(nc)]
            for r in range(1, nr)]
    Path(path).write_text(to_adif(grid_to_records(headers, rows)), encoding="utf-8")


__all__ = ["parse_adif", "to_adif", "records_to_grid", "grid_to_records",
           "load_adif", "save_adif"]
