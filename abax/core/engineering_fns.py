"""Engineering & database spreadsheet functions (pure stdlib).

A companion registry to :mod:`abax.core.functions`. Every callable follows the
same eager convention: it receives a single ``args`` list of already-evaluated
values (a *range* arrives as a :class:`abax.core.values.RangeValue`; scalars
are plain Python values) and returns a float / str / bool or a
:class:`abax.core.errors.CellError` value. No bare exception ever escapes.

Three families live here:

* **Number-base conversions** (``DEC2BIN`` … ``HEX2OCT``) with Excel's 10-bit
  two's-complement semantics for negatives and optional ``places`` zero-pad.
* **Bitwise / step / special functions** (``BITAND`` … ``BESSELK``).
* **Classic database D-functions** (``DSUM`` … ``DVARP``) driven by
  :func:`abax.core.criteria.make_predicate`.

Register with the engine via :func:`register`, which merges the name -> callable
table into the engine's function dictionary.
"""

from __future__ import annotations

import math

from .criteria import make_predicate  # for the database D* functions
from .errors import CellError
from .functions.helpers import _arg, _as_number, _flatten, _numbers, _text, _try_num
from .values import RangeValue

# _as_number / _flatten / _numbers are part of the mandated import surface;
# reference them so linting does not flag the (intentionally imported) helpers
# as unused.
_ = (_as_number, _flatten, _numbers)


# --- number-base conversions -----------------------------------------------

# Valid signed ranges (Excel): the sign bit is the top of a fixed-width field.
_DEC2BIN_MIN, _DEC2BIN_MAX = -512, 511                # 10-bit
_DEC2OCT_MIN, _DEC2OCT_MAX = -(2 ** 29), 2 ** 29 - 1  # 30-bit
_DEC2HEX_MIN, _DEC2HEX_MAX = -(2 ** 39), 2 ** 39 - 1  # 40-bit


def _to_int(v) -> int | None:
    """Coerce an argument to an integer, or ``None`` if not numeric."""
    n = _try_num(v)
    if n is None:
        return None
    try:
        return int(math.trunc(n))
    except (ValueError, OverflowError):
        return None


def _places_pad(digits: str, places_arg):
    """Apply an optional ``places`` zero-pad to a positive result.

    Returns the padded string, or a ``CellError`` when ``places`` is invalid or
    too small to hold ``digits``.
    """
    if places_arg is None or (isinstance(places_arg, str) and places_arg == ""):
        return digits
    p = _try_num(places_arg)
    if p is None:
        return CellError(CellError.VALUE)
    p = int(math.trunc(p))
    if p < 0 or p > 10:
        return CellError(CellError.NUM)
    if p < len(digits):
        return CellError(CellError.NUM)
    return digits.zfill(p)


def _dec2base(args, base: int, width_bits: int, lo: int, hi: int):
    n = _to_int(_arg(args, 0))
    if n is None:
        return CellError(CellError.VALUE)
    if n < lo or n > hi:
        return CellError(CellError.NUM)
    negative = n < 0
    if negative:
        n = (1 << width_bits) + n  # two's-complement in the fixed field
    if base == 2:
        body = format(n, "b")
    elif base == 8:
        body = format(n, "o")
    else:
        body = format(n, "X")
    if negative:
        # A negative result already fills the fixed-width field; two's-complement
        # of the field already produced full width, so no further padding.
        return body
    return _places_pad(body, _arg(args, 1))


def _dec2bin(args):
    return _dec2base(args, 2, 10, _DEC2BIN_MIN, _DEC2BIN_MAX)


def _dec2oct(args):
    return _dec2base(args, 8, 30, _DEC2OCT_MIN, _DEC2OCT_MAX)


def _dec2hex(args):
    return _dec2base(args, 16, 40, _DEC2HEX_MIN, _DEC2HEX_MAX)


def _parse_base(text: str, base: int, width_bits: int) -> int | None:
    """Parse a fixed-width base string with two's-complement negatives."""
    text = text.strip()
    if text == "":
        return 0
    digits = width_bits // {2: 1, 8: 3, 16: 4}[base]
    if len(text) > digits:
        return None
    try:
        val = int(text, base)
    except ValueError:
        return None
    # Leading digit in the top position => negative (two's complement).
    if len(text) == digits:
        top = int(text[0], base)
        sign_hi = {2: 1, 8: 4, 16: 8}[base]
        if top >= sign_hi:
            val -= 1 << width_bits
    return val


