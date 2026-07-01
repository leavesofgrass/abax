"""Find and replace across a :class:`~abax.core.sheet.Sheet`.

Pure, stdlib-only search over cell text. A single compiled regex drives both
matching and replacement; callers pick whether to search raw text (formulas
included) or computed display values, and whether matches must span the whole
cell. Replacement uses :func:`re.sub`, so backreferences like ``\\1`` work in
regex mode.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from .reference import parse_range, to_a1
from .sheet import Sheet


class SearchError(Exception):
    """Raised when a pattern cannot be compiled as a regular expression."""


@dataclass
class SearchOptions:
    regex: bool = True            # treat pattern as a regular expression
    case_sensitive: bool = False
    whole_cell: bool = False      # pattern must match the entire cell text
    use_formula: bool = True      # search raw text (incl. formulas); False = display


@dataclass
class Match:
    row: int
    col: int
    ref: str          # A1, e.g. "B7"
    text: str         # the cell text that was searched
    start: int        # match start index within text
    end: int          # match end index


def _compile(pattern: str, options: SearchOptions) -> "re.Pattern[str]":
    """Compile *pattern* honoring the regex/case/whole-cell options."""
    flags = 0 if options.case_sensitive else re.IGNORECASE
    body = pattern if options.regex else re.escape(pattern)
    if options.whole_cell:
        body = rf"\A(?:{body})\Z"
    try:
        return re.compile(body, flags)
    except re.error as exc:
        raise SearchError(f"invalid pattern: {exc}") from exc


def _scope(sheet: Sheet, rng: Optional[str]) -> tuple[int, int, int, int]:
    """Inclusive ``(r1, c1, r2, c2)`` bounds to iterate, row-major."""
    if rng is not None:
        return parse_range(rng)
    n_rows, n_cols = sheet.used_bounds()
    return 0, 0, n_rows - 1, n_cols - 1


def _cell_text(sheet: Sheet, row: int, col: int, options: SearchOptions) -> str:
    return sheet.get_raw(row, col) if options.use_formula else sheet.display(row, col)


def find_all(
    sheet: Sheet,
    pattern: str,
    options: Optional[SearchOptions] = None,
    rng: Optional[str] = None,
) -> list[Match]:
    """Return one :class:`Match` per cell whose text matches *pattern*.

    Cells are scanned row-major over *rng* (or the sheet's used bounds). Empty
    cells are skipped and only the FIRST match within each cell is reported.
    """
    options = options or SearchOptions()
    regex = _compile(pattern, options)
    r1, c1, r2, c2 = _scope(sheet, rng)

    matches: list[Match] = []
    for row in range(r1, r2 + 1):
        for col in range(c1, c2 + 1):
            text = _cell_text(sheet, row, col, options)
            if text == "":
                continue
            m = regex.search(text)
            if m is None:
                continue
            matches.append(
                Match(
                    row=row,
                    col=col,
                    ref=to_a1(row, col),
                    text=text,
                    start=m.start(),
                    end=m.end(),
                )
            )
    return matches


def replace_all(
    sheet: Sheet,
    pattern: str,
    repl: str,
    options: Optional[SearchOptions] = None,
    rng: Optional[str] = None,
    on_set: Optional[Callable[[str, str], None]] = None,
) -> int:
    """Replace every match across the scope; return the number of changed cells.

    For each cell, the whole text is rewritten with :func:`re.sub`. A cell is
    only written (and ``on_set(ref, new)`` only fired) when the text actually
    changes.
    """
    options = options or SearchOptions()
    regex = _compile(pattern, options)
    r1, c1, r2, c2 = _scope(sheet, rng)

    changed = 0
    for row in range(r1, r2 + 1):
        for col in range(c1, c2 + 1):
            text = _cell_text(sheet, row, col, options)
            if text == "":
                continue
            new = regex.sub(repl, text)
            if new != text:
                sheet.set_cell(row, col, new)
                if on_set is not None:
                    on_set(to_a1(row, col), new)
                changed += 1
    return changed


def replace_match(
    sheet: Sheet,
    m: Match,
    pattern: str,
    repl: str,
    options: Optional[SearchOptions] = None,
    on_set: Optional[Callable[[str, str], None]] = None,
) -> bool:
    """Replace matches in the single cell *m* refers to.

    Returns ``True`` if the cell text changed (and was written), else ``False``.
    The cell text is re-read so a stale :class:`Match` cannot clobber edits.
    """
    options = options or SearchOptions()
    regex = _compile(pattern, options)

    text = _cell_text(sheet, m.row, m.col, options)
    if text == "":
        return False
    new = regex.sub(repl, text)
    if new == text:
        return False
    sheet.set_cell(m.row, m.col, new)
    if on_set is not None:
        on_set(to_a1(m.row, m.col), new)
    return True
