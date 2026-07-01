"""Financial spreadsheet functions (pure stdlib).

Excel-compatible time-value-of-money, cashflow, depreciation and rate helpers.
Each function is ``def _fn(args)`` where ``args`` is a list of already-evaluated
values; it returns a ``float`` or a :class:`CellError`. Register into the engine's
function table with :func:`register`; :data:`SIGNATURES` gives one tooltip per
registered name.

Sign convention follows Excel: cash you pay out is negative, cash you receive is
positive. ``type`` is 0 for payments at period end (default) or 1 for the start.
"""

from __future__ import annotations

import math
from datetime import date

from .errors import CellError
from .functions.helpers import _arg, _as_number, _flatten, _numbers, _try_num
from .values import RangeValue

# --- small internal helpers ------------------------------------------------


def _num(args, i, default=None):
    """Read positional arg ``i`` as a number, substituting ``default`` when the
    arg is missing/blank. Returns ``None`` only when there is no value and no
    default (used to detect required args)."""
    raw = _arg(args, i, None)
    if raw is None or raw == "":
        return default
    if isinstance(raw, RangeValue):
        # A single-cell range is a scalar; anything larger is not a number here.
        if len(raw) != 1:
            return None
        raw = raw.flat()[0]
    try:
        return _as_number(raw)
    except (TypeError, ValueError):
        return _try_num(raw)


def _flat_numbers(args):
    """Flatten all args (RangeValue / lists / scalars) into a list of floats."""
    return _numbers(args)


# --- annuity core ----------------------------------------------------------


def _fv(rate, nper, pmt, pv, typ):
    if rate == 0:
        return -(pv + pmt * nper)
    f = (1 + rate) ** nper
    return -(pv * f + pmt * (1 + rate * typ) * (f - 1) / rate)


def _pv(rate, nper, pmt, fv, typ):
    if rate == 0:
        return -(fv + pmt * nper)
    f = (1 + rate) ** nper
    return -(fv + pmt * (1 + rate * typ) * (f - 1) / rate) / f


def _pmt(rate, nper, pv, fv, typ):
    if nper == 0:
        return None
    if rate == 0:
        return -(pv + fv) / nper
    f = (1 + rate) ** nper
    return -(fv + pv * f) * rate / ((1 + rate * typ) * (f - 1))


# --- time value of money ---------------------------------------------------


def _fn_fv(args):
    try:
        rate = _num(args, 0)
        nper = _num(args, 1)
        pmt = _num(args, 2)
        pv = _num(args, 3, 0.0)
        typ = _num(args, 4, 0.0)
        if rate is None or nper is None or pmt is None or pv is None or typ is None:
            return CellError(CellError.VALUE)
        return _fv(rate, nper, pmt, pv, typ)
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


def _fn_pv(args):
    try:
        rate = _num(args, 0)
        nper = _num(args, 1)
        pmt = _num(args, 2)
        fv = _num(args, 3, 0.0)
        typ = _num(args, 4, 0.0)
        if rate is None or nper is None or pmt is None or fv is None or typ is None:
            return CellError(CellError.VALUE)
        return _pv(rate, nper, pmt, fv, typ)
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


def _fn_pmt(args):
    try:
        rate = _num(args, 0)
        nper = _num(args, 1)
        pv = _num(args, 2)
        fv = _num(args, 3, 0.0)
        typ = _num(args, 4, 0.0)
        if rate is None or nper is None or pv is None or fv is None or typ is None:
            return CellError(CellError.VALUE)
        r = _pmt(rate, nper, pv, fv, typ)
        if r is None:
            return CellError(CellError.NUM)
        return r
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


