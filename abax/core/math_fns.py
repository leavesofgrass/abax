"""Extended pure-stdlib math / information spreadsheet functions.

Companion to :mod:`abax.core.functions`. Each callable follows the engine's
eager convention: it receives a single ``args`` list of already-evaluated
values (float/str/bool/None/CellError/RangeValue/nested-list) and returns a
scalar (float/str/bool) or a :class:`abax.core.errors.CellError` value that
propagates. No bare exception is allowed to escape.

Register with the engine via :func:`register`, which merges every implemented
name (UPPERCASE -> callable) into the engine's function table. :data:`SIGNATURES`
carries one help-string entry per registered name.
"""

from __future__ import annotations

import math

from .errors import CellError, is_error
from .functions.helpers import (  # noqa: F401  (_flatten kept per module contract)
    _arg,
    _as_number,
    _flatten,
    _numbers,
    _text,
    _try_num,
)

# --- small internal utilities ----------------------------------------------


def _num(v):
    """Coerce a single arg to float, or return #VALUE! on failure."""
    try:
        return _as_number(v)
    except (ValueError, TypeError):
        return CellError(CellError.VALUE)


def _NUM():
    return CellError(CellError.NUM)


def _DIV0():
    return CellError(CellError.DIV0)


# --- hyperbolic & inverse --------------------------------------------------


def _sinh(args):
    x = _num(_arg(args, 0))
    if is_error(x):
        return x
    try:
        return math.sinh(x)
    except (ValueError, OverflowError):
        return _NUM()


def _cosh(args):
    x = _num(_arg(args, 0))
    if is_error(x):
        return x
    try:
        return math.cosh(x)
    except (ValueError, OverflowError):
        return _NUM()


def _tanh(args):
    x = _num(_arg(args, 0))
    if is_error(x):
        return x
    return math.tanh(x)


def _asinh(args):
    x = _num(_arg(args, 0))
    if is_error(x):
        return x
    return math.asinh(x)


def _acosh(args):
    x = _num(_arg(args, 0))
    if is_error(x):
        return x
    if x < 1:
        return _NUM()
    return math.acosh(x)


def _atanh(args):
    x = _num(_arg(args, 0))
    if is_error(x):
        return x
    if x <= -1 or x >= 1:
        return _NUM()
    return math.atanh(x)


# --- reciprocal trig -------------------------------------------------------


def _sec(args):
    x = _num(_arg(args, 0))
    if is_error(x):
        return x
    c = math.cos(x)
    if c == 0:
        return _DIV0()
    return 1.0 / c


def _csc(args):
    x = _num(_arg(args, 0))
    if is_error(x):
        return x
    s = math.sin(x)
    if s == 0:
        return _DIV0()
    return 1.0 / s


def _cot(args):
    x = _num(_arg(args, 0))
    if is_error(x):
        return x
    s = math.sin(x)
    if s == 0:
        return _DIV0()
    return math.cos(x) / s


def _sech(args):
    x = _num(_arg(args, 0))
    if is_error(x):
        return x
    try:
        return 1.0 / math.cosh(x)
    except OverflowError:
        return 0.0


def _csch(args):
    x = _num(_arg(args, 0))
    if is_error(x):
        return x
    s = math.sinh(x)
    if s == 0:
        return _DIV0()
    return 1.0 / s


def _coth(args):
    x = _num(_arg(args, 0))
    if is_error(x):
        return x
    t = math.tanh(x)
    if t == 0:
        return _DIV0()
    return 1.0 / t


def _acot(args):
    x = _num(_arg(args, 0))
    if is_error(x):
        return x
    return math.pi / 2 - math.atan(x)


# --- rounding / int --------------------------------------------------------


def _even(args):
    x = _num(_arg(args, 0))
    if is_error(x):
        return x
    if x == 0:
        return 0.0
    n = math.ceil(abs(x) / 2.0) * 2
    return float(-n if x < 0 else n)


def _odd(args):
    x = _num(_arg(args, 0))
    if is_error(x):
        return x
    if x == 0:
        return 1.0
    a = abs(x)
    n = math.ceil((a + 1.0) / 2.0) * 2 - 1
    return float(-n if x < 0 else n)


