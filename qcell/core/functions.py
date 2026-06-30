"""Built-in spreadsheet functions.

Two registries:

* :data:`FUNCTIONS` — eager functions. Each receives a list of already-evaluated
  arguments. A *range* argument arrives as a :class:`RangeValue`; scalars arrive
  as plain Python values. Aggregate functions flatten via :func:`_flatten`.
* :data:`LAZY_FUNCTIONS` — control-flow functions (IF, IFERROR, IFS, SWITCH,
  CHOOSE). Each receives ``(arg_nodes, ev)`` where ``ev(node)`` evaluates an AST
  node on demand, so untaken branches are never computed.

Error values (:class:`CellError`) propagate: most functions short-circuit on
the first error in their arguments.

Add a function by registering it in :data:`FUNCTIONS` (or :data:`LAZY_FUNCTIONS`).
User macros extend :data:`FUNCTIONS` at runtime (see :mod:`qcell.macros`).
"""

from __future__ import annotations

import math
import random
import re
import statistics
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any, Callable, Iterable

from .errors import CellError, is_error
from .values import RangeValue

# --- coercion helpers ------------------------------------------------------


def _flatten(args: Iterable[Any]) -> list[Any]:
    out: list[Any] = []
    for a in args:
        if isinstance(a, RangeValue):
            out.extend(a.flat())
        elif isinstance(a, list):
            out.extend(_flatten(a))
        else:
            out.append(a)
    return out


def _first_error(values: Iterable[Any]) -> CellError | None:
    for v in values:
        if is_error(v):
            return v
    return None


def _numbers_from(flat: Iterable[Any]) -> list[float]:
    """Keep only numeric values from an already-flattened iterable (SUM/AVERAGE rules)."""
    nums: list[float] = []
    for v in flat:
        if isinstance(v, bool):
            nums.append(1.0 if v else 0.0)
        elif isinstance(v, (int, float)):
            nums.append(float(v))
    return nums


def _numbers(args: Iterable[Any]) -> list[float]:
    """Flatten and keep only numeric values (Excel SUM/AVERAGE rules)."""
    return _numbers_checked(args)[1]


def _numbers_checked(args: Iterable[Any]) -> "tuple[CellError | None, list[float]]":
    """Single traversal of the flattened arguments, returning ``(first_error,
    numbers)``.

    Fuses :func:`_flatten`, :func:`_first_error` and :func:`_numbers_from` into
    one pass: a range is walked once and only the numeric list is built -- the
    full value list is never materialized. For ``SUM(A1:A100000)`` that drops two
    whole-range allocations (the flat list and a separate error scan). The
    returned ``numbers`` and ``first_error`` are byte-for-byte what
    ``_numbers_from(_flatten(args))`` and ``_first_error(_flatten(args))`` would
    produce over the same arguments (same values, same flatten order), so every
    aggregate keeps Excel's exact SUM/AVERAGE numeric and error-propagation
    semantics."""
    nums: list[float] = []
    push = nums.append
    state: list[CellError | None] = [None]

    def leaf(v: Any) -> None:
        if isinstance(v, bool):
            push(1.0 if v else 0.0)
        elif isinstance(v, (int, float)):
            push(float(v))
        elif state[0] is None and is_error(v):
            state[0] = v

    def walk(items: Iterable[Any]) -> None:
        for a in items:
            if isinstance(a, RangeValue):
                for row in a.grid:
                    for v in row:
                        if isinstance(v, bool):
                            push(1.0 if v else 0.0)
                        elif isinstance(v, (int, float)):
                            push(float(v))
                        elif state[0] is None and is_error(v):
                            state[0] = v
            elif isinstance(a, list):
                walk(a)
            else:
                leaf(a)

    walk(args)
    return state[0], nums


def _flat_checked(args: Iterable[Any]) -> "tuple[CellError | None, list[Any]]":
    """Flatten once, returning ``(first_error, flat_list)`` so callers that need
    both an error short-circuit and the values don't flatten the args twice."""
    flat = _flatten(args)
    return _first_error(flat), flat


def _as_number(v: Any) -> float:
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if v is None or v == "":
        return 0.0
    return float(v)  # may raise ValueError -> caught by the dispatcher


def _try_num(v: Any) -> float | None:
    try:
        return _as_number(v)
    except (TypeError, ValueError):
        return None


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1")
    return bool(v)


def _text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _equal(a: Any, b: Any) -> bool:
    an, bn = _try_num(a), _try_num(b)
    if an is not None and bn is not None and not isinstance(a, str) and not isinstance(b, str):
        return an == bn
    return _text(a).lower() == _text(b).lower()


def _arg(args: list, i: int, default: Any = None) -> Any:
    return args[i] if i < len(args) else default


# --- math / aggregate ------------------------------------------------------


def _sum(args):
    err, nums = _numbers_checked(args)
    return err if err is not None else sum(nums)


def _sumsq(args):
    err, nums = _numbers_checked(args)
    return err if err is not None else sum(n * n for n in nums)


def _average(args):
    err, nums = _numbers_checked(args)
    if err is not None:
        return err
    return sum(nums) / len(nums) if nums else CellError(CellError.DIV0)


def _count(args):
    return float(len(_numbers(args)))


def _counta(args):
    return float(sum(1 for v in _flatten(args) if v not in (None, "")))


def _countblank(args):
    return float(sum(1 for v in _flatten(args) if v in (None, "")))


def _min(args):
    err, nums = _numbers_checked(args)
    if err is not None:
        return err
    return min(nums) if nums else 0.0


def _max(args):
    err, nums = _numbers_checked(args)
    if err is not None:
        return err
    return max(nums) if nums else 0.0


def _median(args):
    err, nums = _numbers_checked(args)
    if err is not None:
        return err
    return statistics.median(nums) if nums else CellError(CellError.NUM)


def _mode(args):
    nums = _numbers(args)
    try:
        return statistics.mode(nums) if nums else CellError(CellError.NA)
    except statistics.StatisticsError:
        return CellError(CellError.NA)


def _product(args):
    err, nums = _numbers_checked(args)
    if err is not None:
        return err
    result = 1.0
    for n in nums:
        result *= n
    return result


def _stdev(args):
    nums = _numbers(args)
    if len(nums) < 2:
        return CellError(CellError.DIV0)
    return statistics.stdev(nums)


def _stdevp(args):
    nums = _numbers(args)
    return statistics.pstdev(nums) if nums else CellError(CellError.DIV0)


def _var(args):
    nums = _numbers(args)
    if len(nums) < 2:
        return CellError(CellError.DIV0)
    return statistics.variance(nums)


def _varp(args):
    nums = _numbers(args)
    return statistics.pvariance(nums) if nums else CellError(CellError.DIV0)


