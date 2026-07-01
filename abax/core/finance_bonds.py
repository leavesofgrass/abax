"""Wave D tail — bond / security financial functions.

The coupon-schedule half of Excel's financial category that the core
time-value-of-money pack (:mod:`abax.core.finance_fns`) left out: the COUP*
schedule functions, coupon-bond ``PRICE``/``YIELD`` and Macaulay/modified
``DURATION``, the discounted-security family (``DISC``, ``PRICEDISC``,
``YIELDDISC``, ``INTRATE``, ``RECEIVED``), interest-at-maturity securities
(``ACCRINT``, ``ACCRINTM``, ``PRICEMAT``, ``YIELDMAT``) and the Treasury-bill
trio (``TBILLEQ``, ``TBILLPRICE``, ``TBILLYIELD``).

Dates are ISO strings (or datetimes), like the rest of the date family; the
day-count ``basis`` argument follows Excel (0 = US 30/360, 1 = actual/actual,
2 = actual/360, 3 = actual/365, 4 = European 30/360) and reuses the tested
``DAYS360``/``YEARFRAC`` machinery from :mod:`abax.core.text_datetime_fns`.
Coupon schedules walk back from *maturity* in 12/frequency-month steps with
Excel's end-of-month rule (a maturity on the last day of its month keeps every
coupon on a month end).

``ACCRINT`` uses the simple pro-rata form (par × rate × accrued fraction),
which matches Excel's documented examples; the odd-period functions
(ODDF*/ODDL*) are out of scope. Registered by :func:`register`.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Callable

from .errors import CellError, is_error
from .text_datetime_fns import _days360_count, _parse_date, _yearfrac


def _arg(args: list, i: int, default: Any = None) -> Any:
    return args[i] if i < len(args) else default


def _num(v: Any) -> "float | None":
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _yf(start: date, end: date, basis: int) -> "float | CellError":
    """Year fraction between two dates on an Excel day-count basis."""
    return _yearfrac([start.isoformat(), end.isoformat(), float(basis)])


# --- coupon schedule ---------------------------------------------------------


def _days_in_month(y: int, m: int) -> int:
    if m == 12:
        return 31
    return (date(y, m + 1, 1) - date(y, m, 1)).days


def _add_months(d: date, months: int, eom: bool) -> date:
    total = d.month - 1 + months
    y = d.year + total // 12
    m = total % 12 + 1
    day = _days_in_month(y, m) if eom else min(d.day, _days_in_month(y, m))
    return date(y, m, day)


def _coupon_schedule(settlement: date, maturity: date, freq: int) -> "tuple[date, date, int]":
    """(previous coupon date, next coupon date, remaining coupon count) for a
    bond maturing on *maturity*, seen from *settlement*. Coupon dates walk back
    from maturity in 12/freq-month steps (end-of-month rule)."""
    step = 12 // freq
    eom = maturity.day == _days_in_month(maturity.year, maturity.month)
    k = 0
    pcd = maturity
    while pcd > settlement:
        k += 1
        pcd = _add_months(maturity, -step * k, eom)
    ncd = _add_months(maturity, -step * (k - 1), eom) if k else maturity
    return pcd, ncd, k


def _coup_days_bs(pcd: date, settlement: date, basis: int) -> float:
    if basis == 0:
        return float(_days360_count(pcd, settlement, False))
    if basis == 4:
        return float(_days360_count(pcd, settlement, True))
    return float((settlement - pcd).days)


def _coup_days(pcd: date, ncd: date, freq: int, basis: int) -> float:
    if basis == 1:
        return float((ncd - pcd).days)
    if basis == 3:
        return 365.0 / freq
    return 360.0 / freq  # 0, 2, 4


def _coup_days_nc(settlement: date, pcd: date, ncd: date, freq: int, basis: int) -> float:
    if basis in (0, 4):
        return _coup_days(pcd, ncd, freq, basis) - _coup_days_bs(pcd, settlement, basis)
    return float((ncd - settlement).days)


class _Bad(Exception):
    def __init__(self, err: CellError) -> None:
        self.err = err


def _sched_args(args: list) -> "tuple[date, date, int, int]":
    """settlement, maturity, frequency, basis — shared COUP*/PRICE validation."""
    settlement = _parse_date(_arg(args, 0))
    maturity = _parse_date(_arg(args, 1))
    freq = _num(_arg(args, 2))
    basis = _num(_arg(args, 3, 0))
    if settlement is None or maturity is None or freq is None or basis is None:
        raise _Bad(CellError(CellError.VALUE))
    freq, basis = int(freq), int(basis)
    if freq not in (1, 2, 4) or not (0 <= basis <= 4) or settlement >= maturity:
        raise _Bad(CellError(CellError.NUM))
    return settlement, maturity, freq, basis


def _coup_fn(pick: Callable[[date, date, date, int, int], Any]):
    def impl(args: list) -> Any:
        try:
            settlement, maturity, freq, basis = _sched_args(args)
        except _Bad as b:
            return b.err
        pcd, ncd, n = _coupon_schedule(settlement, maturity, freq)
        return pick(settlement, pcd, ncd, freq, basis) if n else CellError(CellError.NUM)
    return impl


_COUPPCD = _coup_fn(lambda s, pcd, ncd, f, b: pcd.isoformat())
_COUPNCD = _coup_fn(lambda s, pcd, ncd, f, b: ncd.isoformat())
_COUPDAYBS = _coup_fn(lambda s, pcd, ncd, f, b: _coup_days_bs(pcd, s, b))
_COUPDAYS = _coup_fn(lambda s, pcd, ncd, f, b: _coup_days(pcd, ncd, f, b))
_COUPDAYSNC = _coup_fn(lambda s, pcd, ncd, f, b: _coup_days_nc(s, pcd, ncd, f, b))


def _coupnum(args: list) -> Any:
    try:
        settlement, maturity, freq, _basis = _sched_args(args)
    except _Bad as b:
        return b.err
    return float(_coupon_schedule(settlement, maturity, freq)[2])


# --- coupon-bond price / yield / duration ------------------------------------


def _bond_price(settlement: date, maturity: date, rate: float, yld: float,
                redemption: float, freq: int, basis: int) -> float:
    pcd, ncd, n = _coupon_schedule(settlement, maturity, freq)
    e = _coup_days(pcd, ncd, freq, basis)
    a = _coup_days_bs(pcd, settlement, basis)
    dsc = _coup_days_nc(settlement, pcd, ncd, freq, basis)
    coupon = 100.0 * rate / freq
    if n == 1:  # one period left: simple interest (Excel's short formula)
        return ((redemption + coupon) / (1.0 + dsc / e * yld / freq)
                - a / e * coupon)
    base = 1.0 + yld / freq
    price = redemption / base ** (n - 1 + dsc / e)
    for k in range(1, n + 1):
        price += coupon / base ** (k - 1 + dsc / e)
    return price - coupon * a / e


def _price(args: list) -> Any:
    """PRICE(settlement, maturity, rate, yld, redemption, frequency, [basis])."""
    try:
        settlement, maturity, _f, _b = _sched_args(
            [_arg(args, 0), _arg(args, 1), _arg(args, 5), _arg(args, 6, 0)])
    except _Bad as b:
        return b.err
    rate = _num(_arg(args, 2))
    yld = _num(_arg(args, 3))
    redemption = _num(_arg(args, 4))
    if rate is None or yld is None or redemption is None:
        return CellError(CellError.VALUE)
    if rate < 0 or yld < 0 or redemption <= 0:
        return CellError(CellError.NUM)
    return _bond_price(settlement, maturity, rate, yld, redemption, _f, _b)


def _yield(args: list) -> Any:
    """YIELD(settlement, maturity, rate, pr, redemption, frequency, [basis]) —
    inverts PRICE by bisection (price is monotone decreasing in yield)."""
    try:
        settlement, maturity, freq, basis = _sched_args(
            [_arg(args, 0), _arg(args, 1), _arg(args, 5), _arg(args, 6, 0)])
    except _Bad as b:
        return b.err
    rate = _num(_arg(args, 2))
    pr = _num(_arg(args, 3))
    redemption = _num(_arg(args, 4))
    if rate is None or pr is None or redemption is None:
        return CellError(CellError.VALUE)
    if rate < 0 or pr <= 0 or redemption <= 0:
        return CellError(CellError.NUM)

    def diff(y: float) -> float:
        return _bond_price(settlement, maturity, rate, y, redemption, freq, basis) - pr

    lo, hi = 0.0, 1.0
    if diff(lo) < 0:  # price at zero yield below target: negative yield
        lo, hi = -0.99, 0.0
    else:
        while diff(hi) > 0 and hi < 1e3:
            hi *= 2
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if diff(mid) > 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12:
            break
    return 0.5 * (lo + hi)


def _duration_impl(args: list, modified: bool) -> Any:
    try:
        settlement, maturity, freq, basis = _sched_args(
            [_arg(args, 0), _arg(args, 1), _arg(args, 4), _arg(args, 5, 0)])
    except _Bad as b:
        return b.err
    coupon_rate = _num(_arg(args, 2))
    yld = _num(_arg(args, 3))
    if coupon_rate is None or yld is None:
        return CellError(CellError.VALUE)
    if coupon_rate < 0 or yld < 0:
        return CellError(CellError.NUM)
    pcd, ncd, n = _coupon_schedule(settlement, maturity, freq)
    e = _coup_days(pcd, ncd, freq, basis)
    dsc = _coup_days_nc(settlement, pcd, ncd, freq, basis)
    coupon = 100.0 * coupon_rate / freq
    base = 1.0 + yld / freq
    wsum = psum = 0.0
    for k in range(1, n + 1):
        t = k - 1 + dsc / e                    # time in coupon periods
        cf = coupon + (100.0 if k == n else 0.0)
        pv = cf / base ** t
        psum += pv
        wsum += t * pv
    if psum == 0:
        return CellError(CellError.NUM)
    dur = wsum / psum / freq                   # Macaulay, in years
    return dur / base if modified else dur


def _duration(args: list) -> Any:
    """DURATION(settlement, maturity, coupon, yld, frequency, [basis])."""
    return _duration_impl(args, modified=False)


def _mduration(args: list) -> Any:
    """MDURATION(settlement, maturity, coupon, yld, frequency, [basis])."""
    return _duration_impl(args, modified=True)


# --- discounted securities -----------------------------------------------------


def _two_dates(args: list, i: int = 0, j: int = 1) -> "tuple[date, date]":
    d1 = _parse_date(_arg(args, i))
    d2 = _parse_date(_arg(args, j))
    if d1 is None or d2 is None:
        raise _Bad(CellError(CellError.VALUE))
    if d1 >= d2:
        raise _Bad(CellError(CellError.NUM))
    return d1, d2


def _basis_arg(args: list, i: int) -> int:
    basis = _num(_arg(args, i, 0))
    if basis is None or not (0 <= int(basis) <= 4):
        raise _Bad(CellError(CellError.NUM))
    return int(basis)


def _pricedisc(args: list) -> Any:
    """PRICEDISC(settlement, maturity, discount, redemption, [basis])."""
    try:
        settlement, maturity = _two_dates(args)
        basis = _basis_arg(args, 4)
    except _Bad as b:
        return b.err
    discount = _num(_arg(args, 2))
    redemption = _num(_arg(args, 3))
    if discount is None or redemption is None:
        return CellError(CellError.VALUE)
    if discount <= 0 or redemption <= 0:
        return CellError(CellError.NUM)
    yf = _yf(settlement, maturity, basis)
    if is_error(yf):
        return yf
    return redemption * (1.0 - discount * yf)


def _yielddisc(args: list) -> Any:
    """YIELDDISC(settlement, maturity, pr, redemption, [basis])."""
    try:
        settlement, maturity = _two_dates(args)
        basis = _basis_arg(args, 4)
    except _Bad as b:
        return b.err
    pr = _num(_arg(args, 2))
    redemption = _num(_arg(args, 3))
    if pr is None or redemption is None:
        return CellError(CellError.VALUE)
    if pr <= 0 or redemption <= 0:
        return CellError(CellError.NUM)
    yf = _yf(settlement, maturity, basis)
    if is_error(yf) or yf == 0:
        return yf if is_error(yf) else CellError(CellError.NUM)
    return (redemption - pr) / pr / yf


def _disc(args: list) -> Any:
    """DISC(settlement, maturity, pr, redemption, [basis])."""
    try:
        settlement, maturity = _two_dates(args)
        basis = _basis_arg(args, 4)
    except _Bad as b:
        return b.err
    pr = _num(_arg(args, 2))
    redemption = _num(_arg(args, 3))
    if pr is None or redemption is None:
        return CellError(CellError.VALUE)
    if pr <= 0 or redemption <= 0:
        return CellError(CellError.NUM)
    yf = _yf(settlement, maturity, basis)
    if is_error(yf) or yf == 0:
        return yf if is_error(yf) else CellError(CellError.NUM)
    return (redemption - pr) / redemption / yf


def _intrate(args: list) -> Any:
    """INTRATE(settlement, maturity, investment, redemption, [basis])."""
    try:
        settlement, maturity = _two_dates(args)
        basis = _basis_arg(args, 4)
    except _Bad as b:
        return b.err
    investment = _num(_arg(args, 2))
    redemption = _num(_arg(args, 3))
    if investment is None or redemption is None:
        return CellError(CellError.VALUE)
    if investment <= 0 or redemption <= 0:
        return CellError(CellError.NUM)
    yf = _yf(settlement, maturity, basis)
    if is_error(yf) or yf == 0:
        return yf if is_error(yf) else CellError(CellError.NUM)
    return (redemption - investment) / investment / yf


def _received(args: list) -> Any:
    """RECEIVED(settlement, maturity, investment, discount, [basis])."""
    try:
        settlement, maturity = _two_dates(args)
        basis = _basis_arg(args, 4)
    except _Bad as b:
        return b.err
    investment = _num(_arg(args, 2))
    discount = _num(_arg(args, 3))
    if investment is None or discount is None:
        return CellError(CellError.VALUE)
    if investment <= 0 or discount <= 0:
        return CellError(CellError.NUM)
    yf = _yf(settlement, maturity, basis)
    if is_error(yf):
        return yf
    denom = 1.0 - discount * yf
    if denom <= 0:
        return CellError(CellError.NUM)
    return investment / denom


# --- interest at maturity -------------------------------------------------------


def _accrint(args: list) -> Any:
    """ACCRINT(issue, first_interest, settlement, rate, par, frequency, [basis])
    — simple pro-rata accrued interest from issue to settlement."""
    issue = _parse_date(_arg(args, 0))
    settlement = _parse_date(_arg(args, 2))
    rate = _num(_arg(args, 3))
    par = _num(_arg(args, 4))
    freq = _num(_arg(args, 5))
    if issue is None or settlement is None or rate is None or par is None or freq is None:
        return CellError(CellError.VALUE)
    if rate <= 0 or par <= 0 or int(freq) not in (1, 2, 4) or issue >= settlement:
        return CellError(CellError.NUM)
    try:
        basis = _basis_arg(args, 6)
    except _Bad as b:
        return b.err
    yf = _yf(issue, settlement, basis)
    return yf if is_error(yf) else par * rate * yf


def _accrintm(args: list) -> Any:
    """ACCRINTM(issue, settlement, rate, par, [basis])."""
    try:
        issue, settlement = _two_dates(args)
        basis = _basis_arg(args, 4)
    except _Bad as b:
        return b.err
    rate = _num(_arg(args, 2))
    par = _num(_arg(args, 3))
    if rate is None or par is None:
        return CellError(CellError.VALUE)
    if rate <= 0 or par <= 0:
        return CellError(CellError.NUM)
    yf = _yf(issue, settlement, basis)
    return yf if is_error(yf) else par * rate * yf


def _pricemat(args: list) -> Any:
    """PRICEMAT(settlement, maturity, issue, rate, yld, [basis])."""
    settlement = _parse_date(_arg(args, 0))
    maturity = _parse_date(_arg(args, 1))
    issue = _parse_date(_arg(args, 2))
    rate = _num(_arg(args, 3))
    yld = _num(_arg(args, 4))
    if settlement is None or maturity is None or issue is None or rate is None or yld is None:
        return CellError(CellError.VALUE)
    if rate < 0 or yld < 0 or not (issue < settlement < maturity):
        return CellError(CellError.NUM)
    try:
        basis = _basis_arg(args, 5)
    except _Bad as b:
        return b.err
    a = _yf(issue, settlement, basis)      # issue -> settlement
    dim = _yf(issue, maturity, basis)      # issue -> maturity
    dsm = _yf(settlement, maturity, basis)  # settlement -> maturity
    for v in (a, dim, dsm):
        if is_error(v):
            return v
    return (100.0 + dim * rate * 100.0) / (1.0 + dsm * yld) - a * rate * 100.0


def _yieldmat(args: list) -> Any:
    """YIELDMAT(settlement, maturity, issue, rate, pr, [basis])."""
    settlement = _parse_date(_arg(args, 0))
    maturity = _parse_date(_arg(args, 1))
    issue = _parse_date(_arg(args, 2))
    rate = _num(_arg(args, 3))
    pr = _num(_arg(args, 4))
    if settlement is None or maturity is None or issue is None or rate is None or pr is None:
        return CellError(CellError.VALUE)
    if rate < 0 or pr <= 0 or not (issue < settlement < maturity):
        return CellError(CellError.NUM)
    try:
        basis = _basis_arg(args, 5)
    except _Bad as b:
        return b.err
    a = _yf(issue, settlement, basis)
    dim = _yf(issue, maturity, basis)
    dsm = _yf(settlement, maturity, basis)
    for v in (a, dim, dsm):
        if is_error(v):
            return v
    if dsm == 0:
        return CellError(CellError.NUM)
    return ((1.0 + dim * rate) / (pr / 100.0 + a * rate) - 1.0) / dsm


# --- Treasury bills ---------------------------------------------------------------


def _tbill_dates(args: list) -> "tuple[date, date, int]":
    settlement, maturity = _two_dates(args)
    dsm = (maturity - settlement).days
    if dsm > 366:
        raise _Bad(CellError(CellError.NUM))
    return settlement, maturity, dsm


def _tbilleq(args: list) -> Any:
    """TBILLEQ(settlement, maturity, discount) — bond-equivalent yield."""
    try:
        _s, _m, dsm = _tbill_dates(args)
    except _Bad as b:
        return b.err
    discount = _num(_arg(args, 2))
    if discount is None:
        return CellError(CellError.VALUE)
    if discount <= 0:
        return CellError(CellError.NUM)
    if dsm <= 182:
        denom = 360.0 - discount * dsm
        if denom <= 0:
            return CellError(CellError.NUM)
        return 365.0 * discount / denom
    # Longer bills: solve the semi-annual compounding relation
    # (1 + y/2)(1 + (T - 1/2)y) = 1/P with T = dsm/365, P = 1 - discount*dsm/360.
    p = 1.0 - discount * dsm / 360.0
    if p <= 0:
        return CellError(CellError.NUM)
    t = dsm / 365.0
    disc_root = t * t + (2.0 * t - 1.0) * (1.0 / p - 1.0)
    if disc_root < 0 or t == 0.5:
        return CellError(CellError.NUM)
    return (-t + math.sqrt(disc_root)) / (t - 0.5)


def _tbillprice(args: list) -> Any:
    """TBILLPRICE(settlement, maturity, discount) — price per 100 face."""
    try:
        _s, _m, dsm = _tbill_dates(args)
    except _Bad as b:
        return b.err
    discount = _num(_arg(args, 2))
    if discount is None:
        return CellError(CellError.VALUE)
    price = 100.0 * (1.0 - discount * dsm / 360.0)
    return price if price > 0 else CellError(CellError.NUM)


def _tbillyield(args: list) -> Any:
    """TBILLYIELD(settlement, maturity, pr) — discount yield from price."""
    try:
        _s, _m, dsm = _tbill_dates(args)
    except _Bad as b:
        return b.err
    pr = _num(_arg(args, 2))
    if pr is None:
        return CellError(CellError.VALUE)
    if pr <= 0 or dsm == 0:
        return CellError(CellError.NUM)
    return (100.0 - pr) / pr * 360.0 / dsm


# --- registry ---------------------------------------------------------------------

_REGISTRY: dict[str, Callable[[list], Any]] = {
    "COUPPCD": _COUPPCD,
    "COUPNCD": _COUPNCD,
    "COUPNUM": _coupnum,
    "COUPDAYBS": _COUPDAYBS,
    "COUPDAYS": _COUPDAYS,
    "COUPDAYSNC": _COUPDAYSNC,
    "PRICE": _price,
    "YIELD": _yield,
    "DURATION": _duration,
    "MDURATION": _mduration,
    "PRICEDISC": _pricedisc,
    "YIELDDISC": _yielddisc,
    "DISC": _disc,
    "INTRATE": _intrate,
    "RECEIVED": _received,
    "ACCRINT": _accrint,
    "ACCRINTM": _accrintm,
    "PRICEMAT": _pricemat,
    "YIELDMAT": _yieldmat,
    "TBILLEQ": _tbilleq,
    "TBILLPRICE": _tbillprice,
    "TBILLYIELD": _tbillyield,
}


def register(functions: dict) -> None:
    """Merge the bond/security functions into the engine's table."""
    functions.update(_REGISTRY)
