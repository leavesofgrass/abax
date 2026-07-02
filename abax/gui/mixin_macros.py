"""MacroMixin — Macros and recording: run/record/replay/save, load macro files, run scripts.

Command macros and scripts execute **out-of-process** in the same isolated
worker as the Python console (sandbox Phase 1) — a crash, runaway allocation,
or hang there cannot take down the GUI, and the worker is resource-limited
(Phase 2). Loading a macro/UDF file still executes it in-process (UDFs must be
callable by the formula engine), which is what the consent gate covers.
"""

from __future__ import annotations

from ..core.reference import to_a1


class MacroMixin:
    def _exec_bridge(self):
        """The shared bridge to the isolated worker for macros and scripts
        (lazily created; independent of the console panel's own bridge)."""
        bridge = getattr(self, "_macro_bridge", None)
        if bridge is None:
            from .console.console_bridge import make_exec_bridge

            bridge = self._macro_bridge = make_exec_bridge(
                getattr(self._settings, "code_isolation", "isolated"))
        return bridge

    def _apply_exec_response(self, resp: dict, what: str) -> bool:
        """Apply a worker response (envelope + errors) to the document.
        Returns True when the run succeeded."""
        from ._qtcompat import QMessageBox

        if resp.get("crashed"):
            reason = resp.get("stderr") or "the worker process exited"
            QMessageBox.critical(self, what, f"{what} crashed the worker process "
                                 f"(the GUI is unaffected).\n{reason}")
            return False
        if resp.get("error"):
            QMessageBox.critical(self, what, resp["error"])
            return False
        self._doc.workbook.load_envelope(resp["envelope"])
        self._doc.mark_dirty()
        self.refresh_table()
        return True

    def _run_macro(self, name: str) -> None:
        registry = self._macro_registry
        if registry is None or name.lower() not in registry.macros:
            from ._qtcompat import QMessageBox

            QMessageBox.critical(self, "Macro failed", f"no such macro: {name!r}")
            return
        resp = self._exec_bridge().execute_macro(
            name, registry.sources, self._current_cell(),
            self._doc.workbook.to_envelope())
        if not self._apply_exec_response(resp, "Macro"):
            return
        out = (resp.get("output") or "").strip().splitlines()
        self._set_status(f"ran macro {name}" + (f" — {out[-1]}" if out else ""))

    def _toggle_recording(self) -> None:
        on = self._recorder.toggle()
        self._update_title()
        self._set_status(
            "* recording — edit cells, then Save recorded macro"
            if on
            else f"stopped — recorded {self._recorder.count} action(s)"
        )

    def _start_relative_recording(self) -> None:
        self._recorder.start(relative=True)
        self._update_title()
        self._set_status("* recording (relative) — replays relative to the active cell")

    def load_macros(self) -> None:
        """Load a macro/UDF .py file into the registry so it's immediately runnable."""
        if not self._require_code_consent("Loading a macro / UDF file"):
            return
        from ._qtcompat import QFileDialog, QMessageBox

        path, _ = QFileDialog.getOpenFileName(
            self, "Load macro / UDF file", "", "Python (*.py);;All files (*)")
        if not path:
            return
        from ..macros import MacroError, load_macro_file

        try:
            load_macro_file(path, self._macro_registry)
        except (MacroError, OSError, SyntaxError) as exc:
            QMessageBox.critical(self, "Load macros", str(exc))
            return
        rebuild = getattr(self, "_rebuild_macros_menu", None)
        if rebuild is not None:
            rebuild()
        self._set_status(f"loaded macros from {path}")

    def run_script(self) -> None:
        """Run a Python script against the workbook, in the isolated worker.

        The script gets the console namespace (``wb``, ``sheet()``, ``cell``,
        ``put``, the engineering toolkit, …) in a fresh scope; the workbook
        crosses as an envelope and comes back with the script's edits. A crash
        or runaway in the script is contained to the worker process.
        """
        if not self._require_code_consent("Running a Python script"):
            return
        from ._qtcompat import QFileDialog, QMessageBox

        path, _ = QFileDialog.getOpenFileName(
            self, "Run Python script", "", "Python (*.py);;All files (*)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
        except OSError as exc:
            QMessageBox.critical(self, "Run script", str(exc))
            return
        resp = self._exec_bridge().execute_script(
            src, path, self._doc.workbook.to_envelope())
        if not self._apply_exec_response(resp, "Run script"):
            return
        self._set_status(f"ran script {path}")

    def _save_recording(self) -> None:
        from ._qtcompat import QFileDialog

        if self._recorder.count == 0:
            self._set_status("nothing recorded yet")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save recorded macro", "", "Python macro (*.py)"
        )
        if not path:
            return
        saved = self._recorder.save_macro(path)
        if self._macro_registry is not None:
            from ..macros import load_macro_file

            load_macro_file(saved, self._macro_registry)  # immediately runnable
            rebuild = getattr(self, "_rebuild_macros_menu", None)
            if rebuild is not None:
                rebuild()
        self._set_status(f"saved macro {saved}")

    def _replay_recording(self) -> None:
        if self._recorder.count == 0:
            self._set_status("nothing recorded to replay")
            return
        self._recorder.replay(self._doc.workbook, at=self._current_cell())
        self._doc.mark_dirty()
        self.refresh_table()
        where = f" at {to_a1(*self._current_cell())}" if self._recorder.relative else ""
        self._set_status(f"replayed {self._recorder.count} action(s){where}")
