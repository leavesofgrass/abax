"""TI-83-style graphing-calculator engine for abax (pure-stdlib).

Models the shared brain behind a TI-82/83/84 faceplate: a home screen
(algebraic evaluation with ``Ans``), a ``Y=`` function list (Y1..Y0), a viewing
``WINDOW``, and graph sampling onto a small monochrome LCD grid. The 82/83/84
all share a 96x64 screen; subtracting a one-pixel border on each side leaves a
:data:`SCREEN_W` x :data:`SCREEN_H` usable plot area.

Expression evaluation reuses :mod:`abax.core.graphing`, whose
:func:`~abax.core.graphing.compile_expr` already sandboxes the namespace and
treats a caret ``^`` as ``**``. Variable ``X`` is exposed as lowercase ``x`` to
the compiler, so callers may write either ``X`` or ``x`` in their expressions.
"""

from __future__ import annotations

import math
from typing import Callable

from abax.core import graphing

SCREEN_W = 94  # usable plot pixels (96 minus a 1px border each side)
SCREEN_H = 62


class TIError(Exception):
    """Raised on an invalid function slot or other calculator misuse."""


class Window:
    """A viewing window; defaults to the TI ``ZStandard`` -10..10 box."""

    def __init__(
        self,
        xmin: float = -10.0,
        xmax: float = 10.0,
        ymin: float = -10.0,
        ymax: float = 10.0,
        xscl: float = 1.0,
        yscl: float = 1.0,
    ) -> None:
        self.xmin = xmin
        self.xmax = xmax
        self.ymin = ymin
        self.ymax = ymax
        self.xscl = xscl
        self.yscl = yscl

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"Window(xmin={self.xmin}, xmax={self.xmax}, "
            f"ymin={self.ymin}, ymax={self.ymax}, "
            f"xscl={self.xscl}, yscl={self.yscl})"
        )


# A TI-style expression compiles ``X`` as the graphing variable ``x``.
def _prep(expr: str) -> str:
    """Map TI surface syntax onto what :func:`graphing.compile_expr` accepts."""
    return expr.replace("X", "x")


def _format_number(value: float) -> str:
    """Render a number the way a TI screen would (trim trailing ``.0``)."""
    if isinstance(value, bool):
        return "1" if value else "0"
    f = float(value)
    if math.isfinite(f) and f == int(f):
        return str(int(f))
    return repr(f)


