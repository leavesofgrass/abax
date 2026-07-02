"""Streaming / chunked CSV import with type inference — stdlib only.

Large CSV files shouldn't force reading everything into memory at once. This
module offers a fast *preview* (delimiter + header detection, a sample of rows,
and per-column inferred types via :mod:`abax.core.typeinfer`) plus *streaming*
iteration that yields fixed-size chunks of rows using the standard-library
``csv`` reader — the whole file is never materialised.

Public API::

    profile = sniff_csv(path)                  # delimiter/header/types/preview
    for chunk in iter_chunks(path, 1000):      # lists of rows, header skipped
        ...
    wb = load_csv_streaming(path, max_rows=10000, coerce_types=True)

Only the standard library is used (``csv``, ``io``, ``os``), so this lives in
``core`` alongside the other importers.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

from ..sheet import Sheet
from ..typeinfer import coerce, infer_column_type

# Files below this size are counted exactly; larger ones are estimated from the
# average physical line length versus the on-disk byte size.
_EXACT_COUNT_LIMIT = 5 * 1024 * 1024  # 5 MB


class CsvStreamError(Exception):
    """Raised when a CSV file cannot be read, is empty, or has no usable rows."""


@dataclass
class CsvProfile:
    """A lightweight preview of a CSV file, produced by :func:`sniff_csv`."""

    delimiter: str
    has_header: bool
    columns: list[str]            # header names (or generated "Column 1"… )
    types: list[str]              # inferred per-column type from a sample
    sample_rows: list[list[str]] = field(default_factory=list)  # first N data rows
    approx_rows: int = 0          # estimated total data rows (exact if small)


def _sniff_delimiter(sample: str) -> str:
    """Guess the field delimiter, falling back to a comma."""
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        return dialect.delimiter
    except csv.Error:
        return ","


def _detect_header(sample: str, delimiter: str, rows: list[list[str]]) -> bool:
    """Decide whether the first row is a header.

    First tries ``csv.Sniffer.has_header``; if that is inconclusive, falls back
    to a simple heuristic: the first row is all-text while some later row has a
    cell that looks numeric.
    """
    try:
        return csv.Sniffer().has_header(sample)
    except csv.Error:
        pass
    if len(rows) < 2:
        return False
    first = rows[0]
    if not first or any(infer_column_type([cell]) != "text" for cell in first if cell != ""):
        return False
    for row in rows[1:]:
        for cell in row:
            if infer_column_type([cell]) in ("int", "float"):
                return True
    return False


def _generated_columns(n: int) -> list[str]:
    """``["Column 1", "Column 2", …]`` for a headerless file."""
    return [f"Column {i + 1}" for i in range(n)]


def _estimate_rows(path: Path, data_row_count: int, sampled_bytes: int) -> int:
    """Estimate the total number of *data* rows in ``path``.

    For files under :data:`_EXACT_COUNT_LIMIT` an exact count is returned.
    Otherwise the count is extrapolated from the average bytes-per-data-row seen
    in the sampled prefix versus the file's total size.
    """
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    if size <= _EXACT_COUNT_LIMIT:
        return data_row_count
    if data_row_count <= 0 or sampled_bytes <= 0:
        return data_row_count
    avg = sampled_bytes / data_row_count
    return max(data_row_count, int(size / avg))


def sniff_csv(path: str | Path, sample_size: int = 200) -> CsvProfile:
    """Profile a CSV file: delimiter, header, column types, preview, row estimate.

    Reads at most ``sample_size`` data rows. The delimiter is sniffed (falling
    back to a comma), a header is detected via :class:`csv.Sniffer` or an
    all-text-first-row heuristic, per-column types come from
    :mod:`abax.core.typeinfer`, and the total data-row count is exact for small
    files (under 5 MB) or estimated from the average line length otherwise.

    Raises :class:`CsvStreamError` if the file is missing or empty.
    """
    path = Path(path)
    try:
        # NB: Path.open(newline=...) works on all supported Pythons; the
        # `newline=` kwarg on Path.read_text() only exists on 3.13+.
        with path.open(newline="", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise CsvStreamError(f"cannot read CSV file: {path}") from exc
    if not text.strip():
        raise CsvStreamError(f"empty CSV file: {path}")

    delimiter = _sniff_delimiter(text[:8192])

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    all_rows = list(reader)
    if not all_rows:
        raise CsvStreamError(f"no rows in CSV file: {path}")

    has_header = _detect_header(text[:8192], delimiter, all_rows)

    if has_header:
        header = list(all_rows[0])
        data_rows = all_rows[1:]
    else:
        header = []
        data_rows = all_rows

    n_cols = max((len(r) for r in all_rows), default=0)
    if has_header and len(header) < n_cols:
        header = header + _generated_columns(n_cols)[len(header):]
    columns = header if has_header else _generated_columns(n_cols)

    sample = data_rows[:sample_size]
    types: list[str] = []
    for c in range(n_cols):
        column = [row[c] for row in sample if c < len(row)]
        types.append(infer_column_type(column))

    sampled_bytes = len(text.encode("utf-8"))
    approx_rows = _estimate_rows(path, len(data_rows), sampled_bytes)

    return CsvProfile(
        delimiter=delimiter,
        has_header=has_header,
        columns=columns,
        types=types,
        sample_rows=sample,
        approx_rows=approx_rows,
    )


def iter_chunks(
    path: str | Path,
    chunk_rows: int = 1000,
    *,
    has_header: bool | None = None,
    delimiter: str | None = None,
):
    """Yield lists of rows from ``path``, ``chunk_rows`` data rows per chunk.

    Each yielded chunk is a ``list[list[str]]``; the final chunk may be shorter.
    The header row is skipped when present. ``has_header`` and ``delimiter``
    default to the values sniffed by :func:`sniff_csv`. Streaming uses the
    stdlib ``csv`` reader, so the whole file is never loaded at once.

    Raises :class:`CsvStreamError` if the file cannot be opened.
    """
    path = Path(path)
    if delimiter is None or has_header is None:
        profile = sniff_csv(path)
        if delimiter is None:
            delimiter = profile.delimiter
        if has_header is None:
            has_header = profile.has_header

    if chunk_rows < 1:
        chunk_rows = 1

    try:
        fh = path.open("r", newline="", encoding="utf-8")
    except OSError as exc:
        raise CsvStreamError(f"cannot open CSV file: {path}") from exc

    with fh:
        reader = csv.reader(fh, delimiter=delimiter)
        chunk: list[list[str]] = []
        first = True
        for row in reader:
            if first:
                first = False
                if has_header:
                    continue
            chunk.append(row)
            if len(chunk) >= chunk_rows:
                yield chunk
                chunk = []
        if chunk:
            yield chunk


def _canonical(value: str, type_name: str) -> str:
    """Canonical text for ``value`` given its column's inferred ``type_name``.

    Coerces via :func:`abax.core.typeinfer.coerce` and renders the result back
    to text (e.g. an ``int`` column turns ``"3.0"`` into ``"3"``). Empty cells
    stay empty; non-canonicalisable values pass through unchanged.
    """
    if value == "":
        return ""
    if type_name == "int":
        # coerce() rejects "3.0" for int (int("3.0") raises); normalise via float.
        try:
            return str(int(float(value)))
        except (TypeError, ValueError):
            return value
    parsed = coerce(value, type_name)
    if parsed is None:
        return ""
    if isinstance(parsed, bool):
        return "TRUE" if parsed else "FALSE"
    return str(parsed)


def load_csv_streaming(
    path: str | Path,
    *,
    max_rows: int | None = None,
    coerce_types: bool = False,
) -> "object":
    """Build a one-sheet :class:`~abax.core.workbook.Workbook` from a CSV file.

    Streams the file in chunks (never loading it whole). With ``max_rows`` set,
    stops after that many *data* rows — useful for previewing huge files. With
    ``coerce_types=True`` each column is normalised to the canonical text of its
    inferred type (see :func:`_canonical`). When the file has a header that row
    becomes the sheet's first row, exactly as in ``csv_io.load_csv``.

    Raises :class:`CsvStreamError` via :func:`sniff_csv` for unreadable/empty
    files.
    """
    from ..workbook import Workbook

    path = Path(path)
    profile = sniff_csv(path)
    sheet = Sheet(path.stem)

    def _items():
        out_row = 0

        def emit(row: list[str]):
            nonlocal out_row
            for c, field_text in enumerate(row):
                if coerce_types and c < len(profile.types):
                    field_text = _canonical(field_text, profile.types[c])
                if field_text != "":
                    yield out_row, c, field_text
            out_row += 1

        if profile.has_header:
            yield from emit(profile.columns)

        data_seen = 0
        done = False
        for chunk in iter_chunks(
            path, has_header=profile.has_header, delimiter=profile.delimiter
        ):
            for row in chunk:
                if max_rows is not None and data_seen >= max_rows:
                    done = True
                    break
                yield from emit(row)
                data_seen += 1
            if done:
                break

    sheet.set_cells_bulk(_items())

    return Workbook.from_sheets([sheet])


__all__ = [
    "CsvStreamError",
    "CsvProfile",
    "sniff_csv",
    "iter_chunks",
    "load_csv_streaming",
]
