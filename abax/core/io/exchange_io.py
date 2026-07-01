"""Generic JSON interchange — the spec's exchange envelope, plus foreign saves.

abax's native ``.json``/``.abax`` is a workbook envelope. But the spec's
"JSON everywhere" principle means other tools write JSON too, each as
``{app, schema_version, written_at, data}`` (§3e). This module
imports any such file by inspecting the payload shape:

* our own workbook envelope        -> loaded losslessly
* qrpn-style ``{stack, registers}`` -> stack + register columns
* list of objects (records)        -> one row per object, keys as headers
* list of lists                    -> rows verbatim
* dict of equal-length lists        -> columns
* dict of scalars                   -> two-column key/value

Pure stdlib → core.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..reference import to_a1
from ..sheet import Sheet
from ..workbook import Workbook


def looks_like_workbook(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    data = obj.get("data", obj)
    return isinstance(data, dict) and "sheets" in data


def to_exchange(workbook: Workbook) -> dict:
    """abax's exchange envelope (same shape other apps can read)."""
    return workbook.to_envelope()


def workbook_from_json(obj: Any) -> Workbook:
    """Build a Workbook from any supported JSON shape."""
    if looks_like_workbook(obj):
        return Workbook.from_envelope(obj)

    app = ""
    payload = obj
    if isinstance(obj, dict) and "data" in obj:
        app = str(obj.get("app", "")).lower()
        payload = obj["data"]

    if "qrpn" in app or _is_qrpn(payload):
        return _wb_from_qrpn(payload)

    sheet = _sheet_from_payload(payload, name="Sheet1")
    return Workbook.from_sheets([sheet])


def load_json(path: str | Path) -> Workbook:
    return workbook_from_json(json.loads(Path(path).read_text(encoding="utf-8")))


# --- shape handlers --------------------------------------------------------


def _row_items(r: int, cells: list[Any]):
    """Yield ``(r, c, raw)`` for the non-empty cells of a row (for set_cells_bulk)."""
    for c, v in enumerate(cells):
        if v is not None and v != "":
            yield r, c, _scalar(v)


def _scalar(v: Any) -> str:
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return repr(v)
    return str(v)


def _sheet_from_payload(payload: Any, name: str) -> Sheet:
    sheet = Sheet(name)
    if isinstance(payload, list):
        sheet.set_cells_bulk(_list_items(payload))
    elif isinstance(payload, dict):
        sheet.set_cells_bulk(_dict_items(payload))
    else:
        sheet.set_cell(0, 0, _scalar(payload))
    return sheet


def _list_items(items: list):
    if items and all(isinstance(x, dict) for x in items):
        headers: list[str] = []
        for x in items:
            for k in x:
                if k not in headers:
                    headers.append(k)
        yield from _row_items(0, headers)
        for r, x in enumerate(items, start=1):
            yield from _row_items(r, [x.get(h, "") for h in headers])
    elif items and all(isinstance(x, (list, tuple)) for x in items):
        for r, row in enumerate(items):
            yield from _row_items(r, list(row))
    else:  # list of scalars -> single column
        for r, v in enumerate(items):
            yield from _row_items(r, [v])


def _dict_items(d: dict):
    values = list(d.values())
    if values and all(isinstance(v, list) for v in values):
        # dict of columns
        headers = list(d.keys())
        yield from _row_items(0, headers)
        height = max(len(v) for v in values)
        for r in range(height):
            yield from _row_items(r + 1, [(v[r] if r < len(v) else "") for v in values])
    else:  # dict of scalars -> key/value
        yield from _row_items(0, ["key", "value"])
        for r, (k, v) in enumerate(d.items(), start=1):
            yield from _row_items(r, [k, v])


# --- qrpn (RPN calculator) saves ------------------------------------------


def _is_qrpn(payload: Any) -> bool:
    return isinstance(payload, dict) and ("stack" in payload or "registers" in payload)


def _wb_from_qrpn(payload: dict) -> Workbook:
    wb = Workbook.__new__(Workbook)
    wb.sheets = []
    wb.active = 0

    stack = payload.get("stack")
    if isinstance(stack, list):
        s = Sheet("stack")
        s.set_cells_bulk(
            [(0, 0, "stack"), *((r, 0, _scalar(v)) for r, v in enumerate(stack, start=1))]
        )
        wb.sheets.append(s)

    regs = payload.get("registers")
    if isinstance(regs, dict) and regs:
        s = Sheet("registers")
        s.set_cells_bulk([
            (0, 0, "register"), (0, 1, "value"),
            *((r, col, val)
              for r, (k, v) in enumerate(regs.items(), start=1)
              for col, val in ((0, str(k)), (1, _scalar(v))))
        ])
        wb.sheets.append(s)
    elif isinstance(regs, list):
        s = Sheet("registers")
        s.set_cells_bulk([
            (0, 0, "register"), (0, 1, "value"),
            *((r + 1, col, val)
              for r, v in enumerate(regs)
              for col, val in ((0, str(r)), (1, _scalar(v))))
        ])
        wb.sheets.append(s)

    wb._add_default_if_empty()
    return wb


__all__ = ["looks_like_workbook", "to_exchange", "workbook_from_json", "load_json", "to_a1"]
