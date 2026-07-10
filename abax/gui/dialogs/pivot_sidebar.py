"""PivotTable Fields sidebar — a drag-drop dock over :func:`core.pivotspec.build_pivot`.

Mirrors Excel's PivotTable Fields pane: a list of source columns and four drop
areas — **Filters**, **Columns**, **Rows**, **Values**. Fields are dragged (or,
for reliability/accessibility, added with the ``→`` buttons) from the source list
into the areas; a live preview updates on every change and **Insert** writes the
result into the sheet at an anchor cell.

The widget keeps a strict split from the logic: every area's contents are read
into a :class:`~abax.core.pivotspec.PivotSpec` and rendered by the pure
``build_pivot`` — so the pivot maths is unit-tested elsewhere and this file is a
thin, drivable shell (``add_to`` / ``current_spec`` / ``refresh_preview`` /
``do_insert`` are callable without real drag events).
"""

from __future__ import annotations

from .._qtcompat import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from ...core import pivot as P
from ...core.pivotspec import ALL, PivotSpec, build_pivot, field_names, filter_values
from ...core.reference import parse_a1, parse_range, to_a1

_FIELD_ROLE = Qt.ItemDataRole.UserRole
_AGG_ROLE = Qt.ItemDataRole.UserRole + 1
_PREVIEW_CAP = 200  # rows shown in the preview table (the full result is inserted)


class _FieldArea(QListWidget):
    """A drop target holding field names; notifies on any change via *on_changed*."""

    def __init__(self, kind: str, on_changed, *, source: bool = False) -> None:
        super().__init__()
        self.kind = kind
        self._on_changed = on_changed
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        if source:
            # The source list keeps its fields (copy out), never accepts drops.
            self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
            self.setDefaultDropAction(Qt.DropAction.CopyAction)
        else:
            self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
            self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().dropEvent(event)
        if self._on_changed is not None:
            self._on_changed()