def _from_base(args, base: int, width_bits: int, out_base=None, out_width=None,
               out_lo=None, out_hi=None):
    val = _parse_base(_text(_arg(args, 0)), base, width_bits)
    if val is None:
        return CellError(CellError.NUM)
    if out_base is None:
        return float(val)  # *2DEC
    # Re-encode into the output base via the DEC2* machinery.
    if val < out_lo or val > out_hi:
        return CellError(CellError.NUM)
    negative = val < 0
    n = (1 << out_width) + val if negative else val
    if out_base == 2:
        body = format(n, "b")
    elif out_base == 8:
        body = format(n, "o")
    else:
        body = format(n, "X")
    if negative:
        return body
    return _places_pad(body, _arg(args, 1))


def _bin2dec(args):
    return _from_base(args, 2, 10)


def _bin2oct(args):
    return _from_base(args, 2, 10, 8, 30, _DEC2OCT_MIN, _DEC2OCT_MAX)


def _bin2hex(args):
    return _from_base(args, 2, 10, 16, 40, _DEC2HEX_MIN, _DEC2HEX_MAX)


def _oct2dec(args):
    return _from_base(args, 8, 30)


def _oct2bin(args):
    return _from_base(args, 8, 30, 2, 10, _DEC2BIN_MIN, _DEC2BIN_MAX)


def _oct2hex(args):
    return _from_base(args, 8, 30, 16, 40, _DEC2HEX_MIN, _DEC2HEX_MAX)


def _hex2dec(args):
    return _from_base(args, 16, 40)


def _hex2bin(args):
    return _from_base(args, 16, 40, 2, 10, _DEC2BIN_MIN, _DEC2BIN_MAX)


def _hex2oct(args):
    return _from_base(args, 16, 40, 8, 30, _DEC2OCT_MIN, _DEC2OCT_MAX)


# --- bitwise ---------------------------------------------------------------

_BIT_MAX = 2 ** 48 - 1


def _bit_operand(v):
    n = _try_num(v)
    if n is None:
        return None
    if n != math.trunc(n):
        return None
    n = int(n)
    if n < 0 or n > _BIT_MAX:
        return None
    return n


def _bit_binary(op):
    def wrapper(args):
        a = _bit_operand(_arg(args, 0))
        b = _bit_operand(_arg(args, 1))
        if a is None or b is None:
            return CellError(CellError.NUM)
        return float(op(a, b))
    return wrapper


def _bitlshift(args):
    n = _bit_operand(_arg(args, 0))
    if n is None:
        return CellError(CellError.NUM)
    s = _to_int(_arg(args, 1))
    if s is None:
        return CellError(CellError.VALUE)
    if abs(s) > 53:
        return CellError(CellError.NUM)
    result = n << s if s >= 0 else n >> (-s)
    if result > _BIT_MAX:
        return CellError(CellError.NUM)
    return float(result)


def _bitrshift(args):
    n = _bit_operand(_arg(args, 0))
    if n is None:
        return CellError(CellError.NUM)
    s = _to_int(_arg(args, 1))
    if s is None:
        return CellError(CellError.VALUE)
    if abs(s) > 53:
        return CellError(CellError.NUM)
    result = n >> s if s >= 0 else n << (-s)
    if result > _BIT_MAX:
        return CellError(CellError.NUM)
    return float(result)


# --- step / compare / special ----------------------------------------------


def _delta(args):
    a = _try_num(_arg(args, 0))
    b = _try_num(_arg(args, 1, 0))
    if a is None or b is None:
        return CellError(CellError.VALUE)
    return 1.0 if a == b else 0.0


def _gestep(args):
    n = _try_num(_arg(args, 0))
    step = _try_num(_arg(args, 1, 0))
    if n is None or step is None:
        return CellError(CellError.VALUE)
    return 1.0 if n >= step else 0.0


def _erf(args):
    lower = _try_num(_arg(args, 0))
    if lower is None:
        return CellError(CellError.VALUE)
    upper_raw = _arg(args, 1)
    try:
        if upper_raw is None or (isinstance(upper_raw, str) and upper_raw == ""):
            return math.erf(lower)
        upper = _try_num(upper_raw)
        if upper is None:
            return CellError(CellError.VALUE)
        return math.erf(upper) - math.erf(lower)
    except (ValueError, OverflowError):
        return CellError(CellError.NUM)


