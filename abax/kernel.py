"""abax as a Jupyter kernel (optional, via ipykernel).

Two layers, split so the important part is testable without a running Jupyter:

* :class:`AbaxShell` — the kernel's *brain*. It runs code cells in the abax
  console namespace (the same ``build_namespace`` the embedded console uses, over a
  workbook) and returns results already in **Jupyter execute-result shape**: a
  ``data`` mime-bundle from :mod:`abax.core.richdisplay`, captured stdout, and the
  execution count. Pure Python, no ZMQ — unit-tested directly.

* :class:`AbaxKernel` + :func:`main` — the thin ipykernel glue (the ZMQ message
  loop). Imported only when ipykernel is installed; it delegates every execution
  to :class:`AbaxShell` and forwards its mime-bundle straight onto the IOPub
  socket. :func:`install_kernelspec` writes the kernelspec that makes "abax"
  selectable in Jupyter.

The default abax experience remains the lightweight out-of-process JSON console
(:mod:`abax.console_worker`); this kernel is the opt-in path for running abax
inside JupyterLab / nbclient, and only pulls in ipykernel when actually launched.
"""

from __future__ import annotations

import code
import contextlib
import io
import json
import sys
import traceback
from pathlib import Path

from .core.console_ns import build_namespace
from .core.richdisplay import mime_bundle
from .core.workbook import Workbook


class AbaxShell:
    """Execute code cells in the abax namespace, returning Jupyter-shaped results."""

    def __init__(self, workbook=None) -> None:
        self.workbook = workbook or Workbook()
        self.ns: dict = build_namespace(self.workbook)
        self.interp = code.InteractiveInterpreter(self.ns)
        self.execution_count = 0

    def run_cell(self, source: str) -> dict:
        """Run one cell. Returns ``{"execution_count", "stdout", "data", "error"}``
        where ``data`` is a mime-bundle for the last expression (or ``None``)."""
        self.execution_count += 1
        buf = io.StringIO()
        bundle: dict = {}

        def hook(value):
            if value is None:
                return
            self.ns["_"] = value
            bundle.clear()
            bundle.update(mime_bundle(value))

        error = None
        prev_hook = sys.displayhook
        sys.displayhook = hook
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                # 'single' so a trailing expression is sent to our displayhook
                self.interp.runsource(source, "<abax>", "single")
        except SystemExit:
            buf.write("(exit() is ignored)\n")
        except BaseException:                      # never let user code escape
            error = traceback.format_exc()
        finally:
            sys.displayhook = prev_hook
        return {
            "execution_count": self.execution_count,
            "stdout": buf.getvalue(),
            "data": dict(bundle) or None,
            "error": error,
        }


def install_kernelspec(prefix: str | None = None) -> Path:
    """Write a Jupyter kernelspec for abax and return its directory.

    The spec launches ``python -m abax.kernel``. With ``prefix`` it writes there
    (e.g. a test dir or a venv share path); otherwise under abax's data dir.
    """
    spec = {
        "argv": [sys.executable, "-m", "abax.kernel", "-f", "{connection_file}"],
        "display_name": "abax",
        "language": "python",
    }
    if prefix is not None:
        target = Path(prefix) / "kernels" / "abax"
    else:
        from ._runtime import DATA_DIR

        target = DATA_DIR / "kernels" / "abax"
    target.mkdir(parents=True, exist_ok=True)
    (target / "kernel.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return target


def _make_kernel_class():
    """Build the ipykernel Kernel subclass (imported lazily so ipykernel stays
    optional). A pure-Python kernel: it does not embed IPython, it forwards
    AbaxShell results onto IOPub."""
    from ipykernel.kernelbase import Kernel

    from . import __version__

    class AbaxKernel(Kernel):
        implementation = "abax"
        implementation_version = __version__
        language = "python"
        language_version = ".".join(map(str, sys.version_info[:3]))
        language_info = {"name": "python", "mimetype": "text/x-python",
                         "file_extension": ".py"}
        banner = "abax kernel — a scriptable spreadsheet in your notebook"

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.shell = AbaxShell()

        def do_execute(self, code, silent, store_history=True,
                       user_expressions=None, allow_stdin=False, **kwargs):
            result = self.shell.run_cell(code)
            if not silent:
                if result["stdout"]:
                    self.send_response(self.iopub_socket, "stream",
                                       {"name": "stdout", "text": result["stdout"]})
                if result["data"]:
                    self.send_response(self.iopub_socket, "execute_result", {
                        "execution_count": result["execution_count"],
                        "data": result["data"], "metadata": {}})
            return {"status": "ok",
                    "execution_count": result["execution_count"],
                    "payload": [], "user_expressions": {}}

    return AbaxKernel


def main() -> None:
    """Launch the abax kernel (requires ipykernel)."""
    try:
        from ipykernel.kernelapp import IPKernelApp
    except ImportError:
        raise SystemExit(
            "the abax Jupyter kernel needs ipykernel — install it with "
            "`pip install ipykernel` (the default abax console needs no extra deps)")
    IPKernelApp.launch_instance(kernel_class=_make_kernel_class())


if __name__ == "__main__":
    main()