def _fn_ipmt(args):
    try:
        rate = _num(args, 0)
        per = _num(args, 1)
        nper = _num(args, 2)
        pv = _num(args, 3)
        fv = _num(args, 4, 0.0)
        typ = _num(args, 5, 0.0)
        if None in (rate, per, nper, pv, fv, typ):
            return CellError(CellError.VALUE)
        if per < 1 or per > nper:
            return CellError(CellError.NUM)
        pmt = _pmt(rate, nper, pv, fv, typ)
        if pmt is None:
            return CellError(CellError.NUM)
        # Balance at start of period `per` = FV of (per-1) periods.
        bal = _fv(rate, per - 1, pmt, pv, typ)
        interest = bal * rate
        if typ == 1:
            # Payment at start of period: first period accrues no interest.
            if per == 1:
                return 0.0
            interest = interest / (1 + rate)
        return interest
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


def _fn_ppmt(args):
    try:
        rate = _num(args, 0)
        per = _num(args, 1)
        nper = _num(args, 2)
        pv = _num(args, 3)
        fv = _num(args, 4, 0.0)
        typ = _num(args, 5, 0.0)
        if None in (rate, per, nper, pv, fv, typ):
            return CellError(CellError.VALUE)
        pmt = _pmt(rate, nper, pv, fv, typ)
        if pmt is None:
            return CellError(CellError.NUM)
        ip = _fn_ipmt(args)
        if isinstance(ip, CellError):
            return ip
        return pmt - ip
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


def _fn_nper(args):
    try:
        rate = _num(args, 0)
        pmt = _num(args, 1)
        pv = _num(args, 2)
        fv = _num(args, 3, 0.0)
        typ = _num(args, 4, 0.0)
        if None in (rate, pmt, pv, fv, typ):
            return CellError(CellError.VALUE)
        if rate == 0:
            if pmt == 0:
                return CellError(CellError.NUM)
            return -(pv + fv) / pmt
        # Solve pv*(1+r)^n + pmt*(1+r*type)*((1+r)^n-1)/r + fv = 0 for (1+r)^n.
        c = pmt * (1 + rate * typ) / rate
        num = c - fv
        den = pv + c
        if den == 0 or num / den <= 0:
            return CellError(CellError.NUM)
        return math.log(num / den) / math.log(1 + rate)
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


def _fn_rate(args):
    try:
        nper = _num(args, 0)
        pmt = _num(args, 1)
        pv = _num(args, 2)
        fv = _num(args, 3, 0.0)
        typ = _num(args, 4, 0.0)
        guess = _num(args, 5, 0.1)
        if None in (nper, pmt, pv, fv, typ, guess):
            return CellError(CellError.VALUE)
        if nper <= 0:
            return CellError(CellError.NUM)

        def f(r):
            return _fv(r, nper, pmt, pv, typ) - fv

        # Newton with numerical derivative, then bisection fallback.
        r = guess
        for _ in range(100):
            y = f(r)
            if abs(y) < 1e-9:
                return r
            h = 1e-6
            dy = (f(r + h) - f(r - h)) / (2 * h)
            if dy == 0:
                break
            step = y / dy
            r_new = r - step
            if r_new <= -1:
                r_new = (r - 1) / 2
            if abs(r_new - r) < 1e-10:
                return r_new
            r = r_new
        # Bisection over a wide bracket.
        lo, hi = -0.999999, 10.0
        try:
            flo, fhi = f(lo), f(hi)
        except (OverflowError, ValueError):
            return CellError(CellError.NUM)
        if flo == 0:
            return lo
        if fhi == 0:
            return hi
        if flo * fhi > 0:
            return CellError(CellError.NUM)
        for _ in range(200):
            mid = (lo + hi) / 2
            fm = f(mid)
            if abs(fm) < 1e-9:
                return mid
            if flo * fm < 0:
                hi = mid
                fhi = fm
            else:
                lo = mid
                flo = fm
        return CellError(CellError.NUM)
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


# --- cashflow analysis -----------------------------------------------------


def _fn_npv(args):
    try:
        rate = _num(args, 0)
        if rate is None:
            return CellError(CellError.VALUE)
        vals = _flat_numbers(args[1:])
        total = 0.0
        for i, v in enumerate(vals, start=1):
            total += v / (1 + rate) ** i
        return total
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


