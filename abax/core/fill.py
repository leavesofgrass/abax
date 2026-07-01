"""Copy / paste / fill operations on a sheet — built on `shift_formula`.

A `Clip` is a JSON-serializable rectangular block of raw cell text. Pasting
shifts relative references by the destination offset (gnumeric's relative-paste
behaviour); ``mode="absolute"`` pastes verbatim. Fill-down/right and fill-series
extend a selection. ``sort_region`` reorders rows by a key column.

Every mutating function accepts an optional ``on_set(ref, raw)`` callback so the
caller (e.g. the macro recorder) can observe each write. Pure stdlib → core.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .reference import parse_a1, parse_range, to_a1
from .series import extend_series
from .translate import shift_formula

OnSet = Callable[[str, str], None]


@dataclass
class Clip:
    origin: tuple[int, int]  # (row, col) of the top-left source cell
    grid: list[list[str]] = field(default_factory=list)  # rows of raw text

    @property
    def nrows(self) -> int:
        return len(self.grid)

    @property
    def ncols(self) -> int:
        return len(self.grid[0]) if self.grid else 0

    def to_dict(self) -> dict:
        return {"origin": list(self.origin), "grid": self.grid}

    @classmethod
    def from_dict(cls, d: dict) -> "Clip":
        return cls(tuple(d.get("origin", (0, 0))), d.get("grid", []))


def _emit(on_set: OnSet | None, r: int, c: int, raw: str) -> None:
    if on_set is not None:
        on_set(to_a1(r, c), raw)


# --- copy / paste ----------------------------------------------------------


def copy_region(sheet, rng: str | tuple) -> Clip:
    r1, c1, r2, c2 = _bounds(rng)
    grid = [[sheet.get_raw(r, c) for c in range(c1, c2 + 1)] for r in range(r1, r2 + 1)]
    return Clip((r1, c1), grid)


def paste_clip(
    sheet, clip: Clip, dest: str | tuple, *, mode: str = "relative", on_set: OnSet | None = None
) -> None:
    dr0, dc0 = _coord(dest)
    dr, dc = dr0 - clip.origin[0], dc0 - clip.origin[1]
    for i, row in enumerate(clip.grid):
        for j, raw in enumerate(row):
            r, c = dr0 + i, dc0 + j
            new = shift_formula(raw, dr, dc) if mode == "relative" else raw
            sheet.set_cell(r, c, new)
            _emit(on_set, r, c, new)


# --- fill ------------------------------------------------------------------


def fill_down(sheet, rng: str | tuple, *, on_set: OnSet | None = None) -> None:
    r1, c1, r2, c2 = _bounds(rng)
    for c in range(c1, c2 + 1):
        src = sheet.get_raw(r1, c)
        for r in range(r1 + 1, r2 + 1):
            new = shift_formula(src, r - r1, 0)
            sheet.set_cell(r, c, new)
            _emit(on_set, r, c, new)


def fill_right(sheet, rng: str | tuple, *, on_set: OnSet | None = None) -> None:
    r1, c1, r2, c2 = _bounds(rng)
    for r in range(r1, r2 + 1):
        src = sheet.get_raw(r, c1)
        for c in range(c1 + 1, c2 + 1):
            new = shift_formula(src, 0, c - c1)
            sheet.set_cell(r, c, new)
            _emit(on_set, r, c, new)


def fill_series(sheet, rng: str | tuple, *, on_set: OnSet | None = None) -> None:
    """Extend the seed cells of a selection into the blank remainder.

    Orientation is chosen by the longer axis (ties go vertical), matching the
    common single-row / single-column case.
    """
    r1, c1, r2, c2 = _bounds(rng)
    vertical = (r2 - r1) >= (c2 - c1)
    if vertical:
        for c in range(c1, c2 + 1):
            seeds, r = [], r1
            while r <= r2 and sheet.get_raw(r, c) != "":
                seeds.append(sheet.get_raw(r, c))
                r += 1
            count = r2 - r + 1
            for k, v in enumerate(extend_series(seeds, count)):
                rr = r + k
                sheet.set_cell(rr, c, v)
                _emit(on_set, rr, c, v)
    else:
        for r in range(r1, r2 + 1):
            seeds, c = [], c1
            while c <= c2 and sheet.get_raw(r, c) != "":
                seeds.append(sheet.get_raw(r, c))
                c += 1
            count = c2 - c + 1
            for k, v in enumerate(extend_series(seeds, count)):
                cc = c + k
                sheet.set_cell(r, cc, v)
                _emit(on_set, r, cc, v)


# --- sort ------------------------------------------------------------------


def sort_region(
    sheet,
    rng: str | tuple,
    key_col: int | None = None,
    *,
    descending: bool = False,
    on_set: OnSet | None = None,
) -> None:
    """Sort the rows of a region by ``key_col`` (absolute col index; default the
    region's first column). Sorts raw values (numbers before text)."""
    r1, c1, r2, c2 = _bounds(rng)
    if key_col is None:
        key_col = c1
    key_idx = key_col - c1
    rows = [[sheet.get_raw(r, c) for c in range(c1, c2 + 1)] for r in range(r1, r2 + 1)]

    def keyf(row):
        v = row[key_idx] if 0 <= key_idx < len(row) else ""
        try:
            return (0, float(v), "")
        except (TypeError, ValueError):
            return (1, 0.0, v.lower())

    rows.sort(key=keyf, reverse=descending)
    for i, row in enumerate(rows):
        for j, raw in enumerate(row):
            r, c = r1 + i, c1 + j
            sheet.set_cell(r, c, raw)
            _emit(on_set, r, c, raw)


# --- TSV (system-clipboard interop) ---------------------------------------


def clip_to_tsv(clip: Clip) -> str:
    return "\n".join("\t".join(row) for row in clip.grid)


def clip_from_tsv(text: str, origin: tuple = (0, 0)) -> Clip:
    grid = [line.split("\t") for line in text.replace("\r\n", "\n").rstrip("\n").split("\n")]
    return Clip(origin, grid)


def region_to_tsv(sheet, rng: str | tuple, *, values: bool = True) -> str:
    r1, c1, r2, c2 = _bounds(rng)
    lines = []
    for r in range(r1, r2 + 1):
        cells = [
            sheet.display(r, c) if values else sheet.get_raw(r, c) for c in range(c1, c2 + 1)
        ]
        lines.append("\t".join(cells))
    return "\n".join(lines)


# --- helpers ---------------------------------------------------------------


def _bounds(rng: str | tuple) -> tuple[int, int, int, int]:
    if isinstance(rng, str):
        return parse_range(rng)
    return rng  # already (r1, c1, r2, c2)


def _coord(dest: str | tuple) -> tuple[int, int]:
    if isinstance(dest, str):
        return parse_a1(dest)
    return dest
