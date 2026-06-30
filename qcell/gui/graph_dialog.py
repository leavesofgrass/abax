"""Function grapher — HP-48 flavored, painted with QPainter (no matplotlib).

Plot a math expression of ``x`` over a range, or plot the selected column of the
grid as a series. Backed by :mod:`qcell.core.graphing`.
"""

from __future__ import annotations

from ._qtcompat import (
    QColor,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPainter,
    QPen,
    QPointF,
    QPushButton,
    Qt,
    QVBoxLayout,
    QWidget,
)
from ..core.graphing import GraphError, sample


class _Canvas(QWidget):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.points: list = []
        self.heatmap: list | None = None   # frames x bins (e.g. spectrogram dB)
        self.scatter: list | None = None   # [(x, y, (r,g,b)), …]
        self.scatter_label: str = ""
        self.scatter_line: tuple | None = None   # (slope, intercept) overlay
        self.roc: tuple | None = None       # (fpr_list, tpr_list, auc_value)
        self.bars: tuple | None = None      # (edges, counts) for a histogram
        self.setMinimumSize(480, 320)

    def _clear_modes(self) -> None:
        self.points = []
        self.heatmap = None
        self.scatter = None
        self.scatter_line = None
        self.roc = None
        self.bars = None

    def set_bars(self, edges, counts, label: str = "") -> None:
        """Histogram bars: ``edges`` are bin boundaries, ``counts`` the bar heights."""
        self._clear_modes()
        self.bars = (edges, counts)
        self.scatter_label = label
        self.update()

    def _paint_bars(self, p, w, h) -> None:
        edges, counts = self.bars
        if not counts:
            return
        pad = 30
        cmax = max(counts) or 1
        n = len(counts)
        bw = (w - 2 * pad) / n
        p.setPen(QPen(QColor("#3b4252"), 1))
        p.drawLine(pad, h - pad, w - pad, h - pad)
        for i, c in enumerate(counts):
            bh = (c / cmax) * (h - 2 * pad)
            x = pad + i * bw
            p.fillRect(int(x + 1), int(h - pad - bh), int(max(1, bw - 2)), int(bh),
                       QColor("#88c0d0"))
        p.setPen(QColor("#cdd1d7"))
        p.drawText(pad, pad - 10, self.scatter_label)
        p.drawText(pad, h - 8, f"{edges[0]:g}")
        p.drawText(int(w - pad - 44), h - 8, f"{edges[-1]:g}")

    def set_points(self, points) -> None:
        self._clear_modes()
        self.points = [(x, y) for x, y in points if y is not None]
        self.update()

    def set_heatmap(self, frames) -> None:
        """``frames`` is a list of frames (x = time), each a list of bin values (y = freq)."""
        self._clear_modes()
        self.heatmap = frames
        self.update()

    def set_scatter(self, pts, label: str = "", line=None) -> None:
        """``pts`` is a list of ``(x, y, (r, g, b))`` coloured points; ``line`` is an
        optional ``(slope, intercept)`` regression line to overlay."""
        self._clear_modes()
        self.scatter = pts
        self.scatter_label = label
        self.scatter_line = line
        self.update()

    def set_roc(self, fpr, tpr, auc_value: float) -> None:
        self._clear_modes()
        self.roc = (fpr, tpr, auc_value)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#11131a"))
        w, h = self.width(), self.height()
        if self.heatmap is not None:
            self._paint_heatmap(p, w, h)
            return
        if self.scatter is not None:
            self._paint_scatter(p, w, h)
            return
        if self.roc is not None:
            self._paint_roc(p, w, h)
            return
        if self.bars is not None:
            self._paint_bars(p, w, h)
            return
        if not self.points:
            return
        xs = [x for x, _ in self.points]
        ys = [y for _, y in self.points]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        if xmax == xmin:
            xmax += 1
        if ymax == ymin:
            ymax += 1
        pad = 28

        def sx(x):
            return pad + (x - xmin) / (xmax - xmin) * (w - 2 * pad)

        def sy(y):
            return h - pad - (y - ymin) / (ymax - ymin) * (h - 2 * pad)

        # axes
        p.setPen(QPen(QColor("#3b4252"), 1))
        if ymin <= 0 <= ymax:
            p.drawLine(int(pad), int(sy(0)), int(w - pad), int(sy(0)))
        if xmin <= 0 <= xmax:
            p.drawLine(int(sx(0)), int(pad), int(sx(0)), int(h - pad))
        p.setPen(QPen(QColor("#6c7086"), 1))
        p.drawText(4, h - 6, f"x:[{xmin:g},{xmax:g}]  y:[{ymin:g},{ymax:g}]")
        # curve
        p.setPen(QPen(QColor("#88c0d0"), 2))
        last = None
        for x, y in self.points:
            px, py = sx(x), sy(y)
            if last is not None:
                p.drawLine(int(last[0]), int(last[1]), int(px), int(py))
            last = (px, py)

    def _paint_roc(self, p, w, h) -> None:
        fpr, tpr, auc_value = self.roc
        pad = 36

        def sx(x):
            return pad + x * (w - 2 * pad)

        def sy(y):
            return h - pad - y * (h - 2 * pad)

        # unit axes + chance diagonal
        p.setPen(QPen(QColor("#3b4252"), 1))
        p.drawLine(int(sx(0)), int(sy(0)), int(sx(1)), int(sy(0)))
        p.drawLine(int(sx(0)), int(sy(0)), int(sx(0)), int(sy(1)))
        p.setPen(QPen(QColor("#4c566a"), 1, Qt.PenStyle.DashLine))
        p.drawLine(int(sx(0)), int(sy(0)), int(sx(1)), int(sy(1)))
        # ROC curve
        p.setPen(QPen(QColor("#a3be8c"), 2))
        last = None
        for x, y in zip(fpr, tpr):
            px, py = sx(x), sy(y)
            if last is not None:
                p.drawLine(int(last[0]), int(last[1]), int(px), int(py))
            last = (px, py)
        p.setPen(QPen(QColor("#d8dee9"), 1))
        p.drawText(int(sx(0.45)), int(sy(0.08)), f"AUC = {auc_value:.3f}")
        p.drawText(4, h - 6, "ROC  (x = FPR, y = TPR)")

    def _paint_scatter(self, p, w, h) -> None:
        pts = self.scatter
        if not pts:
            return
        xs = [x for x, _y, _c in pts]
        ys = [y for _x, y, _c in pts]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        if xmax == xmin:
            xmax += 1
        if ymax == ymin:
            ymax += 1
        pad = 30

        def sx(x):
            return pad + (x - xmin) / (xmax - xmin) * (w - 2 * pad)

        def sy(y):
            return h - pad - (y - ymin) / (ymax - ymin) * (h - 2 * pad)

        p.setPen(QPen(QColor("#3b4252"), 1))
        p.drawLine(int(pad), int(h - pad), int(w - pad), int(h - pad))
        p.drawLine(int(pad), int(pad), int(pad), int(h - pad))
        for x, y, c in pts:
            p.setBrush(QColor(*c))
            p.setPen(QPen(QColor(20, 22, 28), 1))
            p.drawEllipse(QPointF(sx(x), sy(y)), 4.0, 4.0)
        if self.scatter_line is not None:   # OLS fit overlay
            slope, intercept = self.scatter_line
            p.setPen(QPen(QColor("#ebcb8b"), 2))
            p.drawLine(QPointF(sx(xmin), sy(slope * xmin + intercept)),
                       QPointF(sx(xmax), sy(slope * xmax + intercept)))
        p.setPen(QPen(QColor("#6c7086"), 1))
        lbl = self.scatter_label or "scatter"
        p.drawText(4, h - 6, f"{lbl}  x:[{xmin:g},{xmax:g}]  y:[{ymin:g},{ymax:g}]")

    def _paint_heatmap(self, p, w, h) -> None:
        from ..core.format.colormap import colorize

        frames = self.heatmap
        if not frames or not frames[0]:
            return
        nx, ny = len(frames), len(frames[0])
        flat = [v for fr in frames for v in fr]
        vmin, vmax = min(flat), max(flat)
        pad = 28
        cw = (w - 2 * pad) / nx
        ch = (h - 2 * pad) / ny
        for xi, frame in enumerate(frames):
            px = pad + xi * cw
            for yi, val in enumerate(frame):
                r, g, b = colorize(val, vmin, vmax, "viridis")
                # flip y so low frequency sits at the bottom
                py = pad + (ny - 1 - yi) * ch
                p.fillRect(int(px), int(py), int(cw + 1), int(ch + 1), QColor(r, g, b))
        p.setPen(QPen(QColor("#6c7086"), 1))
        p.drawText(4, h - 6, f"spectrogram  {nx}x{ny}  dB[{vmin:.0f},{vmax:.0f}]  (x=time, y=freq)")


class GraphDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Graph")
        self.resize(560, 460)
        self.setModal(False)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self._expr = QLineEdit("sin(x)", self)
        self._xmin = QLineEdit("-6.28", self)
        self._xmax = QLineEdit("6.28", self)
        self._xmin.setMaximumWidth(70)
        self._xmax.setMaximumWidth(70)
        row.addWidget(QLabel("y =", self))
        row.addWidget(self._expr)
        row.addWidget(QLabel("x:", self))
        row.addWidget(self._xmin)
        row.addWidget(self._xmax)
        b_plot = QPushButton("Plot", self)
        b_plot.clicked.connect(self._plot_expr)
        b_sel = QPushButton("Plot selection", self)
        b_sel.clicked.connect(self._plot_selection)
        b_spec = QPushButton("Spectrum (FFT)", self)
        b_spec.setToolTip("FFT magnitude spectrum of the selected column")
        b_spec.clicked.connect(self._plot_spectrum)
        b_sg = QPushButton("Spectrogram", self)
        b_sg.setToolTip("STFT spectrogram heatmap of the selected column")
        b_sg.clicked.connect(self._plot_spectrogram)
        row.addWidget(b_plot)
        row.addWidget(b_sel)
        row.addWidget(b_spec)
        row.addWidget(b_sg)
        layout.addLayout(row)
        row2 = QHBoxLayout()
        b_scatter = QPushButton("Scatter", self)
        b_scatter.setToolTip("Scatter of 2 selected columns (3rd column colours the points)")
        b_scatter.clicked.connect(self._plot_scatter_cols)
        b_pca = QPushButton("PCA scatter", self)
        b_pca.setToolTip("PCA of the selected matrix → first 2 components")
        b_pca.clicked.connect(self._plot_pca_scatter)
        b_clusters = QPushButton("Cluster scatter", self)
        b_clusters.setToolTip("k-means on the selected matrix, coloured by cluster")
        b_clusters.clicked.connect(self._plot_cluster_scatter)
        b_roc = QPushButton("ROC curve", self)
        b_roc.setToolTip("ROC from 2 columns: true label (0/1), then score")
        b_roc.clicked.connect(self._plot_roc)
        b_hist = QPushButton("Histogram", self)
        b_hist.setToolTip("Distribution of the selected column")
        b_hist.clicked.connect(self._plot_histogram)
        b_reg = QPushButton("Regression", self)
        b_reg.setToolTip("Scatter 2 columns (x, y) with the least-squares fit line")
        b_reg.clicked.connect(self._plot_regression)
        self._k = QLineEdit("3", self)
        self._k.setMaximumWidth(40)
        self._k.setToolTip("k for cluster scatter")
        row2.addWidget(b_scatter)
        row2.addWidget(b_pca)
        row2.addWidget(b_clusters)
        row2.addWidget(b_roc)
        row2.addWidget(b_hist)
        row2.addWidget(b_reg)
        row2.addWidget(QLabel("k:", self))
        row2.addWidget(self._k)
        row2.addStretch(1)
        layout.addLayout(row2)
        self._canvas = _Canvas(self)
        layout.addWidget(self._canvas)
        self._status = QLabel("", self)
        layout.addWidget(self._status)
        self._expr.returnPressed.connect(self._plot_expr)
        self._plot_expr()

    def _plot_expr(self) -> None:
        try:
            xmin, xmax = float(self._xmin.text()), float(self._xmax.text())
            pts = sample(self._expr.text(), xmin, xmax, 240)
        except (GraphError, ValueError) as exc:
            self._status.setText(f"error: {exc}")
            return
        self._canvas.set_points(pts)
        self._status.setText(f"y = {self._expr.text()}")

    def _plot_histogram(self) -> None:
        import math

        data = self._read_selection_series()
        if len(data) < 2:
            self._status.setText("select at least 2 numeric cells")
            return
        lo, hi = min(data), max(data)
        if hi == lo:
            hi = lo + 1
        nbins = max(5, min(40, int(math.sqrt(len(data))) + 1))
        width = (hi - lo) / nbins
        counts = [0] * nbins
        for v in data:
            idx = min(nbins - 1, int((v - lo) / width))
            counts[idx] += 1
        edges = [lo + i * width for i in range(nbins + 1)]
        self._canvas.set_bars(edges, counts,
                              f"Histogram — {len(data)} values, {nbins} bins")
        self._status.setText(
            f"histogram: {len(data)} values in {nbins} bins over [{lo:g}, {hi:g}]")

    def _read_selection_series(self) -> list[float]:
        r1, c1, r2, c2 = self._win._selected_bounds()
        sheet = self._win._doc.workbook.sheet
        data: list[float] = []
        for r in range(r1, r2 + 1):
            v = sheet.get_value(r, c1)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                data.append(float(v))
        return data

    def _plot_spectrum(self) -> None:
        from ..core.science.fft import FFTError, rfft_magnitude

        data = self._read_selection_series()
        if len(data) < 2:
            self._status.setText("select at least 2 numeric cells")
            return
        try:
            # sample_rate = len(data) → x-axis is the cycle/bin index (peak = harmonic #)
            freqs, mags = rfft_magnitude(data, float(len(data)))
        except FFTError as exc:
            self._status.setText(f"error: {exc}")
            return
        self._canvas.set_points(list(zip(freqs, mags)))
        self._status.setText(f"FFT magnitude — {len(data)} samples, {len(freqs)} bins (x = cycles/window)")

    def _plot_spectrogram(self) -> None:
        from ..core.science.spectral import SpectralError, spectrogram

        data = self._read_selection_series()
        frame = 64 if len(data) >= 128 else max(8, len(data) // 4)
        if len(data) < 16:
            self._status.setText("select more numeric cells for a spectrogram")
            return
        try:
            _times, _freqs, power_db = spectrogram(data, frame_size=frame, sample_rate=1.0)
        except SpectralError as exc:
            self._status.setText(f"error: {exc}")
            return
        self._canvas.set_heatmap(power_db)
        self._status.setText(
            f"spectrogram — {len(data)} samples, frame={frame}, {len(power_db)} frames")

    def _read_matrix(self) -> list[list[float]]:
        r1, c1, r2, c2 = self._win._selected_bounds()
        sheet = self._win._doc.workbook.sheet
        rows = []
        for r in range(r1, r2 + 1):
            row = []
            for c in range(c1, c2 + 1):
                v = sheet.get_value(r, c)
                row.append(float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0)
            rows.append(row)
        return rows

    def _plot_scatter_cols(self) -> None:
        from ..core.format.colormap import colorize

        m = self._read_matrix()
        if len(m) < 2 or len(m[0]) < 2:
            self._status.setText("select ≥2 rows and ≥2 columns")
            return
        col2 = [r[2] for r in m] if len(m[0]) >= 3 else None
        if col2 is not None:
            lo, hi = min(col2), max(col2)
            pts = [(r[0], r[1], colorize(r[2], lo, hi, "viridis")) for r in m]
            label = "scatter (coloured by col 3)"
        else:
            pts = [(r[0], r[1], (136, 192, 208)) for r in m]
            label = "scatter (col1 vs col2)"
        self._canvas.set_scatter(pts, label)
        self._status.setText(label)

    def _plot_regression(self) -> None:
        """Scatter 2 columns (x, y) and overlay the least-squares fit line."""
        m = self._read_matrix()
        if len(m) < 2 or len(m[0]) < 2:
            self._status.setText("select ≥2 rows and 2 columns (x, then y)")
            return
        xs = [r[0] for r in m]
        ys = [r[1] for r in m]
        n = len(xs)
        sx_, sy_ = sum(xs), sum(ys)
        sxx = sum(x * x for x in xs)
        sxy = sum(x * y for x, y in zip(xs, ys))
        denom = n * sxx - sx_ * sx_
        if denom == 0:
            self._status.setText("x has no variance — can't fit a line")
            return
        slope = (n * sxy - sx_ * sy_) / denom
        intercept = (sy_ - slope * sx_) / n
        # R²
        ybar = sy_ / n
        ss_tot = sum((y - ybar) ** 2 for y in ys) or 1.0
        ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
        r2 = 1 - ss_res / ss_tot
        pts = [(x, y, (136, 192, 208)) for x, y in zip(xs, ys)]
        self._canvas.set_scatter(
            pts, f"y = {slope:.4g}·x + {intercept:.4g}   (R² = {r2:.4f})",
            line=(slope, intercept))
        self._status.setText(f"regression: slope={slope:.4g}, intercept={intercept:.4g}, R²={r2:.4f}")

    def _plot_pca_scatter(self) -> None:
        from ..core.science import ml

        m = self._read_matrix()
        if len(m) < 2 or len(m[0]) < 2:
            self._status.setText("select ≥2 rows and ≥2 columns")
            return
        try:
            _comps, ratio, transformed = ml.pca(m, 2)
        except ml.MLError as exc:
            self._status.setText(f"PCA error: {exc}")
            return
        pts = [(t[0], t[1] if len(t) > 1 else 0.0, (136, 192, 208)) for t in transformed]
        var = sum(ratio[:2])
        self._canvas.set_scatter(pts, f"PCA scatter ({var * 100:.0f}% variance in PC1+PC2)")
        self._status.setText("PCA scatter")

    def _plot_cluster_scatter(self) -> None:
        from ..core.format.colormap import colorize
        from ..core.science import cluster, ml

        m = self._read_matrix()
        if len(m) < 2 or len(m[0]) < 1:
            self._status.setText("select a numeric matrix")
            return
        try:
            k = max(1, int(float(self._k.text())))
            labels, _cent, _inertia = cluster.kmeans(m, k, seed=0)
        except (cluster.ClusterError, ValueError) as exc:
            self._status.setText(f"k-means error: {exc}")
            return
        # 2-D coords for display: first 2 features, or PCA-project when >2 features
        if len(m[0]) >= 3:
            try:
                _c, _r, coords = ml.pca(m, 2)
            except ml.MLError:
                coords = [(row[0], row[1]) for row in m]
        elif len(m[0]) == 2:
            coords = [(row[0], row[1]) for row in m]
        else:
            coords = [(row[0], 0.0) for row in m]
        pts = [(coords[i][0], coords[i][1] if len(coords[i]) > 1 else 0.0,
                colorize(labels[i], 0, max(1, k - 1), "viridis")) for i in range(len(m))]
        self._canvas.set_scatter(pts, f"k-means (k={k}), coloured by cluster")
        self._status.setText(f"cluster scatter k={k}")

    def _plot_roc(self) -> None:
        from ..core.science import metrics

        m = self._read_matrix()
        if len(m) < 2 or len(m[0]) < 2:
            self._status.setText("select 2 columns: true label (0/1), then score")
            return
        y_true = [row[0] for row in m]
        scores = [row[1] for row in m]
        try:
            fpr, tpr, _thr = metrics.roc_curve(y_true, scores)
            area = metrics.auc(fpr, tpr)
        except metrics.MetricsError as exc:
            self._status.setText(f"ROC error: {exc}")
            return
        self._canvas.set_roc(fpr, tpr, area)
        self._status.setText(f"ROC curve — AUC = {area:.3f}")

    def _plot_selection(self) -> None:
        r1, c1, r2, c2 = self._win._selected_bounds()
        sheet = self._win._doc.workbook.sheet
        pts = []
        for i, r in enumerate(range(r1, r2 + 1)):
            v = sheet.get_value(r, c1)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                pts.append((float(i), float(v)))
        if not pts:
            self._status.setText("selection has no numbers")
            return
        self._canvas.set_points(pts)
        self._status.setText(f"plotted {len(pts)} values from column {c1}")
