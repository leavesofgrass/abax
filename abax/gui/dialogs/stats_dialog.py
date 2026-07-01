"""Statistics / analysis tool — run a test over selected columns, show results.

Driven by :mod:`abax.engine.analysis`: descriptive stats, t-test (with Cohen's
d), one-way ANOVA, correlation, OLS regression, Shapiro–Wilk normality, and
Kaplan–Meier survival. Reads a numeric range (a non-numeric first row is taken as
column names), shows the summary (effect sizes + plain-English interpretation),
and writes the result table back into the sheet. Analyses that need optional
packages (scipy/statsmodels/pingouin/lifelines) degrade gracefully — describe and
regression always run; the rest report when their package isn't installed yet.
"""

from __future__ import annotations

from .._qtcompat import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)
from ...core.reference import index_to_col, parse_a1, parse_range, to_a1
from ...engine import analysis as A


def _is_number(value) -> bool:
    if isinstance(value, bool):
        return False
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _fmt(val) -> str:
    if isinstance(val, float):
        return str(int(val)) if val.is_integer() else f"{val:.6g}"
    return "" if val is None else str(val)


class StatsDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Statistics / analysis")
        self.resize(520, 460)
        self._keys = list(A.ANALYSES)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        r1, c1, r2, c2 = self._win._selected_bounds()
        self._in = QLineEdit(f"{to_a1(r1, c1)}:{to_a1(r2, c2)}", self)
        self._op = QComboBox(self)
        for key in self._keys:
            self._op.addItem(A.ANALYSES[key]["label"], key)
        self._op.currentIndexChanged.connect(self._describe_op)
        self._out = QLineEdit(to_a1(r1, max(0, c2 + 2)), self)
        form.addRow("Data (range):", self._in)
        form.addRow("Analysis:", self._op)
        form.addRow("Output top-left:", self._out)
        layout.addLayout(form)

        opts = QHBoxLayout()
        self._paired = QCheckBox("Paired (t-test)", self)
        self._method = QComboBox(self)
        self._method.addItems(["pearson", "spearman"])
        opts.addWidget(self._paired)
        opts.addWidget(QLabel("correlation:", self))
        opts.addWidget(self._method)
        opts.addStretch(1)
        layout.addLayout(opts)

        self._results = QPlainTextEdit(self)
        self._results.setReadOnly(True)
        self._results.setStyleSheet(
            "QPlainTextEdit { font-family: Consolas, monospace; font-size: 12px; }")
        layout.addWidget(self._results, 1)

        row = QHBoxLayout()
        btn = QPushButton("Run", self)
        btn.clicked.connect(self._apply)
        plot = QPushButton("Plot data...", self)
        plot.setToolTip("Open the grapher on the selected data (scatter / spectrum / ROC)")
        plot.clicked.connect(lambda: self._win.show_graph())
        row.addWidget(btn)
        row.addWidget(plot)
        layout.addLayout(row)
        self._describe_op()

    def _describe_op(self) -> None:
        key = self._op.currentData()
        doc = A.ANALYSES[key].get("doc", "")
        ready = "" if A.requirements_met(key) else "  (installs on first run)"
        self._results.setPlainText(f"{doc}{ready}")

    def _read_columns(self, rng: str):
        r1, c1, r2, c2 = parse_range(rng)
        sheet = self._win._doc.workbook.sheet
        raw = [[sheet.get_value(r, c) for r in range(r1, r2 + 1)]
               for c in range(c1, c2 + 1)]
        start = 0
        first = [col[0] if col else None for col in raw]
        if first and all(not _is_number(x) and x not in (None, "") for x in first):
            names = [str(x) for x in first]
            start = 1
        else:
            names = [index_to_col(c) for c in range(c1, c2 + 1)]
        cols = [[float(x) for x in col[start:] if _is_number(x)] for col in raw]
        return names, cols

    def _dispatch(self, key, names, cols):
        if key == "describe":
            return A.describe(cols, names)
        if key == "ttest":
            if len(cols) < 2:
                raise A.AnalysisError("t-test needs two columns")
            return A.ttest(cols[0], cols[1], paired=self._paired.isChecked())
        if key == "anova_oneway":
            return A.anova_oneway(cols, names)
        if key == "correlation":
            return A.correlation(cols, names, method=self._method.currentText())
        if key == "linear_regression":
            if len(cols) < 2:
                raise A.AnalysisError("regression needs a Y column then ≥1 X column")
            return A.linear_regression(cols[0], cols[1:], names)
        if key == "normality":
            return A.normality(cols[0])
        if key == "survival_km":
            if len(cols) < 2:
                raise A.AnalysisError("survival needs durations then events (0/1) columns")
            return A.survival_km(cols[0], [int(round(v)) for v in cols[1]])
        raise A.AnalysisError(f"unknown analysis {key!r}")

    def _apply(self) -> None:
        key = self._op.currentData()
        if not A.requirements_met(key):
            needs = ", ".join(A.ANALYSES[key].get("needs", ()))
            QMessageBox.information(
                self, "Statistics",
                f"“{A.ANALYSES[key]['label']}” needs: {needs}.\n\n"
                "These install automatically on first GUI run — give the background "
                "installer a minute and try again.")
            return
        names, cols = self._read_columns(self._in.text())
        if not any(cols):
            QMessageBox.warning(self, "Statistics", "No numeric data in that range.")
            return
        try:
            result = self._dispatch(key, names, cols)
        except A.AnalysisError as exc:
            QMessageBox.warning(self, "Statistics", str(exc))
            return
        self._write_table(result.table, self._out.text())
        self._results.setPlainText(
            f"{result.title}\n" + "-" * len(result.title) + "\n"
            + "\n".join(result.summary)
            + f"\n\n(result table written at {self._out.text()})")
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        self._win._set_status(f"{result.title}: {result.summary[0] if result.summary else 'done'}")

    def _write_table(self, rows, top_left: str) -> None:
        r0, c0 = parse_a1(top_left)
        sheet = self._win._doc.workbook.sheet
        for i, row in enumerate(rows):
            for j, val in enumerate(row):
                sheet.set_cell(r0 + i, c0 + j, _fmt(val))