def _geomean(args):
    nums = _numbers(args)
    if not nums or any(n <= 0 for n in nums):
        return CellError(CellError.NUM)
    return math.prod(nums) ** (1.0 / len(nums))


def _harmean(args):
    nums = _numbers(args)
    if not nums or any(n == 0 for n in nums):
        return CellError(CellError.NUM)
    return len(nums) / sum(1.0 / n for n in nums)


def _percentile(args):
    nums = sorted(_numbers([_arg(args, 0)]))
    k = _try_num(_arg(args, 1))
    if not nums or k is None or not (0 <= k <= 1):
        return CellError(CellError.NUM)
    return _percentile_inc(nums, k)


def _quartile(args):
    nums = sorted(_numbers([_arg(args, 0)]))
    q = _try_num(_arg(args, 1))
    if not nums or q is None or not (0 <= q <= 4):
        return CellError(CellError.NUM)
    return _percentile_inc(nums, q / 4.0)


def _percentile_inc(nums: list[float], k: float) -> float:
    rank = k * (len(nums) - 1)
    lo = math.floor(rank)
    frac = rank - lo
    if lo + 1 < len(nums):
        return nums[lo] + frac * (nums[lo + 1] - nums[lo])
    return nums[lo]


def _paired(args) -> tuple[list[float], list[float]] | None:
    a, b = _arg(args, 0), _arg(args, 1)
    xs = a.flat() if isinstance(a, RangeValue) else _flatten([a])
    ys = b.flat() if isinstance(b, RangeValue) else _flatten([b])
    pairs = [
        (_try_num(x), _try_num(y))
        for x, y in zip(xs, ys)
        if _try_num(x) is not None and _try_num(y) is not None
    ]
    if not pairs:
        return None
    return [p[0] for p in pairs], [p[1] for p in pairs]


def _correl(args):
    pair = _paired(args)
    if pair is None or len(pair[0]) < 2:
        return CellError(CellError.DIV0)
    try:
        return statistics.correlation(pair[0], pair[1])
    except statistics.StatisticsError:
        return CellError(CellError.DIV0)


def _covar(args):
    pair = _paired(args)
    if pair is None or len(pair[0]) < 2:
        return CellError(CellError.DIV0)
    return statistics.covariance(pair[0], pair[1])


# --- regression (data science) --------------------------------------------
# Spreadsheet convention: SLOPE/INTERCEPT/RSQ(known_ys, known_xs).


def _regress(args, fn):
    pair = _paired(args)  # (ys, xs) in argument order
    if pair is None or len(pair[0]) < 2:
        return CellError(CellError.DIV0)
    from .science.regression import RegressionError

    try:
        return fn(pair[1], pair[0])  # fn(xs, ys)
    except (RegressionError, Exception):
        return CellError(CellError.DIV0)


def _slope(args):
    from .science.regression import slope

    return _regress(args, slope)


def _intercept(args):
    from .science.regression import intercept

    return _regress(args, intercept)


def _rsq(args):
    from .science.regression import rsq

    return _regress(args, rsq)


def _forecast(args):
    x = _try_num(_arg(args, 0))
    ys = _numbers([_arg(args, 1)])
    xs = _numbers([_arg(args, 2)])
    if x is None or len(xs) != len(ys) or len(xs) < 2:
        return CellError(CellError.VALUE)
    from .science.regression import RegressionError, forecast

    try:
        return forecast(x, xs, ys)
    except RegressionError:
        return CellError(CellError.DIV0)


# --- complex numbers (Excel IM* style; values are strings like "3+4i") ----


def _complex_build(args):
    from .science.complexnum import ComplexError, complexnum

    try:
        return complexnum(_as_number(_arg(args, 0, 0)), _as_number(_arg(args, 1, 0)))
    except (ComplexError, ValueError):
        return CellError(CellError.NUM)


def _c_unary(name):
    def f(args):
        from .science import complexnum as C

        try:
            return getattr(C, name)(_text(_arg(args, 0, "0")))
        except Exception:
            return CellError(CellError.NUM)

    return f


def _c_binary(name):
    def f(args):
        from .science import complexnum as C

        try:
            return getattr(C, name)(_text(_arg(args, 0, "0")), _text(_arg(args, 1, "0")))
        except Exception:
            return CellError(CellError.NUM)

    return f


def _c_variadic(name):
    def f(args):
        from .science import complexnum as C

        try:
            return getattr(C, name)(*[_text(a) for a in _flatten(args)])
        except Exception:
            return CellError(CellError.NUM)

    return f


def _impower(args):
    from .science.complexnum import im_power

    try:
        return im_power(_text(_arg(args, 0, "0")), _as_number(_arg(args, 1, 1)))
    except Exception:
        return CellError(CellError.NUM)


# --- matrix (scalar-returning; full ops live in the Python console / tool) -


def _convert(args):
    from .science.units import UnitError, convert

    val = _as_number(_arg(args, 0))
    try:
        return convert(val, _text(_arg(args, 1)), _text(_arg(args, 2)))
    except (UnitError, ValueError, TypeError):
        return CellError(CellError.NA)


def _interp(args):
    from .science.interp import InterpError, linear

    x = _try_num(_arg(args, 0))
    xs = _numbers([_arg(args, 1)])
    ys = _numbers([_arg(args, 2)])
    if x is None or len(xs) != len(ys) or len(xs) < 2:
        return CellError(CellError.VALUE)
    try:
        return linear(x, xs, ys)
    except InterpError:
        return CellError(CellError.VALUE)


def _rms(args):
    from .science.signal import SignalError, rms

    nums = _numbers(args)
    if not nums:
        return CellError(CellError.DIV0)
    try:
        return rms(nums)
    except SignalError:
        return CellError(CellError.DIV0)


def _skew(args):
    from .science.stats import StatsError, skewness

    nums = _numbers(args)
    try:
        return skewness(nums)
    except (StatsError, ValueError, ZeroDivisionError):
        return CellError(CellError.DIV0)


def _kurt(args):
    from .science.stats import StatsError, kurtosis

    nums = _numbers(args)
    try:
        return kurtosis(nums)
    except (StatsError, ValueError, ZeroDivisionError):
        return CellError(CellError.DIV0)


def _ttest(args):
    from .science.stats import StatsError, t_test_ind

    a = _numbers([_arg(args, 0)])
    b = _numbers([_arg(args, 1)])
    if len(a) < 2 or len(b) < 2:
        return CellError(CellError.VALUE)
    try:
        _t, p = t_test_ind(a, b)
        return p
    except (StatsError, ValueError, ZeroDivisionError):
        return CellError(CellError.VALUE)


