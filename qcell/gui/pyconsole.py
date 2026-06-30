"""Embedded Python console — scripting inside the editor, run out-of-process.

User code runs in a SEPARATE process (:mod:`qcell.console_worker`, via
:class:`~qcell.gui.console_bridge.ConsoleBridge`) **on a background thread**, so a
crash, hang, or runaway there never freezes the GUI — and a runaway can be
**Interrupt**ed (which kills the worker; the next command respawns it). The live
workbook is shipped to the worker and back each command as a JSON envelope. It is
still **untrusted code running with your privileges** (gated by the consent
prompt) — the subprocess gives crash/memory isolation, not a security boundary.

Worker namespace: ``doc``, ``wb``, ``sheet()``, ``cell(ref)``, ``put(ref, val)``,
``refresh()``, ``rpn``, the engineering toolkit, and the data-science libraries
when installed.
"""

from __future__ import annotations

from ._qtcompat import (
    QDialog,
    QFont,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

_BANNER = (
    "qcell Python console (sandboxed — runs in a separate process, off the UI thread).\n"
    "Namespace: doc, wb, sheet(), cell(ref), put(ref, val), refresh(), rpn; "
    "engineering: matrix, eigen, units, numeric, complexnum, fft, interp, signal, "
    "spectral, filters, ode, ode_implicit, resynth, stats, cluster, ml, trees, "
    "bayes, metrics, gmm, compile_expr, read_matrix(rng), write_matrix(cell, mat), "
    "sheet_to_df(rng), df_to_sheet(df, cell); data science (if installed): "
    "np/numpy, pd/pandas, scipy, sm/statsmodels, sklearn, pg/pingouin, pm/pymc, "
    "sksurv.\n(The first command starts the sandbox; later commands reuse it. "
    "Use Interrupt to stop a runaway command.)\n>>> "
)


class PyConsole(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self._win = window
        self.setWindowTitle("Python console (sandboxed)")
        self.resize(620, 420)
        self.setModal(False)
        from .console_bridge import ConsoleBridge

        self._bridge = ConsoleBridge()
        self._thread = None
        self._worker = None
        self._closing = False
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        mono = QFont("monospace")
        mono.setStyleHint(QFont.StyleHint.TypeWriter)
        self._out = QPlainTextEdit(self)
        self._out.setReadOnly(True)
        self._out.setFont(mono)
        self._out.setPlainText(_BANNER)
        layout.addWidget(self._out)
        row = QHBoxLayout()
        self._in = QLineEdit(self)
        self._in.setFont(mono)
        self._in.returnPressed.connect(self._run)
        row.addWidget(self._in, 1)
        self._interrupt_btn = QPushButton("Interrupt", self)
        self._interrupt_btn.setEnabled(False)
        self._interrupt_btn.clicked.connect(self._interrupt)
        row.addWidget(self._interrupt_btn)
        layout.addLayout(row)

    # --- async run -------------------------------------------------------

    def _run(self) -> None:
        if self._thread is not None:          # a command is already running
            return
        src = self._in.text()
        self._in.clear()
        self._out.appendPlainText(src)
        envelope = self._win._doc.workbook.to_envelope()
        self._set_running(True)

        from ._qtcompat import QThread
        from ..workers import FuncWorker

        self._thread = QThread(self)
        self._worker = FuncWorker(lambda s=src, e=envelope: self._bridge.execute(s, e))
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.result.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        # Drop refs on the THREAD's finished (not the worker's) — the canonical
        # wiring that avoids "QThread destroyed while still running".
        self._thread.finished.connect(self._teardown_thread)
        self._thread.start()

    def _on_result(self, resp) -> None:
        if self._closing:
            return
        out = resp.get("output", "")
        if out:
            self._out.appendPlainText(out.rstrip("\n"))
        if resp.get("crashed"):
            reason = resp.get("stderr") or ""
            self._out.appendPlainText(
                "[console process exited — it will restart on the next command]"
                + (f"\n{reason}" if reason else ""))
        else:
            try:
                self._win._doc.workbook.load_envelope(resp["envelope"])
                self._win._doc.mark_dirty()
                self._win.refresh_table()
            except Exception as exc:  # pragma: no cover - defensive
                self._out.appendPlainText(f"[could not apply workbook changes: {exc}]")

    def _on_error(self, msg) -> None:
        if not self._closing:
            self._out.appendPlainText(f"[console error: {msg}]")

    def _teardown_thread(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None
        if not self._closing:
            self._set_running(False)
            self._out.appendPlainText(">>> ")

    def _set_running(self, running: bool) -> None:
        self._in.setEnabled(not running)
        self._interrupt_btn.setEnabled(running)
        if not running:
            self._in.setFocus()

    def _interrupt(self) -> None:
        self._out.appendPlainText("[interrupting…]")
        self._bridge.interrupt()              # kills the worker → execute returns crashed

    # --- teardown --------------------------------------------------------

    def _shutdown(self) -> None:
        """Stop any running command and tear down the worker thread + subprocess."""
        self._closing = True
        self._bridge.interrupt()
        th = self._thread
        if th is not None:
            th.quit()
            th.wait(3000)
        self._bridge.close()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._shutdown()
        super().closeEvent(event)
