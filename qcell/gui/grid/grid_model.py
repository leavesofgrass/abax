"""QcellTableModel — a virtualized QAbstractTableModel over the active Sheet.

The model serves only what the view asks for (its viewport), so a huge sheet
costs nothing until it is scrolled into view. It never materializes a widget
per cell — that QTableWidget cost is exactly what this refactor removes.
Conditional-format fills, per-cell styles, and alignment are served lazily
through ``data()`` roles. Editing routes back through the host window's
``_commit_cell`` so undo, macro-recording, and validation are unchanged.

``DisplayRole`` is the computed value (``Sheet.display``); ``EditRole`` is the
raw text (``Sheet.get_raw``) — so the in-cell editor seeds with the *formula*,
not the computed value.
"""

from __future__ import annotations

from .._qtcompat import QAbstractTableModel, QBrush, QColor, QFont, QModelIndex, Qt
from ...core.reference import index_to_col

# Headroom past the used range so there is always blank space to type into; the
# view virtualizes, so a generous extent is cheap. It grows on demand and never
# shrinks during a session (extra blank rows are harmless).
_MARGIN_ROWS = 200
_MARGIN_COLS = 8

_ALIGN = {
    "left": Qt.AlignmentFlag.AlignLeft,
    "center": Qt.AlignmentFlag.AlignHCenter,
    "right": Qt.AlignmentFlag.AlignRight,
}

# A shared null index for the parent= defaults (a QModelIndex is a cheap value
# type, safe to build at import; avoids a call in argument defaults).
_NO_PARENT = QModelIndex()

# Cache sentinel: a cell whose conditional-format result is "no fill" caches as
# None, so we need a distinct miss marker to know it hasn't been computed yet.
_MISS = object()


