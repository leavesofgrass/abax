"""HP-48 style function graphing for abax (pure-stdlib, braille rendering).

Compiles a math expression in ``x`` against a restricted namespace, samples it
over a range, and renders the resulting points onto a Unicode braille canvas
(the U+2800 block, 2 dots wide by 4 dots tall per character) for the TUI. The
sampled points are also returned directly so a GUI plotter can draw them.

The braille canvas packs a (``width`` * 2) by (``height`` * 4) pixel grid into
``height`` lines of ``width`` characters. Each cell carries eight dots whose
standard numbering 1-8 maps to bits::

    1 4      0x01 0x08
    2 5  ->  0x02 0x10
    3 6      0x04 0x20
    7 8      0x40 0x80

so the left pixel column is dots 1,2,3,7 (top to bottom) and the right column
is dots 4,5,6,8; a cell renders as ``chr(0x2800 | bits)``.
"""

from __future__ import annotations

import math
from typing import Callable

# Points are (x, y) pairs; y is None at undefined samples.
Point = tuple[float, "float | None"]


class GraphError(Exception):
    """Raised when an expression cannot be compiled or safely evaluated."""


# Safe names exposed to a compiled expression, in addition to ``x``. Anything
# not present here (and ``__builtins__`` being empty) makes the eval fail.
_SAFE_NAMES: dict[str, object] = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "sqrt": math.sqrt,
    "exp": math.exp,
    "log": math.log,
    "ln": math.log,
    "log10": math.log10,
    "pow": math.pow,
    "fabs": math.fabs,
    "floor": math.floor,
    "ceil": math.ceil,
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "radians": math.radians,
    "degrees": math.degrees,
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    # TI MATH/NUM/PRB-menu functions (so pasted tokens actually evaluate)
    "trunc": math.trunc,
    "iPart": math.trunc,
    "fPart": lambda v: v - math.trunc(v),
    "int": math.floor,
    "gcd": math.gcd,
    "lcm": math.lcm,
    "remainder": lambda a, b: a - b * math.floor(a / b),
    "cbrt": getattr(math, "cbrt", lambda v: math.copysign(abs(v) ** (1.0 / 3.0), v)),
    "xroot": lambda n, v: math.copysign(abs(v) ** (1.0 / n), v),
    "logBASE": lambda v, b: math.log(v) / math.log(b),
    "factorial": math.factorial,
    "perm": math.perm,
    "comb": math.comb,
}

# Bit values for the eight braille dots, keyed by their standard 1-8 number.
_DOT_BITS: dict[int, int] = {
    1: 0x01,
    2: 0x02,
    3: 0x04,
    4: 0x08,
    5: 0x10,
    6: 0x20,
    7: 0x40,
    8: 0x80,
}

# Map a (col, row) within a cell (col in {0,1}, row in 0..3) to its dot bit.
_PIXEL_BITS: tuple[tuple[int, ...], ...] = (
    (_DOT_BITS[1], _DOT_BITS[4]),  # row 0
    (_DOT_BITS[2], _DOT_BITS[5]),  # row 1
    (_DOT_BITS[3], _DOT_BITS[6]),  # row 2
    (_DOT_BITS[7], _DOT_BITS[8]),  # row 3
)

_BRAILLE_BASE = 0x2800


def compile_expr(expr: str) -> Callable[[float], float]:
    """Compile ``expr`` into a callable ``f(x) -> float``.

    The expression is evaluated with an empty ``__builtins__`` and only the safe
    math names (plus ``x``) in scope. A caret ``^`` is treated as ``**``. Raises
    :class:`GraphError` if the expression cannot be compiled or references a name
    outside the allowed set.
    """
    source = expr.replace("^", "**")
    try:
        code = compile(source, "<graph-expr>", "eval")
    except SyntaxError as exc:
        raise GraphError(f"cannot compile {expr!r}: {exc}") from exc

    globals_ns: dict[str, object] = {"__builtins__": {}}

    def f(x: float) -> float:
        local_ns = dict(_SAFE_NAMES)
        local_ns["x"] = x
        try:
            return eval(code, globals_ns, local_ns)  # noqa: S307 - sandboxed ns
        except (ValueError, ZeroDivisionError, OverflowError, ArithmeticError):
            raise
        except Exception as exc:  # NameError, TypeError, etc.
            raise GraphError(f"cannot evaluate {expr!r}: {exc}") from exc

    # Probe once so name errors surface at compile time, not first sample.
    try:
        f(0.0)
    except GraphError:
        raise
    except (ValueError, ZeroDivisionError, OverflowError, ArithmeticError):
        pass  # domain error at x=0 is fine; the expression itself is valid
    return f


