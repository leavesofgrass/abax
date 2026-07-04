"""Degraded, pure-Python restriction mode for running user code.

.. WARNING::
    **This is HARDENING, not a security boundary.**

    The techniques in this module -- AST allowlisting and namespace
    restriction -- can *always* be escaped by a determined attacker running
    inside the same CPython process. Bytecode tricks, C-level escapes,
    reference walking through live objects, resource exhaustion, and countless
    other avenues remain open. Treating this as a real sandbox would be a
    serious mistake.

    Its ONLY purpose is to stop *casual and accidental* harm: the macro that
    calls ``open('/etc/passwd')`` or does ``import os; os.system(...)`` by
    mistake. It raises the bar from "trivial" to "annoying", nothing more.
    When a real OS-level sandbox is available (Phase 1-3) it should be used
    instead; this exists only as a last-resort degraded fallback.

    Do not rely on this to run genuinely untrusted code. It will not hold.

What it DOES do
---------------
* Rejects imports of modules outside a small pure/safe stdlib allowlist.
* Rejects any attribute access to dunder names, which closes the classic
  ``().__class__.__bases__[0].__subclasses__()`` reflection escape.
* Rejects calls to a set of dangerous builtins by name (eval, exec, open, ...).
* Runs code with a curated ``__builtins__`` that omits the dangerous names.
* Captures stdout/stderr and never lets user code kill the caller.

What it does NOT do
-------------------
* It does not stop CPU/memory exhaustion (no timeouts, no memory caps).
* It does not stop bytecode-level or C-extension escapes.
* It does not stop reference walking that avoids literal dunder *syntax*
  (e.g. building a dunder string dynamically) -- though we block the dynamic
  ``getattr``/``setattr`` builtins that would be needed to *use* such a string.
* It is not, and cannot be, a substitute for OS-level isolation.
"""

from __future__ import annotations

import ast
import builtins
import contextlib
import io
import traceback

__all__ = [
    "ALLOWED_IMPORTS",
    "RestrictionError",
    "check_ast",
    "restrictedpython_available",
    "run_restricted",
    "safe_builtins",
]

# ---------------------------------------------------------------------------
# Import allowlist.
#
# WHY: importing arbitrary modules is the single easiest way to reach the OS
# (os, subprocess, socket, shutil, ...) or to re-enter the interpreter
# (importlib, ctypes, builtins). We invert the problem: instead of trying to
# enumerate every dangerous module, we allow only a small set of modules that
# are pure computation / formatting and have no filesystem, network, or
# process side effects worth worrying about for *accidental* harm.
#
# NOTE: this list is deliberately conservative. `io` is excluded because it is
# the gateway to file objects; `pathlib` is excluded because it is a
# filesystem API; `os`/`sys`/`subprocess`/`socket`/`shutil`/`importlib`/
# `ctypes`/`builtins` are all excluded for obvious reasons.
# ---------------------------------------------------------------------------
ALLOWED_IMPORTS: frozenset[str] = frozenset(
    {
        "math",
        "statistics",
        "datetime",
        "json",
        "re",
        "itertools",
        "functools",
        "collections",
        "decimal",
        "fractions",
        "random",
        "string",
        "textwrap",
    }
)

# Builtins we refuse to let user code *call by name*.
#
# WHY each one:
#   eval/exec/compile  -- re-enter the interpreter with arbitrary source.
#   __import__         -- import any module, bypassing the import statement.
#   open               -- filesystem access.
#   input              -- blocks on stdin; not useful and can hang the host.
#   globals/locals/vars-- expose the live namespace (incl. dunder machinery).
#   getattr/setattr/delattr -- dynamic attribute access defeats the static
#                             dunder-attribute check (getattr(x, "__class__")).
#   breakpoint         -- drops into pdb / arbitrary debugger hook.
FORBIDDEN_BUILTIN_CALLS: frozenset[str] = frozenset(
    {
        "eval",
        "exec",
        "compile",
        "__import__",
        "open",
        "input",
        "globals",
        "locals",
        "vars",
        "getattr",
        "setattr",
        "delattr",
        "breakpoint",
    }
)


class RestrictionError(Exception):
    """Raised when source code contains a construct the AST check forbids.

    The message includes the offending line number and a short description of
    what was rejected, so the caller can surface a useful diagnostic.
    """


def _is_dunder(name: str) -> bool:
    """Return True for double-underscore names like ``__class__``.

    WHY: dunder attributes are the doorway to CPython's object model
    (``__class__`` -> ``__bases__`` -> ``__subclasses__`` reaches every loaded
    class, including ones that can spawn processes or open files). We treat any
    ``__x__`` name as off-limits rather than trying to enumerate the dangerous
    ones -- the safe dunders a user might legitimately want are not worth the
    risk of missing a dangerous one.
    """
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