class QcellTableModel(QAbstractTableModel):
    def __init__(self, window) -> None:
        super().__init__()
        self._win = window
        self._rows = 200
        self._cols = 26
        self._min_rows = 200
        self._min_cols = 26
        # Conditional formatting is evaluated lazily, per painted cell, and cached
        # for the current refresh generation — so cost scales with the viewport,
        # not with the (possibly huge) rule ranges. Cleared/rebuilt in refresh().
        self._cond_rules: list = []
        self._scale_ctx: dict = {}
        self._cf_cache: dict[tuple[int, int], str | None] = {}
        # Cached set of populated cells for Ctrl+Arrow edge-jumps; rebuilt lazily,
        # dropped on refresh() (i.e. after any mutation), so navigation doesn't
        # rescan the whole sheet on every keypress.
        self._populated: set[tuple[int, int]] | None = None

    def populated_cells(self) -> set[tuple[int, int]]:
        if self._populated is None:
            self._populated = {(r, c) for r, c, _ in self._sheet().iter_cells()}
        return self._populated

    # -- sheet access ------------------------------------------------------

    def _sheet(self):
        return self._win._doc.workbook.sheet

    # -- Qt model surface --------------------------------------------------

    def rowCount(self, parent=_NO_PARENT) -> int:  # noqa: N802 (Qt override)
        return 0 if parent.isValid() else self._rows

    def columnCount(self, parent=_NO_PARENT) -> int:  # noqa: N802 (Qt override)
        return 0 if parent.isValid() else self._cols

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return index_to_col(section)
        return str(section + 1)

    def flags(self, index):  # noqa: N802 (Qt override)
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return (Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEditable)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        r, c = index.row(), index.column()
        sheet = self._sheet()
        role_e = Qt.ItemDataRole
        if role == role_e.DisplayRole:
            return sheet.display(r, c)
        if role == role_e.EditRole:
            return sheet.get_raw(r, c)
        if role not in (role_e.BackgroundRole, role_e.ForegroundRole,
                        role_e.FontRole, role_e.TextAlignmentRole):
            return None

        # Resolve visual attributes once: conditional fill first, then an
        # explicit per-cell style overrides it (matching the old refresh path).
        fg = bg = None
        bold = italic = underline = False
        align = None
        hexc = self._cond_color(r, c)
        if hexc:
            bg = hexc
            fg = "#111111"  # readable on a conditional fill
        style = sheet.cell_styles.get((r, c))
        if style is not None and not style.is_empty():
            bold, italic, underline = style.bold, style.italic, style.underline
            if style.text_color:
                fg = style.text_color
            if style.bg_color:
                bg = style.bg_color
            if style.align:
                align = style.align

        if role == role_e.BackgroundRole:
            return QBrush(QColor(bg)) if bg else None
        if role == role_e.ForegroundRole:
            return QBrush(QColor(fg)) if fg else None
        if role == role_e.FontRole:
            # The dyslexia font reaches cells via FontRole: a QSS family on the view
            # isn't honored by the item delegate's painter, so set it per cell here.
            fam = getattr(self._win, "_ui_font_family", "")
            if not (bold or italic or underline or fam):
                return None
            font = QFont(self._win._table.font())
            if fam:
                font.setFamily(fam)
            font.setBold(bold)
            font.setItalic(italic)
            font.setUnderline(underline)
            return font
        # TextAlignmentRole
        horiz = _ALIGN.get(align, Qt.AlignmentFlag.AlignLeft)
        return int(horiz | Qt.AlignmentFlag.AlignVCenter)

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):  # noqa: N802
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        return bool(self._win._commit_cell(index.row(), index.column(), str(value)))

    # -- refresh / extent --------------------------------------------------

    def _cond_color(self, r: int, c: int) -> str | None:
        """Conditional-format fill for one cell, computed on demand + cached.

        Only cells the view actually paints ever hit ``color_at``, so a rule over
        a 20k-cell range costs nothing until those cells scroll into view.
        """
        rules = self._cond_rules
        if not rules:
            return None
        cache = self._cf_cache
        key = (r, c)
        hit = cache.get(key, _MISS)
        if hit is _MISS:
            from ...core.format.condformat import color_at

            hit = color_at(self._sheet(), rules, r, c, self._scale_ctx)
            cache[key] = hit
        return hit

    def refresh(self) -> None:
        """Rebuild the lazy conditional-format state + extent and repaint,
        preserving the selection.

        Emitting one ``dataChanged`` over the whole extent is O(1) — the view
        only repaints the visible viewport, never the full range — and the
        per-cell fill cache is dropped so edited values re-color correctly.
        """
        from ...core.format.condformat import scale_context

        sheet = self._sheet()
        self._cond_rules = sheet.cond_rules or []
        # Only a colorscale rule needs a range scan; per-cell rules cost nothing.
        self._scale_ctx = (scale_context(sheet, self._cond_rules)
                           if any(r.kind == "colorscale" for r in self._cond_rules) else {})
        self._cf_cache = {}
        self._populated = None
        used_r, used_c = sheet.used_bounds()
        min_r = max(self._min_rows, getattr(self._win, "_grid_min_rows", self._min_rows))
        min_c = max(self._min_cols, getattr(self._win, "_grid_min_cols", self._min_cols))
        self._grow_to(max(used_r + _MARGIN_ROWS, min_r),
                      max(used_c + _MARGIN_COLS, min_c))
        if self._rows and self._cols:
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(self._rows - 1, self._cols - 1))
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, self._cols - 1)
        self.headerDataChanged.emit(Qt.Orientation.Vertical, 0, self._rows - 1)

    def ensure_extent(self, rows: int, cols: int) -> None:
        """Grow the reported extent so ``(rows-1, cols-1)`` is reachable (cheap)."""
        self._grow_to(max(self._rows, rows), max(self._cols, cols))

    def _grow_to(self, rows: int, cols: int) -> None:
        if cols > self._cols:
            self.beginInsertColumns(QModelIndex(), self._cols, cols - 1)
            self._cols = cols
            self.endInsertColumns()
        if rows > self._rows:
            self.beginInsertRows(QModelIndex(), self._rows, rows - 1)
            self._rows = rows
            self.endInsertRows()
