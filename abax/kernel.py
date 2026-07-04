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

import builtins
import code
import contextlib
import io
import json
import keyword
import sys
import traceback
from pathlib import Path

from .core import completion
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

    def run_cell_block(self, source: str) -> dict:
        """Run a whole cell (many statements), Jupyter-style. Same result shape
        as :meth:`run_cell`.

        :meth:`run_cell` uses the ``code`` module's ``"single"`` mode, which only
        accepts *one* statement — right for the line-at-a-time console, wrong for a
        notebook cell that is a block of statements. Here the cell is compiled in
        ``"exec"`` mode and, if its last statement is a bare expression, that value
        is evaluated separately and shown as the cell's result (an
        ``execute_result``), exactly as a Jupyter frontend does. A runtime error is
        captured in ``error`` (its traceback) rather than dumped to stdout, so
        notebook cells get a real ``error`` output.
        """
        import ast

        self.execution_count += 1
        buf = io.StringIO()
        bundle: dict = {}
        error = None
        try:
            tree = ast.parse(source, "<abax>", "exec")
        except SyntaxError:
            return {"execution_count": self.execution_count, "stdout": "",
                    "data": None, "error": traceback.format_exc()}

        last_expr = None
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last_expr = ast.Expression(tree.body.pop().value)

        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                if tree.body:
                    exec(compile(tree, "<abax>", "exec"), self.ns)  # noqa: S102
                if last_expr is not None:
                    value = eval(compile(last_expr, "<abax>", "eval"), self.ns)  # noqa: S307
                    if value is not None:
                        self.ns["_"] = value
                        bundle.update(mime_bundle(value))
            except SystemExit:
                buf.write("(exit() is ignored)\n")
            except BaseException:                  # never let user code escape
                error = traceback.format_exc()
        return {
            "execution_count": self.execution_count,
            "stdout": buf.getvalue(),
            "data": dict(bundle) or None,
            "error": error,
        }

    # -- completion / introspection (the brains behind do_complete/do_inspect) --

    def complete(self, source: str, cursor: int | None = None) -> dict:
        """Completions for the token ending at ``cursor`` in ``source``.

        Returns ``{"matches", "cursor_start", "cursor_end"}`` (the fields the
        Jupyter ``complete_reply`` needs). A line that starts with ``=`` is a
        **formula**, completed against the function registry via
        :func:`abax.core.completion.complete`; anything else is **Python**,
        completed against the live namespace (``build_namespace`` bindings, the
        session's own globals, and builtins) plus a trailing-attribute path like
        ``fft.rff`` resolved against the real object. This split matters because
        the formula completer gates on a leading ``=`` and so returns nothing for
        plain Python source.
        """
        if cursor is None:
            cursor = len(source)
        cursor = max(0, min(cursor, len(source)))
        # Complete within the logical line the cursor sits on (notebooks and the
        # console send whole cells; formulas are single lines).
        line, line_start = _cursor_line(source, cursor)
        line_cursor = cursor - line_start

        if line.lstrip().startswith("="):
            names = tuple(self._defined_names())
            sheets = tuple(s.name for s in self.workbook.sheets)
            matches = completion.complete(line.lstrip(), require_formula=True,
                                          names=names, sheets=sheets)
            token, _ = completion.current_token(line.lstrip())
            start = cursor - len(token)
            return {"matches": matches, "cursor_start": start, "cursor_end": cursor}

        token, tok_start = completion.current_token(line, line_cursor)
        if not token:
            return {"matches": [], "cursor_start": cursor, "cursor_end": cursor}
        start = line_start + tok_start
        if "." in token:
            obj_expr, _, partial = token.rpartition(".")
            matches = self._attr_matches(obj_expr, partial)
            # Replace only the trailing partial (keep the ``obj.`` prefix).
            return {"matches": matches, "cursor_start": cursor - len(partial),
                    "cursor_end": cursor}
        matches = self._name_matches(token)
        return {"matches": matches, "cursor_start": start, "cursor_end": cursor}

    def inspect(self, source: str, cursor: int | None = None) -> dict:
        """Introspect the token under the cursor (backs ``do_inspect``).

        Returns ``{"found": bool, "text": str}``. For a formula token it hands
        back the function signature; for a Python token it resolves the object in
        the namespace and reports its type, signature (if callable) and docstring.
        """
        if cursor is None:
            cursor = len(source)
        cursor = max(0, min(cursor, len(source)))
        line, line_start = _cursor_line(source, cursor)
        line_cursor = cursor - line_start

        if line.lstrip().startswith("="):
            token, _ = completion.current_token(line.lstrip())
            if token and completion.is_function(token):
                return {"found": True, "text": completion.signature(token)}
            return {"found": False, "text": ""}

        token, _ = completion.current_token(line, line_cursor)
        if not token:
            return {"found": False, "text": ""}
        obj, ok = self._resolve(token)
        if not ok:
            return {"found": False, "text": ""}
        return {"found": True, "text": _describe(token, obj)}

    def is_complete(self, source: str) -> dict:
        """Whether ``source`` is a complete statement (backs ``do_is_complete``).

        ``{"status": "complete" | "incomplete" | "invalid"}`` — mirrors what a
        console needs to decide between executing and continuing the block. Uses
        the same compiler check :class:`code.InteractiveInterpreter` runs on.
        """
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                compiled = code.compile_command(source, "<abax>", "exec")
        except (SyntaxError, ValueError, OverflowError):
            return {"status": "invalid"}
        if compiled is None:
            return {"status": "incomplete", "indent": ""}
        return {"status": "complete"}

    # -- completion helpers --

    def _defined_names(self) -> list[str]:
        """Workbook defined-name strings (empty when the workbook has none)."""
        registry = getattr(self.workbook, "names", None)
        getter = getattr(registry, "names", None)
        if not callable(getter):
            return []
        try:
            return [display for display, _target in getter()]
        except Exception:
            return []

    def _namespace_keys(self) -> list[str]:
        """Every identifier a bare Python token could complete to."""
        keys = set(self.ns)
        keys.update(completion.function_names())     # formula names (per spec)
        keys.update(dir(builtins))
        keys.update(keyword.kwlist)
        return sorted(k for k in keys if isinstance(k, str) and not k.startswith("__"))

    def _name_matches(self, token: str) -> list[str]:
        """Namespace/builtin identifiers that start with ``token`` (prefix match).

        Case-sensitive for the usual Python names; a token typed in a single case
        also picks up the (upper-case) formula function names case-insensitively.
        """
        lo = token.lower()
        out = [k for k in self._namespace_keys()
               if k.startswith(token) or k.lower().startswith(lo)]
        return out

    def _resolve(self, expr: str):
        """Evaluate a dotted ``expr`` against the namespace. ``(obj, ok)``."""
        try:
            return eval(expr, dict(self.ns)), True     # noqa: S307 - trusted ns
        except Exception:
            return None, False

    def _attr_matches(self, obj_expr: str, partial: str) -> list[str]:
        """Attributes of the object named by ``obj_expr`` starting with ``partial``."""
        obj, ok = self._resolve(obj_expr)
        if not ok:
            return []
        try:
            attrs = dir(obj)
        except Exception:
            return []
        pub = [a for a in attrs if not a.startswith("_")]
        return sorted(a for a in pub if a.startswith(partial))


