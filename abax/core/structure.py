"""Structural formula-reference adjustment.

When rows or columns are inserted or deleted in a sheet, formulas that point at
the moved region must be rewritten. Unlike copy/paste shifting (see
``translate.shift_formula``), structural edits move **both** relative and
absolute references — inserting a row pushes everything below it down whether or
not the reference is ``$``-anchored. ``$`` markers are preserved on the survivor
but do not stop the shift.

References whose target cell is deleted become ``#REF!``. Range endpoints that
fall inside a deleted block are clamped to the surviving edge; a range wholly
inside the deleted block collapses to ``#REF!``.

References carry an optional ``Sheet!`` qualifier. A reference is only shifted
when its *target* sheet (its qualifier, or the formula's own sheet when bare)
matches the *edited* sheet (case-insensitive, quotes stripped). Pure stdlib → core.
"""

from __future__ import annotations

import re

from .errors import FormulaError
from .reference import col_to_index, index_to_col
from .tokenizer import Token, tokenize
from .translate import _detokenize

REF_ERROR = "#REF!"

# $col? letters $row? digits — the $ groups mark absolute column / row.
_REF_PARTS = re.compile(r"^(\$?)([A-Za-z]+)(\$?)([0-9]+)$")


def shift_coord(coord: int, index: int, delta: int) -> "int | None":
    """Shift a single 0-based axis coordinate for a structural edit.

    ``delta > 0`` inserts ``delta`` lines at ``index`` (everything at
    ``coord >= index`` moves by ``+delta``). ``delta < 0`` deletes ``-delta``
    lines starting at ``index``. Returns the new coordinate, or ``None`` if
    ``coord`` was deleted.
    """
    if delta >= 0:  # insert
        return coord + delta if coord >= index else coord
    count = -delta
    if coord < index:
        return coord
    if coord < index + count:
        return None  # deleted
    return coord - count


def _split_qualifier(value: str) -> tuple[str, str]:
    """Split ``Sheet!A1`` into ``("Sheet!", "A1")`` on the LAST ``!``.

    Returns ``("", value)`` when there is no qualifier.
    """
    if "!" in value:
        sheet, cell = value.rsplit("!", 1)
        return sheet + "!", cell
    return "", value


def _target_sheet(qualifier: str, formula_sheet: str) -> str:
    """Resolve a ref's target sheet name: its qualifier (quotes stripped) if
    present, else ``formula_sheet``."""
    if not qualifier:
        return formula_sheet
    name = qualifier[:-1]  # drop trailing '!'
    if len(name) >= 2 and name[0] == "'" and name[-1] == "'":
        name = name[1:-1].replace("''", "'")
    return name


def _targets_edited(qualifier: str, formula_sheet: str, edited_sheet: str) -> bool:
    return _target_sheet(qualifier, formula_sheet).lower() == edited_sheet.lower()


def _shift_cell(
    col_abs: str, col_s: str, row_abs: str, row_s: str, axis: str, index: int, delta: int
) -> "tuple[str, str, str, str] | None":
    """Shift one axis of a parsed cell. Returns the new ``(col_abs, col, row_abs,
    row)`` text groups, or ``None`` if the targeted coordinate was deleted."""
    col = col_to_index(col_s)
    row = int(row_s) - 1
    if axis == "col":
        new = shift_coord(col, index, delta)
        if new is None:
            return None
        col = new
    else:  # "row"
        new = shift_coord(row, index, delta)
        if new is None:
            return None
        row = new
    return col_abs, index_to_col(col), row_abs, str(row + 1)


def adjust_reference(
    ref: str,
    edited_sheet: str,
    formula_sheet: str,
    axis: str,
    index: int,
    delta: int,
) -> str:
    """Adjust one A1 reference token value for a structural edit.

    The ref is only shifted when its target sheet matches ``edited_sheet``.
    A deleted single ref becomes ``REF_ERROR``. The ``Sheet!`` qualifier and any
    ``$`` markers are preserved.
    """
    qualifier, cell = _split_qualifier(ref)
    if not _targets_edited(qualifier, formula_sheet, edited_sheet):
        return ref
    m = _REF_PARTS.match(cell)
    if not m:
        return ref
    result = _shift_cell(*m.groups(), axis, index, delta)
    if result is None:
        return REF_ERROR
    col_abs, col, row_abs, row = result
    return f"{qualifier}{col_abs}{col}{row_abs}{row}"