def _mround(args):
    x = _num(_arg(args, 0))
    if is_error(x):
        return x
    m = _num(_arg(args, 1))
    if is_error(m):
        return m
    if m == 0:
        return 0.0
    if (x > 0 and m < 0) or (x < 0 and m > 0):
        return _NUM()
    return math.floor(x / m + 0.5) * m


def _quotient(args):
    a = _num(_arg(args, 0))
    if is_error(a):
        return a
    b = _num(_arg(args, 1))
    if is_error(b):
        return b
    if b == 0:
        return _DIV0()
    return float(math.trunc(a / b))


def _sqrtpi(args):
    x = _num(_arg(args, 0))
    if is_error(x):
        return x
    v = x * math.pi
    if v < 0:
        return _NUM()
    return math.sqrt(v)


def _iso_ceiling(args):
    x = _num(_arg(args, 0))
    if is_error(x):
        return x
    sig_raw = _arg(args, 1, 1)
    sig = _num(sig_raw)
    if is_error(sig):
        return sig
    if sig == 0:
        return 0.0
    sig = abs(sig)
    return math.ceil(x / sig) * sig


# --- combinatorics ---------------------------------------------------------


def _int_domain(v):
    """Coerce to a non-negative-ish integer via trunc; return (int, error)."""
    n = _num(v)
    if is_error(n):
        return None, n
    return math.trunc(n), None


def _factdouble(args):
    n, err = _int_domain(_arg(args, 0))
    if err is not None:
        return err
    if n < -1:
        return _NUM()
    if n in (-1, 0):
        return 1.0
    result = 1
    k = n
    while k > 1:
        result *= k
        k -= 2
    return float(result)


def _combin(args):
    n, err = _int_domain(_arg(args, 0))
    if err is not None:
        return err
    k, err = _int_domain(_arg(args, 1))
    if err is not None:
        return err
    if n < 0 or k < 0 or k > n:
        return _NUM()
    return float(math.comb(n, k))


def _combina(args):
    n, err = _int_domain(_arg(args, 0))
    if err is not None:
        return err
    k, err = _int_domain(_arg(args, 1))
    if err is not None:
        return err
    if n < 0 or k < 0:
        return _NUM()
    if n == 0 and k == 0:
        return 1.0
    return float(math.comb(n + k - 1, k))


def _permut(args):
    n, err = _int_domain(_arg(args, 0))
    if err is not None:
        return err
    k, err = _int_domain(_arg(args, 1))
    if err is not None:
        return err
    if n < 0 or k < 0 or k > n:
        return _NUM()
    return float(math.perm(n, k))


def _permutationa(args):
    n, err = _int_domain(_arg(args, 0))
    if err is not None:
        return err
    k, err = _int_domain(_arg(args, 1))
    if err is not None:
        return err
    if n < 0 or k < 0:
        return _NUM()
    return float(n ** k)