def _irr_solve(vals, guess):
    def npv(r):
        s = 0.0
        for i, v in enumerate(vals):
            s += v / (1 + r) ** i
        return s

    r = guess
    for _ in range(100):
        y = npv(r)
        if abs(y) < 1e-9:
            return r
        h = 1e-6
        dy = (npv(r + h) - npv(r - h)) / (2 * h)
        if dy == 0:
            break
        r_new = r - y / dy
        if r_new <= -1:
            r_new = (r - 1) / 2
        if abs(r_new - r) < 1e-10:
            return r_new
        r = r_new
    # Bisection fallback.
    lo, hi = -0.999999, 10.0
    try:
        flo, fhi = npv(lo), npv(hi)
    except (OverflowError, ValueError):
        return None
    if flo * fhi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        fm = npv(mid)
        if abs(fm) < 1e-9:
            return mid
        if flo * fm < 0:
            hi = mid
        else:
            lo = mid
            flo = fm
    return None


def _fn_irr(args):
    try:
        vals = _flat_numbers([_arg(args, 0)])
        if not vals:
            # values may have been passed as separate scalar args
            vals = _flat_numbers(args[:1])
        guess = _num(args, 1, 0.1)
        if guess is None:
            guess = 0.1
        if len(vals) < 2:
            return CellError(CellError.NUM)
        r = _irr_solve(vals, guess)
        if r is None:
            return CellError(CellError.NUM)
        return r
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


def _parse_dates(arg):
    flat = _flatten([arg])
    out = []
    for v in flat:
        if isinstance(v, str):
            out.append(date.fromisoformat(v.strip()))
        else:
            return None
    return out


def _fn_xnpv(args):
    try:
        rate = _num(args, 0)
        if rate is None:
            return CellError(CellError.VALUE)
        vals = _flat_numbers([_arg(args, 1)])
        dates = _parse_dates(_arg(args, 2))
        if dates is None or len(dates) != len(vals) or not vals:
            return CellError(CellError.NUM)
        d0 = dates[0]
        total = 0.0
        for v, d in zip(vals, dates):
            total += v / (1 + rate) ** ((d - d0).days / 365.0)
        return total
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


def _fn_xirr(args):
    try:
        vals = _flat_numbers([_arg(args, 0)])
        dates = _parse_dates(_arg(args, 1))
        guess = _num(args, 2, 0.1)
        if guess is None:
            guess = 0.1
        if dates is None or len(dates) != len(vals) or len(vals) < 2:
            return CellError(CellError.NUM)
        d0 = dates[0]
        exps = [(d - d0).days / 365.0 for d in dates]

        def xnpv(r):
            s = 0.0
            for v, e in zip(vals, exps):
                s += v / (1 + r) ** e
            return s

        r = guess
        for _ in range(100):
            y = xnpv(r)
            if abs(y) < 1e-7:
                return r
            h = 1e-6
            dy = (xnpv(r + h) - xnpv(r - h)) / (2 * h)
            if dy == 0:
                break
            r_new = r - y / dy
            if r_new <= -1:
                r_new = (r - 1) / 2
            if abs(r_new - r) < 1e-11:
                return r_new
            r = r_new
        lo, hi = -0.999999, 10.0
        flo, fhi = xnpv(lo), xnpv(hi)
        if flo * fhi > 0:
            return CellError(CellError.NUM)
        for _ in range(200):
            mid = (lo + hi) / 2
            fm = xnpv(mid)
            if abs(fm) < 1e-7:
                return mid
            if flo * fm < 0:
                hi = mid
            else:
                lo = mid
                flo = fm
        return CellError(CellError.NUM)
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


