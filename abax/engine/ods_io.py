"""OpenDocument Spreadsheet (.ods) import/export — pure stdlib.

An ``.ods`` file is a ZIP archive whose ``content.xml`` member holds the ODF
spreadsheet XML. We read/write that XML directly with :mod:`zipfile` and
:mod:`xml.etree.ElementTree`, so this adapter needs **no** third-party
dependency (no odfpy/ezodf). It lives in ``engine/`` only because it is an
optional file-format adapter; :func:`available` is always ``True``.

A Workbook/Sheet is built exactly the way :mod:`abax.core.io.csv_io` does it —
``Sheet`` + ``set_cell`` followed by ``Workbook.from_sheets`` — so the data
model stays identical across importers.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from ..core.sheet import Sheet
from ..core.workbook import Workbook

# --- ODF namespaces ---------------------------------------------------------

_OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
_TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
_TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
_MANIFEST = "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"

_NS = {"office": _OFFICE, "table": _TABLE, "text": _TEXT, "manifest": _MANIFEST}

# Register prefixes so ElementTree serializes with readable, valid namespaces.
for _prefix, _uri in _NS.items():
    ET.register_namespace(_prefix, _uri)

_MIMETYPE = "application/vnd.oasis.opendocument.spreadsheet"

# Guard against a pathological repeated-cell/row count blowing up memory.
# Trailing empty repeats are ignored anyway; this just caps interior runs.
_MAX_REPEAT = 1 << 20


class OdsError(Exception):
    """Raised when an ``.ods`` file is missing, not a ZIP, or malformed."""


def _q(uri: str, tag: str) -> str:
    return f"{{{uri}}}{tag}"


def available() -> bool:
    """Always ``True`` — the implementation is pure stdlib."""
    return True


# --- loading ----------------------------------------------------------------


def _cell_text(cell: ET.Element) -> str:
    """A cell's value: ``office:value`` for floats, else concatenated text:p."""
    vtype = cell.get(_q(_OFFICE, "value-type"))
    if vtype == "float":
        val = cell.get(_q(_OFFICE, "value"))
        if val is not None:
            # Normalize "3.0" -> "3" to match how abax stores integers.
            try:
                f = float(val)
                return str(int(f)) if f.is_integer() else val
            except ValueError:
                return val
    # Otherwise gather every <text:p> paragraph in document order.
    paras = []
    for p in cell.iter(_q(_TEXT, "p")):
        paras.append("".join(p.itertext()))
    return "\n".join(paras)


def _int_attr(elem: ET.Element, name: str, default: int = 1) -> int:
    raw = elem.get(name)
    if raw is None:
        return default
    try:
        return max(1, min(int(raw), _MAX_REPEAT))
    except ValueError:
        return default


def load_ods(path: str | Path) -> Workbook:
    """Read the FIRST sheet of an ``.ods`` file into a one-sheet Workbook.

    Honours ``table:number-columns-repeated`` and
    ``table:number-rows-repeated``: a cell or row that declares a repeat count
    is expanded N times, but trailing empty repeated cells/rows are dropped so
    they never inflate the sheet — only cells with content are emitted.
    """
    path = Path(path)
    try:
        with zipfile.ZipFile(path) as zf:
            xml_bytes = zf.read("content.xml")
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise OdsError(f"not a valid .ods file: {path}: {exc}") from exc

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise OdsError(f"malformed content.xml in {path}: {exc}") from exc

    table = root.find(f".//{_q(_TABLE, 'table')}")
    if table is None:
        raise OdsError(f"no table:table element in {path}")

    name = table.get(_q(_TABLE, "name")) or path.stem
    sheet = Sheet(name)

    def _items():
        r = 0
        for row in table.findall(_q(_TABLE, "table-row")):
            row_repeat = _int_attr(row, _q(_TABLE, "number-rows-repeated"))
            cells = row.findall(_q(_TABLE, "table-cell"))

            # Build this row's (col, text) content once; reuse for each repeat.
            row_content: list[tuple[int, str]] = []
            c = 0
            for cell in cells:
                col_repeat = _int_attr(cell, _q(_TABLE, "number-columns-repeated"))
                text = _cell_text(cell)
                if text != "":
                    for k in range(col_repeat):
                        row_content.append((c + k, text))
                c += col_repeat

            if not row_content:
                # Empty row (possibly a huge trailing repeat) — skip without
                # emitting anything, but still advance the row cursor.
                r += row_repeat
                continue

            for _ in range(row_repeat):
                for col, text in row_content:
                    yield r, col, text
                r += 1

    sheet.set_cells_bulk(_items())

    return Workbook.from_sheets([sheet])


# --- saving -----------------------------------------------------------------


def _looks_numeric(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def _build_content(sheet: Sheet) -> bytes:
    doc = ET.Element(_q(_OFFICE, "document-content"))
    doc.set(_q(_OFFICE, "version"), "1.2")
    body = ET.SubElement(doc, _q(_OFFICE, "body"))
    spread = ET.SubElement(body, _q(_OFFICE, "spreadsheet"))
    table = ET.SubElement(spread, _q(_TABLE, "table"))
    table.set(_q(_TABLE, "name"), sheet.name or "Sheet1")

    n_rows, n_cols = sheet.used_bounds()
    for r in range(n_rows):
        row_el = ET.SubElement(table, _q(_TABLE, "table-row"))
        for c in range(n_cols):
            cell_el = ET.SubElement(row_el, _q(_TABLE, "table-cell"))
            text = sheet.display(r, c)
            if text == "":
                continue  # empty <table:table-cell/>
            if _looks_numeric(text):
                cell_el.set(_q(_OFFICE, "value-type"), "float")
                cell_el.set(_q(_OFFICE, "value"), text)
            else:
                cell_el.set(_q(_OFFICE, "value-type"), "string")
            p = ET.SubElement(cell_el, _q(_TEXT, "p"))
            p.text = text

    return ET.tostring(doc, encoding="UTF-8", xml_declaration=True)


def _build_manifest() -> bytes:
    root = ET.Element(_q(_MANIFEST, "manifest"))
    root.set(_q(_MANIFEST, "version"), "1.2")
    for full_path, media in (
        ("/", _MIMETYPE),
        ("content.xml", "text/xml"),
    ):
        entry = ET.SubElement(root, _q(_MANIFEST, "file-entry"))
        entry.set(_q(_MANIFEST, "full-path"), full_path)
        entry.set(_q(_MANIFEST, "media-type"), media)
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True)


def save_ods(workbook: Workbook, path: str | Path) -> None:
    """Write the workbook's active sheet to a valid ``.ods`` ZIP.

    The ``mimetype`` member is written first and STORED (uncompressed) per the
    ODF packaging spec; ``content.xml`` and ``META-INF/manifest.xml`` follow,
    DEFLATED.
    """
    path = Path(path)
    sheet = workbook.sheet
    content = _build_content(sheet)
    manifest = _build_manifest()

    with zipfile.ZipFile(path, "w") as zf:
        # mimetype: first, stored uncompressed, no extra fields.
        zf.writestr(
            zipfile.ZipInfo("mimetype"), _MIMETYPE, compress_type=zipfile.ZIP_STORED
        )
        zf.writestr("content.xml", content, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr(
            "META-INF/manifest.xml", manifest, compress_type=zipfile.ZIP_DEFLATED
        )


__all__ = ["load_ods", "save_ods", "available", "OdsError"]
