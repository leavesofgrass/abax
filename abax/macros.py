"""Macro engine — user Python that drives a workbook, plus user-defined functions.

Two extension points, both opt-in via plain ``.py`` files (code stays code; it
is never embedded in JSON data files):

* ``@macro`` registers a *command* macro — a function ``def name(ctx): ...`` that
  mutates a workbook through :class:`MacroContext`. Run it from the CLI
  (``abax macro run``), the TUI (``:macro name``), or the GUI command palette.
* ``@register_function("NAME")`` registers a *user-defined function* (UDF) that
  becomes callable inside formulas (``=NAME(...)``). UDFs follow the same
  calling convention as built-ins: they receive a list of evaluated arguments.

Macro files are discovered from ``CONFIG_DIR/macros/*.py`` plus any paths passed
with ``--macros``. Executing macros runs arbitrary Python: abax is not a
sandbox — only load macros you trust.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from .core import functions as _fns
from .core.errors import CellError
from .core.functions import FUNCTIONS
from .core.values import RangeValue

log = logging.getLogger("abax.macros")


class MacroError(Exception):
    """Raised when a macro cannot be found or fails to load."""


class MacroContext:
    """The handle a command macro uses to read and mutate a workbook.

    Passed as the single argument to every ``@macro`` function. Keeps a log of
    messages the macro emits so the front-end can show them.
    """

    def __init__(self, workbook, cursor: tuple[int, int] | None = None) -> None:
        self.workbook = workbook
        # The active cell when the macro is invoked (row, col), or None when run
        # headlessly. Relative recorded macros offset from this.
        self.cursor = cursor
        self.messages: list[str] = []

    @property
    def sheet(self):
        return self.workbook.sheet

    def get(self, ref: str) -> Any:
        return self.workbook.sheet.get(ref)

    def set(self, ref: str, value: Any) -> None:
        self.workbook.sheet.set(ref, value if isinstance(value, str) else _fns._text(value))

    def set_rc(self, row: int, col: int, value: Any) -> None:
        """Set a cell by zero-based (row, col) — used by relative macros."""
        if row < 0 or col < 0:
            return
        self.workbook.sheet.set_cell(row, col, value if isinstance(value, str) else _fns._text(value))

    def get_sheet(self, name: str):
        return self.workbook.get_sheet(name)

    def add_sheet(self, name: str | None = None):
        return self.workbook.add_sheet(name)

    def recalc(self) -> None:
        self.workbook.recalculate()

    def log(self, message: Any) -> None:
        text = str(message)
        self.messages.append(text)
        log.info("macro: %s", text)


class MacroRegistry:
    """Collects macros and UDFs discovered from macro files."""

    def __init__(self) -> None:
        self.macros: dict[str, Callable] = {}
        self.functions: dict[str, Callable] = {}

    # decorators handed to macro files at exec time
    def macro(self, name: str | Callable | None = None):
        if callable(name):  # used as a bare @macro
            self.macros[name.__name__.lower()] = name
            return name

        def deco(fn: Callable) -> Callable:
            self.macros[(name or fn.__name__).lower()] = fn
            return fn

        return deco

    def register_function(self, name: str):
        def deco(fn: Callable) -> Callable:
            self.functions[name.upper()] = fn
            return fn

        return deco


# The namespace every macro file is executed in. Macro authors get the
# decorators plus a few helpers so they don't reach into private modules.
def _build_namespace(registry: MacroRegistry) -> dict:
    from .core.translate import shift_formula

    return {
        "macro": registry.macro,
        "register_function": registry.register_function,
        "CellError": CellError,
        "RangeValue": RangeValue,
        # value helpers, re-exported for UDF authors
        "flatten": _fns._flatten,
        "numbers": _fns._numbers,
        "as_number": _fns._as_number,
        "text": _fns._text,
        # reference shifting, used by relative recorded macros
        "shift_refs": shift_formula,
    }


def load_macro_file(path: str | Path, registry: MacroRegistry | None = None) -> MacroRegistry:
    registry = registry or MacroRegistry()
    path = Path(path)
    code = path.read_text(encoding="utf-8")
    ns = _build_namespace(registry)
    ns["__file__"] = str(path)
    try:
        exec(compile(code, str(path), "exec"), ns)  # noqa: S102 - trusted macros, not sandboxed
    except Exception as exc:  # surface as a MacroError, keep the rest loadable
        raise MacroError(f"error loading {path.name}: {exc}") from exc
    return registry


def discover_macros(paths: list[str | Path]) -> MacroRegistry:
    registry = MacroRegistry()
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            files = sorted(p.glob("*.py"))
        elif p.exists():
            files = [p]
        else:
            files = []
        for f in files:
            try:
                load_macro_file(f, registry)
            except MacroError as exc:
                log.error("%s", exc)
    return registry


def default_macro_dirs() -> list[Path]:
    from . import _runtime as rt

    return [rt.CONFIG_DIR / "macros"]


def install_functions(registry: MacroRegistry) -> list[str]:
    """Make a registry's UDFs callable inside formulas. Returns their names."""
    for name, fn in registry.functions.items():
        FUNCTIONS[name] = fn
    return sorted(registry.functions)


def run_macro(
    registry: MacroRegistry,
    name: str,
    workbook,
    cursor: tuple[int, int] | None = None,
) -> MacroContext:
    fn = registry.macros.get(name.lower())
    if fn is None:
        raise MacroError(f"no such macro: {name!r} (have: {', '.join(sorted(registry.macros)) or 'none'})")
    ctx = MacroContext(workbook, cursor)
    fn(ctx)
    return ctx
