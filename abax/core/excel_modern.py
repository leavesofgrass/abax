"""Wave I — modern-Excel completeness functions.

Pure-stdlib pack that fills the everyday-Excel gaps left after Waves A–H:
the spilling text splitter (``TEXTSPLIT``), array/value renderers
(``ARRAYTOTEXT``/``VALUETOTEXT``), the modern match/lookup pair (``XMATCH`` and
the classic ``LOOKUP``), ``CEILING.MATH``/``FLOOR.MATH``, the workhorse
aggregators ``SUBTOTAL`` and ``AGGREGATE``, the configurable-weekend date pair
(``WORKDAY.INTL``/``NETWORKDAYS.INTL``), and the tail of the complex-number
family (``IMTAN`` … ``IMLOG10``).

Simplifications vs. Excel, by design:

* ``SUBTOTAL``/``AGGREGATE`` receive plain value ranges, so the "ignore hidden
  rows" and "ignore nested SUBTOTALs" options can't apply — the 1xx function
  numbers and the hidden/nested option bits behave like their plain
  counterparts. The genuinely useful option — *ignore errors* (2/3/6/7) — is
  honoured.
* ``XMATCH`` search modes 2/-2 (binary) scan linearly; same result on the
  sorted data binary search assumes.

Registered by :func:`register` alongside the other parity packs.
"""

from __future__ import annotations

import cmath
import math
import re
from datetime import timedelta
from typing import Any, Callable
from urllib.parse import quote

from .errors import CellError, is_error
from .science.complexnum import ComplexError
from .science.complexnum import fmt as _cfmt
from .science.complexnum import parse as _cparse
from .text_datetime_fns import _load_holidays, _parse_date
from .values import RangeValue


def _arg(args: list, i: int, default: Any = None) -> Any:
    return args[i] if i < len(args) else default


def _try_num(v: Any) -> "float | None":
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if v is None or v == "":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _flat(v: Any) -> list:
    if isinstance(v, RangeValue):
        return v.flat()
    if isinstance(v, list):
        out: list = []
        for item in v:
            out.extend(_flat(item))
        return out
    return [v]


def _grid(v: Any) -> "list[list[Any]]":
    """A 2-D view of a range/list/scalar (rows of equal length not enforced)."""
    if isinstance(v, RangeValue):
        return v.grid
    if isinstance(v, list):
        if v and isinstance(v[0], list):
            return v
        return [[x] for x in v]  # 1-D list = a column
    return [[v]]


def _text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if is_error(v):
        return str(v)
    if isinstance(v, float) and v.is_integer() and not math.isinf(v):
        return str(int(v))
    return str(v)


def _truthy(v: Any) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1")
    return bool(v)


# --- TEXTSPLIT / ARRAYTOTEXT / VALUETOTEXT ----------------------------------


def _delims(v: Any) -> "list[str] | None":
    """Normalize a delimiter argument (scalar or array) to a list of non-empty
    strings; None on an invalid (empty) delimiter."""
    out = []
    for d in _flat(v):
        if d is None:
            continue
        s = str(d)
        if s == "":
            return None
        out.append(s)
    return out or None


def _split_multi(text: str, delims: "list[str]", fold: bool) -> "list[str]":
    """Split *text* by any of *delims* (longest-first so 'ab' beats 'a')."""
    ordered = sorted(delims, key=len, reverse=True)
    hay = text.lower() if fold else text
    needles = [d.lower() for d in ordered] if fold else ordered
    parts: list[str] = []
    start = i = 0
    while i < len(hay):
        for d in needles:
            if d and hay.startswith(d, i):
                parts.append(text[start:i])
                i += len(d)
                start = i
                break
        else:
            i += 1
    parts.append(text[start:])
    return parts


