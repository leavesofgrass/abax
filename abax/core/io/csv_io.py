"""CSV import/export — stdlib ``csv`` only, so it lives in core.

Import places each field as raw cell text (a field beginning with ``=`` becomes
a formula). Export writes either computed values (default) or raw text.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from ..reference import to_a1
from ..sheet import Sheet


def load_csv(path: str | Path, name: str | None = None, delimiter: str = ",") -> Sheet:
    path = Path(path)
    sheet = Sheet(name or path.stem)
    with path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh, delimiter=delimiter)
        sheet.set_cells_bulk(
            (r, c, field)
            for r, row in enumerate(reader)
            for c, field in enumerate(row) if field != "")
    return sheet


def loads_csv(text: str, name: str = "Sheet1", delimiter: str = ",") -> Sheet:
    sheet = Sheet(name)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    sheet.set_cells_bulk(
        (r, c, field)
        for r, row in enumerate(reader)
        for c, field in enumerate(row) if field != "")
    return sheet


def save_csv(
    sheet: Sheet,
    path: str | Path,
    *,
    values: bool = True,
    delimiter: str = ",",
) -> None:
    """Write the sheet to CSV.

    ``values=True`` writes computed/displayed values; ``values=False`` writes
    raw cell text (preserving formulas).
    """
    path = Path(path)
    n_rows, n_cols = sheet.used_bounds()
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter=delimiter)
        for r in range(n_rows):
            line = []
            for c in range(n_cols):
                if values:
                    line.append(sheet.display(r, c))
                else:
                    line.append(sheet.get_raw(r, c))
            writer.writerow(line)


def dumps_csv(sheet: Sheet, *, values: bool = True, delimiter: str = ",") -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=delimiter)
    n_rows, n_cols = sheet.used_bounds()
    for r in range(n_rows):
        writer.writerow(
            [sheet.display(r, c) if values else sheet.get_raw(r, c) for c in range(n_cols)]
        )
    return buf.getvalue()


__all__ = ["load_csv", "loads_csv", "save_csv", "dumps_csv", "to_a1"]
