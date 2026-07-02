"""A `Workbook` — an ordered collection of named sheets.

Pure stdlib, so it belongs to core. JSON is the native persistence format
(per the spec's "JSON everywhere" principle); Excel/CSV are handled by the
engine adapters layer above.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .reference import parse_a1, to_a1
from .sheet import Sheet

SCHEMA_VERSION = 1


class Workbook:
    def __init__(self) -> None:
        from .names import NameRegistry

        self.sheets: list[Sheet] = []
        self.active: int = 0
        self.names = NameRegistry()
        self._add_default_if_empty()

    def _add_default_if_empty(self) -> None:
        if not self.sheets:
            self.sheets.append(Sheet("Sheet1"))
        self._link_sheets()

    def _link_sheets(self) -> None:
        """Point every sheet back at this workbook so Sheet2!A1 resolves.

        Called by all construction paths (and importers via _add_default_if_empty)
        so cross-sheet references work regardless of how the workbook was built.
        """
        for s in self.sheets:
            s.workbook = self

    def invalidate_caches(self) -> None:
        for s in self.sheets:
            s._value_cache.clear()
            s._spill_dirty = True

    # --- incremental invalidation (WS1 — see core/depgraph.py) ------------

    @property
    def _dep_graph(self):
        """Lazily-built reverse-dependents index. Stored in ``__dict__`` so the
        ``__new__``-based constructors (from_sheets/from_envelope) need no edit."""
        dg = self.__dict__.get("_depgraph_obj")
        if dg is None:
            from .depgraph import DepGraph

            dg = DepGraph()
            self.__dict__["_depgraph_obj"] = dg
        return dg

    def _reset_depgraph(self) -> None:
        """Drop the index so it rebuilds lazily — for structural changes that
        rewrite formulas or the sheet set (bulk load, insert/delete, envelope
        swap, add/remove sheet)."""
        dg = self.__dict__.get("_depgraph_obj")
        if dg is not None:
            dg.clear()

    def _full_clear_and_reset(self) -> None:
        """The sound fallback: blanket-clear every value cache and drop the
        index so the next incremental edit rebuilds from the current formulas."""
        self.invalidate_caches()
        self._reset_depgraph()

    def invalidate_dependents(self, sheet, row: int, col: int) -> None:
        """Incremental replacement for :meth:`invalidate_caches`: clear only the
        value caches an edit at ``(sheet, row, col)`` can affect.

        Falls back to the blanket clear whenever soundness isn't cheap to prove:
        the flag is off, the workbook currently spills (a spilled-into cell's
        dependency on its anchor is not a static edge — Phase A), or the edited
        formula can't be analysed. Name-referencing formulas are always-dirty,
        so a defined-name change needs no special handling here.
        """
        from .depgraph import ABAX_INCREMENTAL

        if not ABAX_INCREMENTAL:
            self.invalidate_caches()
            return
        # Phase A: only fully spill-free workbooks get the precise path. Any
        # array-formula anchor OR an active spill map => the verbatim full clear.
        if any(s._anchor_cells or s._spill_anchor for s in self.sheets):
            self._full_clear_and_reset()
            return
        dg = self._dep_graph
        if not dg.is_built:
            dg.build(self.sheets)
        raw = sheet.get_raw(row, col)
        if not dg.on_cell_changed(self.sheets, sheet.name, row, col, raw):
            self._full_clear_and_reset()
            return
        seeds = {(sheet.name, row, col)}
        seeds |= dg.always_dirty
        by_name = {s.name: s for s in self.sheets}
        for (sname, r, c) in dg.closure(seeds):
            tgt = by_name.get(sname)
            if tgt is not None:
                tgt._value_cache.pop((r, c), None)
        # Keep the spill flag workbook-wide, exactly as invalidate_caches does.
        for s in self.sheets:
            s._spill_dirty = True

    def load_envelope(self, env: dict) -> None:
        """Replace this workbook's contents IN PLACE from an envelope.

        Keeps ``self`` identity (so GUI/TUI references to the workbook stay valid)
        while swapping in the sheets/active from ``env`` — the basis for undo/redo.
        """
        other = Workbook.from_envelope(env)
        self.sheets = other.sheets
        self.active = other.active
        self.names = other.names
        self._link_sheets()
        self._reset_depgraph()  # sheet set replaced — rebuild the index lazily

    @classmethod
    def from_sheets(cls, sheets, active: int = 0) -> "Workbook":
        from .names import NameRegistry

        wb = cls.__new__(cls)
        wb.sheets = list(sheets)
        wb.active = active
        wb.names = NameRegistry()
        wb._add_default_if_empty()
        wb.active = min(max(wb.active, 0), len(wb.sheets) - 1)
        return wb

    # --- sheet management -------------------------------------------------

    @property
    def sheet(self) -> Sheet:
        return self.sheets[self.active]

    def add_sheet(self, name: str | None = None) -> Sheet:
        name = name or f"Sheet{len(self.sheets) + 1}"
        if any(s.name == name for s in self.sheets):
            raise ValueError(f"duplicate sheet name: {name!r}")
        sheet = Sheet(name)
        sheet.workbook = self
        self.sheets.append(sheet)
        self._reset_depgraph()  # sheet set changed — rebuild the index lazily
        return sheet

    def get_sheet(self, name: str) -> Sheet | None:
        return next((s for s in self.sheets if s.name == name), None)

    def remove_sheet(self, name: str) -> None:
        self.sheets = [s for s in self.sheets if s.name != name]
        self._add_default_if_empty()
        self.active = min(self.active, len(self.sheets) - 1)
        self._reset_depgraph()  # sheet set changed — rebuild the index lazily

    def recalculate(self) -> None:
        for sheet in self.sheets:
            sheet.recalculate()

    # --- JSON persistence (native format) --------------------------------

    def to_envelope(self) -> dict:
        """Wrap the workbook in the spec's self-describing exchange envelope."""
        return {
            "app": "abax",
            "schema_version": SCHEMA_VERSION,
            "written_at": datetime.now(timezone.utc).isoformat(),
            "data": {
                "active": self.active,
                "names": self.names.to_dict(),
                "sheets": [
                    {
                        "name": s.name,
                        "cells": s.to_dict(),
                        "cond_rules": [r.to_dict() for r in s.cond_rules],
                        "formats": {to_a1(r, c): spec for (r, c), spec in s.cell_formats.items()},
                        "styles": {to_a1(r, c): st.to_dict()
                                   for (r, c), st in s.cell_styles.items() if not st.is_empty()},
                        "comments": {to_a1(r, c): text for (r, c), text in s.cell_comments.items()},
                        "validations": [
                            {"range": f"{to_a1(r1, c1)}:{to_a1(r2, c2)}", "rule": rule.to_dict()}
                            for r1, c1, r2, c2, rule in s.validations],
                    }
                    for s in self.sheets
                ],
            },
        }

    @classmethod
    def from_envelope(cls, env: dict) -> "Workbook":
        version = env.get("schema_version", 0)
        data = env.get("data", env)  # tolerate bare payloads
        data = _migrate(data, version)
        from .format.cellstyle import CellStyle
        from .format.condformat import CondRule
        from .names import NameRegistry

        wb = cls.__new__(cls)
        wb.sheets = []
        wb.names = NameRegistry.from_dict(data.get("names", {}))
        for s in data.get("sheets", []):
            sheet = Sheet.from_dict(s["name"], s.get("cells", {}))
            sheet.cond_rules = [CondRule.from_dict(d) for d in s.get("cond_rules", [])]
            sheet.cell_formats = {parse_a1(ref): spec for ref, spec in s.get("formats", {}).items()}
            sheet.cell_styles = {parse_a1(ref): CellStyle.from_dict(d)
                                 for ref, d in s.get("styles", {}).items()}
            # Comments are optional — older files without the key load fine.
            sheet.cell_comments = {parse_a1(ref): text
                                   for ref, text in s.get("comments", {}).items()}
            from .validation import ValidationRule

            for v in s.get("validations", []):
                rng = v.get("range", "")
                rule_dict = v.get("rule", {})
                # Skip a malformed/old entry (missing range or rule kind) rather
                # than KeyError out of the whole workbook load.
                if ":" in rng and "kind" in rule_dict:
                    a, b = rng.split(":", 1)
                    r1, c1 = parse_a1(a)
                    r2, c2 = parse_a1(b)
                    sheet.validations.append((r1, c1, r2, c2, ValidationRule.from_dict(rule_dict)))
            wb.sheets.append(sheet)
        wb.active = data.get("active", 0)
        wb._add_default_if_empty()
        wb.active = min(wb.active, len(wb.sheets) - 1)
        return wb

    def save_json(self, path: str | Path) -> None:
        # Atomic write: serialize to a sibling temp file, then replace. A failure
        # mid-write (disk full, permissions) can no longer truncate or corrupt an
        # existing .abax file — the original stays intact until the rename.
        path = Path(path)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(self.to_envelope(), indent=2), encoding="utf-8")
        tmp.replace(path)

    @classmethod
    def load_json(cls, path: str | Path) -> "Workbook":
        env = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_envelope(env)


def _migrate(data: dict, version: int) -> dict:
    """Expand-switch-contract migration hook. v1 is current; no-op for now."""
    # if version < 2: ... transform data ...; data["schema_version"] = 2
    return data
