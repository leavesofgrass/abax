"""Parent-side bridge to the isolated code-execution worker.

Spawns :mod:`abax.console_worker` as a child process and exchanges
length-prefixed JSON frames over its stdin/stdout. Pure subprocess/json (no Qt),
so it's testable headless. The worker runs user code out-of-process — a crash
there can't take down the GUI; the bridge just reports it and respawns next time.

The bridge is the parent half of the sandbox (Phases 1–2): every execution op
(console command, script file, command macro) goes through :meth:`_roundtrip`,
the worker is resource-limited (POSIX rlimits applied in the child; on Windows
the bridge assigns a **Job Object** with memory/CPU/process caps and
kill-on-job-close), and an optional wall-clock ``timeout`` arms a watchdog that
kills a hung worker. This is crash and resource isolation with the user's
privileges — **not** a security boundary (that is Phase 3, strict mode).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading

from ... import sandbox
from ...console_worker import _read_frame, _write_frame
from ...proclimits import assign_windows_job, close_windows_job

_BOOT = "from abax.console_worker import main; main()"

# Returned in place of a worker response when strict mode was requested but no
# OS confinement is available on this platform — we refuse rather than run
# untrusted code unconfined (the Phase 3 fail-closed rule, parent side).
_STRICT_UNAVAILABLE = (
    "Strict sandbox mode is on but this platform has no available OS "
    "confinement (Linux needs bubblewrap; macOS uses sandbox-exec; Windows "
    "needs AppContainer support). Refusing to run code unconfined — disable "
    "strict mode or run abax in a VM/container.")


class ConsoleBridge:
    def __init__(self, strict: bool = False, restricted: bool = False) -> None:
        self._proc = None
        self._job = None  # Windows Job Object handle (keeps the limits alive)
        # Strict mode confines the worker's filesystem + network (Phase 3). It's
        # on when the caller asks OR the environment forces it (so a spawned
        # worker inherits the parent's decision).
        self._strict = strict or sandbox.strict_requested()
        # Restricted mode runs user code through the in-process AST allowlist
        # *inside* the worker (a separate axis from strict OS confinement). The
        # worker reads RESTRICTED_ENV; the bridge just sets it on the child.
        self._restricted = restricted or sandbox.restricted_requested()
        self._scratch: str | None = None
        self._confinement = sandbox.select_confinement() if self._strict else None

    def strict_unavailable(self) -> bool:
        """True when strict mode was requested but can't be honored here."""
        return self._strict and not (self._confinement and self._confinement.available())

    def _alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _spawn(self) -> None:
        env = dict(os.environ)
        # Replicate the parent's import path so the child finds `abax` — including
        # when running from a .pyz (whose path is on sys.path).
        paths = [p for p in sys.path if p]
        if env.get("PYTHONPATH"):
            paths.append(env["PYTHONPATH"])
        env["PYTHONPATH"] = os.pathsep.join(paths)
        # Restricted tier: tell the worker to run user code through the AST
        # allowlist (composes with any process isolation below).
        if self._restricted:
            env[sandbox.RESTRICTED_ENV] = "1"
        creationflags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        argv = [sys.executable, "-c", _BOOT]

        if self._strict and self._confinement and self._confinement.available():
            # Sandbox Phase 3: confine the worker's filesystem + network. Tell
            # the worker (via env) that strict mode is on and where its one
            # writable scratch dir is, so it applies any in-child confinement
            # and runs the fail-closed self-test before executing anything.
            if self._scratch is None:
                self._scratch = tempfile.mkdtemp(prefix="abax-sandbox-")
            env[sandbox.STRICT_ENV] = "1"
            env[sandbox.SCRATCH_ENV] = self._scratch
            env = self._confinement.child_env(env, self._scratch)
            custom = getattr(self._confinement, "custom_spawn", None)
            if custom is not None:
                # A strategy that needs a bespoke launcher (Windows AppContainer).
                self._proc = custom(argv, env, self._scratch, creationflags)
            else:
                # A wrapper strategy (Linux bwrap, macOS sandbox-exec).
                argv = self._confinement.wrap_argv(argv, self._scratch)
                self._proc = subprocess.Popen(
                    argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, env=env, bufsize=0,
                    creationflags=creationflags)
        else:
            self._proc = subprocess.Popen(
                argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=env, bufsize=0,
                creationflags=creationflags)
        # Sandbox Phase 2 (Windows): cap the worker's memory / CPU time /
        # process count via a Job Object; kill-on-job-close ties the worker's
        # lifetime to this handle, so it dies with the GUI no matter what.
        if sys.platform == "win32":
            self._job = assign_windows_job(int(self._proc._handle))  # noqa: SLF001

    def _roundtrip(self, payload: dict, timeout: "float | None" = None) -> dict:
        """Send one request frame, read one response frame.

        On a worker death (crash, kill, resource-limit termination, watchdog
        timeout) returns ``{"crashed": True, ...}`` with the original envelope
        unchanged, so the caller leaves the workbook as-is.
        """
        if self.strict_unavailable():
            # Fail closed at the parent: never spawn an unconfined worker when
            # strict mode was requested but can't be provided.
            return {"output": "", "error": _STRICT_UNAVAILABLE,
                    "envelope": payload.get("envelope", {})}
        if not self._alive():
            self._spawn()
        watchdog = None
        if timeout is not None and timeout > 0:
            watchdog = threading.Timer(timeout, self.interrupt)
            watchdog.daemon = True
            watchdog.start()
        try:
            _write_frame(self._proc.stdin, json.dumps(payload).encode("utf-8"))
            data = _read_frame(self._proc.stdout)
        except (BrokenPipeError, OSError):
            data = None
        finally:
            if watchdog is not None:
                watchdog.cancel()
        if data is None:
            reason = self._dead_reason()
            dead, self._proc = self._proc, None
            self._close_job()
            # Revert the dead worker's confinement side effects (Windows profile
            # + ACL grants) so a crash-and-respawn cycle doesn't leak them; keep
            # the scratch dir for the replacement worker.
            if dead is not None and sys.platform == "win32":
                try:
                    from ...sandbox_windows import cleanup_process

                    cleanup_process(dead)
                except Exception:
                    pass
            return {"output": "", "error": "the console process exited",
                    "envelope": payload.get("envelope", {}), "crashed": True,
                    "stderr": reason}
        return json.loads(data)

    def execute(self, source: str, envelope: dict,
                timeout: "float | None" = None) -> dict:
        """Run a console command in the worker against ``envelope``."""
        return self._roundtrip({"op": "exec", "code": source, "envelope": envelope},
                               timeout)

    def execute_script(self, source: str, path: str, envelope: dict,
                       timeout: "float | None" = None) -> dict:
        """Run a whole script file in the worker (fresh namespace)."""
        return self._roundtrip({"op": "script", "code": source, "path": path,
                                "envelope": envelope}, timeout)

    def execute_macro(self, name: str, files: list, cursor, envelope: dict,
                      timeout: "float | None" = None) -> dict:
        """Load ``files`` into a fresh registry in the worker and run a macro."""
        return self._roundtrip({"op": "macro", "macro": name, "files": list(files),
                                "cursor": list(cursor) if cursor else None,
                                "envelope": envelope}, timeout)

    def interrupt(self) -> None:
        """Kill the current worker to stop a runaway command. A blocked
        ``execute()`` then returns a crashed response (its read hits EOF), and the
        next call respawns a fresh worker. Safe to call from another thread."""
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass

    def _dead_reason(self) -> str:
        proc = self._proc
        if proc is None:
            return ""
        try:
            proc.wait(timeout=1)
            if proc.stderr is not None:
                return proc.stderr.read().decode("utf-8", "replace").strip()
        except Exception:
            pass
        return ""

    def _close_job(self) -> None:
        job, self._job = self._job, None
        close_windows_job(job)

    def _cleanup_confinement(self, proc) -> None:
        """Revert per-process confinement side effects (Windows ACL grants +
        AppContainer profile) and remove the scratch dir."""
        if proc is not None and sys.platform == "win32":
            try:
                from ...sandbox_windows import cleanup_process

                cleanup_process(proc)
            except Exception:
                pass
        if self._scratch is not None:
            shutil.rmtree(self._scratch, ignore_errors=True)
            self._scratch = None

    def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            self._close_job()
            self._cleanup_confinement(None)
            return
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        finally:
            self._close_job()
            self._cleanup_confinement(proc)


