"""Jupyter / IPython notebook (.ipynb) import/export — nbformat 4, no deps.

Export: each sheet becomes a markdown cell (heading + GFM table) plus a code
cell that rebuilds it as a pandas DataFrame. Import: every GFM table found in
markdown cells becomes a sheet (named from the nearest heading). Pure stdlib.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .markdown_io import from_markdown, to_markdown
from ..sheet import Sheet
from ..workbook import Workbook

_IDENT = re.compile(r"\W+")
_HEADING = re.compile(r"^#{1,6}\s+(.*)$")


def _ident(name: str) -> str:
    out = _IDENT.sub("_", name.strip())
    if not out or out[0].isdigit():
        out = "df_" + out
    return out


def to_notebook(workbook: Workbook) -> dict:
    cells: list[dict] = []
    for sheet in workbook.sheets:
        cells.append(_md_cell(f"## {sheet.name}\n\n" + to_markdown(sheet)))
        cells.append(_code_cell(_dataframe_source(sheet)))
    # nbformat 4.5 (nbformat_minor: 5) requires each cell to carry a unique id.
    # Deterministic, index-based ids keep the export reproducible.
    for i, cell in enumerate(cells):
        cell["id"] = f"qcell-{i}"
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
            "qcell": {"app": "qcell", "schema_version": 1},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _md_cell(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": _lines(text)}


def _code_cell(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": _lines(text),
    }


def _lines(text: str) -> list[str]:
    parts = text.split("\n")
    # nbformat stores each line with its trailing newline except the last.
    return [p + "\n" for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def _dataframe_source(sheet: Sheet) -> str:
    n_rows, n_cols = sheet.used_bounds()
    var = _ident(sheet.name)
    if n_rows == 0:
        return f"import pandas as pd\n{var} = pd.DataFrame()\n{var}"
    headers = [sheet.display(0, c) or f"col{c}" for c in range(n_cols)]
    data_rows = [
        [_py_literal(sheet.get_value(r, c)) for c in range(n_cols)] for r in range(1, n_rows)
    ]
    rows_src = ",\n        ".join("[" + ", ".join(row) + "]" for row in data_rows)
    return (
        "import pandas as pd\n"
        f"{var} = pd.DataFrame(\n"
        f"    [\n        {rows_src}\n    ],\n"
        f"    columns={headers!r},\n"
        ")\n"
        f"{var}"
    )


def _py_literal(value) -> str:
    from ..errors import CellError

    if value is None:
        return "None"
    if isinstance(value, CellError):
        return repr(str(value))
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return repr(value)
    return repr(str(value))


def from_notebook(nb: dict, default_name: str = "Sheet") -> Workbook:
    wb = Workbook.__new__(Workbook)
    wb.sheets = []
    wb.active = 0
    last_heading: str | None = None
    used: set[str] = set()
    for cell in nb.get("cells", []):
        src = _source_text(cell)
        if cell.get("cell_type") == "markdown":
            heading = _last_heading(src)
            if heading:
                last_heading = heading
            if "|" in src and "---" in src:
                name = _unique(last_heading or f"{default_name}{len(wb.sheets) + 1}", used)
                wb.sheets.append(from_markdown(src, name))
                last_heading = None
    wb._add_default_if_empty()
    return wb


def _source_text(cell: dict) -> str:
    src = cell.get("source", "")
    return "".join(src) if isinstance(src, list) else src


def _last_heading(text: str) -> str | None:
    found = None
    for line in text.splitlines():
        m = _HEADING.match(line.strip())
        if m:
            found = m.group(1).strip()
    return found


def _unique(name: str, used: set) -> str:
    base, n = name, 2
    while name in used:
        name = f"{base}_{n}"
        n += 1
    used.add(name)
    return name


def save_notebook(workbook: Workbook, path: str | Path) -> None:
    Path(path).write_text(json.dumps(to_notebook(workbook), indent=1), encoding="utf-8")


def load_notebook(path: str | Path) -> Workbook:
    return from_notebook(json.loads(Path(path).read_text(encoding="utf-8")))