def _normsdist(args):
    from .science.stats import normal_cdf

    x = _try_num(_arg(args, 0))
    return CellError(CellError.VALUE) if x is None else normal_cdf(x)


def _normsinv(args):
    from .science.stats import StatsError, normal_ppf

    p = _try_num(_arg(args, 0))
    if p is None:
        return CellError(CellError.VALUE)
    try:
        return normal_ppf(p)
    except (StatsError, ValueError):
        return CellError(CellError.NUM)


# --- distribution functions (Excel-named; familiar to spreadsheet + R users) ---


def _normdist(args):
    """NORMDIST(x, mean, sd, cumulative) — normal CDF (cumulative) or PDF."""
    from .science.stats import StatsError, normal_cdf, normal_pdf

    x = _try_num(_arg(args, 0))
    mu = _try_num(_arg(args, 1, 0.0))
    sd = _try_num(_arg(args, 2, 1.0))
    if x is None or mu is None or sd is None:
        return CellError(CellError.VALUE)
    cumulative = _truthy(_arg(args, 3, True))
    try:
        return normal_cdf(x, mu, sd) if cumulative else normal_pdf(x, mu, sd)
    except (StatsError, ValueError):
        return CellError(CellError.NUM)


def _norminv(args):
    """NORMINV(p, mean, sd) — inverse normal CDF (quantile)."""
    from .science.stats import StatsError, normal_ppf

    p = _try_num(_arg(args, 0))
    mu = _try_num(_arg(args, 1, 0.0))
    sd = _try_num(_arg(args, 2, 1.0))
    if p is None or mu is None or sd is None:
        return CellError(CellError.VALUE)
    try:
        return normal_ppf(p, mu, sd)
    except (StatsError, ValueError):
        return CellError(CellError.NUM)


def _tdist(args):
    """TDIST(x, df, tails) — Student-t right-tail (tails=1) or two-tail (tails=2). x>=0."""
    from .science.stats import StatsError, t_cdf

    x = _try_num(_arg(args, 0))
    df = _try_num(_arg(args, 1))
    tails = _try_num(_arg(args, 2, 2.0))
    if x is None or df is None or tails not in (1.0, 2.0) or x < 0:
        return CellError(CellError.NUM)
    try:
        rt = 1.0 - t_cdf(x, df)
        return rt * tails
    except (StatsError, ValueError):
        return CellError(CellError.NUM)


def _tinv(args):
    """TINV(p, df) — two-tailed inverse Student-t (Excel convention)."""
    from .science.stats import StatsError, t_ppf

    p = _try_num(_arg(args, 0))
    df = _try_num(_arg(args, 1))
    if p is None or df is None:
        return CellError(CellError.VALUE)
    try:
        return t_ppf(1.0 - p / 2.0, df)
    except (StatsError, ValueError):
        return CellError(CellError.NUM)


def _fdist(args):
    """FDIST(x, df1, df2) — F-distribution right-tail probability."""
    from .science.stats import StatsError, f_cdf

    x = _try_num(_arg(args, 0))
    d1 = _try_num(_arg(args, 1))
    d2 = _try_num(_arg(args, 2))
    if x is None or d1 is None or d2 is None:
        return CellError(CellError.VALUE)
    try:
        return 1.0 - f_cdf(x, d1, d2)
    except (StatsError, ValueError):
        return CellError(CellError.NUM)


def _finv(args):
    """FINV(p, df1, df2) — inverse of the F right-tail probability."""
    from .science.stats import StatsError, f_ppf

    p = _try_num(_arg(args, 0))
    d1 = _try_num(_arg(args, 1))
    d2 = _try_num(_arg(args, 2))
    if p is None or d1 is None or d2 is None:
        return CellError(CellError.VALUE)
    try:
        return f_ppf(1.0 - p, d1, d2)
    except (StatsError, ValueError):
        return CellError(CellError.NUM)


def _chidist(args):
    """CHIDIST(x, df) — chi-square right-tail probability."""
    from .science.stats import StatsError, chi_square_cdf

    x = _try_num(_arg(args, 0))
    df = _try_num(_arg(args, 1))
    if x is None or df is None:
        return CellError(CellError.VALUE)
    try:
        return 1.0 - chi_square_cdf(x, df)
    except (StatsError, ValueError):
        return CellError(CellError.NUM)


def _chiinv(args):
    """CHIINV(p, df) — inverse of the chi-square right-tail probability."""
    from .science.stats import StatsError, chi_square_ppf

    p = _try_num(_arg(args, 0))
    df = _try_num(_arg(args, 1))
    if p is None or df is None:
        return CellError(CellError.VALUE)
    try:
        return chi_square_ppf(1.0 - p, df)
    except (StatsError, ValueError):
        return CellError(CellError.NUM)


def _confidence(args):
    """CONFIDENCE(alpha, sd, n) — half-width of the normal confidence interval."""
    from .science.stats import StatsError, normal_ppf

    alpha = _try_num(_arg(args, 0))
    sd = _try_num(_arg(args, 1))
    n = _try_num(_arg(args, 2))
    if alpha is None or sd is None or n is None or not (0.0 < alpha < 1.0) or sd <= 0 or n < 1:
        return CellError(CellError.NUM)
    try:
        return normal_ppf(1.0 - alpha / 2.0) * sd / math.sqrt(n)
    except (StatsError, ValueError):
        return CellError(CellError.NUM)


def _mdeterm(args):
    from .science.matrix import MatrixError, determinant

    rng = _arg(args, 0)
    if not isinstance(rng, RangeValue):
        return CellError(CellError.VALUE)
    try:
        mat = [[float(_try_num(v) or 0.0) for v in row] for row in rng.grid]
        return determinant(mat)
    except (MatrixError, ValueError, ZeroDivisionError):
        return CellError(CellError.VALUE)


def _round(args):
    if (err := _first_error(args)):
        return err
    try:
        num = _as_number(args[0])
        digits = int(_as_number(args[1])) if len(args) > 1 else 0
    except (ValueError, IndexError, TypeError):
        return CellError(CellError.VALUE)
    return round(num, digits)


def _roundup(args):
    return _round_dir(args, up=True)


def _rounddown(args):
    return _round_dir(args, up=False)


def _round_dir(args, *, up: bool):
    if (err := _first_error(args)):
        return err
    try:
        num = _as_number(args[0])
        digits = int(_as_number(args[1])) if len(args) > 1 else 0
    except (ValueError, IndexError):
        return CellError(CellError.VALUE)
    factor = 10.0**digits
    scaled = num * factor
    rounded = math.ceil(abs(scaled)) if up else math.floor(abs(scaled))
    return math.copysign(rounded, num) / factor