def sample(
    expr: str | Callable[[float], float],
    xmin: float,
    xmax: float,
    n: int = 160,
) -> list[Point]:
    """Sample ``expr`` at ``n`` evenly spaced points in ``[xmin, xmax]``.

    ``expr`` may be a string (compiled here) or an already-compiled callable.
    Each result is ``(x, y)`` where ``y`` is ``None`` at points where the
    function is undefined (it raises a math/arithmetic error).
    """
    f = compile_expr(expr) if isinstance(expr, str) else expr
    if n <= 0:
        return []
    if n == 1:
        xs = [xmin]
    else:
        step = (xmax - xmin) / (n - 1)
        xs = [xmin + step * i for i in range(n)]

    points: list[Point] = []
    for x in xs:
        try:
            y = float(f(x))
            if not math.isfinite(y):
                y = None
        except (ValueError, ZeroDivisionError, OverflowError, ArithmeticError):
            y = None
        points.append((x, y))
    return points


def _finite_points(points: list[Point]) -> list[tuple[float, float]]:
    return [
        (x, y)
        for (x, y) in points
        if y is not None and math.isfinite(x) and math.isfinite(y)
    ]


def braille_plot(
    points: list[Point],
    width: int = 70,
    height: int = 22,
    *,
    xmin: float | None = None,
    xmax: float | None = None,
    ymin: float | None = None,
    ymax: float | None = None,
) -> str:
    """Render ``points`` onto a braille canvas ``height`` lines by ``width`` chars.

    ``points`` are ``(x, y)`` pairs where ``y`` may be ``None`` (undefined and
    skipped). When a bound is ``None`` it is auto-ranged from the finite points;
    the y-range is padded slightly and a flat line is given a unit span. A zero
    axis line is drawn for any axis whose value 0 falls inside the range. Points
    outside the resolved range are skipped. Returns the multi-line string.
    """
    width = max(1, int(width))
    height = max(1, int(height))
    px_w = width * 2
    px_h = height * 4

    finite = _finite_points(points)

    # Resolve x-range.
    if xmin is None or xmax is None:
        if finite:
            xs = [x for (x, _y) in finite]
            ax_min, ax_max = min(xs), max(xs)
        else:
            ax_min, ax_max = 0.0, 1.0
        rxmin = ax_min if xmin is None else xmin
        rxmax = ax_max if xmax is None else xmax
    else:
        rxmin, rxmax = xmin, xmax
    if rxmax <= rxmin:
        rxmax = rxmin + 1.0

    # Resolve y-range (pad slightly; handle a flat line).
    if ymin is None or ymax is None:
        if finite:
            ys = [y for (_x, y) in finite]
            ay_min, ay_max = min(ys), max(ys)
        else:
            ay_min, ay_max = 0.0, 1.0
        if ay_max <= ay_min:
            ay_min -= 1.0
            ay_max += 1.0
        else:
            pad = (ay_max - ay_min) * 0.05
            ay_min -= pad
            ay_max += pad
        rymin = ay_min if ymin is None else ymin
        rymax = ay_max if ymax is None else ymax
    else:
        rymin, rymax = ymin, ymax
    if rymax <= rymin:
        rymax = rymin + 1.0

    # Bit grid: one int per character cell.
    cells = [[0] * width for _ in range(height)]

    def set_pixel(px: int, py: int) -> None:
        if 0 <= px < px_w and 0 <= py < px_h:
            cell = cells[py // 4][px // 2]
            cells[py // 4][px // 2] = cell | _PIXEL_BITS[py % 4][px % 2]

    def to_px(x: float) -> int:
        frac = (x - rxmin) / (rxmax - rxmin)
        return int(round(frac * (px_w - 1)))

    def to_py(y: float) -> int:
        frac = (y - rymin) / (rymax - rymin)
        # Invert so larger y is higher on screen (smaller row).
        return int(round((1.0 - frac) * (px_h - 1)))

    # Zero axis lines (drawn first so data sits on top).
    if rymin <= 0.0 <= rymax:
        zy = to_py(0.0)
        for px in range(px_w):
            set_pixel(px, zy)
    if rxmin <= 0.0 <= rxmax:
        zx = to_px(0.0)
        for py in range(px_h):
            set_pixel(zx, py)

    # Plot the data points.
    for x, y in finite:
        if not (rxmin <= x <= rxmax and rymin <= y <= rymax):
            continue
        set_pixel(to_px(x), to_py(y))

    lines = ["".join(chr(_BRAILLE_BASE | bits) for bits in row) for row in cells]
    return "\n".join(lines)