class InProcessBridge:
    """The 'off' isolation level: run code in *this* process, no worker.

    Presents the same surface as :class:`ConsoleBridge` (so callers don't
    branch), but calls the pure :class:`~abax.console_worker.Worker` directly —
    no subprocess, no resource limits, no OS confinement, and no interrupt (a
    runaway can't be killed in-process). This is the fast, full-access,
    *no-isolation* mode; a crash in a C extension will take the GUI down with
    it. The workbook still crosses as an envelope, so the calling code applies
    the result exactly as it does for the out-of-process bridge.
    """

    def __init__(self) -> None:
        from ...console_worker import Worker

        self._worker = Worker()

    def strict_unavailable(self) -> bool:
        return False

    def execute(self, source: str, envelope: dict,
                timeout: "float | None" = None) -> dict:
        return self._worker.dispatch({"op": "exec", "code": source,
                                      "envelope": envelope})

    def execute_script(self, source: str, path: str, envelope: dict,
                       timeout: "float | None" = None) -> dict:
        return self._worker.dispatch({"op": "script", "code": source, "path": path,
                                      "envelope": envelope})

    def execute_macro(self, name: str, files: list, cursor, envelope: dict,
                      timeout: "float | None" = None) -> dict:
        return self._worker.dispatch({"op": "macro", "macro": name,
                                      "files": list(files),
                                      "cursor": list(cursor) if cursor else None,
                                      "envelope": envelope})

    def interrupt(self) -> None:
        # No way to interrupt in-process code — the price of the "off" level.
        pass

    def close(self) -> None:
        pass


def make_exec_bridge(isolation: str):
    """Pick the execution transport for a ``code_isolation`` level:

    * ``"off"`` — :class:`InProcessBridge` (in-process, no isolation).
    * ``"restricted"`` — :class:`ConsoleBridge` running user code through the
      in-process AST allowlist (:mod:`abax.restricted`) inside the worker:
      out-of-process + resource limits **and** a blocked-imports/no-open
      language subset. Optional ``RestrictedPython`` adds compile-time guards.
    * ``"isolated"`` — :class:`ConsoleBridge` (out-of-process + resource limits).
    * ``"strict"`` — :class:`ConsoleBridge` with OS confinement (Phase 3).

    Unknown levels fall back to ``"isolated"``.
    """
    if isolation == "off":
        return InProcessBridge()
    return ConsoleBridge(strict=(isolation == "strict"),
                         restricted=(isolation == "restricted"))