def _textsplit(args: list) -> Any:
    """TEXTSPLIT(text, col_delimiter, [row_delimiter], [ignore_empty],
    [match_mode], [pad_with]) — split text into a spilled array."""
    v = _arg(args, 0)
    if is_error(v):
        return v
    text = _text(v)
    col_arg, row_arg = _arg(args, 1), _arg(args, 2)
    col_d = _delims(col_arg) if col_arg is not None else None
    row_d = _delims(row_arg) if row_arg is not None else None
    if (col_arg is not None and col_d is None) or (row_arg is not None and row_d is None):
        return CellError(CellError.VALUE)  # an explicitly-empty delimiter
    if col_d is None and row_d is None:
        return CellError(CellError.VALUE)
    ignore_empty = _truthy(_arg(args, 3, False))
    fold = _try_num(_arg(args, 4, 0)) == 1.0  # 1 = case-insensitive
    pad = _arg(args, 5, CellError(CellError.NA))

    rows = _split_multi(text, row_d, fold) if row_d else [text]
    grid = [_split_multi(r, col_d, fold) if col_d else [r] for r in rows]
    if ignore_empty:
        grid = [[c for c in row if c != ""] for row in grid]
        grid = [row for row in grid if row]
    if not grid:
        return CellError(CellError.CALC)
    width = max(len(row) for row in grid)
    return [row + [pad] * (width - len(row)) for row in grid]


def _render_scalar(v: Any, strict: bool) -> str:
    if strict and isinstance(v, str):
        return '"' + v.replace('"', '""') + '"'
    return _text(v)


def _arraytotext(args: list) -> Any:
    """ARRAYTOTEXT(array, [format]) — 0 = concise ("a, b"), 1 = strict
    ("{1,\"a\";2,\"b\"}")."""
    strict = _try_num(_arg(args, 1, 0)) == 1.0
    grid = _grid(_arg(args, 0))
    if strict:
        rows = [",".join(_render_scalar(v, True) for v in row) for row in grid]
        return "{" + ";".join(rows) + "}"
    return ", ".join(_text(v) for row in grid for v in row)


def _valuetotext(args: list) -> Any:
    """VALUETOTEXT(value, [format]) — scalar sibling of ARRAYTOTEXT."""
    v = _arg(args, 0)
    if isinstance(v, (RangeValue, list)):
        return _arraytotext(args)
    strict = _try_num(_arg(args, 1, 0)) == 1.0
    return _render_scalar(v, strict)


# --- XMATCH / LOOKUP ---------------------------------------------------------


def _cmp_key(v: Any) -> "tuple[int, Any]":
    """Order values the way Excel sorts a lookup vector: numbers < text < bool."""
    if isinstance(v, bool):
        return (2, v)
    if isinstance(v, (int, float)):
        return (0, float(v))
    return (1, str(v).lower())


def _same_kind(a: Any, b: Any) -> bool:
    return _cmp_key(a)[0] == _cmp_key(b)[0]


def _values_equal(a: Any, b: Any) -> bool:
    return _same_kind(a, b) and _cmp_key(a) == _cmp_key(b)


def _wild_match(pattern: str, s: str) -> bool:
    """Excel wildcards: ``?`` one char, ``*`` any run, ``~`` escapes."""
    import re

    out = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "~" and i + 1 < len(pattern):
            out.append(re.escape(pattern[i + 1]))
            i += 2
            continue
        if ch == "?":
            out.append(".")
        elif ch == "*":
            out.append(".*")
        else:
            out.append(re.escape(ch))
        i += 1
    return re.fullmatch("".join(out), s, re.IGNORECASE) is not None


def _xmatch(args: list) -> Any:
    """XMATCH(lookup, array, [match_mode], [search_mode]) — 1-based position."""
    needle = _arg(args, 0)
    hay = _flat(_arg(args, 1))
    mode = _try_num(_arg(args, 2, 0))
    order = _try_num(_arg(args, 3, 1))
    if mode is None or order is None:
        return CellError(CellError.VALUE)
    mode, order = int(mode), int(order)
    idx = range(len(hay) - 1, -1, -1) if order < 0 else range(len(hay))

    if mode == 2:
        pat = _text(needle)
        for i in idx:
            if isinstance(hay[i], str) and _wild_match(pat, hay[i]):
                return float(i + 1)
        return CellError(CellError.NA)

    best_i, best_key = None, None
    nk = _cmp_key(needle)
    for i in idx:
        v = hay[i]
        if _values_equal(v, needle):
            return float(i + 1)
        if mode == 0 or not _same_kind(v, needle):
            continue
        k = _cmp_key(v)
        if mode == -1 and k < nk and (best_key is None or k > best_key):
            best_i, best_key = i, k
        elif mode == 1 and k > nk and (best_key is None or k < best_key):
            best_i, best_key = i, k
    if best_i is None:
        return CellError(CellError.NA)
    return float(best_i + 1)


