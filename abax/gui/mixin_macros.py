"""MacroMixin — Macros and recording: run/record/replay/save, load macro files, run scripts."""

from __future__ import annotations

from ..core.reference import to_a1


class MacroMixin:
    def _run_macro(self, name: str) -> None:
        from ._qtcompat import QMessageBox
        from ..macros import MacroError, run_macro

        try:
            ctx = run_macro(self._macro_registry, name, self._doc.workbook, cursor=self._current_cell())
        except MacroError as exc:
            QMessageBox.critical(self, "Macro failed", str(exc))
            return
        self._doc.mark_dirty()
        self.refresh_table()
        self._set_status(f"ran macro {name}" + (f" — {ctx.messages[-1]}" if ctx.messages else ""))

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
        """Run an arbitrary Python script against the workbook (no sandbox)."""
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
        wb = self._doc.workbook
        ns = {
            "__name__": "abax_script",
            "doc": self._doc,
            "wb": wb,
            "sheet": wb.sheet,
            "cell": lambda ref: wb.sheet.get(ref),
            "put": lambda ref, val: wb.sheet.set(ref, val if isinstance(val, str) else str(val)),
            "refresh": self.refresh_table,
        }
        try:
            exec(compile(src, path, "exec"), ns)
        except Exception:  # noqa: BLE001 - report any script error to the user
            import traceback

            QMessageBox.critical(self, "Run script", traceback.format_exc())
            return
        self._doc.mark_dirty()
        self.refresh_table()
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
