"""MacroMixin — Macros and recording: run/record/replay/save, load macro files, run scripts.

Command macros and scripts execute **out-of-process** in the same isolated
worker as the Python console (sandbox Phase 1) — a crash, runaway allocation,
or hang there cannot take down the GUI, and the worker is resource-limited
(Phase 2). Loading a macro/UDF file still executes it in-process (UDFs must be
callable by the formula engine), which is what the consent gate covers.

**And off the GUI thread, which the two entry points here used to ignore.**
``_run_macro`` and :meth:`run_script` called the bridge *synchronously from a Qt
slot*, so everything the bridge does before a result comes back was paid with
the window frozen: spawning the worker, and — in strict mode on Windows —
establishing the AppContainer's ACL grants. That last part is not a fast
operation and never was. Granting ALL APPLICATION PACKAGES read+execute on the
interpreter prefix is a full DACL propagation walk, measured at 19-21 s on this
platform (``abax/sandbox_windows.py``, the note above ``_hold_session_grant``),
and since those grants became serialised across processes a spawn may *also*
wait up to ``_ACL_MUTEX_GRANT_WAIT`` (60 s) for another abax's walk to finish
before starting its own. A single spawn was measured blocking 36.7 s. The user
code itself is on top of that and is unbounded — these two calls pass no
``timeout``, so a macro that runs for a minute froze the window for a minute
even with no sandbox in sight.

So both now go through :meth:`~abax.gui.mixin_io.DocumentIOMixin._run_io` with a
:class:`~abax.workers.FuncWorker`, which is the lifecycle the Python console has
always used (``abax/gui/console/pyconsole.py``) and the one six file operations
in ``mixin_io.py`` already use: the blocking call happens on a QThread, the
window keeps painting, the busy cursor and progress bar say so, and the response
is applied back on the GUI thread from ``_on_io_result``. The envelope, the
macro sources and the cursor are snapshotted *here*, before the thread starts —
the worker callable must touch no widgets and no document (spec §7).
"""

from __future__ import annotations

import os

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
        from ..workers import FuncWorker

        # Everything the worker callable needs, read here on the GUI thread: the
        # bridge object (constructing it is cheap — the ~20 s work is inside
        # `execute_macro`), and copies of the registry sources, the cursor and
        # the workbook. The callable itself closes over those four values and
        # nothing else — no `self`, no widget, no document (spec §7). `on_success`
        # does touch `self`, and may: it is delivered back on the GUI thread.
        bridge = self._exec_bridge()
        sources = list(registry.sources)
        cursor = self._current_cell()
        envelope = self._doc.workbook.to_envelope()
        self._run_io(
            FuncWorker(lambda: bridge.execute_macro(name, sources, cursor, envelope)),
            on_success=lambda resp: self._macro_finished(resp, name),
            busy_msg=f"running macro {name}...")

    def _macro_finished(self, resp: dict, name: str) -> None:
        """Apply a finished macro run. Back on the GUI thread (queued signal)."""
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
        or runaway in the script is contained to the worker process, and the run
        itself is contained to a worker *thread* (module docstring).
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
        from ..workers import FuncWorker

        bridge = self._exec_bridge()
        envelope = self._doc.workbook.to_envelope()
        self._run_io(
            FuncWorker(lambda: bridge.execute_script(src, path, envelope)),
            on_success=lambda resp: self._script_finished(resp, path),
            busy_msg=f"running script {os.path.basename(path)}...")

    def _script_finished(self, resp: dict, path: str) -> None:
        """Apply a finished script run. Back on the GUI thread (queued signal)."""
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
