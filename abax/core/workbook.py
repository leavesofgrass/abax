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

SCHEMA_VERSION = 2


class RecalcCancelled(Exception):
    """Raised inside a recalc when its ``should_cancel`` callback returns truthy.

    Caught by ``Workbook.recalculate`` (which returns ``False``); a caller using
    ``Sheet.recalculate`` directly should catch it too.
    """


class Workbook:
    def __init__(self) -> None:
        from .connections import ConnectionRegistry
        from .names import NameRegistry
        from .pm.projects import ProjectRegistry
        from .tables import TableRegistry

        self.sheets: list[Sheet] = []
        self.active: int = 0
        self.names = NameRegistry()
        self.tables = TableRegistry()
        self.projects = ProjectRegistry()
        # Named, refreshable data sources (REST/SQL/web-table). Only non-secret
        # metadata is stored here / persisted; credentials live session-only in
        # sandbox.SecretsHolder keyed by Connection.secret_ref.
        self.connections = ConnectionRegistry()
        # Calculation mode: "auto" recomputes dependents on every edit (via the
        # incremental dependency graph); "manual" defers all dependent recalc
        # until recalculate() (the GUI's F9), for very large/slow sheets.
        self.calc_mode = "auto"
        self._calc_dirty = False  # edits pending a manual recalc
        # Iterative calculation (opt-in; set from Settings by the front-end). When
        # on, recalculate_iterative() resolves circular references by capped
        # fixed-point iteration instead of #CIRC!.
        self.calc_iterative = False
        self.calc_max_iterations = 100
        self.calc_max_change = 0.001
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
        the flag is off, the edited formula can't be analysed, or the edit
        interacts with a dynamic-array spill (Phase B, below). Name-referencing
        formulas are always-dirty, so a defined-name change needs no special
        handling here.

        **Phase B — spilling workbooks stay incremental.** A spill's grid depends
        only on its anchor's formula inputs, and its extent changes only when the
        anchor recomputes — which happens iff the anchor is in the edit's static
        closure. So an edit is safe to scope precisely unless it *interacts* with
        a spill: it (re)defines or removes an array formula, lands inside a live
        spill region, unblocks a ``#SPILL!`` error, or feeds an anchor. Every such
        case degrades to the sound blanket clear; all other edits get the precise
        path even when spills exist elsewhere in the book (Phase A pessimistically
        blanket-cleared on *any* spill anywhere). Proven equal to the full-recalc
        oracle by ``tests/test_depgraph_property.py`` on spilling workbooks.
        """
        from .depgraph import ABAX_INCREMENTAL

        if not ABAX_INCREMENTAL:
            self.invalidate_caches()
            return

        key = (row, col)
        spilling = any(s._anchor_cells for s in self.sheets)
        # Pre-sync involvement — captured before the sync below, which erases a
        # just-removed anchor from the map (so removal would otherwise slip past).
        was_in_spill = key in sheet._spill_anchor
        if spilling or was_in_spill or any(s._spill_error for s in self.sheets):
            # Materialise the current spill map so region membership is exact:
            # a freshly created spill or an unblocked #SPILL! becomes visible, and
            # regions reflect the current formulas. Regions that would *grow* need
            # the anchor to recompute, which the closure gate catches regardless.
            for s in self.sheets:
                if s._anchor_cells and s._spill_dirty:
                    s._sync_spills()
            if (key in sheet._anchor_cells          # edits/creates a spill formula
                    or was_in_spill                 # edits a just-removed anchor / spilled cell
                    or key in sheet._spill_anchor   # lands inside a live spill (post-sync)
                    or any(s._spill_error for s in self.sheets)):  # a spill is #SPILL!
                self._full_clear_and_reset()
                return
            guard_anchors = True
        else:
            guard_anchors = False

        dg = self._dep_graph
        if not dg.is_built:
            dg.build(self.sheets)
        raw = sheet.get_raw(row, col)
        if not dg.on_cell_changed(self.sheets, sheet.name, row, col, raw):
            self._full_clear_and_reset()
            return
        seeds = {(sheet.name, row, col)}
        seeds |= dg.always_dirty
        closure = dg.closure(seeds)

        if guard_anchors:
            anchor_keys = {(s.name, r, c) for s in self.sheets for (r, c) in s._anchor_cells}
            if closure & anchor_keys:
                # Recomputing an anchor can resize/move its spill; readers of the
                # (old or new) spilled cells are not in this static closure.
                self._full_clear_and_reset()
                return

        by_name = {s.name: s for s in self.sheets}
        for (sname, r, c) in closure:
            tgt = by_name.get(sname)
            if tgt is not None:
                tgt._value_cache.pop((r, c), None)
        if not guard_anchors:
            # Keep the spill flag workbook-wide, exactly as invalidate_caches does
            # (a no-op without anchors). When spilling, the map was synced above
            # and no anchor changed, so it stays current — no re-dirty needed.
            for s in self.sheets:
                s._spill_dirty = True

    def recalculate_iterative(self, max_iterations: "int | None" = None,
                              max_change: "float | None" = None) -> "tuple[int, bool]":
        """Resolve circular references by capped fixed-point iteration.

        Sweeps every formula cell repeatedly; a circular read returns the previous
        iteration's value (0 the first time) instead of ``#CIRC!``, so an
        accumulator (``B1 = A1 + B1``) or a convergent model settles to its fixed
        point. Returns ``(iterations_run, converged)`` — converged is True once the
        largest change across a full sweep is within ``max_change``, else the sweep
        stops at ``max_iterations``. The converged values are left in the value
        caches (the front-end repaints without invalidating). A cycle-free workbook
        settles in one sweep. This is the explicit, bounded, sound path — normal
        (non-iterative) evaluation still surfaces ``#CIRC!``.
        """
        max_iter = max(1, max_iterations if max_iterations is not None else self.calc_max_iterations)
        tol = max_change if max_change is not None else self.calc_max_change
        formula_cells = [(sh, r, c)
                         for sh in self.sheets
                         for (r, c), cell in sh._cells.items() if cell.raw.startswith("=")]
        for sh in self.sheets:
            sh._iterating = True
        iterations = 0
        converged = False
        try:
            for _ in range(max_iter):
                iterations += 1
                for sh in self.sheets:
                    sh._value_cache.clear()
                    sh._spill_dirty = True
                max_delta = 0.0
                for (sh, r, c) in formula_cells:
                    old = sh._iter_values.get((r, c))
                    val = sh.get_value(r, c)
                    sh._iter_values[(r, c)] = val
                    if (isinstance(old, (int, float)) and isinstance(val, (int, float))
                            and not isinstance(old, bool) and not isinstance(val, bool)):
                        max_delta = max(max_delta, abs(float(val) - float(old)))
                    elif old != val:
                        max_delta = float("inf")  # non-numeric change — keep going
                if max_delta <= tol:
                    converged = True
                    break
        finally:
            for sh in self.sheets:
                sh._iterating = False
        return iterations, converged

    def load_envelope(self, env: dict) -> None:
        """Replace this workbook's contents IN PLACE from an envelope.

        Keeps ``self`` identity (so GUI/TUI references to the workbook stay valid)
        while swapping in the sheets/active from ``env`` — the basis for undo/redo.
        """
        other = Workbook.from_envelope(env)
        self.sheets = other.sheets
        self.active = other.active
        self.names = other.names
        self.tables = other.tables
        self.projects = other.projects
        self.connections = other.connections
        self._link_sheets()
        self._reset_depgraph()  # sheet set replaced — rebuild the index lazily

    @classmethod
    def from_sheets(cls, sheets, active: int = 0) -> "Workbook":
        from .connections import ConnectionRegistry
        from .names import NameRegistry
        from .pm.projects import ProjectRegistry
        from .tables import TableRegistry

        wb = cls.__new__(cls)
        wb.sheets = list(sheets)
        wb.active = active
        wb.names = NameRegistry()
        wb.tables = TableRegistry()
        wb.projects = ProjectRegistry()
        wb.connections = ConnectionRegistry()
        wb._add_default_if_empty()
        wb.active = min(max(wb.active, 0), len(wb.sheets) - 1)
        return wb

    # --- sheet management -------------------------------------------------

    @property
    def sheet(self) -> Sheet:
        return self.sheets[self.active]

    def use_windowed_stores(self, capacity: int) -> None:
        """Bound every sheet's resident cells to ``capacity`` (0 = off).

        Called once by a front-end after a large workbook is opened, when the
        ``windowed_store_capacity`` setting is on. Per-sheet detail:
        :meth:`Sheet.use_windowed_store`.
        """
        if not capacity or capacity <= 0:
            return
        for sheet in self.sheets:
            sheet.use_windowed_store(capacity)

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

    def set_calc_mode(self, mode: str) -> None:
        """Switch between ``"auto"`` and ``"manual"`` calculation.

        Switching back to ``"auto"`` forces a full recompute so any edits made
        while manual take effect immediately.
        """
        if mode not in ("auto", "manual"):
            raise ValueError(f"calc_mode must be 'auto' or 'manual', got {mode!r}")
        self.calc_mode = mode
        if mode == "auto" and self._calc_dirty:
            self.recalculate()

    def recalculate(self, *, should_cancel=None, progress=None) -> bool:
        """Full recompute of every sheet. Returns ``True`` when it completed.

        With both callbacks omitted this is the original tight loop. Otherwise:

        * ``should_cancel()`` is polled between cells — when it returns truthy the
          recalc stops, the workbook is left partially recomputed and dirty
          (``_calc_dirty``), and this returns ``False`` instead of raising, so a
          cancelled F9 is a normal outcome rather than an error.
        * ``progress(done, total)`` fires as cells are evaluated (throttled to
          ~every 256 cells, plus a final 100% call), for a progress bar.

        Cancellation is *cooperative*: because Python's GIL serializes formula
        evaluation, the win here is responsiveness (abort a runaway recalc, show
        progress) — the GUI pumps events inside ``progress`` and sets the cancel
        flag from the button, no worker thread needed. Results are byte-identical
        to the plain recalc when the run completes.
        """
        if should_cancel is None and progress is None:
            for sheet in self.sheets:
                sheet.recalculate()
            self._calc_dirty = False
            return True

        total = sum(len(s._cells) for s in self.sheets) or 1
        done = [0]

        def _tick() -> None:
            done[0] += 1
            if progress is not None and (done[0] & 0xFF) == 0:
                progress(done[0], total)

        try:
            for sheet in self.sheets:
                sheet.recalculate(should_cancel=should_cancel, tick=_tick)
        except RecalcCancelled:
            self._calc_dirty = True  # partial recompute — stays dirty
            if progress is not None:
                progress(done[0], total)
            return False
        if progress is not None:
            progress(total, total)
        self._calc_dirty = False
        return True

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
                # Omitted when empty to keep files lean (older readers ignore it).
                **({"tables": self.tables.to_dict()} if len(self.tables) else {}),
                **({"projects": self.projects.to_dict()} if len(self.projects) else {}),
                # Non-secret connection metadata only (credentials never persist).
                **({"connections": self.connections.to_dict()}
                   if len(self.connections) else {}),
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
                        # v2 layout & fidelity (omitted when empty to keep files lean).
                        **({"col_widths": {str(c): w for c, w in s.col_widths.items()}}
                           if s.col_widths else {}),
                        **({"row_heights": {str(r): h for r, h in s.row_heights.items()}}
                           if s.row_heights else {}),
                        **({"frozen": [s.frozen_rows, s.frozen_cols]}
                           if (s.frozen_rows or s.frozen_cols) else {}),
                        **({"borders": {to_a1(r, c): edges
                                        for (r, c), edges in s.cell_borders.items()}}
                           if s.cell_borders else {}),
                        **({"merges": [f"{to_a1(r1, c1)}:{to_a1(r2, c2)}"
                                       for (r1, c1, r2, c2) in s.merges]}
                           if s.merges else {}),
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
        from .connections import ConnectionRegistry
        from .format.cellstyle import CellStyle
        from .format.condformat import CondRule
        from .names import NameRegistry
        from .pm.projects import ProjectRegistry
        from .tables import TableRegistry

        wb = cls.__new__(cls)
        wb.sheets = []
        wb.names = NameRegistry.from_dict(data.get("names", {}))
        wb.tables = TableRegistry.from_dict(data.get("tables", {}))
        wb.projects = ProjectRegistry.from_dict(data.get("projects", {}))
        wb.connections = ConnectionRegistry.from_dict(data.get("connections", {}))
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
            # v2 layout & fidelity (all optional; a v1 file simply has none).
            sheet.col_widths = {int(c): int(w) for c, w in s.get("col_widths", {}).items()}
            sheet.row_heights = {int(r): int(h) for r, h in s.get("row_heights", {}).items()}
            fr = s.get("frozen") or [0, 0]
            sheet.frozen_rows, sheet.frozen_cols = int(fr[0]), int(fr[1])
            sheet.cell_borders = {parse_a1(ref): dict(edges)
                                  for ref, edges in s.get("borders", {}).items()}
            for m in s.get("merges", []):
                if ":" in m:
                    a, b = m.split(":", 1)
                    mr1, mc1 = parse_a1(a)
                    mr2, mc2 = parse_a1(b)
                    sheet.merges.append((mr1, mc1, mr2, mc2))
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
    """Expand-switch-contract migration hook.

    v1 -> v2 added per-sheet layout & fidelity keys (``col_widths`` /
    ``row_heights`` / ``frozen`` / ``borders`` / ``merges``). They are read with
    defaults in :meth:`Workbook.from_envelope`, so a v1 file (which lacks them)
    loads unchanged — no data transform is needed, only the version label.
    """
    if version < 2:
        data["schema_version"] = 2
    return data
