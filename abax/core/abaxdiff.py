"""Lossless cell-level diff engine for abax workbooks (pure stdlib, Qt-free).

Two saved workbooks are compared at the level the *user* actually edits: the raw
cell strings — formulas and literal values exactly as stored in the envelope
(``data.sheets[].cells`` maps A1 ref -> raw text; see
:meth:`abax.core.workbook.Workbook.to_envelope`). We diff those raw strings and
nothing else, which is why the result is *lossless* in the sense that matters for
review: a formula edit (``=B1+C1`` -> ``=B1*C1``) shows as a change, never as a
value that silently recomputed. Working on the envelope (rather than a live
``Workbook``) keeps the engine cheap and side-effect-free — no evaluation, no
dependency graph, no Qt — so it can back a CLI ``abax diff``, a TUI pane, or a
GUI split view identically.

Design notes / WHY:

* A1-keyed dicts are the natural join key across the two sides, so the whole
  engine is set arithmetic on the key sets plus a value compare on the
  intersection. That makes it order-independent (envelope cell order is
  incidental) and O(cells).
* Sheets present on only one side are reported as whole-sheet add/remove by
  folding every cell into ``added`` / ``removed`` — a caller rendering a report
  needs no special case, yet the information (this sheet is entirely new/gone) is
  still recoverable from :attr:`SheetDiff.only_in`.
* Malformed input raises :class:`DiffError` with a human-readable message rather
  than letting a ``KeyError``/``JSONDecodeError`` escape as a bare traceback,
  because the front-ends surface this string straight to the user.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "DiffError",
    "SheetDiff",
    "WorkbookDiff",
    "diff_envelopes",
    "diff_files",
    "render_text",
]

# --- ANSI colouring ---------------------------------------------------------
# The existing ``core.format.ansipalette`` stores colours as (r, g, b) tuples for
# the pyte-backed terminal *view*; it does not emit SGR escape sequences for a
# plain stdout report. So we keep our own minimal, self-contained SGR codes here
# (the spec's "else basic codes" path) — green=added, red=removed, yellow=changed.
_GREEN = "\x1b[32m"
_RED = "\x1b[31m"
_YELLOW = "\x1b[33m"
_RESET = "\x1b[0m"


class DiffError(Exception):
    """Raised for malformed diff input (bad envelope shape or unreadable file).

    Front-ends catch this and show ``str(exc)`` to the user, so the message is
    written to be read by a human, not chained from a low-level exception.
    """


@dataclass
class SheetDiff:
    """Per-cell differences for one sheet name.

    ``added`` / ``removed`` / ``changed`` are keyed by A1 ref. A cell that exists
    on both sides with different raw text lands in ``changed`` as ``(old, new)``;
    a cell only on the new side is ``added`` (value = new raw); only on the old
    side is ``removed`` (value = old raw). ``only_in`` records whole-sheet
    presence: ``"new"`` when the sheet was added, ``"old"`` when removed, and
    ``None`` when the sheet exists on both sides.
    """

    name: str
    added: dict[str, str] = field(default_factory=dict)
    removed: dict[str, str] = field(default_factory=dict)
    changed: dict[str, tuple[str, str]] = field(default_factory=dict)
    only_in: str | None = None  # "old" | "new" | None

    @property
    def is_empty(self) -> bool:
        """True when this sheet has no cell-level differences at all."""
        return not (self.added or self.removed or self.changed)


@dataclass
class WorkbookDiff:
    """The full result: an ordered list of :class:`SheetDiff` plus roll-up counts.

    Sheet order follows the union of both sides (old sheets first, in their
    original order, then any sheets new in the right-hand workbook) so a rendered
    report reads stably regardless of which side introduced a sheet.
    """

    sheets: list[SheetDiff] = field(default_factory=list)

    @property
    def added(self) -> int:
        """Total added cells across every sheet."""
        return sum(len(s.added) for s in self.sheets)

    @property
    def removed(self) -> int:
        """Total removed cells across every sheet."""
        return sum(len(s.removed) for s in self.sheets)

    @property
    def changed(self) -> int:
        """Total changed cells across every sheet."""
        return sum(len(s.changed) for s in self.sheets)

    @property
    def is_empty(self) -> bool:
        """True when the two workbooks are cell-for-cell identical."""
        return all(s.is_empty for s in self.sheets)


# --- envelope traversal -----------------------------------------------------

def _sheet_cells(env: dict, where: str) -> "dict[str, dict[str, str]]":
    """Extract an ordered ``{sheet_name: {a1: raw}}`` map from an envelope.

    Tolerates both the wrapped envelope (``{"data": {"sheets": [...]}}``) and a
    bare payload (``{"sheets": [...]}``), mirroring ``from_envelope``'s leniency.
    Raises :class:`DiffError` — with ``where`` naming which side is bad — on any
    structural surprise, so the caller never sees a raw ``KeyError``/``TypeError``.
    """
    if not isinstance(env, dict):
        raise DiffError(f"{where} envelope must be a dict, got {type(env).__name__}")
    data = env.get("data", env)
    if not isinstance(data, dict):
        raise DiffError(f"{where} envelope 'data' must be a dict")
    sheets = data.get("sheets", [])
    if not isinstance(sheets, list):
        raise DiffError(f"{where} envelope 'sheets' must be a list")

    out: dict[str, dict[str, str]] = {}
    for i, s in enumerate(sheets):
        if not isinstance(s, dict):
            raise DiffError(f"{where} sheet #{i} must be a dict")
        name = s.get("name")
        if not isinstance(name, str):
            raise DiffError(f"{where} sheet #{i} is missing a string 'name'")
        cells = s.get("cells", {})
        if not isinstance(cells, dict):
            raise DiffError(f"{where} sheet {name!r} has a non-dict 'cells'")
        # Coerce raw values to str defensively: the envelope stores raw text, but a
        # hand-edited/foreign file might carry a number or None. Comparing strings
        # keeps the diff total-orderable and the report printable.
        out[name] = {str(ref): ("" if raw is None else str(raw))
                     for ref, raw in cells.items()}
    return out


def _diff_sheet(name: str, old: dict[str, str], new: dict[str, str],
                only_in: str | None) -> SheetDiff:
    """Set-arithmetic diff of two A1->raw maps for a single sheet."""
    old_keys = set(old)
    new_keys = set(new)
    added = {ref: new[ref] for ref in (new_keys - old_keys)}
    removed = {ref: old[ref] for ref in (old_keys - new_keys)}
    changed = {ref: (old[ref], new[ref])
               for ref in (old_keys & new_keys) if old[ref] != new[ref]}
    return SheetDiff(name=name, added=added, removed=removed,
                     changed=changed, only_in=only_in)


def diff_envelopes(old: dict, new: dict) -> WorkbookDiff:
    """Compare two envelope dicts and return a :class:`WorkbookDiff`.

    The workbook is treated as the ``data.sheets`` list; each sheet's ``cells``
    map is diffed by A1 ref. Sheets in only one envelope are folded whole into
    the added/removed side (and tagged via :attr:`SheetDiff.only_in`).
    """
    old_sheets = _sheet_cells(old, "old")
    new_sheets = _sheet_cells(new, "new")

    # Union order: every old sheet in its original order, then new-only sheets in
    # theirs. Preserves a stable, readable report ordering.
    ordered_names: list[str] = list(old_sheets)
    ordered_names += [n for n in new_sheets if n not in old_sheets]

    sheet_diffs: list[SheetDiff] = []
    for name in ordered_names:
        in_old = name in old_sheets
        in_new = name in new_sheets
        if in_old and in_new:
            sheet_diffs.append(_diff_sheet(name, old_sheets[name], new_sheets[name], None))
        elif in_new:  # whole sheet added
            sheet_diffs.append(_diff_sheet(name, {}, new_sheets[name], "new"))
        else:  # whole sheet removed
            sheet_diffs.append(_diff_sheet(name, old_sheets[name], {}, "old"))
    return WorkbookDiff(sheets=sheet_diffs)


def diff_files(old_path: str, new_path: str) -> WorkbookDiff:
    """Load two ``.abax``/JSON envelope files and diff them.

    Any read or JSON-parse failure is re-raised as :class:`DiffError` with the
    offending path, so a bad file never surfaces as a bare traceback.
    """
    return diff_envelopes(_load_json(old_path, "old"), _load_json(new_path, "new"))


def _load_json(path: str, where: str) -> dict:
    """Read and JSON-decode one file, converting every failure to DiffError."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise DiffError(f"cannot read {where} file {path!r}: {exc}") from exc
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DiffError(f"{where} file {path!r} is not valid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise DiffError(f"{where} file {path!r} did not contain a JSON object")
    return obj


# --- rendering --------------------------------------------------------------

def _paint(text: str, code: str, color: bool) -> str:
    """Wrap ``text`` in an SGR colour when colouring is on, else return it raw."""
    return f"{code}{text}{_RESET}" if color else text


def render_text(diff: WorkbookDiff, *, color: bool = False) -> str:
    """Render a unified, human-readable report grouped by sheet.

    One line per changed cell:

        ``+B5: 42``            a cell was added (green)
        ``-C9: old``           a cell was removed (red)
        ``~A1: =B1+C1 -> =B1*C1``  a cell changed (yellow)

    Sheets with no differences are skipped entirely, so an identical pair of
    workbooks renders to the empty string (a caller can print "no changes"
    itself). Whole-sheet add/remove is annotated on the sheet header. With
    ``color=True`` each line is coloured green/red/yellow via ANSI SGR codes.
    """
    blocks: list[str] = []
    for sd in diff.sheets:
        if sd.is_empty:
            continue
        header = sd.name
        if sd.only_in == "new":
            header += "  (added sheet)"
        elif sd.only_in == "old":
            header += "  (removed sheet)"
        lines = [header]
        # Deterministic per-sheet ordering (A1 refs sorted as plain strings keeps
        # the report stable run-to-run without pulling in reference parsing).
        for ref in sorted(sd.added):
            lines.append(_paint(f"  +{ref}: {sd.added[ref]}", _GREEN, color))
        for ref in sorted(sd.removed):
            lines.append(_paint(f"  -{ref}: {sd.removed[ref]}", _RED, color))
        for ref in sorted(sd.changed):
            old, new = sd.changed[ref]
            lines.append(_paint(f"  ~{ref}: {old} -> {new}", _YELLOW, color))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