def _lookup(args: list) -> Any:
    """LOOKUP(value, vector, [result_vector]) — the classic largest-value-<=
    lookup. Array form: search the first row/column of a 2-D array and return
    from the last."""
    needle = _arg(args, 0)
    table = _arg(args, 1)
    result = _arg(args, 2)

    if result is None and isinstance(table, RangeValue) and table.nrows > 1 and table.ncols > 1:
        if table.ncols > table.nrows:  # wide: search first row, return last row
            hay, res = table.row(0), table.row(table.nrows - 1)
        else:  # tall (or square): search first column, return last column
            hay, res = table.col(0), table.col(table.ncols - 1)
    else:
        hay = _flat(table)
        res = _flat(result) if result is not None else hay

    nk = _cmp_key(needle)
    best_i, best_key = None, None
    for i, v in enumerate(hay):
        if not _same_kind(v, needle):
            continue
        k = _cmp_key(v)
        if k <= nk and (best_key is None or k > best_key):
            best_i, best_key = i, k
    if best_i is None or best_i >= len(res):
        return CellError(CellError.NA)
    return res[best_i]


# --- CEILING.MATH / FLOOR.MATH ----------------------------------------------


def _ceiling_math(args: list) -> Any:
    x = _try_num(_arg(args, 0))
    sig = _try_num(_arg(args, 1, 1.0))
    mode = _try_num(_arg(args, 2, 0.0))
    if x is None or sig is None or mode is None:
        return CellError(CellError.VALUE)
    sig = abs(sig)
    if sig == 0:
        return 0.0
    if x < 0 and mode != 0:  # away from zero
        return math.floor(x / sig) * sig
    return math.ceil(x / sig) * sig


def _floor_math(args: list) -> Any:
    x = _try_num(_arg(args, 0))
    sig = _try_num(_arg(args, 1, 1.0))
    mode = _try_num(_arg(args, 2, 0.0))
    if x is None or sig is None or mode is None:
        return CellError(CellError.VALUE)
    sig = abs(sig)
    if sig == 0:
        return CellError(CellError.DIV0)
    if x < 0 and mode != 0:  # toward zero
        return math.ceil(x / sig) * sig
    return math.floor(x / sig) * sig


# --- SUBTOTAL / AGGREGATE ----------------------------------------------------


def _numbers_only(values: list) -> list:
    return [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]


def _variance(xs: list, sample: bool) -> float:
    n = len(xs)
    m = sum(xs) / n
    ss = sum((x - m) ** 2 for x in xs)
    return ss / (n - 1) if sample else ss / n


def _percentile_inc(xs: list, k: float) -> "float | CellError":
    xs = sorted(xs)
    n = len(xs)
    if n == 0 or not (0.0 <= k <= 1.0):
        return CellError(CellError.NUM)
    rank = k * (n - 1)
    lo = int(math.floor(rank))
    frac = rank - lo
    if lo + 1 >= n:
        return xs[-1]
    return xs[lo] + frac * (xs[lo + 1] - xs[lo])


def _mode_sngl(xs: list) -> "float | CellError":
    counts: dict[float, int] = {}
    order: list[float] = []
    for x in xs:
        if x not in counts:
            order.append(x)
        counts[x] = counts.get(x, 0) + 1
    best = max(counts.values(), default=0)
    if best < 2:
        return CellError(CellError.NA)
    for x in order:
        if counts[x] == best:
            return x
    return CellError(CellError.NA)  # pragma: no cover


