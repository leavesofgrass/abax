"""DataFrame viewer — open the selected range as a typed pandas DataFrame.

Uses :mod:`abax.core.typeinfer` to coerce each column to its inferred type
(int/float/bool/date/text), then shows the shape, dtypes, ``describe()`` and a
head preview. ``describe()`` can be written back into the sheet. Requires pandas
(auto-installs on first GUI run); reports cleanly when it isn't ready yet.
"""

from __future__ import annotations

from .._qtcompat import (
    QDialog,
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)
from ...core import typeinfer
from ...core.reference import index_to_col, to_a1


class DataFrameDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("DataFrame viewer (pandas)")
        self.resize(620, 520)
        self._df = None
        self._anchor = (0, 0)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        self._view = QPlainTextEdit(self)
        self._view.setReadOnly(True)
        self._view.setStyleSheet(
            "QPlainTextEdit { font-family: Consolas, monospace; font-size: 12px; }")
        layout.addWidget(self._view, 1)

        btns = QHBoxLayout()
        self._desc_btn = QPushButton("Write describe() to sheet", self)
        self._desc_btn.clicked.connect(self._write_describe)
        close = QPushButton("Close", self)
        close.clicked.connect(self.close)
        btns.addStretch(1)
        btns.addWidget(self._desc_btn)
        btns.addWidget(close)
        layout.addLayout(btns)

        self._load()

    def _load(self) -> None:
        try:
            import pandas as pd
        except Exception:
            self._view.setPlainText(
                "pandas is not installed yet.\n\n"
                "It installs automatically on first GUI run — give the background "
                "installer a minute, then reopen this viewer.")
            self._desc_btn.setEnabled(False)
            return

        r1, c1, r2, c2 = self._win._selected_bounds()
        sheet = self._win._doc.workbook.sheet
        block = [[sheet.get_value(r, c) for c in range(c1, c2 + 1)]
                 for r in range(r1, r2 + 1)]
        str_rows = [["" if v is None else str(v) for v in row] for row in block]
        # header = a non-numeric first row
        has_header = bool(str_rows) and all(
            typeinfer.infer_value_type(v) in ("text", "empty") for v in str_rows[0])
        names = (str_rows[0] if has_header
                 else [index_to_col(c) for c in range(c1, c2 + 1)])
        types = typeinfer.infer_types(str_rows, header=has_header)
        data = str_rows[1:] if has_header else str_rows
        columns = {}
        for j, name in enumerate(names):
            t = types[j] if j < len(types) else "text"
            columns[str(name)] = [
                typeinfer.coerce(row[j] if j < len(row) else "", t) for row in data]
        df = pd.DataFrame(columns)
        self._df = df
        self._anchor = (r1, max(0, c2 + 2))

        out = [f"shape: {df.shape[0]} rows × {df.shape[1]} columns", "", "dtypes:",
               df.dtypes.to_string(), "", "describe():"]
        try:
            out.append(df.describe(include="all").to_string())
        except Exception as exc:
            out.append(f"(describe unavailable: {exc})")
        out += ["", "head(20):", df.head(20).to_string()]
        self._view.setPlainText("\n".join(out))

    def _write_describe(self) -> None:
        if self._df is None:
            return
        try:
            desc = self._df.describe(include="all")
        except Exception as exc:
            QMessageBox.warning(self, "DataFrame", f"describe() failed: {exc}")
            return
        r0, c0 = self._anchor
        sheet = self._win._doc.workbook.sheet
        sheet.set_cell(r0, c0, "statistic")
        for j, name in enumerate(desc.columns):
            sheet.set_cell(r0, c0 + 1 + j, str(name))
        for i, stat in enumerate(desc.index):
            sheet.set_cell(r0 + 1 + i, c0, str(stat))
            for j, name in enumerate(desc.columns):
                val = desc.iloc[i, j]
                sheet.set_cell(r0 + 1 + i, c0 + 1 + j,
                               "" if val is None else str(val))
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        self._win._set_status(
            f"describe() written at {to_a1(r0, c0)}")
        self.close()