def _ceiling(args):
    if (err := _first_error(args)):
        return err
    try:
        num = _as_number(args[0])
        sig = _as_number(args[1]) if len(args) > 1 else 1.0
    except (ValueError, IndexError):
        return CellError(CellError.VALUE)
    if sig == 0:
        return 0.0
    return math.ceil(num / sig) * sig


def _floor(args):
    if (err := _first_error(args)):
        return err
    try:
        num = _as_number(args[0])
        sig = _as_number(args[1]) if len(args) > 1 else 1.0
    except (ValueError, IndexError):
        return CellError(CellError.VALUE)
    if sig == 0:
        return CellError(CellError.DIV0)
    return math.floor(num / sig) * sig


def _trunc(args):
    if (err := _first_error(args)):
        return err
    try:
        num = _as_number(args[0])
        digits = int(_as_number(args[1])) if len(args) > 1 else 0
    except (ValueError, IndexError):
        return CellError(CellError.VALUE)
    factor = 10.0**digits
    return math.trunc(num * factor) / factor


def _int(args):
    if (err := _first_error(args)):
        return err
    try:
        return float(math.floor(_as_number(args[0])))
    except (ValueError, IndexError):
        return CellError(CellError.VALUE)


def _abs(args):
    if (err := _first_error(args)):
        return err
    n = _try_num(_arg(args, 0))
    return abs(n) if n is not None else CellError(CellError.VALUE)


def _sign(args):
    if (err := _first_error(args)):
        return err
    n = _try_num(_arg(args, 0))
    if n is None:
        return CellError(CellError.VALUE)
    return float((n > 0) - (n < 0))


def _sqrt(args):
    if (err := _first_error(args)):
        return err
    n = _try_num(_arg(args, 0))
    if n is None:
        return CellError(CellError.VALUE)
    return math.sqrt(n) if n >= 0 else CellError(CellError.NUM)


def _power(args):
    if (err := _first_error(args)):
        return err
    try:
        return math.pow(_as_number(args[0]), _as_number(args[1]))
    except (ValueError, IndexError, OverflowError):
        return CellError(CellError.NUM)


def _exp(args):
    n = _try_num(_arg(args, 0))
    try:
        return math.exp(n) if n is not None else CellError(CellError.VALUE)
    except OverflowError:
        return CellError(CellError.NUM)


def _ln(args):
    n = _try_num(_arg(args, 0))
    if n is None:
        return CellError(CellError.VALUE)
    return math.log(n) if n > 0 else CellError(CellError.NUM)


def _log(args):
    n = _try_num(_arg(args, 0))
    base = _try_num(_arg(args, 1, 10.0))
    if n is None or base is None:
        return CellError(CellError.VALUE)
    if n <= 0 or base <= 0 or base == 1:
        return CellError(CellError.NUM)
    return math.log(n, base)


def _log10(args):
    n = _try_num(_arg(args, 0))
    if n is None:
        return CellError(CellError.VALUE)
    return math.log10(n) if n > 0 else CellError(CellError.NUM)


def _mod(args):
    if (err := _first_error(args)):
        return err
    a, b = _try_num(_arg(args, 0)), _try_num(_arg(args, 1))
    if a is None or b is None:
        return CellError(CellError.VALUE)
    if b == 0:
        return CellError(CellError.DIV0)
    return a - b * math.floor(a / b)  # Excel MOD: sign follows divisor


def _gcd(args):
    nums = [int(n) for n in _numbers(args)]
    return float(math.gcd(*nums)) if nums else 0.0


def _lcm(args):
    nums = [int(n) for n in _numbers(args)]
    if not nums:
        return 0.0
    result = 1
    for n in nums:
        result = math.lcm(result, n)
    return float(result)


def _fact(args):
    n = _try_num(_arg(args, 0))
    if n is None or n < 0:
        return CellError(CellError.NUM)
    return float(math.factorial(int(n)))


def _pi(args):
    return math.pi


def _sumproduct(args):
    ranges = [a for a in args if isinstance(a, RangeValue)]
    if not ranges:
        return 0.0
    length = len(ranges[0])
    if any(len(r) != length for r in ranges):
        return CellError(CellError.VALUE)
    total = 0.0
    flats = [r.flat() for r in ranges]
    for i in range(length):
        product = 1.0
        for f in flats:
            product *= _try_num(f[i]) or 0.0
        total += product
    return total


def _large(args):
    nums = sorted(_numbers([_arg(args, 0)]), reverse=True)
    k = _try_num(_arg(args, 1, 1))
    if k is None or k < 1 or k > len(nums):
        return CellError(CellError.NUM)
    return nums[int(k) - 1]


def _small(args):
    nums = sorted(_numbers([_arg(args, 0)]))
    k = _try_num(_arg(args, 1, 1))
    if k is None or k < 1 or k > len(nums):
        return CellError(CellError.NUM)
    return nums[int(k) - 1]


def _rank(args):
    val = _try_num(_arg(args, 0))
    nums = _numbers([_arg(args, 1)])
    order = _try_num(_arg(args, 2, 0))
    if val is None or not nums:
        return CellError(CellError.NA)
    ordered = sorted(nums) if order else sorted(nums, reverse=True)
    try:
        return float(ordered.index(val) + 1)
    except ValueError:
        return CellError(CellError.NA)


def _rand(args):
    return random.random()


def _randbetween(args):
    lo, hi = _try_num(_arg(args, 0)), _try_num(_arg(args, 1))
    if lo is None or hi is None:
        return CellError(CellError.VALUE)
    return float(random.randint(int(lo), int(hi)))


# trig
def _trig(fn):
    def inner(args, fn=fn):
        n = _try_num(_arg(args, 0))
        if n is None:
            return CellError(CellError.VALUE)
        try:
            return fn(n)
        except (ValueError, OverflowError):
            return CellError(CellError.NUM)

    return inner


def _atan2(args):
    x, y = _try_num(_arg(args, 0)), _try_num(_arg(args, 1))
    if x is None or y is None:
        return CellError(CellError.VALUE)
    return math.atan2(y, x)  # Excel order is (x, y)


# --- conditional aggregation ----------------------------------------------


def _make_predicate(criteria: Any) -> Callable[[Any], bool]:
    if isinstance(criteria, bool):
        return lambda v: isinstance(v, bool) and v == criteria
    if isinstance(criteria, (int, float)):
        target = float(criteria)
        return lambda v: (n := _try_num(v)) is not None and not isinstance(v, str) and n == target
    s = str(criteria).strip()
    m = re.match(r"^(<=|>=|<>|=|<|>)(.*)$", s)
    op, rest = ("=", s)
    if m:
        op, rest = m.group(1), m.group(2).strip()
    num = _try_num(rest) if rest != "" else None
    if num is not None:

        def num_pred(v, op=op, num=num):
            x = _try_num(v)
            if x is None or isinstance(v, str):
                return False
            return _cmp(op, x, num)

        return num_pred

    pattern = _wildcard_re(rest)

    def text_pred(v, op=op, pattern=pattern, rest=rest):
        s2 = _text(v)
        if op == "=":
            return pattern.match(s2) is not None
        if op == "<>":
            return pattern.match(s2) is None
        return _cmp(op, s2.lower(), rest.lower())

    return text_pred


