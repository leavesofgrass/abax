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
import re
from typing import Callable

from abax.core import graphing
from abax.core.science import regression as _reg
from abax.core.science import stats as _stats

# A stored letter variable used as a whole token (A-Z, not part of a longer
# name). Faceplate function tokens are lower-case, so an upper-case single letter
# is unambiguously a variable.
_VAR_RE = re.compile(r"\b([A-Z])\b")
# A store assignment: ``<expr> -> V`` / ``<expr> → V`` (the TI STO> key).
_STORE_RE = re.compile(r"^(.*?)(?:->|→)\s*([A-Z])\s*$", re.DOTALL)

SCREEN_W = 94  # usable plot pixels (96 minus a 1px border each side)
SCREEN_H = 62

# The six named stat lists a TI ships with (STAT EDIT / 2nd L1..L6).
STAT_LISTS = ("L1", "L2", "L3", "L4", "L5", "L6")


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
        # A-Z letter variables (STO>). An unset variable reads as 0, like a TI.
        self._vars: dict[str, float] = {}
        # STAT list editor store. L1..L6 exist as empty lists, like a TI.
        self._lists: dict[str, list[float]] = {name: [] for name in STAT_LISTS}

    # --- letter variables (STO>) ----------------------------------------
    def get_var(self, name: str) -> float:
        """The value of letter variable ``name`` (0 if never stored)."""
        return self._vars.get(name.upper(), 0.0)

    def store(self, value: float, name: str) -> None:
        """Store ``value`` into letter variable ``name`` (also updates ``Ans``)."""
        self._vars[name.upper()] = float(value)
        self._ans = float(value)

    def _substitute(self, text: str) -> str:
        """Replace ``Ans`` and stored letter variables with their values."""
        text = text.replace("Ans", f"({_format_number(self._ans)})")
        return _VAR_RE.sub(lambda m: f"({_format_number(self.get_var(m.group(1)))})", text)

    # --- STAT list editor ------------------------------------------------
    def _list_key(self, name: str) -> str:
        """Normalise and validate a stat-list name (``L1``..``L6``)."""
        key = str(name).upper()
        if key not in self._lists:
            raise TIError(f"unknown stat list: {name!r} (expected one of {STAT_LISTS})")
        return key

    def set_list(self, name: str, values: list[float]) -> None:
        """Replace stat list ``name`` (``L1``..``L6``) with ``values``."""
        key = self._list_key(name)
        self._lists[key] = [float(v) for v in values]

    def get_list(self, name: str) -> list[float]:
        """Return a copy of stat list ``name`` (``L1``..``L6``)."""
        return list(self._lists[self._list_key(name)])

    def append_list(self, name: str, value: float) -> None:
        """Append a single value to stat list ``name`` (entry-by-entry input)."""
        self._lists[self._list_key(name)].append(float(value))

    def clear_list(self, name: str) -> None:
        """Empty stat list ``name`` (TI ``ClrList``)."""
        self._lists[self._list_key(name)] = []

    def clear_all_lists(self) -> None:
        """Empty every stat list (TI ``ClrAllLists``)."""
        for key in self._lists:
            self._lists[key] = []

    # --- STAT CALC -------------------------------------------------------
    def one_var_stats(self, name: str = "L1") -> dict:
        """1-Var Stats over list ``name``: n, mean, sums, sd, min/Q1/med/Q3/max.

        Mirrors the TI ``1-Var Stats`` screen. Reuses
        :mod:`abax.core.science.stats` for the mean, variance-based standard
        deviations and quartiles. Raises :class:`TIError` on an empty list.
        """
        data = self._lists[self._list_key(name)]
        if not data:
            raise TIError(f"1-Var Stats: {name} is empty")
        n = len(data)
        sx = math.fsum(data)
        sx2 = math.fsum(x * x for x in data)
        mean = _stats.mean(data)
        # Sample sd needs >= 2 points; population sd is defined for >= 1.
        sample_sd = _stats.stdev(data, sample=True) if n >= 2 else 0.0
        pop_sd = _stats.stdev(data, sample=False)
        return {
            "n": n,
            "mean": mean,
            "sum": sx,
            "sum_sq": sx2,
            "Sx": sample_sd,
            "sigma_x": pop_sd,
            "min": min(data),
            "Q1": _stats.quantile(data, 0.25),
            "median": _stats.median(data),
            "Q3": _stats.quantile(data, 0.75),
            "max": max(data),
        }

    def _paired(self, x_name: str, y_name: str) -> tuple[list[float], list[float]]:
        """Fetch two equal-length, non-empty stat lists for two-variable work."""
        xs = self._lists[self._list_key(x_name)]
        ys = self._lists[self._list_key(y_name)]
        if not xs or not ys:
            raise TIError(f"2-Var Stats: {x_name}/{y_name} must be non-empty")
        if len(xs) != len(ys):
            raise TIError(f"2-Var Stats: {x_name} and {y_name} differ in length")
        return xs, ys

    def two_var_stats(self, x_name: str = "L1", y_name: str = "L2") -> dict:
        """2-Var Stats over (``x_name``, ``y_name``): per-list stats plus Σxy.

        Returns ``n``, the mean/sum/sum-of-squares and both standard deviations
        for each variable (``mean_x``/``Sx``/... and ``mean_y``/``Sy``/...), and
        the cross term ``sum_xy``. Reuses :mod:`abax.core.science.stats`.
        """
        xs, ys = self._paired(x_name, y_name)
        vx = self.one_var_stats(x_name)
        vy = self.one_var_stats(y_name)
        return {
            "n": vx["n"],
            "mean_x": vx["mean"],
            "sum_x": vx["sum"],
            "sum_x_sq": vx["sum_sq"],
            "Sx": vx["Sx"],
            "sigma_x": vx["sigma_x"],
            "min_x": vx["min"],
            "max_x": vx["max"],
            "mean_y": vy["mean"],
            "sum_y": vy["sum"],
            "sum_y_sq": vy["sum_sq"],
            "Sy": vy["Sx"],
            "sigma_y": vy["sigma_x"],
            "min_y": vy["min"],
            "max_y": vy["max"],
            "sum_xy": math.fsum(a * b for a, b in zip(xs, ys)),
        }

    def lin_reg(self, x_name: str = "L1", y_name: str = "L2") -> dict:
        """LinReg(ax+b) over (``x_name``, ``y_name``): slope a, intercept b, r, r2.

        Reuses :func:`abax.core.science.regression.linregress`; the TI names the
        slope ``a`` and the intercept ``b`` for the ``ax+b`` model.
        """
        xs, ys = self._paired(x_name, y_name)
        try:
            fit = _reg.linregress(xs, ys)
        except _reg.RegressionError as exc:
            raise TIError(f"LinReg: {exc}") from exc
        return {
            "a": fit["slope"],
            "b": fit["intercept"],
            "r": fit["r"],
            "r2": fit["r2"],
            "n": fit["n"],
        }

    # --- home screen -----------------------------------------------------
    def home_eval(self, expr: str) -> str:
        """Evaluate ``expr`` (X-free context; X = 0), set ``Ans``, log it.

        Returns the result as a TI-style string. ``Ans`` and any stored letter
        variables are substituted before compiling; a trailing ``->V`` / ``→V``
        stores the result in variable ``V``. On any error the TI string
        ``"ERR: SYNTAX"`` is returned and no exception propagates.
        """
        target = None
        store = _STORE_RE.match(expr)
        if store is not None:
            expr_body, target = store.group(1), store.group(2)
        else:
            expr_body = expr
        text = self._substitute(expr_body)
        try:
            f = graphing.compile_expr(_prep(text))
            value = float(f(0.0))
        except Exception:  # noqa: BLE001 - TI surfaces every error as a string
            return "ERR: SYNTAX"
        if not math.isfinite(value):
            return "ERR: SYNTAX"
        if target is not None:
            self._vars[target] = value
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