def _fn_mirr(args):
    try:
        vals = _flat_numbers([_arg(args, 0)])
        finance = _num(args, 1)
        reinvest = _num(args, 2)
        if finance is None or reinvest is None:
            return CellError(CellError.VALUE)
        n = len(vals)
        if n < 2:
            return CellError(CellError.NUM)
        neg = 0.0  # PV of negative flows at finance rate
        pos = 0.0  # FV of positive flows at reinvest rate
        for i, v in enumerate(vals):
            if v < 0:
                neg += v / (1 + finance) ** i
            elif v > 0:
                pos += v * (1 + reinvest) ** (n - 1 - i)
        if neg == 0 or pos == 0:
            return CellError(CellError.DIV0)
        ratio = -pos / (neg)
        if ratio <= 0:
            return CellError(CellError.NUM)
        return ratio ** (1.0 / (n - 1)) - 1
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


def _cum(args, want_principal):
    rate = _num(args, 0)
    nper = _num(args, 1)
    pv = _num(args, 2)
    start = _num(args, 3)
    end = _num(args, 4)
    typ = _num(args, 5, 0.0)
    if None in (rate, nper, pv, start, end, typ):
        return CellError(CellError.VALUE)
    if rate <= 0 or nper <= 0 or pv <= 0:
        return CellError(CellError.NUM)
    if start < 1 or end < start or end > nper:
        return CellError(CellError.NUM)
    total = 0.0
    s = int(start)
    e = int(end)
    for per in range(s, e + 1):
        sub = [rate, per, nper, pv, 0.0, typ]
        if want_principal:
            part = _fn_ppmt(sub)
        else:
            part = _fn_ipmt(sub)
        if isinstance(part, CellError):
            return part
        total += part
    return total


def _fn_cumipmt(args):
    try:
        return _cum(args, want_principal=False)
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


def _fn_cumprinc(args):
    try:
        return _cum(args, want_principal=True)
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


# --- depreciation ----------------------------------------------------------


def _fn_sln(args):
    try:
        cost = _num(args, 0)
        salvage = _num(args, 1)
        life = _num(args, 2)
        if None in (cost, salvage, life):
            return CellError(CellError.VALUE)
        if life == 0:
            return CellError(CellError.DIV0)
        return (cost - salvage) / life
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


def _fn_syd(args):
    try:
        cost = _num(args, 0)
        salvage = _num(args, 1)
        life = _num(args, 2)
        per = _num(args, 3)
        if None in (cost, salvage, life, per):
            return CellError(CellError.VALUE)
        if life <= 0:
            return CellError(CellError.NUM)
        if per < 1 or per > life:
            return CellError(CellError.NUM)
        return (cost - salvage) * (life - per + 1) * 2.0 / (life * (life + 1))
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


def _fn_db(args):
    try:
        cost = _num(args, 0)
        salvage = _num(args, 1)
        life = _num(args, 2)
        period = _num(args, 3)
        month = _num(args, 4, 12.0)
        if None in (cost, salvage, life, period, month):
            return CellError(CellError.VALUE)
        if life <= 0 or cost <= 0 or period < 1:
            return CellError(CellError.NUM)
        if cost == 0:
            return 0.0
        rate = round(1 - (salvage / cost) ** (1.0 / life), 3)
        life_i = int(life)
        # First (partial) year.
        prev_total = 0.0
        result = 0.0
        for p in range(1, int(period) + 1):
            if p == 1:
                dep = cost * rate * month / 12.0
            elif p == life_i + 1:
                dep = (cost - prev_total) * rate * (12.0 - month) / 12.0
            else:
                dep = (cost - prev_total) * rate
            if p == int(period):
                result = dep
            prev_total += dep
        return result
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


def _ddb_dep(cost, salvage, life, period, factor):
    """Depreciation for a single DDB period (period is 1-based)."""
    total = 0.0
    dep = 0.0
    for p in range(1, int(math.ceil(period)) + 1):
        rate_dep = min((cost - total) * factor / life, max(cost - salvage - total, 0.0))
        if rate_dep < 0:
            rate_dep = 0.0
        dep = rate_dep
        total += dep
    return dep