def _cmp(op: str, a, b) -> bool:
    if op == "=":
        return a == b
    if op == "<>":
        return a != b
    if op == "<":
        return a < b
    if op == ">":
        return a > b
    if op == "<=":
        return a <= b
    if op == ">=":
        return a >= b
    return False


@lru_cache(maxsize=256)
def _wildcard_re(pattern: str) -> re.Pattern:
    out = ["(?i)^"]
    for ch in pattern:
        if ch == "*":
            out.append(".*")
        elif ch == "?":
            out.append(".")
        else:
            out.append(re.escape(ch))
    out.append("$")
    return re.compile("".join(out))


def _countif(args):
    rng = _arg(args, 0)
    if not isinstance(rng, RangeValue):
        return CellError(CellError.VALUE)
    pred = _make_predicate(_arg(args, 1))
    return float(sum(1 for v in rng.flat() if pred(v)))


def _sumif(args):
    rng = _arg(args, 0)
    if not isinstance(rng, RangeValue):
        return CellError(CellError.VALUE)
    pred = _make_predicate(_arg(args, 1))
    sum_rng = _arg(args, 2)
    crit = rng.flat()
    values = sum_rng.flat() if isinstance(sum_rng, RangeValue) else crit
    total = 0.0
    for crit_v, sum_v in zip(crit, values):
        if pred(crit_v):
            total += _try_num(sum_v) or 0.0
    return total


def _averageif(args):
    rng = _arg(args, 0)
    if not isinstance(rng, RangeValue):
        return CellError(CellError.VALUE)
    pred = _make_predicate(_arg(args, 1))
    avg_rng = _arg(args, 2)
    crit = rng.flat()
    values = avg_rng.flat() if isinstance(avg_rng, RangeValue) else crit
    matched = [_try_num(s) or 0.0 for c, s in zip(crit, values) if pred(c)]
    return sum(matched) / len(matched) if matched else CellError(CellError.DIV0)


# --- lookup ----------------------------------------------------------------


def _vlookup(args):
    value = _arg(args, 0)
    table = _arg(args, 1)
    col_index = _try_num(_arg(args, 2))
    approximate = _truthy(_arg(args, 3, True))
    if not isinstance(table, RangeValue) or col_index is None:
        return CellError(CellError.VALUE)
    col = int(col_index)
    if col < 1 or col > table.ncols:
        return CellError(CellError.REF)
    match_row = _search_vector([row[0] for row in table.grid], value, approximate)
    if match_row is None:
        return CellError(CellError.NA)
    return table.grid[match_row][col - 1]


def _hlookup(args):
    value = _arg(args, 0)
    table = _arg(args, 1)
    row_index = _try_num(_arg(args, 2))
    approximate = _truthy(_arg(args, 3, True))
    if not isinstance(table, RangeValue) or row_index is None:
        return CellError(CellError.VALUE)
    row = int(row_index)
    if row < 1 or row > table.nrows:
        return CellError(CellError.REF)
    match_col = _search_vector(list(table.grid[0]), value, approximate)
    if match_col is None:
        return CellError(CellError.NA)
    return table.grid[row - 1][match_col]


def _search_vector(vec: list, value, approximate: bool) -> int | None:
    if not approximate:
        for i, v in enumerate(vec):
            if _equal(v, value):
                return i
        return None
    # approximate: largest entry <= value, assuming ascending order
    target = _try_num(value)
    best = None
    for i, v in enumerate(vec):
        n = _try_num(v)
        if target is not None and n is not None:
            if n <= target:
                best = i
            else:
                break
        elif _equal(v, value):
            return i
    return best


def _match(args):
    value = _arg(args, 0)
    rng = _arg(args, 1)
    match_type = _try_num(_arg(args, 2, 1))
    if not isinstance(rng, RangeValue):
        return CellError(CellError.VALUE)
    vec = rng.flat()
    mt = int(match_type) if match_type is not None else 1
    if mt == 0:
        for i, v in enumerate(vec):
            if _equal(v, value):
                return float(i + 1)
        return CellError(CellError.NA)
    target = _try_num(value)
    best = None
    for i, v in enumerate(vec):
        n = _try_num(v)
        if n is None or target is None:
            continue
        if mt > 0 and n <= target:
            best = i
        elif mt < 0 and n >= target:
            best = i
    return float(best + 1) if best is not None else CellError(CellError.NA)


def _index(args):
    rng = _arg(args, 0)
    if not isinstance(rng, RangeValue):
        return CellError(CellError.VALUE)
    row_num = _try_num(_arg(args, 1, 0))
    col_num = _try_num(_arg(args, 2, 0))
    r = int(row_num) if row_num is not None else 0
    c = int(col_num) if col_num is not None else 0
    # Single-row or single-column ranges accept one index.
    if rng.nrows == 1 and c == 0:
        c, r = r, 1
    if rng.ncols == 1 and c == 0:
        c = 1
    if r < 1 or r > rng.nrows or c < 1 or c > rng.ncols:
        return CellError(CellError.REF)
    return rng.grid[r - 1][c - 1]


# --- text ------------------------------------------------------------------


def _concat(args):
    err, flat = _flat_checked(args)
    return err or "".join(_text(v) for v in flat)


def _len(args):
    if (err := _first_error(args)):
        return err
    return float(len(_text(_arg(args, 0, ""))))


def _left(args):
    if (err := _first_error(args)):
        return err
    s = _text(_arg(args, 0, ""))
    n = int(_try_num(_arg(args, 1, 1)) or 0)
    return s[:n]


def _right(args):
    if (err := _first_error(args)):
        return err
    s = _text(_arg(args, 0, ""))
    n = int(_try_num(_arg(args, 1, 1)) or 0)
    return s[-n:] if n else ""


def _mid(args):
    if (err := _first_error(args)):
        return err
    try:
        s = _text(args[0])
        start = int(_as_number(args[1])) - 1
        length = int(_as_number(args[2]))
    except (ValueError, IndexError):
        return CellError(CellError.VALUE)
    start = max(start, 0)
    return s[start : start + length]


def _upper(args):
    return _first_error(args) or _text(_arg(args, 0, "")).upper()


