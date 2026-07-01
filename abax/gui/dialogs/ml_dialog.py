"""ML tool — PCA, k-means clustering, and regression over a data matrix.

Reads a numeric range as a samples×features matrix, runs an operation from
:mod:`abax.core.science.ml` / :mod:`abax.core.science.cluster`, and writes the result
(transformed scores, cluster labels, coefficients) back to the grid.
"""

from __future__ import annotations

from .._qtcompat import (
    QComboBox,
    QDialog,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
)
from ...core.reference import parse_a1, parse_range, to_a1
from ...core.science import cluster as CL
from ...core.science import ml as ML

_OPS = [
    "PCA (param = #components)",
    "K-means (param = k)",
    "GMM cluster (param = #components)",
    "Linear regression (last col = y)",
    "Standardize (z-score)",
    "Decision tree classify (last col = y)",
    "Random forest classify (last col = y)",
    "Naive Bayes classify (last col = y)",
]


class MLDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("ML tool")
        self._build()

    def _build(self) -> None:
        form = QFormLayout(self)
        r1, c1, r2, c2 = self._win._selected_bounds()
        self._in = QLineEdit(f"{to_a1(r1, c1)}:{to_a1(r2, c2)}", self)
        self._op = QComboBox(self)
        self._op.addItems(_OPS)
        self._param = QLineEdit("2", self)
        self._param.setToolTip("number of PCA components, or k for k-means")
        self._out = QLineEdit(to_a1(r1, max(0, c2 + 2)), self)
        form.addRow("Data (range):", self._in)
        form.addRow("Operation:", self._op)
        form.addRow("Param:", self._param)
        form.addRow("Output top-left:", self._out)
        btn = QPushButton("Run", self)
        btn.clicked.connect(self._apply)
        form.addRow(btn)

    def _read_matrix(self, rng: str) -> list[list[float]]:
        r1, c1, r2, c2 = parse_range(rng)
        sheet = self._win._doc.workbook.sheet
        rows: list[list[float]] = []
        for r in range(r1, r2 + 1):
            row = []
            for c in range(c1, c2 + 1):
                v = sheet.get_value(r, c)
                row.append(float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0)
            rows.append(row)
        return rows

    def _write(self, rows, top_left: str) -> None:
        r0, c0 = parse_a1(top_left)
        sheet = self._win._doc.workbook.sheet
        for i, row in enumerate(rows):
            cells = row if isinstance(row, (list, tuple)) else [row]
            for j, v in enumerate(cells):
                sheet.set_cell(r0 + i, c0 + j, _fmt(v))

    def _read_labels(self) -> list:
        """Read the LAST column of the range as raw values (supports string classes)."""
        r1, _c1, r2, c2 = parse_range(self._in.text())
        sheet = self._win._doc.workbook.sheet
        return [sheet.get_value(r, c2) if sheet.get_value(r, c2) is not None else ""
                for r in range(r1, r2 + 1)]

    def _classify(self, op: str, X) -> None:
        from ...core.science import bayes, trees
        from ...core.science.metrics import accuracy

        xs = [row[:-1] for row in X]
        ys = self._read_labels()
        if not xs or not xs[0]:
            raise ValueError("need ≥1 feature column plus a label column")
        if op.startswith("Decision tree"):
            model = trees.DecisionTreeClassifier(seed=0)
        elif op.startswith("Random forest"):
            model = trees.RandomForestClassifier(seed=0)
        else:
            model = bayes.GaussianNB()
        model.fit(xs, ys)
        preds = model.predict(xs)
        acc = accuracy(ys, preds)
        self._write([[str(p)] for p in preds], self._out.text())
        self._win._set_status(f"{op.split('(')[0].strip()}: train accuracy={acc:.3f}")

    def _apply(self) -> None:
        X = self._read_matrix(self._in.text())
        if len(X) < 2 or not X[0]:
            QMessageBox.warning(self, "ML", "Select a numeric data matrix (≥2 rows).")
            return
        op = self._op.currentText()
        try:
            if op.startswith("PCA"):
                n = int(float(self._param.text()))
                comps, ratio, transformed = ML.pca(X, n)
                self._write(transformed, self._out.text())
                self._win._set_status(
                    "PCA explained variance: "
                    + ", ".join(f"{x:.3f}" for x in ratio[:n]))
            elif op.startswith("K-means"):
                k = int(float(self._param.text()))
                labels, centroids, inertia = CL.kmeans(X, k, seed=0)
                self._write([[lab] for lab in labels], self._out.text())
                self._win._set_status(
                    f"k-means: k={k}, inertia={inertia:.4g} (labels written)")
            elif op.startswith("GMM"):
                from ...core.science.gmm import GaussianMixture

                k = int(float(self._param.text()))
                gm = GaussianMixture(k, seed=0).fit(X)
                self._write([[lab] for lab in gm.predict(X)], self._out.text())
                self._win._set_status(
                    f"GMM: {k} comps, BIC={gm.bic(X):.1f} (labels written)")
            elif op.startswith("Linear"):
                ys = [row[-1] for row in X]
                xs = [row[:-1] for row in X]
                coeffs, intercept = ML.linear_regression(xs, ys)
                preds = ML.predict_linear(coeffs, intercept, xs)
                r2 = ML.r_squared(ys, preds)
                self._write(
                    [["intercept", intercept]]
                    + [[f"b{i+1}", c] for i, c in enumerate(coeffs)]
                    + [["R^2", r2]], self._out.text())
                self._win._set_status(f"linear regression: R²={r2:.4f}")
            elif op.startswith("Standardize"):
                Xs, _means, _stds = ML.standardize(X)
                self._write(Xs, self._out.text())
                self._win._set_status("standardized (z-score)")
            elif "classify" in op:
                self._classify(op, X)
        except (ML.MLError, CL.ClusterError, ValueError, ZeroDivisionError) as exc:
            QMessageBox.warning(self, "ML", str(exc))
            return
        except Exception as exc:  # trees.TreeError / bayes.BayesError
            QMessageBox.warning(self, "ML", str(exc))
            return
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        self.accept()


def _fmt(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, int):
        return str(v)
    return str(int(v)) if isinstance(v, float) and v.is_integer() else f"{v:.6g}"
