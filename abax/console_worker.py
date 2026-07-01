"""Out-of-process worker for the sandboxed Python console.

Spawned by :mod:`abax.gui.console.console_bridge` as a child process
(``python -c "from abax.console_worker import main; main()"``). It runs user code
in a separate process — crash isolation now, and a seam for OS-level confinement
later. The live workbook is shipped in and out as an envelope each command, so the
child never touches the GUI.

Wire protocol (length-prefixed JSON, 4-byte big-endian length):
  request  = {"code": str, "envelope": dict}
  response = {"output": str, "error": str|None, "envelope": dict}
"""

from __future__ import annotations

import builtins
import code
import contextlib
import io
import json
import struct
import sys
import traceback

from .core.console_ns import build_namespace
from .core.richdisplay import best_text
from .core.workbook import Workbook


def _displayhook(value) -> None:
    """Echo an expression result using the rich-display protocol, so objects with
    ``_repr_markdown_`` / ``_repr_html_`` (e.g. a Sheet) print a readable table
    instead of an opaque ``repr``. Mirrors the stdlib hook otherwise (``None`` is
    silent; the result is bound to ``_``)."""
    if value is None:
        return
    builtins._ = value
    sys.stdout.write(best_text(value) + "\n")


class Worker:
    """Holds the persistent console namespace + interpreter across commands.

    ``handle`` is pure (no I/O), so it is unit-testable without a subprocess: the
    workbook arrives/returns as an envelope, user vars persist in ``ns``, and the
    workbook-facing helpers are rebound to each command's workbook.
    """

    def __init__(self) -> None:
        self.ns: dict = {}
        self.interp = code.InteractiveInterpreter(self.ns)

    def handle(self, source: str, envelope: dict) -> dict:
        wb = Workbook.from_envelope(envelope)
        self.ns.update(build_namespace(wb))     # rebind workbook helpers; keep user vars
        buf = io.StringIO()
        prev_hook = sys.displayhook
        sys.displayhook = _displayhook
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                self.interp.runsource(source, "<console>")
        except SystemExit:
            buf.write("(exit() is ignored in the console)\n")
        except BaseException:                    # never let user code kill the worker
            buf.write(traceback.format_exc())
        finally:
            sys.displayhook = prev_hook
        return {"output": buf.getvalue(), "error": None, "envelope": wb.to_envelope()}


def _read_frame(stream) -> bytes | None:
    header = stream.read(4)
    if not header or len(header) < 4:
        return None
    (length,) = struct.unpack(">I", header)
    data = bytearray()
    while len(data) < length:
        chunk = stream.read(length - len(data))
        if not chunk:
            return None
        data += chunk
    return bytes(data)


def _write_frame(stream, payload: bytes) -> None:
    stream.write(struct.pack(">I", len(payload)))
    stream.write(payload)
    stream.flush()


def main() -> None:
    # Reserve the real stdout pipe for framing; discard stray prints (e.g. from
    # imports) so they can't corrupt the frame stream. (User code's own output is
    # captured per-command in handle().) Real errors still go to stderr.
    import os

    out = sys.stdout.buffer
    inp = sys.stdin.buffer
    sys.stdout = open(os.devnull, "w")

    worker = Worker()
    while True:
        raw = _read_frame(inp)
        if raw is None:
            break
        msg: dict = {}
        try:
            msg = json.loads(raw)
            resp = worker.handle(msg.get("code", ""), msg.get("envelope", {}))
        except Exception:
            resp = {"output": traceback.format_exc(), "error": "worker error",
                    "envelope": msg.get("envelope", {})}
        _write_frame(out, json.dumps(resp).encode("utf-8"))


if __name__ == "__main__":
    main()