def _agg_reduce(fn: int, xs: list, values: list, k: "float | None") -> Any:
    """Apply AGGREGATE/SUBTOTAL function number *fn* (1-19, already
    normalized) to numbers *xs* / raw *values*."""
    need = {1: 1, 4: 1, 5: 1, 7: 2, 8: 1, 10: 2, 11: 1, 12: 1, 13: 1}.get(fn, 0)
    if len(xs) < need:
        return CellError(CellError.DIV0)
    try:
        if fn == 1:
            return sum(xs) / len(xs)
        if fn == 2:
            return float(len(xs))
        if fn == 3:
            return float(sum(1 for v in values if v is not None and v != ""))
        if fn == 4:
            return max(xs)
        if fn == 5:
            return min(xs)
        if fn == 6:
            out = 1.0
            for x in xs:
                out *= x
            return out
        if fn == 7:
            return math.sqrt(_variance(xs, True))
        if fn == 8:
            return math.sqrt(_variance(xs, False))
        if fn == 9:
            return float(sum(xs))
        if fn == 10:
            return _variance(xs, True)
        if fn == 11:
            return _variance(xs, False)
        if fn == 12:
            xs = sorted(xs)
            n = len(xs)
            mid = n // 2
            return xs[mid] if n % 2 else 0.5 * (xs[mid - 1] + xs[mid])
        if fn == 13:
            return _mode_sngl(xs)
        # 14-19 need k
        if k is None:
            return CellError(CellError.VALUE)
        if fn == 14:  # LARGE
            k = int(k)
            if not (1 <= k <= len(xs)):
                return CellError(CellError.NUM)
            return sorted(xs, reverse=True)[k - 1]
        if fn == 15:  # SMALL
            k = int(k)
            if not (1 <= k <= len(xs)):
                return CellError(CellError.NUM)
            return sorted(xs)[k - 1]
        if fn == 16:
            return _percentile_inc(xs, k)
        if fn == 17:
            return _percentile_inc(xs, k / 4.0)
        if fn in (18, 19):
            from .gnumeric_stats import _percentile_exc

            return _percentile_exc(xs, k if fn == 18 else k / 4.0)
    except (ValueError, ZeroDivisionError, OverflowError):
        return CellError(CellError.NUM)
    return CellError(CellError.VALUE)


def _subtotal(args: list) -> Any:
    """SUBTOTAL(function_num, ref1, …) — 1-11 / 101-111 (hidden-row variants
    behave like the plain ones here; see module docstring)."""
    fn = _try_num(_arg(args, 0))
    if fn is None:
        return CellError(CellError.VALUE)
    fn = int(fn)
    if fn > 100:
        fn -= 100
    if not (1 <= fn <= 11):
        return CellError(CellError.VALUE)
    values = _flat(args[1:])
    for v in values:
        if is_error(v):
            return v
    return _agg_reduce(fn, _numbers_only(values), values, None)


def _aggregate(args: list) -> Any:
    """AGGREGATE(function_num, options, ref1, [k]) — options 2/3/6/7 ignore
    errors in the data; the hidden-row/nested bits are no-ops here."""
    fn = _try_num(_arg(args, 0))
    opts = _try_num(_arg(args, 1))
    if fn is None or opts is None:
        return CellError(CellError.VALUE)
    fn, opts = int(fn), int(opts)
    if not (1 <= fn <= 19) or not (0 <= opts <= 7):
        return CellError(CellError.VALUE)
    ignore_errors = opts in (2, 3, 6, 7)

    k = None
    if fn >= 14:
        data = _arg(args, 2)
        k = _try_num(_arg(args, 3))
        if k is None:
            return CellError(CellError.VALUE)
        values = _flat(data)
    else:
        values = _flat(args[2:])

    if ignore_errors:
        values = [v for v in values if not is_error(v)]
    else:
        for v in values:
            if is_error(v):
                return v
    return _agg_reduce(fn, _numbers_only(values), values, k)


# --- WORKDAY.INTL / NETWORKDAYS.INTL ----------------------------------------

# Weekend numbers -> set of Python weekday ints (Mon=0 … Sun=6).
_WEEKENDS = {
    1: {5, 6}, 2: {6, 0}, 3: {0, 1}, 4: {1, 2}, 5: {2, 3}, 6: {3, 4}, 7: {4, 5},
    11: {6}, 12: {0}, 13: {1}, 14: {2}, 15: {3}, 16: {4}, 17: {5},
}


