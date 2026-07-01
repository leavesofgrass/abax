"""Find / Replace dialog — regex-capable, backed by core.search.

Modeless so the user can keep navigating the grid. Find Next steps the selection
through matches; Replace All rewrites every matching cell and refreshes.
"""

from __future__ import annotations

from .._qtcompat import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)
from ...core.search import SearchError, SearchOptions, find_all, replace_all


class FindReplaceDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self._matches = []
        self._idx = 0
        self._last_key = None
        self.setWindowTitle("Find / Replace")
        self.setModal(False)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._find = QLineEdit(self)
        self._repl = QLineEdit(self)
        form.addRow("Find:", self._find)
        form.addRow("Replace:", self._repl)
        layout.addLayout(form)

        opts = QHBoxLayout()
        self._regex = QCheckBox("Regex", self)
        self._regex.setChecked(True)
        self._case = QCheckBox("Case", self)
        self._whole = QCheckBox("Whole cell", self)
        self._formula = QCheckBox("In formulas", self)
        self._formula.setChecked(True)
        self._selection = QCheckBox("Selection only", self)
        self._selection.setToolTip("Limit find/replace to the selected cells")
        for cb in (self._regex, self._case, self._whole, self._formula, self._selection):
            opts.addWidget(cb)
        layout.addLayout(opts)

        btns = QHBoxLayout()
        b_find = QPushButton("Find Next", self)
        b_repl = QPushButton("Replace", self)
        b_all = QPushButton("Replace All", self)
        b_close = QPushButton("Close", self)
        b_find.clicked.connect(self.find_next)
        b_repl.clicked.connect(self.replace_current)
        b_all.clicked.connect(self.replace_all)
        b_close.clicked.connect(self.close)
        for b in (b_find, b_repl, b_all, b_close):
            btns.addWidget(b)
        layout.addLayout(btns)

        self._status = QLabel("", self)
        layout.addWidget(self._status)
        self._find.returnPressed.connect(self.find_next)

    def _options(self) -> SearchOptions:
        return SearchOptions(
            regex=self._regex.isChecked(),
            case_sensitive=self._case.isChecked(),
            whole_cell=self._whole.isChecked(),
            use_formula=self._formula.isChecked(),
        )

    def _sheet(self):
        return self._win._doc.workbook.sheet

    def _scope(self):
        """An 'A1:C9' range when 'Selection only' is on and cells are selected."""
        if not self._selection.isChecked():
            return None
        ranges = self._win._table.selectedRanges()
        if not ranges:
            return None
        from ...core.reference import to_a1

        r = ranges[0]
        return (f"{to_a1(r.topRow(), r.leftColumn())}:"
                f"{to_a1(r.bottomRow(), r.rightColumn())}")

    def find_next(self) -> None:
        pattern = self._find.text()
        if not pattern:
            return
        scope = self._scope()
        key = (pattern, repr(self._options()), scope)
        try:
            if key != self._last_key:
                self._matches = find_all(self._sheet(), pattern, self._options(), scope)
                self._idx = 0
                self._last_key = key
        except SearchError as exc:
            self._status.setText(f"bad pattern: {exc}")
            return
        if not self._matches:
            self._status.setText("no matches")
            return
        m = self._matches[self._idx % len(self._matches)]
        self._win._table.setCurrentCell(m.row, m.col)
        self._status.setText(f"match {self._idx % len(self._matches) + 1} of {len(self._matches)} — {m.ref}")
        self._idx += 1

    def replace_current(self) -> None:
        from ...core.search import replace_match

        if not self._matches:
            self.find_next()
            return
        m = self._matches[(self._idx - 1) % len(self._matches)]
        try:
            replace_match(self._sheet(), m, self._find.text(), self._repl.text(),
                          self._options(), on_set=self._win._record)
        except SearchError as exc:
            self._status.setText(f"bad pattern: {exc}")
            return
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        self._last_key = None  # force re-find (positions changed)
        self.find_next()

    def replace_all(self) -> None:
        try:
            n = replace_all(self._sheet(), self._find.text(), self._repl.text(),
                            self._options(), self._scope(), on_set=self._win._record)
        except SearchError as exc:
            self._status.setText(f"bad pattern: {exc}")
            return
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        self._last_key = None
        self._status.setText(f"replaced in {n} cell(s)")