def _lower(args):
    return _first_error(args) or _text(_arg(args, 0, "")).lower()


def _proper(args):
    return _first_error(args) or _text(_arg(args, 0, "")).title()


def _trim(args):
    return _first_error(args) or " ".join(_text(_arg(args, 0, "")).split())


def _find(args):
    needle = _text(_arg(args, 0, ""))
    hay = _text(_arg(args, 1, ""))
    start = int(_try_num(_arg(args, 2, 1)) or 1) - 1
    idx = hay.find(needle, max(start, 0))
    return float(idx + 1) if idx >= 0 else CellError(CellError.VALUE)


def _search(args):
    needle = _text(_arg(args, 0, "")).lower()
    hay = _text(_arg(args, 1, "")).lower()
    start = int(_try_num(_arg(args, 2, 1)) or 1) - 1
    idx = hay.find(needle, max(start, 0))
    return float(idx + 1) if idx >= 0 else CellError(CellError.VALUE)


def _replace(args):
    s = _text(_arg(args, 0, ""))
    start = int(_try_num(_arg(args, 1, 1)) or 1) - 1
    length = int(_try_num(_arg(args, 2, 0)) or 0)
    new = _text(_arg(args, 3, ""))
    if start < 0:
        return CellError(CellError.VALUE)
    return s[:start] + new + s[start + length :]


def _substitute(args):
    s = _text(_arg(args, 0, ""))
    old = _text(_arg(args, 1, ""))
    new = _text(_arg(args, 2, ""))
    if not old:
        return s
    # A 4th arg (instance) is optional; absence != 0, so check length explicitly.
    if len(args) <= 3 or args[3] in (None, ""):
        return s.replace(old, new)
    instance = _try_num(args[3])
    if instance is None:
        return s.replace(old, new)
    # replace only the nth occurrence
    n = int(instance)
    idx = -1
    for _ in range(n):
        idx = s.find(old, idx + 1)
        if idx < 0:
            return s
    return s[:idx] + new + s[idx + len(old) :]


def _rept(args):
    s = _text(_arg(args, 0, ""))
    n = int(_try_num(_arg(args, 1, 0)) or 0)
    return s * max(n, 0)


def _exact(args):
    return _text(_arg(args, 0, "")) == _text(_arg(args, 1, ""))


def _char(args):
    n = _try_num(_arg(args, 0))
    if n is None or not (1 <= n <= 0x10FFFF):
        return CellError(CellError.VALUE)
    return chr(int(n))


def _code(args):
    s = _text(_arg(args, 0, ""))
    return float(ord(s[0])) if s else CellError(CellError.VALUE)


def _text_fn(args):
    """TEXT(value, format) — minimal format-code subset."""
    if (err := _first_error(args)):
        return err
    val = _try_num(_arg(args, 0))
    fmt = _text(_arg(args, 1, ""))
    if val is None:
        return _text(_arg(args, 0, ""))
    if fmt.endswith("%"):
        decimals = _fmt_decimals(fmt[:-1])
        return f"{val * 100:.{decimals}f}%"
    if "." in fmt:
        return f"{val:.{_fmt_decimals(fmt)}f}"
    if fmt in ("0", "#"):
        return str(int(round(val)))
    if "," in fmt:
        return f"{val:,.{_fmt_decimals(fmt)}f}"
    return _text(_arg(args, 0, ""))


def _fmt_decimals(fmt: str) -> int:
    if "." in fmt:
        return len(fmt.split(".", 1)[1].replace("#", "0").rstrip().replace(" ", "")) or 0
    return 0


def _value(args):
    n = _try_num(_arg(args, 0))
    return n if n is not None else CellError(CellError.VALUE)


def _t(args):
    v = _arg(args, 0)
    return v if isinstance(v, str) else ""


# --- date / time -----------------------------------------------------------


def _parse_date(v: Any) -> datetime | None:
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v)
        except ValueError:
            return None
    return None


def _now(args):
    return datetime.now().isoformat(timespec="seconds")


def _today(args):
    return date.today().isoformat()


def _date(args):
    y, m, d = _try_num(_arg(args, 0)), _try_num(_arg(args, 1)), _try_num(_arg(args, 2))
    if None in (y, m, d):
        return CellError(CellError.VALUE)
    try:
        return date(int(y), int(m), int(d)).isoformat()
    except ValueError:
        return CellError(CellError.NUM)


def _date_part(getter):
    def inner(args, getter=getter):
        dt = _parse_date(_arg(args, 0))
        return float(getter(dt)) if dt else CellError(CellError.VALUE)

    return inner


def _weekday(args):
    dt = _parse_date(_arg(args, 0))
    if dt is None:
        return CellError(CellError.VALUE)
    # Default type 1: Sunday=1 .. Saturday=7.
    return float((dt.weekday() + 1) % 7 + 1)


def _datedif(args):
    start = _parse_date(_arg(args, 0))
    end = _parse_date(_arg(args, 1))
    unit = _text(_arg(args, 2, "D")).upper()
    if start is None or end is None:
        return CellError(CellError.VALUE)
    if end < start:
        return CellError(CellError.NUM)
    if unit == "D":
        return float((end - start).days)
    if unit == "M":
        return float((end.year - start.year) * 12 + (end.month - start.month) - (end.day < start.day))
    if unit == "Y":
        years = end.year - start.year
        if (end.month, end.day) < (start.month, start.day):
            years -= 1
        return float(years)
    return CellError(CellError.NUM)


def _edate(args):
    start = _parse_date(_arg(args, 0))
    months = _try_num(_arg(args, 1))
    if start is None or months is None:
        return CellError(CellError.VALUE)
    total = start.month - 1 + int(months)
    year = start.year + total // 12
    month = total % 12 + 1
    day = min(start.day, _days_in_month(year, month))
    return date(year, month, day).isoformat()


def _days(args):
    end = _parse_date(_arg(args, 0))
    start = _parse_date(_arg(args, 1))
    if end is None or start is None:
        return CellError(CellError.VALUE)
    return float((end - start).days)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day


# --- logical / info --------------------------------------------------------


def _and(args):
    err, flat = _flat_checked(args)
    return err or all(_truthy(v) for v in flat)


def _or(args):
    err, flat = _flat_checked(args)
    return err or any(_truthy(v) for v in flat)


def _xor(args):
    err, flat = _flat_checked(args)
    if err:
        return err
    return sum(1 for v in flat if _truthy(v)) % 2 == 1


def _not(args):
    if (err := _first_error(args)):
        return err
    return not _truthy(_arg(args, 0))


def _true(args):
    return True


def _false(args):
    return False


def _na(args):
    return CellError(CellError.NA)