def _weekend_set(spec: Any) -> "set[int] | None":
    if spec is None:
        return {5, 6}
    if isinstance(spec, str):
        if len(spec) != 7 or set(spec) - {"0", "1"}:
            return None
        days = {i for i, ch in enumerate(spec) if ch == "1"}  # char 0 = Monday
        return days if len(days) < 7 else None
    n = _try_num(spec)
    if n is None:
        return None
    return _WEEKENDS.get(int(n))


def _workday_intl(args: list) -> Any:
    """WORKDAY.INTL(start, days, [weekend], [holidays])."""
    start = _parse_date(_arg(args, 0))
    days = _try_num(_arg(args, 1))
    weekend = _weekend_set(_arg(args, 2))
    if start is None or days is None or weekend is None:
        return CellError(CellError.VALUE)
    holidays = _load_holidays(_arg(args, 3))
    days = int(days)
    step = 1 if days >= 0 else -1
    remaining = abs(days)
    cur = start
    while remaining > 0:
        cur = cur + timedelta(days=step)
        if cur.weekday() in weekend or cur in holidays:
            continue
        remaining -= 1
    return cur.isoformat()


def _networkdays_intl(args: list) -> Any:
    """NETWORKDAYS.INTL(start, end, [weekend], [holidays])."""
    start = _parse_date(_arg(args, 0))
    end = _parse_date(_arg(args, 1))
    weekend = _weekend_set(_arg(args, 2))
    if start is None or end is None or weekend is None:
        return CellError(CellError.VALUE)
    holidays = _load_holidays(_arg(args, 3))
    sign = 1
    if end < start:
        start, end = end, start
        sign = -1
    count = 0
    cur = start
    while cur <= end:
        if cur.weekday() not in weekend and cur not in holidays:
            count += 1
        cur = cur + timedelta(days=1)
    return float(sign * count)


# --- the IM* tail ------------------------------------------------------------


def _im_unary(fn: Callable[[complex], complex]):
    def impl(args: list) -> Any:
        v = _arg(args, 0)
        if is_error(v):
            return v
        suffix = "j" if isinstance(v, str) and "j" in v else "i"
        try:
            return _cfmt(fn(_cparse(v)), suffix)
        except (ComplexError, ValueError, OverflowError, ZeroDivisionError):
            return CellError(CellError.NUM)
    return impl


def _recip(fn: Callable[[complex], complex]) -> Callable[[complex], complex]:
    def wrapped(z: complex) -> complex:
        w = fn(z)
        if w == 0:
            raise ZeroDivisionError
        return 1.0 / w
    return wrapped


_LN2 = math.log(2.0)
_LN10 = math.log(10.0)


# --- web / info ---------------------------------------------------------------


def _encodeurl(args: list) -> Any:
    """ENCODEURL(text) — percent-encode ``text`` for use as a URL component.

    Excel semantics: every character outside the RFC 3986 unreserved set
    (``A–Z a–z 0–9 - _ . ~``) is %-escaped, non-ASCII as its UTF-8 bytes first —
    so ``/``, ``:``, ``&``, and spaces are all encoded. It escapes a URL
    *component* (a path segment or query value), not a whole URL.
    """
    v = _arg(args, 0, "")
    if is_error(v):
        return v
    if isinstance(v, (RangeValue, list)):
        return CellError(CellError.VALUE)
    return quote(_text(v), safe="")


def _hyperlink(args: list) -> Any:
    """HYPERLINK(link_location, [friendly_name]) — the link's display value.

    abax's grid has no clickable cells, so HYPERLINK contributes exactly the
    *value* the cell shows in Excel: ``friendly_name`` when given (verbatim — a
    number stays a number), else the link text itself.
    """
    link = _arg(args, 0, "")
    if is_error(link):
        return link
    if isinstance(link, (RangeValue, list)):
        return CellError(CellError.VALUE)
    if len(args) < 2:
        return _text(link)
    friendly = args[1]
    if is_error(friendly):
        return friendly
    if isinstance(friendly, (RangeValue, list)):
        return CellError(CellError.VALUE)
    return friendly


