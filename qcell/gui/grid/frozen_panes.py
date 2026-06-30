"""Freeze panes for the cell grid — keep top rows / left columns pinned.

QTableView has no native frozen panes, so this overlays read-only mirror *views*
on top of the main grid: a *top* overlay shows the frozen rows (all columns,
horizontally scroll-synced) and a *left* overlay shows the frozen columns
(vertically scroll-synced).

The overlays **share the main grid's model and selection model**, so they
virtualize exactly like the main view — no per-cell items are materialized, and
they repaint automatically when the model changes. :meth:`sync` only repositions
them and matches column widths; row heights are uniform, so there is no row loop
(the old item-mirroring overlay built one widget per row, defeating the point of
the virtualized grid).
"""

from __future__ import annotations

from .._qtcompat import QAbstractItemView, QEvent, QObject, Qt, QTableView


class FrozenPanes(QObject):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self._main: QTableView = window._table
        self.rows = 0
        self.cols = 0
        self._top: QTableView | None = None
        self._left: QTableView | None = None
        self._main.horizontalScrollBar().valueChanged.connect(self._scroll)
        self._main.verticalScrollBar().valueChanged.connect(self._scroll)
        self._main.horizontalHeader().sectionResized.connect(self._on_section)
        self._main.verticalHeader().sectionResized.connect(self._on_section)
        self._main.viewport().installEventFilter(self)

    # -- public API --------------------------------------------------------

    def freeze(self, rows: int, cols: int) -> None:
        self.rows = max(0, rows)
        self.cols = max(0, cols)
        self._rebuild()
        self.sync()

    def freeze_at_cursor(self) -> None:
        self.freeze(max(0, self._main.currentRow()), max(0, self._main.currentColumn()))

    def unfreeze(self) -> None:
        self.freeze(0, 0)

    @property
    def active(self) -> bool:
        return self.rows > 0 or self.cols > 0

    # -- overlay construction ---------------------------------------------

    def _make_overlay(self) -> QTableView:
        ov = QTableView(self._main)
        ov.setModel(self._main.model())
        ov.setSelectionModel(self._main.selectionModel())  # selection shows through
        ov.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        ov.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        ov.horizontalHeader().hide()
        ov.verticalHeader().hide()
        ov.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        ov.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        ov.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        ov.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        ov.setFrameShape(QTableView.Shape.NoFrame)
        ov.setAlternatingRowColors(self._main.alternatingRowColors())
        ov.setShowGrid(self._main.showGrid())
        ov.setFont(self._main.font())
        ov.setStyleSheet("QTableView { border: 1px solid #5a6072; }")
        return ov

    def _rebuild(self) -> None:
        for ov in (self._top, self._left):
            if ov is not None:
                ov.deleteLater()
        self._top = self._make_overlay() if self.rows > 0 else None
        self._left = self._make_overlay() if self.cols > 0 else None

    # -- sync (position + sizing + scroll) --------------------------------

    def sync(self) -> None:
        if not self.active:
            return
        m = self._main
        vh_w = m.verticalHeader().width()
        hh_h = m.horizontalHeader().height()
        frozen_h = sum(m.rowHeight(r) for r in range(self.rows))
        frozen_w = sum(m.columnWidth(c) for c in range(self.cols))
        vp = m.viewport()

        if self._top is not None:
            self._match_columns(self._top)
            self._top.verticalScrollBar().setValue(0)  # pinned to the frozen rows
            self._top.setGeometry(vh_w, hh_h, vp.width(), frozen_h)
            self._top.raise_()
        if self._left is not None:
            self._match_columns(self._left)
            self._left.horizontalScrollBar().setValue(0)  # pinned to the frozen cols
            self._left.setGeometry(vh_w, hh_h + frozen_h, frozen_w, vp.height() - frozen_h)
            self._left.raise_()
        self._scroll()

    def _match_columns(self, ov: QTableView) -> None:
        # Overlays share the model but keep independent column widths; match the
        # main grid so columns line up. Cheap (a handful of columns). Row heights
        # are uniform and align via ScrollPerPixel scroll-sync, so no row loop.
        m = self._main
        ov.verticalHeader().setDefaultSectionSize(m.verticalHeader().defaultSectionSize())
        for c in range(m.columnCount()):
            ov.setColumnWidth(c, m.columnWidth(c))

    def _scroll(self) -> None:
        if self._top is not None:
            self._top.horizontalScrollBar().setValue(self._main.horizontalScrollBar().value())
        if self._left is not None:
            self._left.verticalScrollBar().setValue(self._main.verticalScrollBar().value())

    def _on_section(self, *_a) -> None:
        self.sync()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt override)
        if self.active and event.type() == QEvent.Type.Resize:
            self.sync()
        return False