def _isblank(args):
    return _arg(args, 0) in (None, "")


def _isnumber(args):
    v = _arg(args, 0)
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _istext(args):
    return isinstance(_arg(args, 0), str)


def _islogical(args):
    return isinstance(_arg(args, 0), bool)


def _iserror(args):
    return is_error(_arg(args, 0))


# --- lazy (control-flow) functions ----------------------------------------


def _lazy_if(nodes, ev):
    if not nodes:
        return CellError(CellError.VALUE)
    cond = ev(nodes[0])
    if is_error(cond):
        return cond
    if _truthy(cond):
        return ev(nodes[1]) if len(nodes) > 1 else True
    return ev(nodes[2]) if len(nodes) > 2 else False


def _lazy_iferror(nodes, ev):
    if not nodes:
        return CellError(CellError.VALUE)
    val = ev(nodes[0])
    if is_error(val):
        return ev(nodes[1]) if len(nodes) > 1 else ""
    return val


def _lazy_ifna(nodes, ev):
    if not nodes:
        return CellError(CellError.VALUE)
    val = ev(nodes[0])
    if is_error(val) and val.code == CellError.NA:
        return ev(nodes[1]) if len(nodes) > 1 else ""
    return val


def _lazy_ifs(nodes, ev):
    i = 0
    while i + 1 < len(nodes):
        cond = ev(nodes[i])
        if is_error(cond):
            return cond
        if _truthy(cond):
            return ev(nodes[i + 1])
        i += 2
    return CellError(CellError.NA)


def _lazy_switch(nodes, ev):
    if len(nodes) < 2:
        return CellError(CellError.VALUE)
    target = ev(nodes[0])
    i = 1
    while i + 1 < len(nodes):
        if _equal(target, ev(nodes[i])):
            return ev(nodes[i + 1])
        i += 2
    if i < len(nodes):  # trailing default
        return ev(nodes[i])
    return CellError(CellError.NA)


def _lazy_choose(nodes, ev):
    if not nodes:
        return CellError(CellError.VALUE)
    idx = ev(nodes[0])
    if is_error(idx):
        return idx
    k = _try_num(idx)
    if k is None or k < 1 or int(k) >= len(nodes):
        return CellError(CellError.VALUE)
    return ev(nodes[int(k)])


# --- registries ------------------------------------------------------------

FUNCTIONS: dict[str, Callable[[list], Any]] = {
    # aggregate
    "SUM": _sum, "SUMSQ": _sumsq, "AVERAGE": _average, "AVG": _average,
    "COUNT": _count, "COUNTA": _counta, "COUNTBLANK": _countblank,
    "MIN": _min, "MAX": _max, "MEDIAN": _median, "MODE": _mode, "PRODUCT": _product,
    "STDEV": _stdev, "STDEVP": _stdevp, "VAR": _var, "VARP": _varp,
    "GEOMEAN": _geomean, "HARMEAN": _harmean,
    "PERCENTILE": _percentile, "QUARTILE": _quartile,
    "CORREL": _correl, "COVAR": _covar,
    "SLOPE": _slope, "INTERCEPT": _intercept, "RSQ": _rsq, "FORECAST": _forecast,
    # complex numbers
    "COMPLEX": _complex_build, "IMSUM": _c_variadic("im_sum"),
    "IMPRODUCT": _c_variadic("im_product"), "IMSUB": _c_binary("im_sub"),
    "IMDIV": _c_binary("im_div"), "IMABS": _c_unary("im_abs"),
    "IMREAL": _c_unary("im_real"), "IMAGINARY": _c_unary("im_imaginary"),
    "IMCONJUGATE": _c_unary("im_conjugate"), "IMARGUMENT": _c_unary("im_argument"),
    "IMSQRT": _c_unary("im_sqrt"), "IMEXP": _c_unary("im_exp"), "IMLN": _c_unary("im_ln"),
    "IMSIN": _c_unary("im_sin"), "IMCOS": _c_unary("im_cos"), "IMPOWER": _impower,
    # matrix (scalar)
    "MDETERM": _mdeterm,
    # units
    "CONVERT": _convert,
    # signal / data
    "INTERP": _interp, "RMS": _rms,
    # statistics
    "SKEW": _skew, "KURT": _kurt, "TTEST": _ttest,
    "NORMSDIST": _normsdist, "NORMSINV": _normsinv,
    # distribution functions (normal / t / F / chi-square) + confidence interval
    "NORMDIST": _normdist, "NORMINV": _norminv,
    "TDIST": _tdist, "TINV": _tinv,
    "FDIST": _fdist, "FINV": _finv,
    "CHIDIST": _chidist, "CHIINV": _chiinv,
    "CONFIDENCE": _confidence,
    "LARGE": _large, "SMALL": _small, "RANK": _rank,
    "SUMPRODUCT": _sumproduct,
    # conditional aggregate
    "SUMIF": _sumif, "COUNTIF": _countif, "AVERAGEIF": _averageif,
    # math
    "ROUND": _round, "ROUNDUP": _roundup, "ROUNDDOWN": _rounddown,
    "CEILING": _ceiling, "FLOOR": _floor, "TRUNC": _trunc, "INT": _int,
    "ABS": _abs, "SIGN": _sign, "SQRT": _sqrt, "POWER": _power,
    "EXP": _exp, "LN": _ln, "LOG": _log, "LOG10": _log10, "MOD": _mod,
    "GCD": _gcd, "LCM": _lcm, "FACT": _fact, "PI": _pi,
    "RAND": _rand, "RANDBETWEEN": _randbetween,
    "SIN": _trig(math.sin), "COS": _trig(math.cos), "TAN": _trig(math.tan),
    "ASIN": _trig(math.asin), "ACOS": _trig(math.acos), "ATAN": _trig(math.atan),
    "ATAN2": _atan2, "DEGREES": _trig(math.degrees), "RADIANS": _trig(math.radians),
    # lookup
    "VLOOKUP": _vlookup, "HLOOKUP": _hlookup, "MATCH": _match, "INDEX": _index,
    # text
    "CONCAT": _concat, "CONCATENATE": _concat, "LEN": _len,
    "LEFT": _left, "RIGHT": _right, "MID": _mid,
    "UPPER": _upper, "LOWER": _lower, "PROPER": _proper, "TRIM": _trim,
    "FIND": _find, "SEARCH": _search, "REPLACE": _replace, "SUBSTITUTE": _substitute,
    "REPT": _rept, "EXACT": _exact, "CHAR": _char, "CODE": _code,
    "TEXT": _text_fn, "VALUE": _value, "T": _t,
    # date/time
    "NOW": _now, "TODAY": _today, "DATE": _date,
    "YEAR": _date_part(lambda d: d.year), "MONTH": _date_part(lambda d: d.month),
    "DAY": _date_part(lambda d: d.day), "HOUR": _date_part(lambda d: d.hour),
    "MINUTE": _date_part(lambda d: d.minute), "SECOND": _date_part(lambda d: d.second),
    "WEEKDAY": _weekday, "DATEDIF": _datedif, "EDATE": _edate, "DAYS": _days,
    # logical / info
    "AND": _and, "OR": _or, "XOR": _xor, "NOT": _not, "TRUE": _true, "FALSE": _false,
    "NA": _na, "ISBLANK": _isblank, "ISNUMBER": _isnumber, "ISTEXT": _istext,
    "ISLOGICAL": _islogical, "ISERROR": _iserror,
}