# --- FILTERXML ---------------------------------------------------------------


def _xml_find(root, path: str) -> list:
    """ElementTree findall with a few XPath conveniences normalized for the root.

    ElementTree matches relative to the element it is called on and never matches
    the root's own tag, so ``/root/item`` becomes ``item`` and ``//item`` becomes
    ``.//item``. Namespaces are not resolved (a documented simplification).
    """
    p = path.strip()
    if p.startswith("//"):
        return root.findall(".//" + p[2:])
    if p.startswith("/"):
        p = p[1:]
    head, _, tail = p.partition("/")
    if head == root.tag:                 # strip a leading root-tag segment
        p = tail
    if p in ("", "."):
        return [root]
    try:
        return root.findall(p)
    except SyntaxError:                  # malformed ElementTree path
        return []


def _filterxml(args: list) -> Any:
    """FILTERXML(xml, xpath) — spill the node/attribute values matching *xpath*.

    A trailing ``/@attr`` selects attribute values. XML with a DOCTYPE/entity
    declaration is refused (an entity-expansion guard). No match yields ``#N/A``;
    malformed XML or XPath yields ``#VALUE!``.
    """
    xml_v, xpath_v = _arg(args, 0), _arg(args, 1)
    if is_error(xml_v):
        return xml_v
    if is_error(xpath_v):
        return xpath_v
    xml_text = _text(xml_v)
    xpath = _text(xpath_v).strip()
    if not xml_text or not xpath:
        return CellError(CellError.VALUE)
    if "<!DOCTYPE" in xml_text or "<!ENTITY" in xml_text:
        return CellError(CellError.VALUE)  # refuse DTDs/entities (billion-laughs)

    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return CellError(CellError.VALUE)

    attr = None
    m = re.search(r"/@([A-Za-z_][\w.-]*)$", xpath)
    if m:
        attr = m.group(1)
        xpath = xpath[: m.start()]
    matched = _xml_find(root, xpath)
    if attr is not None:
        vals = [el.get(attr) for el in matched if el.get(attr) is not None]
    else:
        vals = [(el.text or "") for el in matched]
    if not vals:
        return CellError(CellError.NA)
    return [[v] for v in vals]           # spill down a single column


# --- registry ----------------------------------------------------------------

_REGISTRY: dict[str, Callable[[list], Any]] = {
    "TEXTSPLIT": _textsplit,
    "FILTERXML": _filterxml,
    "ARRAYTOTEXT": _arraytotext,
    "VALUETOTEXT": _valuetotext,
    "XMATCH": _xmatch,
    "LOOKUP": _lookup,
    "CEILING.MATH": _ceiling_math,
    "FLOOR.MATH": _floor_math,
    "SUBTOTAL": _subtotal,
    "AGGREGATE": _aggregate,
    "WORKDAY.INTL": _workday_intl,
    "NETWORKDAYS.INTL": _networkdays_intl,
    "ENCODEURL": _encodeurl,
    "HYPERLINK": _hyperlink,
    "IMTAN": _im_unary(cmath.tan),
    "IMCOT": _im_unary(_recip(cmath.tan)),
    "IMSEC": _im_unary(_recip(cmath.cos)),
    "IMCSC": _im_unary(_recip(cmath.sin)),
    "IMSINH": _im_unary(cmath.sinh),
    "IMCOSH": _im_unary(cmath.cosh),
    "IMTANH": _im_unary(cmath.tanh),
    "IMSECH": _im_unary(_recip(cmath.cosh)),
    "IMCSCH": _im_unary(_recip(cmath.sinh)),
    "IMLOG2": _im_unary(lambda z: cmath.log(z) / _LN2),
    "IMLOG10": _im_unary(lambda z: cmath.log(z) / _LN10),
}


def register(functions: dict) -> None:
    """Merge the modern-Excel completeness functions into the engine's table."""
    functions.update(_REGISTRY)