def _cursor_line(source: str, cursor: int) -> tuple[str, int]:
    """The line containing ``cursor`` and that line's start offset in ``source``."""
    start = source.rfind("\n", 0, cursor) + 1
    end = source.find("\n", cursor)
    if end == -1:
        end = len(source)
    return source[start:end], start


def _describe(name: str, obj) -> str:
    """A short introspection blurb: type, signature (if any), first doc lines."""
    import inspect

    lines = [f"{name}: {type(obj).__name__}"]
    if callable(obj):
        try:
            lines[0] = f"{name}{inspect.signature(obj)}"
        except (TypeError, ValueError):
            pass
    doc = inspect.getdoc(obj)
    if doc:
        lines.append("")
        lines.extend(doc.splitlines()[:20])
    return "\n".join(lines)


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

        def do_complete(self, code, cursor_pos):
            res = self.shell.complete(code, cursor_pos)
            return {"status": "ok", "matches": res["matches"],
                    "cursor_start": res["cursor_start"],
                    "cursor_end": res["cursor_end"], "metadata": {}}

        def do_inspect(self, code, cursor_pos, detail_level=0, **kwargs):
            res = self.shell.inspect(code, cursor_pos)
            data = {"text/plain": res["text"]} if res["found"] else {}
            return {"status": "ok", "found": res["found"],
                    "data": data, "metadata": {}}

        def do_is_complete(self, code):
            return self.shell.is_complete(code)

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
