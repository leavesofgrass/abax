"""Signal / data tool — apply a DSP operation over a column of samples.

Reads a numeric range (flattened row-major into a 1-D series), applies an
operation from :mod:`abax.core.science.signal` / :mod:`abax.core.science.fft`, and writes the
result back as one or more columns starting at a target cell (or reports a scalar
like RMS in the status line).
"""

from __future__ import annotations

import math

from .._qtcompat import (
    QComboBox,
    QDialog,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
)
from ...core.reference import parse_a1, parse_range, to_a1
from ...core.science import fft as F
from ...core.science import filters as FL
from ...core.science import signal as S
from ...core.science import spectral as SP

# label -> (handler(data, param) -> list[list[float]] | float, needs_param_hint)
_OPS = [
    "FFT magnitude (freq, mag)",
    "FFT phase",
    "Power spectrum",
    "Moving average (window)",
    "Exponential smoothing (alpha)",
    "Normalize — minmax",
    "Normalize — zscore",
    "Detrend",
    "Cumulative sum",
    "Autocorrelation",
    "Hann window",
    "Butterworth low-pass (cutoff 0–0.5)",
    "Butterworth high-pass (cutoff 0–0.5)",
    "FIR low-pass (cutoff 0–0.5)",
    "Spectrogram dB (frame=param)",
    "Welch PSD dB (param=sample rate; 2 cols = I/Q)",
    "RMS (status only)",
]


class SignalDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Signal / data tool")
        self._build()

    def _build(self) -> None:
        form = QFormLayout(self)
        r1, c1, r2, c2 = self._win._selected_bounds()
        self._in = QLineEdit(f"{to_a1(r1, c1)}:{to_a1(r2, c2)}", self)
        self._op = QComboBox(self)
        self._op.addItems(_OPS)
        self._param = QLineEdit("3", self)
        self._param.setToolTip("window size (MA), alpha 0–1 (EWMA), or sample rate (FFT)")
        self._out = QLineEdit(to_a1(r1, max(0, c2 + 2)), self)
        form.addRow("Samples (range):", self._in)
        form.addRow("Operation:", self._op)
        form.addRow("Param:", self._param)
        form.addRow("Output top-left:", self._out)
        btn = QPushButton("Apply", self)
        btn.clicked.connect(self._apply)
        form.addRow(btn)

    def _read_series(self, rng: str) -> list[float]:
        r1, c1, r2, c2 = parse_range(rng)
        sheet = self._win._doc.workbook.sheet
        series: list[float] = []
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                v = sheet.get_value(r, c)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    series.append(float(v))
        return series

    def _read_iq(self, rng: str):
        """Read a range as samples for PSD. A range spanning two or more columns
        is read as quadrature (I = first column, Q = second, row-aligned) and
        returns complex samples; a single column returns a real series. Returns
        ``(samples, is_iq)``."""
        r1, c1, r2, c2 = parse_range(rng)
        if c2 - c1 < 1:
            return self._read_series(rng), False
        sheet = self._win._doc.workbook.sheet

        def num(r: int, c: int) -> float | None:
            v = sheet.get_value(r, c)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return float(v)
            return None

        out: list[complex] = []
        for r in range(r1, r2 + 1):
            iv = num(r, c1)
            if iv is None:
                continue
            qv = num(r, c1 + 1)
            out.append(complex(iv, qv if qv is not None else 0.0))
        return out, True

    def _apply_welch(self) -> None:
        samples, is_iq = self._read_iq(self._in.text())
        if len(samples) < 2:
            QMessageBox.warning(self, "Signal", "Select at least 2 numeric cells.")
            return
        seg = 1
        while seg * 2 <= min(256, len(samples)):
            seg *= 2
        try:
            fs = float(self._param.text().strip() or 1.0)
            freqs, psd = SP.welch_psd(samples, sample_rate=fs, nperseg=max(2, seg))
        except (SP.SpectralError, ValueError, ZeroDivisionError) as exc:
            QMessageBox.warning(self, "Signal", str(exc))
            return
        psd_db = [10.0 * math.log10(p) if p > 0 else -300.0 for p in psd]
        self._write_cols([freqs, psd_db], self._out.text())
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        kind = "I/Q two-sided" if is_iq else "real one-sided"
        self._win._set_status(f"Welch PSD ({kind}, {len(freqs)} bins, seg={seg})")
        self.accept()

    def _write_cols(self, cols: list[list[float]], top_left: str) -> None:
        r0, c0 = parse_a1(top_left)
        sheet = self._win._doc.workbook.sheet
        for j, col in enumerate(cols):
            for i, v in enumerate(col):
                sheet.set_cell(r0 + i, c0 + j, _fmt(v))

    def _compute(self, op: str, data: list[float], param: str):
        if op.startswith("FFT magnitude"):
            freqs, mags = F.rfft_magnitude(data, float(param or 1.0))
            return [freqs, mags]
        if op == "FFT phase":
            return [F.phase(F.fft(data))]
        if op == "Power spectrum":
            return [F.power_spectrum(F.fft(data))]
        if op.startswith("Moving average"):
            return [S.moving_average(data, int(float(param)))]
        if op.startswith("Exponential"):
            return [S.exponential_smoothing(data, float(param))]
        if op == "Normalize — minmax":
            return [S.normalize(data, "minmax")]
        if op == "Normalize — zscore":
            return [S.normalize(data, "zscore")]
        if op == "Detrend":
            return [S.detrend(data)]
        if op == "Cumulative sum":
            return [S.cumulative_sum(data)]
        if op == "Autocorrelation":
            return [S.autocorrelation(data)]
        if op == "Hann window":
            return [S.apply_window(data, "hann")]
        if op.startswith("Butterworth low"):
            b, a = FL.butter_lowpass(float(param), 1.0, order=4)
            return [FL.filtfilt(b, a, data)]
        if op.startswith("Butterworth high"):
            b, a = FL.butter_highpass(float(param), 1.0, order=4)
            return [FL.filtfilt(b, a, data)]
        if op.startswith("FIR low"):
            taps = FL.fir_lowpass(float(param), 1.0, numtaps=51)
            return [FL.fir_filter(taps, data)]
        if op.startswith("Spectrogram"):
            # columns = time frames, rows = frequency bins (dB)
            _times, _freqs, power_db = SP.spectrogram(
                data, frame_size=int(float(param)), sample_rate=1.0)
            return power_db
        if op.startswith("RMS"):
            return S.rms(data)
        return None

    def _apply(self) -> None:
        if self._op.currentText().startswith("Welch PSD"):
            self._apply_welch()
            return
        data = self._read_series(self._in.text())
        if len(data) < 2:
            QMessageBox.warning(self, "Signal", "Select at least 2 numeric cells.")
            return
        op = self._op.currentText()
        try:
            result = self._compute(op, data, self._param.text().strip())
        except (S.SignalError, F.FFTError, FL.FilterError, SP.SpectralError,
                ValueError, ZeroDivisionError) as exc:
            QMessageBox.warning(self, "Signal", str(exc))
            return
        if isinstance(result, float):
            self._win._set_status(f"{op}: {_fmt(result)}")
            self.accept()
            return
        if result is None:
            return
        self._write_cols(result, self._out.text())
        self._win._doc.mark_dirty()
        self._win.refresh_table()
        self._win._set_status(f"signal: {op} ({len(result[0])} rows)")
        self.accept()


def _fmt(v: float) -> str:
    return str(int(v)) if isinstance(v, float) and v.is_integer() else f"{v:.10g}"