def _erf_precise(args):
    x = _try_num(_arg(args, 0))
    if x is None:
        return CellError(CellError.VALUE)
    try:
        return math.erf(x)
    except (ValueError, OverflowError):
        return CellError(CellError.NUM)


def _erfc(args):
    x = _try_num(_arg(args, 0))
    if x is None:
        return CellError(CellError.VALUE)
    try:
        return math.erfc(x)
    except (ValueError, OverflowError):
        return CellError(CellError.NUM)


# --- Bessel functions ------------------------------------------------------


def _besselj(x: float, n: int) -> float:
    """J_n(x) via the ascending power series."""
    total = 0.0
    for m in range(0, 60):
        term = ((-1) ** m) / (math.factorial(m) * math.factorial(m + n))
        term *= (x / 2.0) ** (2 * m + n)
        total += term
        if abs(term) < 1e-18 and m > n:
            break
    return total


def _besseli(x: float, n: int) -> float:
    """I_n(x) via the ascending power series (modified Bessel, 1st kind)."""
    total = 0.0
    for m in range(0, 80):
        term = 1.0 / (math.factorial(m) * math.factorial(m + n))
        term *= (x / 2.0) ** (2 * m + n)
        total += term
        if abs(term) < 1e-18 and m > n:
            break
    return total


_EULER_GAMMA = 0.5772156649015329


def _bessely(x: float, n: int) -> float:
    """Y_n(x) (Weber function) for integer order via the standard series."""
    if x <= 0:
        raise ValueError("Y_n requires x > 0")
    # Y_n = (2/pi) J_n ln(x/2) - (1/pi) sum_{k=0}^{n-1} (n-1-k)!/k! (x/2)^(2k-n)
    #       - (1/pi) sum_{k=0}^inf (-1)^k [psi(k+1)+psi(n+k+1)]/(k!(n+k)!) (x/2)^(2k+n)
    half = x / 2.0
    s1 = 0.0
    for k in range(0, n):
        s1 += math.factorial(n - 1 - k) / math.factorial(k) * half ** (2 * k - n)
    s2 = 0.0
    # digamma psi(m) = -gamma + sum_{j=1}^{m-1} 1/j
    def psi(m: int) -> float:
        return -_EULER_GAMMA + sum(1.0 / j for j in range(1, m))
    for k in range(0, 80):
        coeff = ((-1) ** k) * (psi(k + 1) + psi(n + k + 1))
        coeff /= math.factorial(k) * math.factorial(n + k)
        s2 += coeff * half ** (2 * k + n)
    return (2.0 / math.pi) * _besselj(x, n) * math.log(half) \
        - (1.0 / math.pi) * s1 - (1.0 / math.pi) * s2


def _besselk(x: float, n: int) -> float:
    """K_n(x) (modified Bessel, 2nd kind) for integer order via the series."""
    if x <= 0:
        raise ValueError("K_n requires x > 0")
    half = x / 2.0

    def psi(m: int) -> float:
        return -_EULER_GAMMA + sum(1.0 / j for j in range(1, m))

    s1 = 0.0
    for k in range(0, n):
        s1 += ((-1) ** k) * math.factorial(n - 1 - k) / math.factorial(k) * half ** (2 * k - n)
    s2 = 0.0
    for k in range(0, 80):
        coeff = (psi(k + 1) + psi(n + k + 1))
        coeff /= math.factorial(k) * math.factorial(n + k)
        s2 += coeff * half ** (2 * k + n)
    return 0.5 * s1 + ((-1) ** (n + 1)) * math.log(half) * _besseli(x, n) \
        + ((-1) ** n) * 0.5 * s2


def _bessel(fn):
    def wrapper(args):
        x = _try_num(_arg(args, 0))
        nraw = _try_num(_arg(args, 1))
        if x is None or nraw is None:
            return CellError(CellError.VALUE)
        n = int(math.trunc(nraw))
        if n < 0:
            return CellError(CellError.NUM)
        try:
            return fn(float(x), n)
        except (ValueError, OverflowError, ZeroDivisionError):
            return CellError(CellError.NUM)
    return wrapper


# --- database (D*) functions -----------------------------------------------