def adjust_range(
    rng: str,
    edited_sheet: str,
    formula_sheet: str,
    axis: str,
    index: int,
    delta: int,
) -> str:
    """Adjust an ``A1:C3`` range value for a structural edit.

    On deletion, endpoints inside the deleted block are clamped: a start endpoint
    clamps to the first survivor (post-shift ``index``); an end endpoint clamps to
    the last line before the block (``index - 1`` pre-shift). A range wholly
    inside the deleted block collapses to ``REF_ERROR``. Insert shifts both ends.
    """
    qualifier, body = _split_qualifier(rng)
    if not _targets_edited(qualifier, formula_sheet, edited_sheet):
        return rng
    a, _, b = body.partition(":")
    ma = _REF_PARTS.match(a)
    mb = _REF_PARTS.match(b)
    if not ma or not mb:
        return rng

    if delta >= 0:  # insert — simple shift of both endpoints
        sa = _shift_cell(*ma.groups(), axis, index, delta)
        sb = _shift_cell(*mb.groups(), axis, index, delta)
        # inserts never delete an endpoint
        assert sa is not None and sb is not None
        ca_abs, ca, ra_abs, ra = sa
        cb_abs, cb, rb_abs, rb = sb
        return f"{qualifier}{ca_abs}{ca}{ra_abs}{ra}:{cb_abs}{cb}{rb_abs}{rb}"

    # delete — clamp endpoints that land inside the removed block.
    ca_abs, ca_s, ra_abs, ra_s = ma.groups()
    cb_abs, cb_s, rb_abs, rb_s = mb.groups()

    def axis_coord(col_s: str, row_s: str) -> int:
        return col_to_index(col_s) if axis == "col" else int(row_s) - 1

    start = axis_coord(ca_s, ra_s)
    end = axis_coord(cb_s, rb_s)

    def clamp(coord: int, is_start: bool) -> int:
        new = shift_coord(coord, index, delta)
        if new is not None:
            return new
        # coord was in the deleted block: clamp to surviving edge.
        return index if is_start else index - 1

    new_start = clamp(start, is_start=True)
    new_end = clamp(end, is_start=False)
    if new_start > new_end:
        return REF_ERROR

    def rebuild(col_abs, col_s, row_abs, row_s, coord) -> str:
        if axis == "col":
            return f"{col_abs}{index_to_col(coord)}{row_abs}{row_s}"
        return f"{col_abs}{col_s}{row_abs}{coord + 1}"

    a_out = rebuild(ca_abs, ca_s, ra_abs, ra_s, new_start)
    b_out = rebuild(cb_abs, cb_s, rb_abs, rb_s, new_end)
    return f"{qualifier}{a_out}:{b_out}"


def adjust_formula(
    raw: str,
    edited_sheet: str,
    formula_sheet: str,
    axis: str,
    index: int,
    delta: int,
) -> str:
    """Return ``raw`` with all references adjusted for a structural edit.

    Non-formula text (no leading ``=``) is returned unchanged. ``REF`` tokens go
    through :func:`adjust_reference` and ``RANGE`` tokens through
    :func:`adjust_range`; everything else is left alone. A tokenizer
    ``FormulaError`` returns ``raw`` unchanged.
    """
    if not raw.startswith("="):
        return raw
    try:
        tokens = tokenize(raw[1:])
    except FormulaError:
        return raw
    out: list[Token] = []
    for t in tokens:
        if t.kind == "REF":
            out.append(
                Token(
                    "REF",
                    adjust_reference(
                        t.value, edited_sheet, formula_sheet, axis, index, delta
                    ),
                )
            )
        elif t.kind == "RANGE":
            out.append(
                Token(
                    "RANGE",
                    adjust_range(
                        t.value, edited_sheet, formula_sheet, axis, index, delta
                    ),
                )
            )
        else:
            out.append(t)
    return "=" + _detokenize(out)