def _fn_ddb(args):
    try:
        cost = _num(args, 0)
        salvage = _num(args, 1)
        life = _num(args, 2)
        period = _num(args, 3)
        factor = _num(args, 4, 2.0)
        if None in (cost, salvage, life, period, factor):
            return CellError(CellError.VALUE)
        if life <= 0 or period < 1 or period > life or factor <= 0:
            return CellError(CellError.NUM)
        return _ddb_dep(cost, salvage, life, period, factor)
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


def _fn_vdb(args):
    try:
        cost = _num(args, 0)
        salvage = _num(args, 1)
        life = _num(args, 2)
        start = _num(args, 3)
        end = _num(args, 4)
        factor = _num(args, 5, 2.0)
        no_switch_raw = _arg(args, 6, False)
        no_switch = bool(no_switch_raw) if no_switch_raw not in (None, "") else False
        if None in (cost, salvage, life, start, end, factor):
            return CellError(CellError.VALUE)
        if life <= 0 or start < 0 or end < start or end > life or factor <= 0:
            return CellError(CellError.NUM)

        # Sum DDB depreciation across whole periods in [start, end], optionally
        # switching to straight-line when it gives a larger deduction.
        total_dep = 0.0
        accumulated = 0.0
        e = int(math.ceil(end))
        for p in range(1, e + 1):
            remaining_life = life - (p - 1)
            ddb = min(
                (cost - accumulated) * factor / life,
                max(cost - salvage - accumulated, 0.0),
            )
            if not no_switch and remaining_life > 0:
                sl = (cost - salvage - accumulated) / remaining_life
                if sl > ddb:
                    ddb = sl
            if ddb < 0:
                ddb = 0.0
            # Fraction of this period inside [start, end].
            lo = max(start, p - 1)
            hi = min(end, p)
            frac = hi - lo
            if frac > 0:
                total_dep += ddb * frac
            accumulated += ddb
        return total_dep
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


# --- rates & misc ----------------------------------------------------------


def _fn_effect(args):
    try:
        nominal = _num(args, 0)
        npery = _num(args, 1)
        if nominal is None or npery is None:
            return CellError(CellError.VALUE)
        npery = int(npery)
        if nominal <= 0 or npery < 1:
            return CellError(CellError.NUM)
        return (1 + nominal / npery) ** npery - 1
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


def _fn_nominal(args):
    try:
        effect = _num(args, 0)
        npery = _num(args, 1)
        if effect is None or npery is None:
            return CellError(CellError.VALUE)
        npery = int(npery)
        if effect <= 0 or npery < 1:
            return CellError(CellError.NUM)
        return npery * ((1 + effect) ** (1.0 / npery) - 1)
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


def _fn_dollarde(args):
    try:
        frac_dollar = _num(args, 0)
        fraction = _num(args, 1)
        if frac_dollar is None or fraction is None:
            return CellError(CellError.VALUE)
        fraction = int(fraction)
        if fraction < 0:
            return CellError(CellError.NUM)
        if fraction == 0:
            return CellError(CellError.DIV0)
        whole = math.trunc(frac_dollar)
        frac = frac_dollar - whole
        digits = math.ceil(math.log10(fraction)) if fraction > 1 else 1
        return whole + frac * (10 ** digits) / fraction
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


def _fn_dollarfr(args):
    try:
        dec_dollar = _num(args, 0)
        fraction = _num(args, 1)
        if dec_dollar is None or fraction is None:
            return CellError(CellError.VALUE)
        fraction = int(fraction)
        if fraction < 0:
            return CellError(CellError.NUM)
        if fraction == 0:
            return CellError(CellError.DIV0)
        whole = math.trunc(dec_dollar)
        frac = dec_dollar - whole
        digits = math.ceil(math.log10(fraction)) if fraction > 1 else 1
        return whole + frac * fraction / (10 ** digits)
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


