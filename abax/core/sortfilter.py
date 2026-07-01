"""Multi-column sort + filter engine over a block of raw cell strings.

Operates on ``rows: list[list[str]]`` — a rectangular block of RAW cell text
(the GUI extracts/writes these). Sorting is type-aware and stable: within a
column, blanks sort LAST, then numbers (by numeric value), then text
(case-insensitive). ``descending`` reverses the number/text ordering of a
column but blanks always remain last. Filtering applies predicates with a
logical AND. Pure stdlib → core (no Qt, no third-party).

The number-before-text key convention matches ``core/fill.py:sort_region``;
this module extends it to multiple keys and a blanks-last sentinel.
"""

from __future__ import annotations

from functools import cmp_to_key


class SortFilterError(Exception):
    """Raised on an out-of-range column index, empty keys, or unknown op."""


# --- type-aware cell key ---------------------------------------------------


def _cell_key(s: str) -> tuple[int, float, str]:
    """Comparable sort key for a raw cell string.

    Returns a 3-tuple ``(bucket, number, text)`` where ``bucket`` is 0 for
    numbers, 1 for text, 2 for blank — so blanks always sort last and numbers
    before text. Only the relevant slot carries a value; the others are inert.
    """
    if s == "":
        return (2, 0.0, "")
    try:
        return (0, float(s), "")
    except (TypeError, ValueError):
        return (1, 0.0, s.lower())


def _cmp_keys(a: str, b: str) -> int:
    """Three-way comparison of two raw cells using ``_cell_key`` ordering."""
    ka, kb = _cell_key(a), _cell_key(b)
    return (ka > kb) - (ka < kb)


# --- sorting ---------------------------------------------------------------


def _check_cols(rows: list[list[str]], cols: list[int]) -> None:
    for row in rows:
        for c in cols:
            if not (0 <= c < len(row)):
                raise SortFilterError(f"column index {c} out of range")


def sort_order(rows: list[list[str]], keys: list[tuple[int, bool]]) -> list[int]:
    """Return the permutation of row indices that sorts ``rows`` by ``keys``.

    ``keys`` is a list of ``(col_index, descending)``; the first key is
    primary. The sort is STABLE — rows equal on all keys keep their original
    order. Blanks sort last in a column regardless of ``descending`` (only the
    number/text ordering flips). Raises ``SortFilterError`` if ``keys`` is
    empty or a ``col_index`` is out of range for any row.
    """
    if not keys:
        raise SortFilterError("keys must be non-empty")
    _check_cols(rows, [c for c, _ in keys])

    def compare(i: int, j: int) -> int:
        for col, descending in keys:
            ka = _cell_key(rows[i][col])
            kb = _cell_key(rows[j][col])
            if ka == kb:
                continue
            # Blanks (bucket 2) always sort last, never flipped by descending.
            a_blank = ka[0] == 2
            b_blank = kb[0] == 2
            if a_blank or b_blank:
                # Non-blank precedes blank; if both blank they were equal above.
                return -1 if b_blank else 1
            c = (ka > kb) - (ka < kb)
            return -c if descending else c
        return (i > j) - (i < j)  # stable tie-break by original index

    return sorted(range(len(rows)), key=cmp_to_key(compare))


def sort_rows(rows: list[list[str]], keys: list[tuple[int, bool]]) -> list[list[str]]:
    """Return a new list of rows reordered by :func:`sort_order`."""
    order = sort_order(rows, keys)
    return [rows[i] for i in order]


# --- matching / filtering --------------------------------------------------


def _as_number(s: str) -> float | None:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def match(value: str, op: str, operand: str = "") -> bool:
    """Test ``value`` against ``operand`` under comparison ``op``.

    Supported ops: ``eq ne contains ncontains startswith endswith gt lt ge le
    between blank nonblank``. Comparisons are numeric when BOTH ``value`` and
    ``operand`` parse as numbers, otherwise case-insensitive string. ``between``
    takes ``operand`` ``"lo|hi"`` (inclusive). ``blank``/``nonblank`` ignore
    ``operand``. An unknown op raises ``SortFilterError``.
    """
    if op == "blank":
        return value == ""
    if op == "nonblank":
        return value != ""

    if op == "between":
        lo, _, hi = operand.partition("|")
        return _between(value, lo, hi)

    if op in ("contains", "ncontains", "startswith", "endswith"):
        v, o = value.lower(), operand.lower()
        if op == "contains":
            return o in v
        if op == "ncontains":
            return o not in v
        if op == "startswith":
            return v.startswith(o)
        return v.endswith(o)  # endswith

    if op in ("eq", "ne", "gt", "lt", "ge", "le"):
        nv, no = _as_number(value), _as_number(operand)
        if nv is not None and no is not None:
            a: float | str = nv
            b: float | str = no
        else:
            a = value.lower()
            b = operand.lower()
        if op == "eq":
            return a == b
        if op == "ne":
            return a != b
        if op == "gt":
            return a > b
        if op == "lt":
            return a < b
        if op == "ge":
            return a >= b
        return a <= b  # le

    raise SortFilterError(f"unknown op: {op!r}")


def _between(value: str, lo: str, hi: str) -> bool:
    nv, nlo, nhi = _as_number(value), _as_number(lo), _as_number(hi)
    if nv is not None and nlo is not None and nhi is not None:
        return nlo <= nv <= nhi
    v, slo, shi = value.lower(), lo.lower(), hi.lower()
    return slo <= v <= shi


def filter_rows(
    rows: list[list[str]], predicates: list[tuple[int, str, str]]
) -> list[int]:
    """Return indices of rows matching ALL ``predicates`` (logical AND).

    Each predicate is ``(col_index, op, operand)``. Empty ``predicates``
    returns every index. Raises ``SortFilterError`` on an out-of-range
    ``col_index`` (or an unknown op, via :func:`match`).
    """
    if not predicates:
        return list(range(len(rows)))
    _check_cols(rows, [c for c, _, _ in predicates])

    out: list[int] = []
    for i, row in enumerate(rows):
        if all(match(row[col], op, operand) for col, op, operand in predicates):
            out.append(i)
    return out