def _multinomial(args):
    nums = _numbers(args)
    if not nums:
        return _NUM()
    ints = []
    total = 0
    for v in nums:
        iv = math.trunc(v)
        if iv < 0:
            return _NUM()
        ints.append(iv)
        total += iv
    denom = 1
    for iv in ints:
        denom *= math.factorial(iv)
    return float(math.factorial(total) // denom)


# --- sum families ----------------------------------------------------------


def _sumx2my2(args):
    xs = _numbers([_arg(args, 0)])
    ys = _numbers([_arg(args, 1)])
    if len(xs) != len(ys):
        return CellError(CellError.NA)
    return float(sum(x * x - y * y for x, y in zip(xs, ys)))


def _sumx2py2(args):
    xs = _numbers([_arg(args, 0)])
    ys = _numbers([_arg(args, 1)])
    if len(xs) != len(ys):
        return CellError(CellError.NA)
    return float(sum(x * x + y * y for x, y in zip(xs, ys)))


def _sumxmy2(args):
    xs = _numbers([_arg(args, 0)])
    ys = _numbers([_arg(args, 1)])
    if len(xs) != len(ys):
        return CellError(CellError.NA)
    return float(sum((x - y) ** 2 for x, y in zip(xs, ys)))


def _seriessum(args):
    x = _num(_arg(args, 0))
    if is_error(x):
        return x
    n = _num(_arg(args, 1))
    if is_error(n):
        return n
    m = _num(_arg(args, 2))
    if is_error(m):
        return m
    coeffs = _numbers([_arg(args, 3)])
    if not coeffs:
        return _NUM()
    try:
        return float(sum(c * x ** (n + i * m) for i, c in enumerate(coeffs)))
    except (ValueError, OverflowError, ZeroDivisionError):
        return _NUM()


# --- numerals --------------------------------------------------------------

_ROMAN_TABLE = (
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
)

_ROMAN_VALUES = {
    "I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000,
}


def _roman(args):
    n, err = _int_domain(_arg(args, 0))
    if err is not None:
        return err
    if n < 1 or n > 3999:
        return _NUM()
    out = []
    for value, sym in _ROMAN_TABLE:
        while n >= value:
            out.append(sym)
            n -= value
    return "".join(out)


def _arabic(args):
    s = _text(_arg(args, 0)).strip().upper()
    if s == "":
        return 0.0
    sign = 1
    if s.startswith("-"):
        sign = -1
        s = s[1:]
    total = 0
    prev = 0
    for ch in reversed(s):
        if ch not in _ROMAN_VALUES:
            return CellError(CellError.VALUE)
        val = _ROMAN_VALUES[ch]
        if val < prev:
            total -= val
        else:
            total += val
            prev = val
    return float(sign * total)


_DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _base(args):
    n, err = _int_domain(_arg(args, 0))
    if err is not None:
        return err
    radix, err = _int_domain(_arg(args, 1))
    if err is not None:
        return err
    min_len_raw = _arg(args, 2, 0)
    min_len_n = _num(min_len_raw)
    if is_error(min_len_n):
        return min_len_n
    min_len = math.trunc(min_len_n)
    if radix < 2 or radix > 36:
        return _NUM()
    if n < 0:
        return _NUM()
    if n == 0:
        out = "0"
    else:
        chars = []
        k = n
        while k > 0:
            chars.append(_DIGITS[k % radix])
            k //= radix
        out = "".join(reversed(chars))
    if min_len > len(out):
        out = "0" * (min_len - len(out)) + out
    return out


def _decimal(args):
    s = _text(_arg(args, 0)).strip()
    radix, err = _int_domain(_arg(args, 1))
    if err is not None:
        return err
    if radix < 2 or radix > 36:
        return _NUM()
    if s == "":
        return 0.0
    try:
        return float(int(s, radix))
    except ValueError:
        return CellError(CellError.NUM)


# --- gamma -----------------------------------------------------------------


def _gammaln(args):
    x = _num(_arg(args, 0))
    if is_error(x):
        return x
    if x <= 0:
        return _NUM()
    try:
        return math.lgamma(x)
    except (ValueError, OverflowError):
        return _NUM()


def _gamma(args):
    x = _num(_arg(args, 0))
    if is_error(x):
        return x
    if x == 0 or (x < 0 and float(x).is_integer()):
        return _NUM()
    try:
        return math.gamma(x)
    except (ValueError, OverflowError):
        return _NUM()


# --- information -----------------------------------------------------------


def _iseven(args):
    v = _arg(args, 0)
    if is_error(v):
        return v
    n = _try_num(v)
    if n is None:
        return CellError(CellError.VALUE)
    return math.trunc(n) % 2 == 0


def _isodd(args):
    v = _arg(args, 0)
    if is_error(v):
        return v
    n = _try_num(v)
    if n is None:
        return CellError(CellError.VALUE)
    return math.trunc(n) % 2 != 0


def _iserr(args):
    v = _arg(args, 0)
    return is_error(v) and v != CellError(CellError.NA)


def _isna(args):
    v = _arg(args, 0)
    return is_error(v) and v == CellError(CellError.NA)


def _isnontext(args):
    v = _arg(args, 0)
    return not isinstance(v, str)


def _n(args):
    v = _arg(args, 0)
    if is_error(v):
        return v
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    return 0.0


def _type(args):
    v = _arg(args, 0)
    if is_error(v):
        return 16.0
    if isinstance(v, bool):
        return 4.0
    if isinstance(v, (int, float)):
        return 1.0
    if isinstance(v, str):
        return 2.0
    # ranges / arrays
    if isinstance(v, list) or hasattr(v, "grid"):
        return 64.0
    return 1.0


_ERROR_TYPE_MAP = {
    "#NULL!": 1.0,
    CellError.DIV0: 2.0,
    CellError.VALUE: 3.0,
    CellError.REF: 4.0,
    CellError.NAME: 5.0,
    CellError.NUM: 6.0,
    CellError.NA: 7.0,
}


def _error_type(args):
    v = _arg(args, 0)
    if is_error(v):
        code = str(v)
        if code in _ERROR_TYPE_MAP:
            return _ERROR_TYPE_MAP[code]
    return CellError(CellError.NA)


# --- registration ----------------------------------------------------------

_IMPLS = {
    "SINH": _sinh,
    "COSH": _cosh,
    "TANH": _tanh,
    "ASINH": _asinh,
    "ACOSH": _acosh,
    "ATANH": _atanh,
    "SEC": _sec,
    "CSC": _csc,
    "COT": _cot,
    "SECH": _sech,
    "CSCH": _csch,
    "COTH": _coth,
    "ACOT": _acot,
    "EVEN": _even,
    "ODD": _odd,
    "MROUND": _mround,
    "QUOTIENT": _quotient,
    "SQRTPI": _sqrtpi,
    "ISO.CEILING": _iso_ceiling,
    "FACTDOUBLE": _factdouble,
    "COMBIN": _combin,
    "COMBINA": _combina,
    "PERMUT": _permut,
    "PERMUTATIONA": _permutationa,
    "MULTINOMIAL": _multinomial,
    "SUMX2MY2": _sumx2my2,
    "SUMX2PY2": _sumx2py2,
    "SUMXMY2": _sumxmy2,
    "SERIESSUM": _seriessum,
    "ROMAN": _roman,
    "ARABIC": _arabic,
    "BASE": _base,
    "DECIMAL": _decimal,
    "GAMMALN": _gammaln,
    "GAMMA": _gamma,
    "ISEVEN": _iseven,
    "ISODD": _isodd,
    "ISERR": _iserr,
    "ISNA": _isna,
    "ISNONTEXT": _isnontext,
    "N": _n,
    "TYPE": _type,
    "ERROR.TYPE": _error_type,
}

SIGNATURES = {
    "SINH": "SINH(number)",
    "COSH": "COSH(number)",
    "TANH": "TANH(number)",
    "ASINH": "ASINH(number)",
    "ACOSH": "ACOSH(number)",
    "ATANH": "ATANH(number)",
    "SEC": "SEC(number)",
    "CSC": "CSC(number)",
    "COT": "COT(number)",
    "SECH": "SECH(number)",
    "CSCH": "CSCH(number)",
    "COTH": "COTH(number)",
    "ACOT": "ACOT(number)",
    "EVEN": "EVEN(number)",
    "ODD": "ODD(number)",
    "MROUND": "MROUND(number, multiple)",
    "QUOTIENT": "QUOTIENT(numerator, denominator)",
    "SQRTPI": "SQRTPI(number)",
    "ISO.CEILING": "ISO.CEILING(number, [significance])",
    "FACTDOUBLE": "FACTDOUBLE(number)",
    "COMBIN": "COMBIN(number, number_chosen)",
    "COMBINA": "COMBINA(number, number_chosen)",
    "PERMUT": "PERMUT(number, number_chosen)",
    "PERMUTATIONA": "PERMUTATIONA(number, number_chosen)",
    "MULTINOMIAL": "MULTINOMIAL(number1, ...)",
    "SUMX2MY2": "SUMX2MY2(array_x, array_y)",
    "SUMX2PY2": "SUMX2PY2(array_x, array_y)",
    "SUMXMY2": "SUMXMY2(array_x, array_y)",
    "SERIESSUM": "SERIESSUM(x, n, m, coefficients)",
    "ROMAN": "ROMAN(number)",
    "ARABIC": "ARABIC(text)",
    "BASE": "BASE(number, radix, [min_length])",
    "DECIMAL": "DECIMAL(text, radix)",
    "GAMMALN": "GAMMALN(x)",
    "GAMMA": "GAMMA(x)",
    "ISEVEN": "ISEVEN(number)",
    "ISODD": "ISODD(number)",
    "ISERR": "ISERR(value)",
    "ISNA": "ISNA(value)",
    "ISNONTEXT": "ISNONTEXT(value)",
    "N": "N(value)",
    "TYPE": "TYPE(value)",
    "ERROR.TYPE": "ERROR.TYPE(error_val)",
}


def register(functions: dict) -> None:
    """Merge the extended math/information functions into ``functions``."""
    functions.update(_IMPLS)