def _fn_pduration(args):
    try:
        rate = _num(args, 0)
        pv = _num(args, 1)
        fv = _num(args, 2)
        if None in (rate, pv, fv):
            return CellError(CellError.VALUE)
        if rate <= 0 or pv <= 0 or fv <= 0:
            return CellError(CellError.NUM)
        return (math.log(fv) - math.log(pv)) / math.log(1 + rate)
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


def _fn_rri(args):
    try:
        nper = _num(args, 0)
        pv = _num(args, 1)
        fv = _num(args, 2)
        if None in (nper, pv, fv):
            return CellError(CellError.VALUE)
        if nper <= 0 or pv == 0:
            return CellError(CellError.NUM)
        ratio = fv / pv
        if ratio < 0:
            return CellError(CellError.NUM)
        return ratio ** (1.0 / nper) - 1
    except (ValueError, TypeError, OverflowError, ZeroDivisionError):
        return CellError(CellError.NUM)


# --- public surface --------------------------------------------------------


def register(functions: dict) -> None:
    functions.update({
        "FV": _fn_fv,
        "PV": _fn_pv,
        "PMT": _fn_pmt,
        "IPMT": _fn_ipmt,
        "PPMT": _fn_ppmt,
        "NPER": _fn_nper,
        "RATE": _fn_rate,
        "NPV": _fn_npv,
        "IRR": _fn_irr,
        "XNPV": _fn_xnpv,
        "XIRR": _fn_xirr,
        "MIRR": _fn_mirr,
        "CUMIPMT": _fn_cumipmt,
        "CUMPRINC": _fn_cumprinc,
        "SLN": _fn_sln,
        "SYD": _fn_syd,
        "DB": _fn_db,
        "DDB": _fn_ddb,
        "VDB": _fn_vdb,
        "EFFECT": _fn_effect,
        "NOMINAL": _fn_nominal,
        "DOLLARDE": _fn_dollarde,
        "DOLLARFR": _fn_dollarfr,
        "PDURATION": _fn_pduration,
        "RRI": _fn_rri,
    })


SIGNATURES = {
    "FV": "FV(rate, nper, pmt, [pv], [type])",
    "PV": "PV(rate, nper, pmt, [fv], [type])",
    "PMT": "PMT(rate, nper, pv, [fv], [type])",
    "IPMT": "IPMT(rate, per, nper, pv, [fv], [type])",
    "PPMT": "PPMT(rate, per, nper, pv, [fv], [type])",
    "NPER": "NPER(rate, pmt, pv, [fv], [type])",
    "RATE": "RATE(nper, pmt, pv, [fv], [type], [guess])",
    "NPV": "NPV(rate, value1, [value2], ...)",
    "IRR": "IRR(values, [guess])",
    "XNPV": "XNPV(rate, values, dates)",
    "XIRR": "XIRR(values, dates, [guess])",
    "MIRR": "MIRR(values, finance_rate, reinvest_rate)",
    "CUMIPMT": "CUMIPMT(rate, nper, pv, start_period, end_period, type)",
    "CUMPRINC": "CUMPRINC(rate, nper, pv, start_period, end_period, type)",
    "SLN": "SLN(cost, salvage, life)",
    "SYD": "SYD(cost, salvage, life, per)",
    "DB": "DB(cost, salvage, life, period, [month])",
    "DDB": "DDB(cost, salvage, life, period, [factor])",
    "VDB": "VDB(cost, salvage, life, start_period, end_period, [factor], [no_switch])",
    "EFFECT": "EFFECT(nominal_rate, npery)",
    "NOMINAL": "NOMINAL(effect_rate, npery)",
    "DOLLARDE": "DOLLARDE(fractional_dollar, fraction)",
    "DOLLARFR": "DOLLARFR(decimal_dollar, fraction)",
    "PDURATION": "PDURATION(rate, pv, fv)",
    "RRI": "RRI(nper, pv, fv)",
}
