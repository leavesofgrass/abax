"""Extended pure-stdlib text and date/time spreadsheet functions.

Companion to :mod:`abax.core.functions`. Each callable follows the engine's
eager convention: it receives a single ``args`` list of already-evaluated
values (float/str/bool/None/CellError/RangeValue/nested-list) and returns a
scalar (str/float/bool) or a :class:`abax.core.errors.CellError` value that
propagates. No bare exception is allowed to escape.

Dates follow abax's model: they are ISO date strings ("YYYY-MM-DD"). Date
functions parse ISO strings (or datetime/date values) and return ISO strings
for date results -- there are no Excel serial numbers here.

Register with the engine via :func:`register`, which merges every implemented
name (UPPERCASE -> callable) into the engine's function table. :data:`SIGNATURES`
carries one help-string entry per registered name.
"""

from __future__ import annotations

import unicodedata
from datetime import date, datetime, timedelta

from .errors import CellError
from .functions.helpers import _arg, _flatten, _text, _try_num

# --- small internal utilities ----------------------------------------------


def _VALUE() -> CellError:
    return CellError(CellError.VALUE)


def _NUM() -> CellError:
    return CellError(CellError.NUM)


def _NA() -> CellError:
    return CellError(CellError.NA)


def _parse_date(v):
    """Accept a datetime/date/ISO-string and return a ``date`` (or None)."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        s = v.strip()
        try:
            return date.fromisoformat(s[:10] if len(s) >= 10 else s)
        except ValueError:
            return None
    return None


def _truthy_arg(v) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes")
    return bool(v)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day


# --- text functions --------------------------------------------------------


def _textjoin(args):
    delim = _text(_arg(args, 0))
    ignore = _truthy_arg(_arg(args, 1))
    parts = []
    for v in _flatten(args[2:]):
        if ignore and (v is None or v == ""):
            continue
        parts.append(_text(v))
    return delim.join(parts)


def _textbefore(args):
    text = _text(_arg(args, 0))
    delim = _text(_arg(args, 1))
    inst = _try_num(_arg(args, 2, 1))
    if inst is None:
        return _VALUE()
    inst = int(inst)
    if delim == "":
        return ""
    if inst == 0:
        return _VALUE()
    if inst > 0:
        idx = -1
        for _ in range(inst):
            idx = text.find(delim, idx + 1)
            if idx == -1:
                return _NA()
        return text[:idx]
    # negative: count from the end
    idx = len(text)
    for _ in range(-inst):
        idx = text.rfind(delim, 0, idx)
        if idx == -1:
            return _NA()
    return text[:idx]


def _textafter(args):
    text = _text(_arg(args, 0))
    delim = _text(_arg(args, 1))
    inst = _try_num(_arg(args, 2, 1))
    if inst is None:
        return _VALUE()
    inst = int(inst)
    if delim == "":
        return text
    if inst == 0:
        return _VALUE()
    if inst > 0:
        idx = -1
        for _ in range(inst):
            idx = text.find(delim, idx + 1)
            if idx == -1:
                return _NA()
        return text[idx + len(delim):]
    idx = len(text)
    for _ in range(-inst):
        idx = text.rfind(delim, 0, idx)
        if idx == -1:
            return _NA()
    return text[idx + len(delim):]


def _clean(args):
    text = _text(_arg(args, 0))
    return "".join(ch for ch in text if ord(ch) >= 32)


def _unichar(args):
    n = _try_num(_arg(args, 0))
    if n is None:
        return _VALUE()
    n = int(n)
    if n <= 0:
        return _VALUE()
    try:
        return chr(n)
    except (ValueError, OverflowError):
        return _VALUE()


def _unicode(args):
    text = _text(_arg(args, 0))
    if text == "":
        return _VALUE()
    return float(ord(text[0]))


def _group_int(digits: str) -> str:
    """Insert thousands separators into a string of integer digits."""
    n = len(digits)
    if n <= 3:
        return digits
    out = []
    first = n % 3
    if first:
        out.append(digits[:first])
    for i in range(first, n, 3):
        out.append(digits[i:i + 3])
    return ",".join(out)


def _dollar(args):
    x = _try_num(_arg(args, 0))
    if x is None:
        return _VALUE()
    dec = _try_num(_arg(args, 1, 2))
    if dec is None:
        return _VALUE()
    dec = int(dec)
    neg = x < 0
    a = abs(x)
    if dec >= 0:
        s = f"{a:.{dec}f}"
    else:
        factor = 10 ** (-dec)
        s = f"{round(a / factor) * factor:.0f}"
    if "." in s:
        intpart, frac = s.split(".")
        body = _group_int(intpart) + "." + frac
    else:
        body = _group_int(s)
    body = "$" + body
    return f"({body})" if neg else body


def _fixed(args):
    x = _try_num(_arg(args, 0))
    if x is None:
        return _VALUE()
    dec = _try_num(_arg(args, 1, 2))
    if dec is None:
        return _VALUE()
    dec = int(dec)
    no_commas = _truthy_arg(_arg(args, 2, False))
    neg = x < 0
    a = abs(x)
    if dec >= 0:
        s = f"{a:.{dec}f}"
    else:
        factor = 10 ** (-dec)
        s = f"{round(a / factor) * factor:.0f}"
    if "." in s:
        intpart, frac = s.split(".")
    else:
        intpart, frac = s, ""
    if not no_commas:
        intpart = _group_int(intpart)
    out = intpart + ("." + frac if frac else "")
    return "-" + out if neg else out


def _numbervalue(args):
    text = _text(_arg(args, 0))
    dsep = _text(_arg(args, 1, ".")) or "."
    gsep = _text(_arg(args, 2, ",")) or ","
    s = text.strip()
    if s == "":
        return 0.0
    # Trailing percent signs each divide by 100.
    pct = 0
    while s.endswith("%"):
        pct += 1
        s = s[:-1].rstrip()
    s = s.replace(gsep, "")
    s = s.replace(dsep, ".")
    s = s.replace(" ", "")
    try:
        val = float(s)
    except ValueError:
        return _VALUE()
    if pct:
        val /= 100 ** pct
    return val


# --- date / time functions -------------------------------------------------


def _time(args):
    h = _try_num(_arg(args, 0))
    m = _try_num(_arg(args, 1))
    sec = _try_num(_arg(args, 2))
    if None in (h, m, sec):
        return _VALUE()
    total = h * 3600 + m * 60 + sec
    frac = (total % 86400) / 86400
    return float(frac)


def _timevalue(args):
    text = _text(_arg(args, 0)).strip()
    if text == "":
        return _VALUE()
    up = text.upper()
    ampm = None
    if up.endswith("AM") or up.endswith("PM"):
        ampm = up[-2:]
        text = up[:-2].strip()
    parts = text.split(":")
    if len(parts) < 2 or len(parts) > 3:
        return _VALUE()
    try:
        h = int(parts[0])
        m = int(parts[1])
        s = int(parts[2]) if len(parts) == 3 else 0
    except ValueError:
        return _VALUE()
    if ampm == "AM":
        if h == 12:
            h = 0
    elif ampm == "PM":
        if h != 12:
            h += 12
    if not (0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60):
        return _VALUE()
    return float((h * 3600 + m * 60 + s) / 86400)


_DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%d/%m/%Y",
    "%d-%b-%Y",
    "%d-%b-%y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
    "%Y/%m/%d",
)


def _datevalue(args):
    v = _arg(args, 0)
    d = _parse_date(v)
    if d is not None:
        return d.isoformat()
    text = _text(v).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return _VALUE()


def _eomonth(args):
    start = _parse_date(_arg(args, 0))
    months = _try_num(_arg(args, 1))
    if start is None or months is None:
        return _VALUE()
    total = start.month - 1 + int(months)
    year = start.year + total // 12
    month = total % 12 + 1
    try:
        return date(year, month, _days_in_month(year, month)).isoformat()
    except ValueError:
        return _NUM()


def _load_holidays(arg) -> set:
    out = set()
    if arg is None:
        return out
    for v in _flatten([arg]):
        d = _parse_date(v)
        if d is not None:
            out.add(d)
    return out


def _workday(args):
    start = _parse_date(_arg(args, 0))
    days = _try_num(_arg(args, 1))
    if start is None or days is None:
        return _VALUE()
    days = int(days)
    holidays = _load_holidays(_arg(args, 2))
    step = 1 if days >= 0 else -1
    remaining = abs(days)
    cur = start
    while remaining > 0:
        cur = cur + timedelta(days=step)
        if cur.weekday() >= 5:
            continue
        if cur in holidays:
            continue
        remaining -= 1
    return cur.isoformat()


def _networkdays(args):
    start = _parse_date(_arg(args, 0))
    end = _parse_date(_arg(args, 1))
    if start is None or end is None:
        return _VALUE()
    holidays = _load_holidays(_arg(args, 2))
    sign = 1
    if end < start:
        start, end = end, start
        sign = -1
    count = 0
    cur = start
    while cur <= end:
        if cur.weekday() < 5 and cur not in holidays:
            count += 1
        cur = cur + timedelta(days=1)
    return float(sign * count)


def _weeknum(args):
    d = _parse_date(_arg(args, 0))
    if d is None:
        return _VALUE()
    rtype = _try_num(_arg(args, 1, 1))
    if rtype is None:
        return _VALUE()
    rtype = int(rtype)
    if rtype == 21:
        return float(d.isocalendar()[1])
    # week-start weekday offset: type 1 -> Sunday, type 2 -> Monday.
    if rtype == 2:
        start_weekday = 0  # Monday
    else:
        start_weekday = 6  # Sunday (default, type 1)
    jan1 = date(d.year, 1, 1)
    # days since the first day-of-week on/before Jan 1
    jan1_offset = (jan1.weekday() - start_weekday) % 7
    week_start_of_year = jan1 - timedelta(days=jan1_offset)
    delta = (d - week_start_of_year).days
    return float(delta // 7 + 1)


def _isoweeknum(args):
    d = _parse_date(_arg(args, 0))
    if d is None:
        return _VALUE()
    return float(d.isocalendar()[1])


def _days360_count(start, end, european: bool) -> int:
    sd = start.day
    sm = start.month
    sy = start.year
    ed = end.day
    em = end.month
    ey = end.year
    if european:
        if sd == 31:
            sd = 30
        if ed == 31:
            ed = 30
    else:
        # US NASD method
        if sd == 31:
            sd = 30
        if ed == 31:
            if sd == 30:
                ed = 30
            # else leave ed = 31
    return (ey - sy) * 360 + (em - sm) * 30 + (ed - sd)


def _days360(args):
    start = _parse_date(_arg(args, 0))
    end = _parse_date(_arg(args, 1))
    if start is None or end is None:
        return _VALUE()
    european = _truthy_arg(_arg(args, 2, False))
    return float(_days360_count(start, end, european))


def _yearfrac(args):
    start = _parse_date(_arg(args, 0))
    end = _parse_date(_arg(args, 1))
    if start is None or end is None:
        return _VALUE()
    basis = _try_num(_arg(args, 2, 0))
    if basis is None:
        return _VALUE()
    basis = int(basis)
    if start == end:
        return 0.0
    lo, hi = (start, end) if start <= end else (end, start)
    if basis == 0:
        return float(_days360_count(lo, hi, False) / 360.0)
    if basis == 4:
        return float(_days360_count(lo, hi, True) / 360.0)
    if basis == 2:
        return float((hi - lo).days / 360.0)
    if basis == 3:
        return float((hi - lo).days / 365.0)
    if basis == 1:
        # actual/actual
        days = (hi - lo).days
        if lo.year == hi.year:
            denom = 366.0 if _is_leap(lo.year) else 365.0
            return float(days / denom)
        # average year length across the spanned years
        years = hi.year - lo.year + 1
        total_days = (date(hi.year + 1, 1, 1) - date(lo.year, 1, 1)).days
        avg = total_days / years
        return float(days / avg)
    return _NUM()


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


# --- CJK / Thai text (the curated-coverage tail) ---------------------------

def _asc(args):
    """ASC(text) — full-width (double-byte) → half-width (single-byte).

    Converts full-width ASCII letters/digits/symbols (U+FF01–FF5E) and the
    ideographic space (U+3000) to their half-width forms, and full-width →
    half-width katakana where a mapping exists. Other characters pass through.
    """
    s = _text(_arg(args, 0))
    out = []
    for ch in s:
        o = ord(ch)
        if o == 0x3000:                       # ideographic space → ASCII space
            out.append(" ")
        elif 0xFF01 <= o <= 0xFF5E:           # full-width ASCII → half-width
            out.append(chr(o - 0xFEE0))
        elif 0x30A0 <= o <= 0x30FF:           # katakana → its NFKD half-width, if any
            dec = unicodedata.normalize("NFKD", ch)
            out.append(dec if all(ord(c) <= 0xFFDC for c in dec) else ch)
        else:
            out.append(ch)
    return "".join(out)


def _dbcs(args):
    """DBCS(text) — half-width (single-byte) → full-width (double-byte).

    The inverse of :func:`_asc`: half-width ASCII (U+0021–007E) → full-width
    (U+FF01–FF5E), ASCII space → ideographic space, and half-width katakana
    (U+FF61–FF9F) → full-width katakana. Other characters pass through.
    """
    s = _text(_arg(args, 0))
    out = []
    for ch in s:
        o = ord(ch)
        if o == 0x20:                         # ASCII space → ideographic space
            out.append("　")
        elif 0x21 <= o <= 0x7E:               # half-width ASCII → full-width
            out.append(chr(o + 0xFEE0))
        elif 0xFF61 <= o <= 0xFF9F:           # half-width katakana → full-width
            out.append(unicodedata.normalize("NFKC", ch))
        else:
            out.append(ch)
    return "".join(out)


def _phonetic(args):
    """PHONETIC(text) — the phonetic (furigana) guide for a string.

    abax does not store per-cell furigana (there is no phonetic run to read),
    so — matching Excel's behaviour when a cell carries no phonetic guide — this
    returns the source text unchanged.
    """
    return _text(_arg(args, 0))


# Thai numeral reading for BAHTTEXT.
_THAI_DIGIT = ["", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]
_THAI_PLACE = ["", "สิบ", "ร้อย", "พัน", "หมื่น", "แสน"]


def _thai_read_group(n: int) -> str:
    """Read an integer 0..999999 as Thai text (no leading ``ศูนย์``)."""
    if n == 0:
        return ""
    digits = str(n)
    length = len(digits)
    out = []
    for i, dch in enumerate(digits):
        d = int(dch)
        place = length - i - 1               # 0 = units, 1 = tens, …
        if d == 0:
            continue
        if place == 0:                       # units
            out.append("เอ็ด" if (d == 1 and length > 1) else _THAI_DIGIT[d])
        elif place == 1:                     # tens
            out.append("สิบ" if d == 1 else ("ยี่สิบ" if d == 2 else _THAI_DIGIT[d] + "สิบ"))
        else:
            out.append(_THAI_DIGIT[d] + _THAI_PLACE[place])
    return "".join(out)


def _thai_read_int(n: int) -> str:
    """Read a non-negative integer as Thai text (``ศูนย์`` for zero)."""
    if n == 0:
        return "ศูนย์"
    parts = []
    if n >= 1_000_000:
        parts.append(_thai_read_int(n // 1_000_000) + "ล้าน")
        n %= 1_000_000
    parts.append(_thai_read_group(n))
    return "".join(parts)


def _bahttext(args):
    """BAHTTEXT(number) — a number as Thai baht text (บาท / สตางค์)."""
    num = _try_num(_arg(args, 0))
    if num is None:
        return CellError(CellError.VALUE)
    negative = num < 0
    num = abs(float(num))
    baht = int(num)
    satang = int(round((num - baht) * 100))
    if satang >= 100:                        # rounding carried into the baht
        baht += 1
        satang = 0
    text = _thai_read_int(baht) + "บาท"
    text += "ถ้วน" if satang == 0 else (_thai_read_int(satang) + "สตางค์")
    if negative and (baht or satang):
        text = "ลบ" + text
    return text


# --- registration ----------------------------------------------------------

_IMPLS = {
    "ASC": _asc,
    "DBCS": _dbcs,
    "JIS": _dbcs,                            # JIS is DBCS's Excel-JP alias
    "PHONETIC": _phonetic,
    "BAHTTEXT": _bahttext,
    "TEXTJOIN": _textjoin,
    "TEXTBEFORE": _textbefore,
    "TEXTAFTER": _textafter,
    "CLEAN": _clean,
    "UNICHAR": _unichar,
    "UNICODE": _unicode,
    "DOLLAR": _dollar,
    "FIXED": _fixed,
    "NUMBERVALUE": _numbervalue,
    "TIME": _time,
    "TIMEVALUE": _timevalue,
    "DATEVALUE": _datevalue,
    "EOMONTH": _eomonth,
    "WORKDAY": _workday,
    "NETWORKDAYS": _networkdays,
    "WEEKNUM": _weeknum,
    "ISOWEEKNUM": _isoweeknum,
    "YEARFRAC": _yearfrac,
    "DAYS360": _days360,
}

SIGNATURES = {
    "ASC": "ASC(text)",
    "DBCS": "DBCS(text)",
    "JIS": "JIS(text)",
    "PHONETIC": "PHONETIC(text)",
    "BAHTTEXT": "BAHTTEXT(number)",
    "TEXTJOIN": "TEXTJOIN(delimiter, ignore_empty, text1, ...)",
    "TEXTBEFORE": "TEXTBEFORE(text, delimiter, [instance_num])",
    "TEXTAFTER": "TEXTAFTER(text, delimiter, [instance_num])",
    "CLEAN": "CLEAN(text)",
    "UNICHAR": "UNICHAR(number)",
    "UNICODE": "UNICODE(text)",
    "DOLLAR": "DOLLAR(number, [decimals])",
    "FIXED": "FIXED(number, [decimals], [no_commas])",
    "NUMBERVALUE": "NUMBERVALUE(text, [decimal_sep], [group_sep])",
    "TIME": "TIME(hour, minute, second)",
    "TIMEVALUE": "TIMEVALUE(time_text)",
    "DATEVALUE": "DATEVALUE(date_text)",
    "EOMONTH": "EOMONTH(start_date, months)",
    "WORKDAY": "WORKDAY(start_date, days, [holidays])",
    "NETWORKDAYS": "NETWORKDAYS(start_date, end_date, [holidays])",
    "WEEKNUM": "WEEKNUM(date, [return_type])",
    "ISOWEEKNUM": "ISOWEEKNUM(date)",
    "YEARFRAC": "YEARFRAC(start_date, end_date, [basis])",
    "DAYS360": "DAYS360(start_date, end_date, [method])",
}


def register(functions: dict) -> None:
    """Merge the extended text and date/time functions into ``functions``."""
    functions.update(_IMPLS)