def _resolve_field(db: RangeValue, field) -> int | None:
    """Return the 0-based column index of ``field`` (header name or 1-based idx)."""
    headers = db.grid[0] if db.grid else []
    fnum = _try_num(field)
    if fnum is not None and not isinstance(field, str):
        idx = int(math.trunc(fnum)) - 1
        if 0 <= idx < len(headers):
            return idx
        return None
    name = _text(field).strip().lower()
    for j, h in enumerate(headers):
        if _text(h).strip().lower() == name:
            return j
    return None


def _record_matches(record: dict, crit: RangeValue) -> bool:
    """Excel criteria: AND across a row's columns, OR across criteria rows."""
    crit_headers = crit.grid[0] if crit.grid else []
    for row in crit.grid[1:]:
        row_ok = True
        any_cond = False
        for cj, cheader in enumerate(crit_headers):
            cell = row[cj] if cj < len(row) else None
            if cell is None or (isinstance(cell, str) and cell.strip() == ""):
                continue
            any_cond = True
            key = _text(cheader).strip().lower()
            if key not in record:
                row_ok = False
                break
            pred = make_predicate(cell)
            if not pred(record[key]):
                row_ok = False
                break
        if any_cond and row_ok:
            return True
    return False


def _matching_values(args):
    """Return ``(list_of_field_values, error)`` for matched records.

    ``error`` is a CellError to short-circuit on; otherwise ``None``.
    """
    db = _arg(args, 0)
    field = _arg(args, 1)
    crit = _arg(args, 2)
    if not isinstance(db, RangeValue) or not isinstance(crit, RangeValue):
        return None, CellError(CellError.VALUE)
    if len(db.grid) < 1:
        return None, CellError(CellError.VALUE)
    col = _resolve_field(db, field)
    if col is None:
        return None, CellError(CellError.VALUE)
    headers = [_text(h).strip().lower() for h in db.grid[0]]
    out = []
    for row in db.grid[1:]:
        record = {headers[j]: (row[j] if j < len(row) else None) for j in range(len(headers))}
        if _record_matches(record, crit):
            out.append(row[col] if col < len(row) else None)
    return out, None


def _num_values(values):
    nums = []
    for v in values:
        if isinstance(v, bool):
            continue
        n = _try_num(v)
        if n is not None and not isinstance(v, str):
            nums.append(float(n))
    return nums


def _dsum(args):
    vals, err = _matching_values(args)
    if err:
        return err
    return math.fsum(_num_values(vals))


def _dproduct(args):
    vals, err = _matching_values(args)
    if err:
        return err
    nums = _num_values(vals)
    if not nums:
        return 0.0
    p = 1.0
    for n in nums:
        p *= n
    return p


def _dcount(args):
    vals, err = _matching_values(args)
    if err:
        return err
    return float(len(_num_values(vals)))


def _dcounta(args):
    vals, err = _matching_values(args)
    if err:
        return err
    return float(sum(1 for v in vals if not (v is None or (isinstance(v, str) and v == ""))))


def _daverage(args):
    vals, err = _matching_values(args)
    if err:
        return err
    nums = _num_values(vals)
    if not nums:
        return CellError(CellError.DIV0)
    return math.fsum(nums) / len(nums)


def _dmax(args):
    vals, err = _matching_values(args)
    if err:
        return err
    nums = _num_values(vals)
    if not nums:
        return 0.0
    return max(nums)


def _dmin(args):
    vals, err = _matching_values(args)
    if err:
        return err
    nums = _num_values(vals)
    if not nums:
        return 0.0
    return min(nums)


def _dget(args):
    vals, err = _matching_values(args)
    if err:
        return err
    if len(vals) == 0:
        return CellError(CellError.VALUE)
    if len(vals) > 1:
        return CellError(CellError.NUM)
    return vals[0]


def _dvar_core(args, population: bool):
    vals, err = _matching_values(args)
    if err:
        return err
    nums = _num_values(vals)
    n = len(nums)
    if population:
        if n < 1:
            return CellError(CellError.DIV0)
        denom = n
    else:
        if n < 2:
            return CellError(CellError.DIV0)
        denom = n - 1
    mean = math.fsum(nums) / n
    return math.fsum((x - mean) ** 2 for x in nums) / denom


def _dvar(args):
    return _dvar_core(args, population=False)


def _dvarp(args):
    return _dvar_core(args, population=True)


def _dstdev(args):
    v = _dvar_core(args, population=False)
    return v if isinstance(v, CellError) else math.sqrt(v)