class PivotSidebar(QDockWidget):
    """Dockable PivotTable Fields pane bound to the active window/sheet."""

    def __init__(self, window) -> None:
        super().__init__("PivotTable Fields", window)
        self._win = window
        self.setObjectName("PivotSidebar")
        self._build()

    # -- construction ------------------------------------------------------

    def _build(self) -> None:
        # field -> chosen keep-value for the per-field filter picker (ALL = none).
        self._filter_vals: dict[str, str] = {}
        root = QWidget()
        outer = QVBoxLayout(root)

        # Source range + load.
        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("Data range:"))
        self._range = QLineEdit(self._default_range())
        src_row.addWidget(self._range)
        load = QPushButton("Load fields")
        load.clicked.connect(self.reload_fields)
        src_row.addWidget(load)
        outer.addLayout(src_row)

        # Source field list + add-to buttons.
        outer.addWidget(QLabel("Fields:"))
        self._source = _FieldArea("source", None, source=True)
        outer.addWidget(self._source)
        add_row = QHBoxLayout()
        for label, kind in (("→ Rows", "rows"), ("→ Cols", "columns"),
                            ("→ Values", "values"), ("→ Filter", "filters")):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, k=kind: self._add_selected_source(k))
            add_row.addWidget(b)
        outer.addLayout(add_row)

        # The four areas.
        self._areas: dict[str, _FieldArea] = {}
        for kind, title in (("filters", "Filters"), ("columns", "Columns"),
                            ("rows", "Rows"), ("values", "Values")):
            box = QGroupBox(title)
            lay = QVBoxLayout(box)
            area = _FieldArea(kind, self._on_changed)
            area.itemSelectionChanged.connect(self._sync_agg_combo)
            self._areas[kind] = area
            lay.addWidget(area)
            outer.addWidget(box)

        # Per-field filter value picker (enabled when a Filters field is selected).
        filt_row = QHBoxLayout()
        filt_row.addWidget(QLabel("Keep value:"))
        self._filter_combo = QComboBox()
        self._filter_combo.setEnabled(False)
        self._filter_combo.currentIndexChanged.connect(self._apply_filter_value)
        filt_row.addWidget(self._filter_combo)
        outer.addLayout(filt_row)
        self._areas["filters"].itemSelectionChanged.connect(self._sync_filter_combo)

        # Values aggregation + remove.
        agg_row = QHBoxLayout()
        agg_row.addWidget(QLabel("Summarize:"))
        self._agg = QComboBox()
        for key, label in P.AGGREGATIONS.items():
            self._agg.addItem(label, key)
        self._agg.currentIndexChanged.connect(self._apply_agg_to_selected)
        agg_row.addWidget(self._agg)
        remove = QPushButton("Remove")
        remove.clicked.connect(self._remove_selected)
        agg_row.addWidget(remove)
        outer.addLayout(agg_row)

        # Options.
        opt_row = QHBoxLayout()
        self._totals = QCheckBox("Grand totals")
        self._totals.stateChanged.connect(self._on_changed)
        opt_row.addWidget(self._totals)
        opt_row.addWidget(QLabel("% of:"))
        self._pct = QComboBox()
        self._pct.addItem("none", None)
        for m in ("grand", "row", "col"):
            self._pct.addItem(m, m)
        self._pct.currentIndexChanged.connect(self._on_changed)
        opt_row.addWidget(self._pct)
        outer.addLayout(opt_row)

        # Preview + insert.
        outer.addWidget(QLabel("Preview:"))
        self._preview = QTableWidget(0, 0)
        self._preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        outer.addWidget(self._preview)
        ins_row = QHBoxLayout()
        ins_row.addWidget(QLabel("Insert at:"))
        self._out = QLineEdit("A1")
        ins_row.addWidget(self._out)
        ins_btn = QPushButton("Insert into sheet")
        ins_btn.clicked.connect(self.do_insert)
        ins_row.addWidget(ins_btn)
        outer.addLayout(ins_row)

        self._status = QLabel("")
        outer.addWidget(self._status)

        self.setWidget(root)
        self.reload_fields()

    # -- data access -------------------------------------------------------

    def _default_range(self) -> str:
        sheet = self._win._doc.workbook.sheet
        try:
            n_rows, n_cols = sheet.used_bounds()
        except Exception:  # noqa: BLE001
            n_rows = n_cols = 0
        if n_rows and n_cols:
            return f"A1:{to_a1(n_rows - 1, n_cols - 1)}"
        return "A1:D20"

    def _rows(self) -> list[list[str]]:
        r1, c1, r2, c2 = parse_range(self._range.text())
        sheet = self._win._doc.workbook.sheet
        out = []
        for r in range(r1, r2 + 1):
            row = []
            for c in range(c1, c2 + 1):
                v = sheet.get_value(r, c)
                row.append("" if v is None else str(v))
            out.append(row)
        return out

    def reload_fields(self) -> None:
        """Repopulate the source list from the current data range's header."""
        try:
            names = field_names(self._rows())
        except Exception as exc:  # noqa: BLE001 — bad range → empty, with a note
            self._status.setText(f"range error: {exc}")
            names = []
        self._source.clear()
        for name in names:
            self._source.addItem(name)
        self.refresh_preview()

    # -- area helpers (also the programmatic/test API) ---------------------

    def add_to(self, kind: str, field: str, agg: str = "sum") -> None:
        """Add *field* to area *kind* (``rows``/``columns``/``values``/``filters``)."""
        area = self._areas[kind]
        # Avoid duplicates within one area.
        for i in range(area.count()):
            if area.item(i).data(_FIELD_ROLE) == field:
                return
        area.addItem(field)
        item = area.item(area.count() - 1)
        item.setData(_FIELD_ROLE, field)
        if kind == "values":
            item.setData(_AGG_ROLE, agg)
        self._on_changed()

    def _add_selected_source(self, kind: str) -> None:
        it = self._source.currentItem()
        if it is not None:
            self.add_to(kind, it.text())

    def _remove_selected(self) -> None:
        for area in self._areas.values():
            row = area.currentRow()
            if row >= 0 and area.hasFocus():
                area.takeItem(row)
                self._on_changed()
                return
        # No focused area: remove from Values by default if one is selected.
        vals = self._areas["values"]
        if vals.currentRow() >= 0:
            vals.takeItem(vals.currentRow())
            self._on_changed()

    def _field_of(self, item) -> str:
        return item.data(_FIELD_ROLE) or item.text()

    def _sync_agg_combo(self) -> None:
        it = self._areas["values"].currentItem()
        if it is None:
            return
        agg = it.data(_AGG_ROLE) or "sum"
        idx = self._agg.findData(agg)
        if idx >= 0:
            self._agg.blockSignals(True)
            self._agg.setCurrentIndex(idx)
            self._agg.blockSignals(False)

    def _apply_agg_to_selected(self) -> None:
        it = self._areas["values"].currentItem()
        if it is None:
            return
        it.setData(_AGG_ROLE, self._agg.currentData())
        self._on_changed()

    def _normalize(self) -> None:
        """Keep item text/data coherent after drags between areas."""
        for kind, area in self._areas.items():
            for i in range(area.count()):
                item = area.item(i)
                field = self._field_of(item)
                item.setData(_FIELD_ROLE, field)
                if kind == "values":
                    agg = item.data(_AGG_ROLE) or "sum"
                    item.setData(_AGG_ROLE, agg)
                    item.setText(f"{agg} of {field}")
                else:
                    item.setText(field)

    # -- spec + preview + insert -------------------------------------------

    def current_spec(self) -> PivotSpec:
        self._normalize()
        rows_f = [self._field_of(self._areas["rows"].item(i))
                  for i in range(self._areas["rows"].count())]
        cols = [self._field_of(self._areas["columns"].item(i))
                for i in range(self._areas["columns"].count())]
        vals, aggs = [], []
        varea = self._areas["values"]
        for i in range(varea.count()):
            it = varea.item(i)
            vals.append(self._field_of(it))
            aggs.append(it.data(_AGG_ROLE) or "sum")
        filters = {}
        for i in range(self._areas["filters"].count()):
            f = self._field_of(self._areas["filters"].item(i))
            filters[f] = self._filter_vals.get(f, ALL)
        return PivotSpec(
            row_fields=rows_f,
            column_field=cols[0] if cols else None,
            value_fields=vals, aggs=aggs, filters=filters,
            margins=self._totals.isChecked(),
            pct_of=self._pct.currentData(),
        )

    def set_filter_value(self, field: str, value: str) -> None:
        """Set the keep-value for a Filters *field* (:data:`ALL` = no restriction).

        The programmatic counterpart to the keep-value picker, so headless tests
        (and callers) can choose a filter's slice without a real combo event.
        """
        self._filter_vals[field] = value
        cur = self._areas["filters"].currentItem()
        if cur is not None and self._field_of(cur) == field:
            self._sync_filter_combo()
        self._on_changed()

    def _sync_filter_combo(self) -> None:
        """Repopulate the keep-value picker for the currently selected filter."""
        combo = self._filter_combo
        it = self._areas["filters"].currentItem()
        combo.blockSignals(True)
        combo.clear()
        if it is None:
            combo.setEnabled(False)
            combo.blockSignals(False)
            return
        field = self._field_of(it)
        try:
            options = filter_values(self._rows(), field)
        except Exception:  # noqa: BLE001 — bad range → just offer "no restriction"
            options = [ALL]
        combo.addItems(options)
        idx = combo.findText(self._filter_vals.get(field, ALL))
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.setEnabled(True)
        combo.blockSignals(False)

    def _apply_filter_value(self) -> None:
        it = self._areas["filters"].currentItem()
        if it is None:
            return
        self._filter_vals[self._field_of(it)] = self._filter_combo.currentText() or ALL
        self._on_changed()

    def _on_changed(self) -> None:
        self.refresh_preview()

    def build(self) -> "list[list[str]] | None":
        """Return the pivot result, or ``None`` (with a status note) on error."""
        try:
            return build_pivot(self._rows(), self.current_spec())
        except (P.PivotError, ValueError) as exc:
            self._status.setText(str(exc))
            return None

    def refresh_preview(self) -> None:
        out = self.build()
        if out is None:
            self._preview.setRowCount(0)
            self._preview.setColumnCount(0)
            return
        self._status.setText(f"{len(out) - 1} row(s) × {len(out[0]) if out else 0} col(s)")
        shown = out[:_PREVIEW_CAP + 1]
        self._preview.setColumnCount(len(shown[0]) if shown else 0)
        self._preview.setRowCount(max(0, len(shown) - 1))
        if shown:
            self._preview.setHorizontalHeaderLabels([str(h) for h in shown[0]])
        for i, row in enumerate(shown[1:]):
            for j, val in enumerate(row):
                self._preview.setItem(i, j, QTableWidgetItem(str(val)))

    def do_insert(self) -> None:
        out = self.build()
        if out is None:
            QMessageBox.warning(self, "PivotTable", self._status.text() or "nothing to insert")
            return
        try:
            r0, c0 = parse_a1(self._out.text())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "PivotTable", f"bad anchor: {exc}")
            return
        sheet = self._win._doc.workbook.sheet
        for i, row in enumerate(out):
            for j, val in enumerate(row):
                sheet.set_cell(r0 + i, c0 + j, str(val))
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        self._status.setText(f"inserted {len(out) - 1} row(s) at {self._out.text()}")
