"""Recode / clean column tool — retype, fill blanks, normalize, map, clip, ...

Applies a :mod:`abax.core.recode` operation to each column in the selected range
(raw cell text in, recoded text out) and writes the result back in place. The
single *Options* field is interpreted per operation (a live hint shows the form).
"""

from __future__ import annotations

from .._qtcompat import (
    QComboBox,
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)
from ...core import recode as R
from ...core.reference import parse_range, to_a1

# per-op hint for the Options field
_HINTS = {
    "retype": "target type: int | float | bool | date | text",
    "fill_missing": "method[:fill] — value:0 | mean | median | ffill | bfill | zero",
    "strip_whitespace": "(no options)",
    "to_case": "upper | lower | title",
    "standardize_dates": "output format (default %Y-%m-%d)",
    "map_values": "old=new, old2=new2  (default after a trailing ',' => *)",
    "normalize": "minmax | zscore",
    "clip": "low,high  (blank side = unbounded, e.g. 0, or ,100)",
}


class RecodeDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Recode / clean column")
        self._keys = list(R.OPERATIONS)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        r1, c1, r2, c2 = self._win._selected_bounds()
        self._range = QLineEdit(f"{to_a1(r1, c1)}:{to_a1(r2, c2)}", self)
        self._op = QComboBox(self)
        for key in self._keys:
            self._op.addItem(R.OPERATIONS[key]["label"], key)
        self._op.currentIndexChanged.connect(self._update_hint)
        self._opts = QLineEdit(self)
        self._hint = QLabel(self)
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("color: palette(mid);")
        form.addRow("Column range:", self._range)
        form.addRow("Operation:", self._op)
        form.addRow("Options:", self._opts)
        layout.addLayout(form)
        layout.addWidget(self._hint)
        btn = QPushButton("Apply", self)
        btn.clicked.connect(self._apply)
        layout.addWidget(btn)
        self._update_hint()

    def _update_hint(self) -> None:
        key = self._op.currentData()
        doc = R.OPERATIONS[key].get("doc", "")
        self._hint.setText(f"{doc}\nOptions: {_HINTS.get(key, '')}")

    def _run_op(self, key, values, opt):
        if key == "retype":
            return R.retype(values, opt or "float")
        if key == "fill_missing":
            method, _, fill = opt.partition(":")
            return R.fill_missing(values, method=method or "value", fill=fill)
        if key == "strip_whitespace":
            return R.strip_whitespace(values)
        if key == "to_case":
            return R.to_case(values, opt or "upper")
        if key == "standardize_dates":
            return R.standardize_dates(values, out_fmt=opt or "%Y-%m-%d")
        if key == "map_values":
            mapping, default = {}, None
            for part in opt.split(","):
                k, sep, v = part.partition("=")
                if sep:
                    mapping[k.strip()] = v.strip()
                elif part.strip() == "*":
                    default = ""
            return R.map_values(values, mapping, default=default)
        if key == "normalize":
            return R.normalize(values, method=opt or "minmax")
        if key == "clip":
            lo_s, _, hi_s = opt.partition(",")
            lo = float(lo_s) if lo_s.strip() else None
            hi = float(hi_s) if hi_s.strip() else None
            return R.clip(values, low=lo, high=hi)
        raise R.RecodeError(f"unknown op {key!r}")

    def _apply(self) -> None:
        key = self._op.currentData()
        opt = self._opts.text().strip()
        try:
            r1, c1, r2, c2 = parse_range(self._range.text())
        except Exception as exc:
            QMessageBox.warning(self, "Recode", f"Bad range: {exc}")
            return
        sheet = self._win._doc.workbook.sheet
        changed = 0
        try:
            for c in range(c1, c2 + 1):
                values = []
                for r in range(r1, r2 + 1):
                    v = sheet.get_value(r, c)
                    values.append("" if v is None else str(v))
                out = self._run_op(key, values, opt)
                for i, new in enumerate(out):
                    if new != values[i]:
                        sheet.set_cell(r1 + i, c, new)
                        changed += 1
        except (R.RecodeError, ValueError) as exc:
            QMessageBox.warning(self, "Recode", str(exc))
            return
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        self._win._set_status(
            f"{R.OPERATIONS[key]['label']}: recoded {changed} cell(s)")
        self.accept()