def _dstdevp(args):
    v = _dvar_core(args, population=True)
    return v if isinstance(v, CellError) else math.sqrt(v)


# --- public surface --------------------------------------------------------


def register(functions: dict) -> None:
    functions.update({
        # number-base conversions
        "DEC2BIN": _dec2bin, "DEC2OCT": _dec2oct, "DEC2HEX": _dec2hex,
        "BIN2DEC": _bin2dec, "BIN2OCT": _bin2oct, "BIN2HEX": _bin2hex,
        "OCT2DEC": _oct2dec, "OCT2BIN": _oct2bin, "OCT2HEX": _oct2hex,
        "HEX2DEC": _hex2dec, "HEX2BIN": _hex2bin, "HEX2OCT": _hex2oct,
        # bitwise
        "BITAND": _bit_binary(lambda a, b: a & b),
        "BITOR": _bit_binary(lambda a, b: a | b),
        "BITXOR": _bit_binary(lambda a, b: a ^ b),
        "BITLSHIFT": _bitlshift, "BITRSHIFT": _bitrshift,
        # step / compare / special
        "DELTA": _delta, "GESTEP": _gestep,
        "ERF": _erf, "ERF.PRECISE": _erf_precise,
        "ERFC": _erfc, "ERFC.PRECISE": _erfc,
        # Bessel
        "BESSELJ": _bessel(_besselj), "BESSELY": _bessel(_bessely),
        "BESSELI": _bessel(_besseli), "BESSELK": _bessel(_besselk),
        # database D-functions
        "DSUM": _dsum, "DCOUNT": _dcount, "DCOUNTA": _dcounta,
        "DAVERAGE": _daverage, "DMAX": _dmax, "DMIN": _dmin, "DGET": _dget,
        "DPRODUCT": _dproduct, "DSTDEV": _dstdev, "DSTDEVP": _dstdevp,
        "DVAR": _dvar, "DVARP": _dvarp,
    })


SIGNATURES = {
    "DEC2BIN": "DEC2BIN(number, [places])",
    "DEC2OCT": "DEC2OCT(number, [places])",
    "DEC2HEX": "DEC2HEX(number, [places])",
    "BIN2DEC": "BIN2DEC(text)",
    "BIN2OCT": "BIN2OCT(text, [places])",
    "BIN2HEX": "BIN2HEX(text, [places])",
    "OCT2DEC": "OCT2DEC(text)",
    "OCT2BIN": "OCT2BIN(text, [places])",
    "OCT2HEX": "OCT2HEX(text, [places])",
    "HEX2DEC": "HEX2DEC(text)",
    "HEX2BIN": "HEX2BIN(text, [places])",
    "HEX2OCT": "HEX2OCT(text, [places])",
    "BITAND": "BITAND(number1, number2)",
    "BITOR": "BITOR(number1, number2)",
    "BITXOR": "BITXOR(number1, number2)",
    "BITLSHIFT": "BITLSHIFT(number, shift_amount)",
    "BITRSHIFT": "BITRSHIFT(number, shift_amount)",
    "DELTA": "DELTA(number1, [number2])",
    "GESTEP": "GESTEP(number, [step])",
    "ERF": "ERF(lower_limit, [upper_limit])",
    "ERF.PRECISE": "ERF.PRECISE(x)",
    "ERFC": "ERFC(x)",
    "ERFC.PRECISE": "ERFC.PRECISE(x)",
    "BESSELJ": "BESSELJ(x, n)",
    "BESSELY": "BESSELY(x, n)",
    "BESSELI": "BESSELI(x, n)",
    "BESSELK": "BESSELK(x, n)",
    "DSUM": "DSUM(database, field, criteria)",
    "DCOUNT": "DCOUNT(database, field, criteria)",
    "DCOUNTA": "DCOUNTA(database, field, criteria)",
    "DAVERAGE": "DAVERAGE(database, field, criteria)",
    "DMAX": "DMAX(database, field, criteria)",
    "DMIN": "DMIN(database, field, criteria)",
    "DGET": "DGET(database, field, criteria)",
    "DPRODUCT": "DPRODUCT(database, field, criteria)",
    "DSTDEV": "DSTDEV(database, field, criteria)",
    "DSTDEVP": "DSTDEVP(database, field, criteria)",
    "DVAR": "DVAR(database, field, criteria)",
    "DVARP": "DVARP(database, field, criteria)",
}
