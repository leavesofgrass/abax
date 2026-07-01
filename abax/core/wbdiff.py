"""Cell-by-cell diff of two sheets or workbooks.

Pure stdlib, part of :mod:`abax.core`. Operates entirely through the public
``Sheet`` / ``Workbook`` API (raw cell text, used bounds, sheet list), so a diff
compares what the user actually typed rather than computed values.

A cell is *empty* when :meth:`Sheet.get_raw` returns ``""``. Each cell-level
change is classified as:

* ``"added"``   — empty in *a*, non-empty in *b*
* ``"removed"`` — non-empty in *a*, empty in *b*
* ``"changed"`` — non-empty in both and the raw text differs
"""

from __future__ import annotations


def _classify(raw_a: str, raw_b: str) -> str | None:
    """Return the change kind for a cell pair, or ``None`` if they are equal."""
    if raw_a == raw_b:
        return None
    if raw_a == "":
        return "added"
    if raw_b == "":
        return "removed"
    return "changed"


def diff_sheets(a, b) -> list[dict]:
    """Compare two ``Sheet`` objects over the union of their used bounds.

    Returns a list of ``{"row", "col", "a", "b", "kind"}`` dicts, one per cell
    whose raw text differs, ordered by ``(row, col)``.
    """
    a_rows, a_cols = a.used_bounds()
    b_rows, b_cols = b.used_bounds()
    n_rows = max(a_rows, b_rows)
    n_cols = max(a_cols, b_cols)

    changes: list[dict] = []
    for r in range(n_rows):
        for c in range(n_cols):
            raw_a = a.get_raw(r, c)
            raw_b = b.get_raw(r, c)
            kind = _classify(raw_a, raw_b)
            if kind is not None:
                changes.append(
                    {"row": r, "col": c, "a": raw_a, "b": raw_b, "kind": kind}
                )
    return changes


def diff_workbooks(a, b) -> dict:
    """Compare two ``Workbook`` objects sheet by sheet.

    Returns ``{"sheets": {name: [changes...]}, "only_in_a": [...],
    "only_in_b": [...]}``. Sheets present in both workbooks are diffed with
    :func:`diff_sheets`; sheets present in only one are listed by name and not
    diffed cell-by-cell.
    """
    a_by_name = {s.name: s for s in a.sheets}
    b_by_name = {s.name: s for s in b.sheets}

    sheets: dict[str, list[dict]] = {}
    for name, sheet_a in a_by_name.items():
        sheet_b = b_by_name.get(name)
        if sheet_b is not None:
            sheets[name] = diff_sheets(sheet_a, sheet_b)

    only_in_a = [s.name for s in a.sheets if s.name not in b_by_name]
    only_in_b = [s.name for s in b.sheets if s.name not in a_by_name]

    return {"sheets": sheets, "only_in_a": only_in_a, "only_in_b": only_in_b}


def summary(diff: dict) -> str:
    """One-line human summary of a :func:`diff_workbooks` result.

    Example: ``"3 changed, 1 added, 0 removed across 2 sheet(s); 1 sheet only
    in A"``.
    """
    changed = added = removed = 0
    for changes in diff["sheets"].values():
        for ch in changes:
            if ch["kind"] == "changed":
                changed += 1
            elif ch["kind"] == "added":
                added += 1
            elif ch["kind"] == "removed":
                removed += 1

    n_sheets = len(diff["sheets"])
    text = (
        f"{changed} changed, {added} added, {removed} removed "
        f"across {n_sheets} sheet(s)"
    )

    extras = []
    only_a = len(diff["only_in_a"])
    only_b = len(diff["only_in_b"])
    if only_a:
        extras.append(f"{only_a} sheet{'s' if only_a != 1 else ''} only in A")
    if only_b:
        extras.append(f"{only_b} sheet{'s' if only_b != 1 else ''} only in B")
    if extras:
        text += "; " + ", ".join(extras)
    return text
