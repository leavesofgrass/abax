"""Parent-side bridge to the sandboxed Python console worker.

Spawns :mod:`abax.console_worker` as a child process and exchanges
length-prefixed JSON frames over its stdin/stdout. Pure subprocess/json (no Qt),
so it's testable headless. The worker runs user code out-of-process — a crash
there can't take down the GUI; the bridge just reports it and respawns next time.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from ...console_worker import _read_frame, _write_frame

_BOOT = "from abax.console_worker import main; main()"


class ConsoleBridge:
    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None

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
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        self._proc = subprocess.Popen(
            [sys.executable, "-c", _BOOT],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, bufsize=0, **kwargs,
        )

    def execute(self, source: str, envelope: dict) -> dict:
        """Run ``source`` in the worker against ``envelope``; return its response.

        On a worker death returns ``{"crashed": True, ...}`` with the original
        envelope unchanged, so the caller leaves the workbook as-is.
        """
        if not self._alive():
            self._spawn()
        try:
            _write_frame(self._proc.stdin,
                         json.dumps({"code": source, "envelope": envelope}).encode("utf-8"))
            data = _read_frame(self._proc.stdout)
        except (BrokenPipeError, OSError):
            data = None
        if data is None:
            reason = self._dead_reason()
            self._proc = None
            return {"output": "", "error": "the console process exited",
                    "envelope": envelope, "crashed": True, "stderr": reason}
        return json.loads(data)

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

    def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
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