LAZY_FUNCTIONS: dict[str, Callable] = {
    "IF": _lazy_if,
    "IFERROR": _lazy_iferror,
    "IFNA": _lazy_ifna,
    "IFS": _lazy_ifs,
    "SWITCH": _lazy_switch,
    "CHOOSE": _lazy_choose,
}


# --- RF / ham-radio functions (backed by core.science.rf) ------------------
# SI base units (Hz, m, W, H, F); see docs/rf-toolkit.md. The GUI presents
# metric + imperial, but the formula layer stays unit-neutral.

_RF_REQUIRED = object()


def _rf_numeric(name: str, spec: tuple):
    """Wrap a numeric ``core.science.rf`` function for the formula layer.

    ``spec`` is one entry per positional argument: ``_RF_REQUIRED`` for a required
    arg, or a default value for an optional one. Missing/blank required args →
    ``#VALUE!``; domain errors (rf raises ``ValueError``) → ``#NUM!``.
    """
    def wrapper(args):
        from .science import rf as R

        vals = []
        for i, dflt in enumerate(spec):
            raw = _arg(args, i, None)
            if raw is None or raw == "":
                if dflt is _RF_REQUIRED:
                    return CellError(CellError.VALUE)
                vals.append(dflt)
            else:
                try:
                    vals.append(_as_number(raw))
                except (ValueError, TypeError):
                    return CellError(CellError.VALUE)
        try:
            return getattr(R, name)(*vals)
        except (ValueError, TypeError, ZeroDivisionError, OverflowError):
            return CellError(CellError.NUM)
    return wrapper


def _rf_gridsquare(args):
    from .science import rf as R
    try:
        prec = int(_as_number(_arg(args, 2, 6)))
        return R.grid_square(_as_number(_arg(args, 0)), _as_number(_arg(args, 1)), prec)
    except (ValueError, TypeError):
        return CellError(CellError.NUM)


def _rf_grid_component(idx: int):
    def wrapper(args):
        from .science import rf as R
        try:
            return R.grid_to_latlon(_text(_arg(args, 0)))[idx]
        except (ValueError, TypeError):
            return CellError(CellError.NUM)
    return wrapper


def _rf_grid_pair(fn: str):
    def wrapper(args):
        from .science import rf as R
        try:
            return getattr(R, fn)(_text(_arg(args, 0)), _text(_arg(args, 1)))
        except (ValueError, TypeError):
            return CellError(CellError.NUM)
    return wrapper


_R = _RF_REQUIRED
FUNCTIONS.update({
    "DBM2W": _rf_numeric("dbm_to_w", (_R,)),
    "W2DBM": _rf_numeric("w_to_dbm", (_R,)),
    "DBW2W": _rf_numeric("dbw_to_w", (_R,)),
    "W2DBW": _rf_numeric("w_to_dbw", (_R,)),
    "DB2RATIO": _rf_numeric("db_to_ratio", (_R,)),
    "RATIO2DB": _rf_numeric("ratio_to_db", (_R,)),
    "DBADD": _rf_numeric("db_add", (_R, _R)),
    "DBUV2DBM": _rf_numeric("dbuv_to_dbm", (_R, 50.0)),
    "SUNIT2DBM": _rf_numeric("s_unit_to_dbm", (_R,)),
    "NOISEFLOOR": _rf_numeric("noise_floor_dbm", (_R, 290.0)),
    "NF2NT": _rf_numeric("nf_to_noise_temp", (_R, 290.0)),
    "NT2NF": _rf_numeric("noise_temp_to_nf", (_R, 290.0)),
    "WAVELENGTH": _rf_numeric("wavelength", (_R, 1.0)),
    "WL2FREQ": _rf_numeric("freq_from_wavelength", (_R, 1.0)),
    "DIPOLELEN": _rf_numeric("dipole_length", (_R, 0.95)),
    "MONOPOLELEN": _rf_numeric("monopole_length", (_R, 0.95)),
    "XL": _rf_numeric("reactance_inductive", (_R, _R)),
    "XC": _rf_numeric("reactance_capacitive", (_R, _R)),
    "RESFREQ": _rf_numeric("resonant_freq", (_R, _R)),
    "VSWR": _rf_numeric("vswr_from_z", (_R, 50.0)),
    "VSWRG": _rf_numeric("vswr_from_gamma", (_R,)),
    "REFLCOEF": _rf_numeric("reflection_coefficient", (_R, 50.0)),
    "RETURNLOSS": _rf_numeric("return_loss_db", (_R,)),
    "MISMATCHLOSS": _rf_numeric("mismatch_loss_db", (_R,)),
    "VSWR2GAMMA": _rf_numeric("vswr_to_gamma", (_R,)),
    "Z0COAX": _rf_numeric("z0_coax", (_R, _R, 1.0)),
    "VELFACTOR": _rf_numeric("velocity_factor", (_R,)),
    "FSPL": _rf_numeric("fspl_db", (_R, _R)),
    "FRIIS": _rf_numeric("friis_rx_dbm", (_R, _R, _R, _R, _R)),
    "EIRP": _rf_numeric("eirp_dbm", (_R, _R, 0.0)),
    "FRESNEL": _rf_numeric("fresnel_radius", (_R, _R, _R, 1)),
    "RADIOHORIZON": _rf_numeric("radio_horizon_km", (_R, 0.0)),
    "SKINDEPTH": _rf_numeric("skin_depth", (_R, 5.8e7, 1.0)),
    "DBI2DBD": _rf_numeric("dbi_to_dbd", (_R,)),
    "DBD2DBI": _rf_numeric("dbd_to_dbi", (_R,)),
    "GRIDSQUARE": _rf_gridsquare,
    "GRIDLAT": _rf_grid_component(0),
    "GRIDLON": _rf_grid_component(1),
    "GRIDDIST": _rf_grid_pair("grid_distance_km"),
    "GRIDBEARING": _rf_grid_pair("grid_bearing_deg"),
})