class TIEngine:
    """A small TI-82/83/84 calculator: home screen, ``Y=`` list, window, graph."""

    def __init__(self, degrees: bool = False) -> None:
        self.degrees = degrees
        self._functions: list[str] = ["" for _ in range(10)]
        self._history: list[tuple[str, str]] = []
        self._window = Window()
        self._ans: float = 0.0

    # --- home screen -----------------------------------------------------
    def home_eval(self, expr: str) -> str:
        """Evaluate ``expr`` (X-free context; X = 0), set ``Ans``, log it.

        Returns the result as a TI-style string. ``Ans`` may appear literally
        in the expression and is substituted with the current answer before
        compiling. On any error the TI string ``"ERR: SYNTAX"`` is returned and
        no exception propagates.
        """
        text = expr.replace("Ans", f"({_format_number(self._ans)})")
        try:
            f = graphing.compile_expr(_prep(text))
            value = float(f(0.0))
        except Exception:  # noqa: BLE001 - TI surfaces every error as a string
            return "ERR: SYNTAX"
        if not math.isfinite(value):
            return "ERR: SYNTAX"
        self._ans = value
        result = _format_number(value)
        self._history.append((expr, result))
        return result

    @property
    def ans(self) -> float:
        """The most recent home-screen answer (``Ans``)."""
        return self._ans

    def history(self) -> list[tuple[str, str]]:
        """The home-screen history as ``(entry, result)`` pairs, newest last."""
        return list(self._history)

    # --- Y= editor -------------------------------------------------------
    def set_function(self, index: int, expr: str) -> None:
        """Set slot ``index`` (1..10 = Y1..Y0). Empty string clears the slot.

        Validates that a non-empty expression compiles; raises :class:`TIError`
        on a bad index or an uncompilable expression.
        """
        slot = self._slot(index)
        if expr:
            try:
                graphing.compile_expr(_prep(expr))
            except graphing.GraphError as exc:
                raise TIError(f"invalid function Y{index}: {exc}") from exc
        self._functions[slot] = expr

    def get_function(self, index: int) -> str:
        """Return the expression string for slot ``index`` (1..10)."""
        return self._functions[self._slot(index)]

    def functions(self) -> list[str]:
        """The 10 function slots (Y1..Y0), empty strings for unused ones."""
        return list(self._functions)

    @staticmethod
    def _slot(index: int) -> int:
        if not isinstance(index, int) or not 1 <= index <= 10:
            raise TIError(f"function index out of range: {index!r} (expected 1..10)")
        return index - 1

    def _compiled(self) -> list[tuple[int, Callable[[float], float]]]:
        """Compile every defined function, keyed by its 1-based index."""
        out: list[tuple[int, Callable[[float], float]]] = []
        for i, expr in enumerate(self._functions, start=1):
            if not expr:
                continue
            try:
                out.append((i, graphing.compile_expr(_prep(expr))))
            except graphing.GraphError:
                continue
        return out

    # --- window / zoom ---------------------------------------------------
    @property
    def window(self) -> Window:
        """The current viewing window."""
        return self._window

    def set_window(self, **kw: float) -> None:
        """Update any of xmin/xmax/ymin/ymax/xscl/yscl on the window."""
        allowed = {"xmin", "xmax", "ymin", "ymax", "xscl", "yscl"}
        for key, value in kw.items():
            if key not in allowed:
                raise TIError(f"unknown window field: {key!r}")
            setattr(self._window, key, float(value))

    def zoom_standard(self) -> None:
        """ZStandard: -10..10 on both axes, unit scale marks."""
        self._window = Window(-10.0, 10.0, -10.0, 10.0, 1.0, 1.0)

    def zoom_decimal(self) -> None:
        """ZDecimal: -4.7..4.7 in x, -3.1..3.1 in y (friendly pixel steps)."""
        self._window = Window(-4.7, 4.7, -3.1, 3.1, 1.0, 1.0)

    def zoom_fit(self) -> None:
        """ZoomFit: fit the y-range to the defined functions over the x window."""
        compiled = self._compiled()
        if not compiled:
            return
        w = self._window
        n = max(2, SCREEN_W)
        ys: list[float] = []
        for _i, f in compiled:
            for x, y in graphing.sample(f, w.xmin, w.xmax, n):
                if y is not None and math.isfinite(y):
                    ys.append(y)
        if not ys:
            return
        ymin, ymax = min(ys), max(ys)
        if ymax <= ymin:
            ymin -= 1.0
            ymax += 1.0
        else:
            margin = (ymax - ymin) * 0.05
            ymin -= margin
            ymax += margin
        w.ymin = ymin
        w.ymax = ymax

    # --- graphing --------------------------------------------------------
    def graph_pixels(
        self, w: int = SCREEN_W, h: int = SCREEN_H
    ) -> dict[int, list[tuple[int, int]]]:
        """Sample every defined function onto an ``w`` x ``h`` pixel grid.

        One sample per screen column over ``[xmin, xmax]``; world coordinates map
        to integer pixels with row 0 at the TOP. Off-screen and non-finite points
        are dropped. Returns ``{function_index: [(px, py), ...]}``.
        """
        win = self._window
        result: dict[int, list[tuple[int, int]]] = {}
        if w <= 0 or h <= 0:
            return result
        xspan = win.xmax - win.xmin
        yspan = win.ymax - win.ymin
        if xspan == 0 or yspan == 0:
            return result
        for index, f in self._compiled():
            pts: list[tuple[int, int]] = []
            for x, y in graphing.sample(f, win.xmin, win.xmax, w):
                if y is None or not math.isfinite(y):
                    continue
                px = round((x - win.xmin) / xspan * (w - 1))
                py = round((win.ymax - y) / yspan * (h - 1))
                if 0 <= px < w and 0 <= py < h:
                    pts.append((px, py))
            result[index] = pts
        return result

    def axes_pixels(self, w: int = SCREEN_W, h: int = SCREEN_H) -> dict:
        """Pixel row for y=0 and pixel column for x=0 (``None`` if off-range)."""
        win = self._window
        x_axis_row: int | None = None
        y_axis_col: int | None = None
        yspan = win.ymax - win.ymin
        xspan = win.xmax - win.xmin
        if w > 0 and h > 0 and yspan != 0 and win.ymin <= 0.0 <= win.ymax:
            row = round((win.ymax - 0.0) / yspan * (h - 1))
            if 0 <= row < h:
                x_axis_row = row
        if w > 0 and h > 0 and xspan != 0 and win.xmin <= 0.0 <= win.xmax:
            col = round((0.0 - win.xmin) / xspan * (w - 1))
            if 0 <= col < w:
                y_axis_col = col
        return {"x_axis_row": x_axis_row, "y_axis_col": y_axis_col}

    def table(self, start: float, step: float, rows: int = 7) -> list[list[str]]:
        """A TI TABLE: a header then ``rows`` rows of X and each defined Y value."""
        compiled = self._compiled()
        header = ["X"] + [f"Y{i}" for i, _f in compiled]
        out: list[list[str]] = [header]
        for r in range(rows):
            x = start + step * r
            row = [_format_number(x)]
            for _i, f in compiled:
                try:
                    y = float(f(x))
                    cell = _format_number(y) if math.isfinite(y) else "ERR"
                except Exception:  # noqa: BLE001 - undefined point -> blank-ish
                    cell = "ERR"
                row.append(cell)
            out.append(row)
        return out