class _Checker(ast.NodeVisitor):
    """Walks the AST and raises RestrictionError on any forbidden construct."""

    def __init__(self, filename: str) -> None:
        self.filename = filename

    def _reject(self, node: ast.AST, what: str) -> None:
        line = getattr(node, "lineno", "?")
        raise RestrictionError(f"{self.filename}:{line}: {what}")

    # -- imports -----------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            # `import a.b.c` -- only the top-level package name matters for the
            # allowlist decision (importing `a.b` pulls in `a`).
            top = alias.name.split(".", 1)[0]
            if top not in ALLOWED_IMPORTS:
                self._reject(node, f"import of module {alias.name!r} is not allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        # `from . import x` has module=None (a relative import); reject those
        # outright since there is no package to import from in this context.
        module = node.module or ""
        top = module.split(".", 1)[0]
        if not top or top not in ALLOWED_IMPORTS:
            self._reject(
                node, f"import from module {module or '<relative>'!r} is not allowed"
            )
        self.generic_visit(node)

    # -- attribute access --------------------------------------------------
    def visit_Attribute(self, node: ast.Attribute) -> None:
        # Blanket rule: no dunder attribute access at all. This is what closes
        # ().__class__.__bases__[0].__subclasses__() and every variation of it.
        if _is_dunder(node.attr):
            self._reject(node, f"access to dunder attribute {node.attr!r} is not allowed")
        self.generic_visit(node)

    # -- bare names --------------------------------------------------------
    def visit_Name(self, node: ast.Name) -> None:
        # Reject dunder *names* too (e.g. referencing __builtins__ directly, or
        # assigning to a dunder to smuggle it past the attribute check).
        if _is_dunder(node.id):
            self._reject(node, f"use of dunder name {node.id!r} is not allowed")
        self.generic_visit(node)

    # -- calls -------------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        # Reject direct calls to dangerous builtins by name. This catches
        # eval("..."), open(...), getattr(x, "..."), etc. It does NOT catch a
        # rebound alias (foo = eval; foo(...)) -- but such an alias still can't
        # succeed at runtime because the name is absent from safe_builtins().
        func = node.func
        if isinstance(func, ast.Name) and func.id in FORBIDDEN_BUILTIN_CALLS:
            self._reject(node, f"call to builtin {func.id!r} is not allowed")
        self.generic_visit(node)


def check_ast(source: str, *, filename: str = "<restricted>") -> None:
    """Parse *source* and raise RestrictionError on any forbidden construct.

    This is a *static* check performed before execution. It is the first line
    of the (leaky) defense; runtime restrictions in :func:`safe_builtins` back
    it up. A ``SyntaxError`` from ``ast.parse`` is allowed to propagate
    unchanged -- it is not a restriction violation.
    """
    tree = ast.parse(source, filename=filename)
    _Checker(filename).visit(tree)


def _restricted_import(
    name: str,
    globals=None,  # noqa: A002 - matches builtins.__import__ signature
    locals=None,  # noqa: A002 - matches builtins.__import__ signature
    fromlist=(),
    level: int = 0,
):
    """A drop-in for ``__import__`` that only permits allowlisted modules.

    WHY provide this at all: the ``import`` statement compiles to a call to
    ``__builtins__.__import__``. If we removed it entirely, even the allowed
    ``import math`` would fail. So we install a wrapper that enforces the same
    allowlist at runtime -- defense in depth behind the static AST check.
    """
    top = name.split(".", 1)[0]
    if level != 0 or top not in ALLOWED_IMPORTS:
        raise RestrictionError(f"import of module {name!r} is not allowed")
    return builtins.__import__(name, globals, locals, fromlist, level)


def safe_builtins() -> dict:
    """Return a curated ``__builtins__`` mapping for restricted execution.

    Contains pure/harmless builtins (numeric, container, iteration, and string
    helpers), the exception hierarchy, and a restricted ``__import__``. It
    deliberately OMITS eval, exec, compile, open, input, getattr, setattr,
    delattr, globals, locals, vars, and breakpoint.

    WHY exceptions are included: user code should be able to ``raise
    ValueError(...)`` and ``except KeyError:``. These types are harmless.
    """
    names = (
        # numeric / logic
        "abs",
        "min",
        "max",
        "sum",
        "round",
        "divmod",
        "pow",
        "bin",
        "hex",
        "oct",
        "chr",
        "ord",
        # types / constructors
        "int",
        "float",
        "str",
        "bool",
        "list",
        "dict",
        "set",
        "tuple",
        "frozenset",
        "bytes",
        "bytearray",
        "complex",
        # iteration / sequences
        "len",
        "range",
        "enumerate",
        "zip",
        "map",
        "filter",
        "sorted",
        "reversed",
        "iter",
        "next",
        "slice",
        # predicates / introspection (safe subset)
        "isinstance",
        "issubclass",
        "any",
        "all",
        "callable",
        "hash",
        "id",
        "type",
        # output / formatting
        "print",
        "repr",
        "format",
        "ascii",
    )
    safe: dict = {name: getattr(builtins, name) for name in names}

    # Constants.
    safe["True"] = True
    safe["False"] = False
    safe["None"] = None
    safe["Ellipsis"] = Ellipsis
    safe["NotImplemented"] = NotImplemented

    # The whole exception hierarchy (BaseException down) plus warnings -- these
    # are just classes and are needed for raise/except to work.
    for name in dir(builtins):
        obj = getattr(builtins, name)
        if isinstance(obj, type) and issubclass(obj, BaseException):
            safe[name] = obj

    # Restricted import wrapper (see _restricted_import for the why).
    safe["__import__"] = _restricted_import
    return safe


# ---------------------------------------------------------------------------
# Optional RestrictedPython enhancement.
#
# When the third-party ``RestrictedPython`` package is installed, we compile via
# its ``compile_restricted`` instead of the stdlib ``compile``. That rewrites
# attribute access, subscripting, iteration, and augmented assignment to go
# through *guard* functions, closing a broader class of escapes than the
# stdlib compile + our AST check alone (e.g. ``x[0]`` and ``for a, b in ...``
# unpacking are routed through guards that we control). It is GUARDED: importing
# it is wrapped in try/except, and its absence just means we fall back to the
# stdlib compile path. This module never *requires* RestrictedPython.
# ---------------------------------------------------------------------------


def restrictedpython_available() -> bool:
    """True iff the optional ``RestrictedPython`` package is importable.

    Used to decide whether the ``restricted`` isolation tier can add
    RestrictedPython's compile-time guards on top of the always-present
    stdlib AST allowlist. Never imports at module load; never raises.
    """
    import importlib.util

    try:
        return importlib.util.find_spec("RestrictedPython") is not None
    except Exception:  # noqa: BLE001 - a broken/partial install = "not available"
        return False


def _restrictedpython_pieces():
    """Return ``(compile_restricted, guards)`` from RestrictedPython, or None.

    Imported lazily and guarded so the module stays pure-stdlib at import time.
    ``guards`` is a small dict of the guard callables RestrictedPython-compiled
    code expects in its globals (``_getitem_``, ``_getiter_``, ...).
    """
    try:
        from RestrictedPython import compile_restricted
        from RestrictedPython.Eval import (
            default_guarded_getitem,
            default_guarded_getiter,
        )
        from RestrictedPython.Guards import (
            guarded_iter_unpack_sequence,
            guarded_unpack_sequence,
        )
    except Exception:  # noqa: BLE001 - any import problem => no enhancement
        return None

    guards = {
        "_getitem_": default_guarded_getitem,
        "_getiter_": default_guarded_getiter,
        "_iter_unpack_sequence_": guarded_iter_unpack_sequence,
        "_unpack_sequence_": guarded_unpack_sequence,
        # We forbid attribute writes entirely in restricted code; a write guard
        # that always refuses keeps RestrictedPython-compiled assignments from
        # silently mutating objects we hand in.
        "_write_": _deny_write,
        # RestrictedPython rewrites `print(...)` to a collector referenced as
        # `_print_`; route its output to the live (redirected) stdout so the
        # captured buffer sees it exactly like the stdlib compile path.
        "_print_": _StreamingPrintCollector,
        # RestrictedPython-compiled code references `_getattr_` for guarded
        # attribute access (and the print collector's constructor takes it). Ours
        # mirrors the AST policy: dunder attributes stay off-limits, everything
        # else reads through unchanged.
        "_getattr_": _guarded_getattr,
    }
    return compile_restricted, guards


def _guarded_getattr(obj, name, default=None):
    """RestrictedPython ``_getattr_`` guard mirroring the AST dunder ban.

    Attribute reads on dunder names (``__class__`` etc.) are refused -- the same
    reflection doorway the static :func:`check_ast` closes -- so the runtime
    guard can't be used to reach it either. Any other attribute reads normally.
    """
    if _is_dunder(name):
        raise RestrictionError(f"access to dunder attribute {name!r} is not allowed")
    return getattr(obj, name, default) if default is not None else getattr(obj, name)


class _StreamingPrintCollector:
    """A RestrictedPython ``_print_`` that writes to the current ``sys.stdout``.

    RestrictedPython-compiled code does ``_print = _print_(_getattr_)`` then
    ``_print(...)``; the default collector buffers text into ``.txt`` and only
    surfaces it via a ``printed`` name the code must reference. We instead
    forward every write to ``sys.stdout`` (which :func:`run_restricted` has
    redirected into its capture buffer), so ``print`` behaves normally and its
    output is captured without the code needing to read ``printed``.
    """

    def __init__(self, _getattr_=None) -> None:
        self._getattr_ = _getattr_

    def write(self, text) -> None:
        import sys

        sys.stdout.write(text)

    def __call__(self):  # `printed` -> "" (we streamed, nothing buffered)
        return ""

    def _call_print(self, *objects, **kwargs) -> None:
        import sys

        # Honour an explicit file= if given (guarded), else write to us (stdout).
        if kwargs.get("file", None) is None:
            kwargs["file"] = sys.stdout
        elif self._getattr_ is not None:
            self._getattr_(kwargs["file"], "write")
        print(*objects, **kwargs)  # noqa: T201 - restricted print goes to stdout


def _deny_write(obj):
    """RestrictedPython ``_write_`` guard: refuse all guarded writes.

    RestrictedPython routes ``obj.attr = x`` / ``obj[i] = x`` through ``_write_``
    to obtain a writable proxy. Returning a refusal here means restricted code
    cannot mutate attributes/items of objects it was handed -- consistent with
    the AST check, which already blocks dunder attribute access.
    """
    raise RestrictionError("writing attributes/items is not allowed in restricted code")


def run_restricted(
    source: str,
    namespace: dict | None = None,
    *,
    filename: str = "<restricted>",
    use_restrictedpython: bool | None = None,
) -> dict:
    """Check, compile, and run *source* under the restricted environment.

    Returns a dict with keys:
      * ``output``    -- combined captured stdout+stderr (str).
      * ``error``     -- a formatted traceback string if execution raised, else
                         None. RestrictionError from the static check surfaces
                         here too (execution never begins in that case).
      * ``namespace`` -- the globals dict the code ran in, so the caller can
                         read back any values it defined.

    User code can NEVER kill the caller: every BaseException from the check or
    the exec is caught and formatted into ``error``. This is intentional --
    ``run_restricted`` is a boundary, not a passthrough.

    ``use_restrictedpython`` controls the compile-time guards: ``True`` requires
    the optional package (falling back to stdlib compile if it can't be loaded),
    ``False`` forces the pure stdlib path, and ``None`` (default) uses
    RestrictedPython when it is installed. Either way the always-present AST
    allowlist (:func:`check_ast`) runs first, so the pure fallback is never
    weaker on the checks this module owns.

    Reminder: this is hardening, not a sandbox. See the module docstring.
    """
    # Build the execution globals: our safe builtins plus any caller-supplied
    # names. We copy the incoming namespace so we don't mutate the caller's.
    exec_globals: dict = {"__builtins__": safe_builtins()}
    if namespace:
        exec_globals.update(namespace)

    out = io.StringIO()
    error: str | None = None

    want_rp = restrictedpython_available() if use_restrictedpython is None else use_restrictedpython
    pieces = _restrictedpython_pieces() if want_rp else None

    try:
        # Static allowlist check first. If this raises RestrictionError we do
        # not execute anything at all -- regardless of the compile backend.
        check_ast(source, filename=filename)
        if pieces is not None:
            compile_restricted, guards = pieces
            # RestrictedPython-compiled code references guard names in globals;
            # inject them alongside our safe builtins.
            exec_globals.update(guards)
            # RestrictedPython warns "Prints, but never reads 'printed'" because
            # our collector streams to stdout instead of exposing `printed`; that
            # is intentional, so silence just that compile-time warning.
            import warnings

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Line None: Prints")
                code = compile_restricted(source, filename, "exec")
        else:
            code = compile(source, filename, "exec")
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            # Note: passing a single dict makes it serve as both globals and
            # locals, which is the normal module-execution model.
            exec(code, exec_globals)  # noqa: S102 - intentional, restricted env
    except BaseException:  # noqa: BLE001 - boundary: never propagate to caller
        # Format the traceback into a string rather than letting it escape.
        error = traceback.format_exc()

    return {"output": out.getvalue(), "error": error, "namespace": exec_globals}
