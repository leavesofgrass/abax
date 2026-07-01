"""HP-12C financial, statistics, and calendar math — pure-Python primitives.

The float side of the HP-12C keypad (:mod:`abax.core.calc.rpn12`) implements the
five TVM registers itself; this module supplies the *rest* of the 12C's stubbed
functionality so those keys can do real work: discounted cash flows
(:func:`npv`, :func:`irr`), bond pricing (:func:`bond_price`, :func:`bond_ytm`),
the three classic depreciation schedules (:func:`depreciation_sl`,
:func:`depreciation_soyd`, :func:`depreciation_db`), the percent keys
(:func:`percent`, :func:`percent_change`, :func:`percent_total`,
:func:`factorial`), the Sigma+/Sigma- statistics accumulator (:class:`Stats`),
and the date arithmetic keys (:func:`days_between`, :func:`date_plus_days`).

Everything is stdlib-only (:mod:`math` plus :class:`datetime.date` for actual-day
counts). Routines guard divisions, watch for degenerate inputs, and raise
:class:`FinanceError` rather than returning a bogus result. Rates are expressed
in *percent* throughout (matching the 12C keypad), and the HP cash-flow sign
convention applies: money received is positive, money paid out is negative.
"""

from __future__ import annotations

import datetime
import math


class FinanceError(Exception):
    """Raised when a financial/statistical routine cannot produce a result."""


# --- cash flows ----------------------------------------------------------


def npv(rate_pct: float, cashflows: list[float]) -> float:
    """Net present value of ``cashflows`` discounted at ``rate_pct`` percent.

    ``cashflows[0]`` is the time-0 flow CF0; the rest are one period apart::

        NPV = sum_j cashflows[j] / (1 + rate_pct / 100) ** j

    Raises :class:`FinanceError` for an empty list or a discount factor of zero
    (``rate_pct == -100``).
    """
    if not cashflows:
        raise FinanceError("cashflows must be non-empty")
    factor = 1.0 + rate_pct / 100.0
    if factor == 0.0:
        raise FinanceError("discount factor is zero (rate_pct == -100)")
    total = 0.0
    for j, cf in enumerate(cashflows):
        total += cf / factor ** j
    if not math.isfinite(total):
        raise FinanceError("non-finite NPV")
    return total


def irr(cashflows: list[float], guess_pct: float = 10.0) -> float:
    """Internal rate of return (percent) where ``npv(rate, cashflows) == 0``.

    A sign change is bracketed by scanning a wide range of plausible rates, then
    the root is polished by bisection. Raises :class:`FinanceError` if the cash
    flows are empty, never change sign, or no bracket can be found.
    """
    if not cashflows:
        raise FinanceError("cashflows must be non-empty")
    signs = {cf > 0 for cf in cashflows if cf != 0.0}
    if len(signs) < 2:
        raise FinanceError("cashflows must have at least one sign change")

    def f(rate_pct: float) -> float:
        return npv(rate_pct, cashflows)

    # Scan rates from just above -100% upward for a sign change; start the scan
    # near the guess so a well-posed problem is found quickly.
    lo, hi = -99.999, 1000.0
    steps = 2000
    prev_r = lo
    try:
        prev_v = f(prev_r)
    except FinanceError:
        prev_v = math.nan
    bracket: tuple[float, float] | None = None
    for k in range(1, steps + 1):
        r = lo + (hi - lo) * k / steps
        try:
            v = f(r)
        except FinanceError:
            prev_r, prev_v = r, math.nan
            continue
        if v == 0.0:
            return r
        if math.isfinite(prev_v) and (prev_v < 0.0) != (v < 0.0):
            bracket = (prev_r, r)
            break
        prev_r, prev_v = r, v

    if bracket is None:
        raise FinanceError("could not bracket an IRR")

    a, b = bracket
    fa = f(a)
    for _ in range(200):
        m = 0.5 * (a + b)
        fm = f(m)
        if abs(fm) < 1e-10 or (b - a) < 1e-12:
            return m
        if (fa < 0.0) != (fm < 0.0):
            b = m
        else:
            a, fa = m, fm
    return 0.5 * (a + b)


# --- bonds ---------------------------------------------------------------


def bond_price(yield_pct: float, coupon_pct: float, years: float, freq: int = 2) -> float:
    """Price per 100 face for an annual ``coupon_pct`` bond at ``yield_pct``.

    Coupons are paid ``freq`` times a year (semiannual by default) for ``years``
    years; the face value of 100 is returned at maturity. Raises
    :class:`FinanceError` for non-positive ``freq``/``years`` or a per-period
    yield of -100%.
    """
    if freq <= 0:
        raise FinanceError("freq must be positive")
    if years <= 0:
        raise FinanceError("years must be positive")
    periods = years * freq
    nper = int(round(periods))
    if abs(periods - nper) > 1e-9:
        raise FinanceError("years * freq must be a whole number of periods")
    r = (yield_pct / 100.0) / freq
    if r <= -1.0:
        raise FinanceError("per-period yield must exceed -100%")
    coupon = (coupon_pct / 100.0) * 100.0 / freq
    price = 0.0
    for t in range(1, nper + 1):
        price += coupon / (1.0 + r) ** t
    price += 100.0 / (1.0 + r) ** nper
    if not math.isfinite(price):
        raise FinanceError("non-finite bond price")
    return price


def bond_ytm(price: float, coupon_pct: float, years: float, freq: int = 2) -> float:
    """Yield to maturity (percent) for a bond trading at ``price`` per 100 face.

    Inverts :func:`bond_price` by bracketing a sign change in
    ``bond_price(y) - price`` and bisecting. Raises :class:`FinanceError` for a
    non-positive price or if no yield can be bracketed.
    """
    if price <= 0.0:
        raise FinanceError("price must be positive")
    if freq <= 0:
        raise FinanceError("freq must be positive")
    if years <= 0:
        raise FinanceError("years must be positive")

    def f(y: float) -> float:
        return bond_price(y, coupon_pct, years, freq) - price

    # Bond price falls monotonically as yield rises; scan upward for a bracket.
    lo, hi = -99.0, 1000.0
    steps = 2000
    prev_r = lo
    prev_v = f(prev_r)
    bracket: tuple[float, float] | None = None
    for k in range(1, steps + 1):
        r = lo + (hi - lo) * k / steps
        v = f(r)
        if v == 0.0:
            return r
        if (prev_v < 0.0) != (v < 0.0):
            bracket = (prev_r, r)
            break
        prev_r, prev_v = r, v
    if bracket is None:
        raise FinanceError("could not bracket a yield to maturity")

    a, b = bracket
    fa = f(a)
    for _ in range(200):
        m = 0.5 * (a + b)
        fm = f(m)
        if abs(fm) < 1e-10 or (b - a) < 1e-12:
            return m
        if (fa < 0.0) != (fm < 0.0):
            b = m
        else:
            a, fa = m, fm
    return 0.5 * (a + b)


# --- date-based (SIA) bonds ----------------------------------------------


def add_months(date: tuple[int, int, int], months: int) -> tuple[int, int, int]:
    """Shift a date by whole months, clamping the day to the month's last valid day
    (e.g. add_months((2020,1,31), 1) -> (2020,2,29)). Negative months go backward."""
    y, m, d = date
    # Validate the input as a real calendar date first.
    _to_date(date)
    total = (y * 12 + (m - 1)) + months
    ny, nm = divmod(total, 12)
    nm += 1
    # Clamp the day to the last valid day of the target month.
    if nm == 12:
        next_month_first = datetime.date(ny + 1, 1, 1)
    else:
        next_month_first = datetime.date(ny, nm + 1, 1)
    last_day = (next_month_first - datetime.timedelta(days=1)).day
    nd = d if d <= last_day else last_day
    return ny, nm, nd


def coupon_schedule(
    settlement: tuple[int, int, int],
    maturity: tuple[int, int, int],
    freq: int = 2,
) -> tuple[tuple[int, int, int], tuple[int, int, int], int]:
    """Return (prev_coupon, next_coupon, n_remaining) for a bond paying ``freq`` coupons/yr,
    coupons falling every 12//freq months counting BACK from maturity. prev_coupon is the
    coupon date on/just before settlement, next_coupon the one just after, n_remaining the
    count of coupons from next_coupon through maturity inclusive. FinanceError if settlement
    is not strictly before maturity or freq not in (1,2,4,6,12)."""
    if freq not in (1, 2, 4, 6, 12):
        raise FinanceError("freq must be one of 1, 2, 4, 6, 12")
    s = _to_date(settlement)
    mat = _to_date(maturity)
    if not s < mat:
        raise FinanceError("settlement must be strictly before maturity")
    step = 12 // freq
    # Walk coupon dates backward from maturity until we pass settlement.
    next_coupon = maturity
    k = 0  # number of steps back from maturity to next_coupon
    while True:
        prev_coupon = add_months(maturity, -step * (k + 1))
        pc_date = _to_date(prev_coupon)
        if pc_date <= s:
            break
        next_coupon = prev_coupon
        k += 1
    # next_coupon is k steps back from maturity, so coupons remaining = k + 1.
    n_remaining = k + 1
    return prev_coupon, next_coupon, n_remaining


def bond_price_dated(
    yield_pct: float,
    coupon_pct: float,
    settlement: tuple[int, int, int],
    maturity: tuple[int, int, int],
    *,
    freq: int = 2,
    basis: str = "30/360",
    redemption: float = 100.0,
) -> tuple[float, float]:
    """SIA bond price per ``redemption`` face, settling between coupon dates. Returns
    (clean_price, accrued_interest). ``basis`` in {"30/360","actual"} chooses the day-count
    (30/360 US, or actual/actual). Coupons are ``coupon_pct``% annual paid ``freq`` times/yr.
    FinanceError on bad basis/freq/dates."""
    if basis not in ("30/360", "actual"):
        raise FinanceError("basis must be '30/360' or 'actual'")
    pc, nc, N = coupon_schedule(settlement, maturity, freq)
    actual = basis == "actual"
    E = days_between(pc, nc, actual=actual)
    if E <= 0:
        raise FinanceError("degenerate coupon period")
    DSC = days_between(settlement, nc, actual=actual)
    A = days_between(pc, settlement, actual=actual)
    yf = yield_pct / 100.0 / freq
    if yf <= -1.0:
        raise FinanceError("per-period yield must exceed -100%")
    c = redemption * coupon_pct / 100.0 / freq
    t = DSC / E
    dirty = 0.0
    for k in range(1, N + 1):
        dirty += c / (1.0 + yf) ** (k - 1 + t)
    dirty += redemption / (1.0 + yf) ** (N - 1 + t)
    accrued = c * (A / E)
    clean = dirty - accrued
    if not (math.isfinite(clean) and math.isfinite(accrued)):
        raise FinanceError("non-finite bond price")
    return clean, accrued


def bond_ytm_dated(
    clean_price: float,
    coupon_pct: float,
    settlement: tuple[int, int, int],
    maturity: tuple[int, int, int],
    *,
    freq: int = 2,
    basis: str = "30/360",
    redemption: float = 100.0,
) -> float:
    """Annual yield-to-maturity % such that bond_price_dated(...) clean price == clean_price.
    Bracket then bisect (mirror the existing bond_ytm). FinanceError if no root in a sane range."""
    if clean_price <= 0.0:
        raise FinanceError("clean_price must be positive")

    def f(y: float) -> float:
        return bond_price_dated(
            y,
            coupon_pct,
            settlement,
            maturity,
            freq=freq,
            basis=basis,
            redemption=redemption,
        )[0] - clean_price

    # Clean price falls monotonically as yield rises; scan upward for a bracket.
    lo, hi = -99.0, 1000.0
    steps = 2000
    prev_r = lo
    prev_v = f(prev_r)
    bracket: tuple[float, float] | None = None
    for k in range(1, steps + 1):
        r = lo + (hi - lo) * k / steps
        v = f(r)
        if v == 0.0:
            return r
        if (prev_v < 0.0) != (v < 0.0):
            bracket = (prev_r, r)
            break
        prev_r, prev_v = r, v
    if bracket is None:
        raise FinanceError("could not bracket a yield to maturity")

    a, b = bracket
    fa = f(a)
    for _ in range(200):
        m = 0.5 * (a + b)
        fm = f(m)
        if abs(fm) < 1e-10 or (b - a) < 1e-12:
            return m
        if (fa < 0.0) != (fm < 0.0):
            b = m
        else:
            a, fa = m, fm
    return 0.5 * (a + b)


# --- depreciation --------------------------------------------------------


def _check_depr(cost: float, salvage: float, life: int, year: int) -> None:
    if life <= 0:
        raise FinanceError("life must be positive")
    if year < 1 or year > life:
        raise FinanceError("year must be in 1..life")
    if salvage > cost:
        raise FinanceError("salvage must not exceed cost")


def depreciation_sl(cost: float, salvage: float, life: int, year: int) -> float:
    """Straight-line depreciation for ``year`` (1-based): constant each period."""
    _check_depr(cost, salvage, life, year)
    return (cost - salvage) / life


def depreciation_soyd(cost: float, salvage: float, life: int, year: int) -> float:
    """Sum-of-years-digits depreciation for ``year`` (1-based).

    The depreciable base ``cost - salvage`` is allocated by the weight
    ``(life - year + 1) / (life * (life + 1) / 2)``.
    """
    _check_depr(cost, salvage, life, year)
    digits = life * (life + 1) / 2.0
    if digits == 0.0:
        raise FinanceError("degenerate sum-of-years digits")
    weight = (life - year + 1) / digits
    return (cost - salvage) * weight


def depreciation_db(
    cost: float, salvage: float, life: int, year: int, factor: float = 2.0
) -> float:
    """Declining-balance depreciation for ``year`` (1-based).

    The book value is reduced by ``factor / life`` each period and never falls
    below ``salvage``; the returned figure is the depreciation taken in ``year``.
    """
    _check_depr(cost, salvage, life, year)
    if factor <= 0.0:
        raise FinanceError("factor must be positive")
    rate = factor / life
    book = cost
    depr = 0.0
    for y in range(1, year + 1):
        depr = book * rate
        if book - depr < salvage:
            depr = book - salvage
        if depr < 0.0:
            depr = 0.0
        book -= depr
    return depr


# --- percents ------------------------------------------------------------


def percent(base: float, rate_pct: float) -> float:
    """``rate_pct`` percent of ``base`` (the 12C ``%`` key): ``base * rate / 100``."""
    return base * rate_pct / 100.0


def percent_change(old: float, new: float) -> float:
    """Percent change from ``old`` to ``new`` (the ``Delta%`` key).

    Raises :class:`FinanceError` when ``old`` is zero.
    """
    if old == 0.0:
        raise FinanceError("percent_change base (old) is zero")
    return (new - old) / old * 100.0


def percent_total(total: float, part: float) -> float:
    """``part`` as a percent of ``total`` (the ``%T`` key).

    Raises :class:`FinanceError` when ``total`` is zero.
    """
    if total == 0.0:
        raise FinanceError("percent_total base (total) is zero")
    return part / total * 100.0


def factorial(n: float) -> float:
    """``n!`` for a non-negative integer ``n`` (the ``n!`` key).

    Accepts a float that is integer-valued. Raises :class:`FinanceError` for a
    negative or non-integer argument.
    """
    if n < 0:
        raise FinanceError("factorial of a negative number")
    if abs(n - round(n)) > 1e-9:
        raise FinanceError("factorial of a non-integer")
    return float(math.factorial(int(round(n))))


# --- statistics accumulator ----------------------------------------------


class Stats:
    """The HP-12C Sigma+/Sigma- statistics registers and their summary stats.

    Accumulates the running sums ``n``, ``Sx``, ``Sx2``, ``Sy``, ``Sy2``,
    ``Sxy`` as paired ``(x, y)`` points are added or removed, then derives the
    means, sample standard deviations, the least-squares line (forecast), and
    the Pearson correlation. Removing a point that was never added simply runs
    the sums backward (as the real 12C does).
    """

    def __init__(self) -> None:
        self._n = 0
        self.Sx = 0.0
        self.Sx2 = 0.0
        self.Sy = 0.0
        self.Sy2 = 0.0
        self.Sxy = 0.0

    @property
    def n(self) -> int:
        return self._n

    def add(self, x: float, y: float = 0.0) -> int:
        """Add point ``(x, y)`` to the accumulator; return the new count ``n``."""
        self._n += 1
        self.Sx += x
        self.Sx2 += x * x
        self.Sy += y
        self.Sy2 += y * y
        self.Sxy += x * y
        return self._n

    def remove(self, x: float, y: float = 0.0) -> int:
        """Remove point ``(x, y)`` from the accumulator; return the new count.

        Raises :class:`FinanceError` if the count is already zero.
        """
        if self._n <= 0:
            raise FinanceError("no points to remove")
        self._n -= 1
        self.Sx -= x
        self.Sx2 -= x * x
        self.Sy -= y
        self.Sy2 -= y * y
        self.Sxy -= x * y
        return self._n

    def mean(self) -> tuple[float, float]:
        """The means ``(x̄, ȳ)``. Raises :class:`FinanceError` when empty."""
        if self._n == 0:
            raise FinanceError("mean of no points")
        return self.Sx / self._n, self.Sy / self._n

    def stdev(self) -> tuple[float, float]:
        """Sample standard deviations ``(sx, sy)`` (n-1 in the denominator).

        Raises :class:`FinanceError` with fewer than two points.
        """
        if self._n < 2:
            raise FinanceError("need at least two points for stdev")
        nf = float(self._n)
        var_x = (self.Sx2 - self.Sx * self.Sx / nf) / (nf - 1.0)
        var_y = (self.Sy2 - self.Sy * self.Sy / nf) / (nf - 1.0)
        # Guard tiny negatives from floating-point cancellation.
        sx = math.sqrt(var_x) if var_x > 0.0 else 0.0
        sy = math.sqrt(var_y) if var_y > 0.0 else 0.0
        return sx, sy

    def _slope_intercept(self) -> tuple[float, float]:
        if self._n < 2:
            raise FinanceError("need at least two points for a regression")
        nf = float(self._n)
        denom = self.Sx2 - self.Sx * self.Sx / nf
        if abs(denom) < 1e-300:
            raise FinanceError("x values have no spread")
        slope = (self.Sxy - self.Sx * self.Sy / nf) / denom
        intercept = (self.Sy - slope * self.Sx) / nf
        return slope, intercept

    def linear_estimate(self, x: float) -> float:
        """Forecast ``ŷ`` for ``x`` from the least-squares line through the data."""
        slope, intercept = self._slope_intercept()
        return slope * x + intercept

    def correlation(self) -> float:
        """Pearson correlation coefficient ``r``.

        Raises :class:`FinanceError` with fewer than two points or when either
        variable has no spread.
        """
        if self._n < 2:
            raise FinanceError("need at least two points for correlation")
        nf = float(self._n)
        sxx = self.Sx2 - self.Sx * self.Sx / nf
        syy = self.Sy2 - self.Sy * self.Sy / nf
        sxy = self.Sxy - self.Sx * self.Sy / nf
        denom = sxx * syy
        if denom <= 0.0:
            raise FinanceError("cannot compute correlation (no spread)")
        return sxy / math.sqrt(denom)


# --- calendar ------------------------------------------------------------


def _to_date(d: tuple[int, int, int]) -> datetime.date:
    try:
        return datetime.date(d[0], d[1], d[2])
    except (ValueError, TypeError) as exc:
        raise FinanceError(f"invalid date {d!r}: {exc}") from exc


def _days_360(d1: tuple[int, int, int], d2: tuple[int, int, int]) -> int:
    """30/360 (US/NASD) day count between two dates."""
    y1, m1, day1 = d1
    y2, m2, day2 = d2
    # Validate via real dates first.
    _to_date(d1)
    _to_date(d2)
    if day1 == 31:
        day1 = 30
    if day2 == 31 and day1 == 30:
        day2 = 30
    return (y2 - y1) * 360 + (m2 - m1) * 30 + (day2 - day1)


def days_between(
    d1: tuple[int, int, int], d2: tuple[int, int, int], actual: bool = True
) -> int:
    """Days from ``d1`` to ``d2`` (signed; positive when ``d2`` is later).

    With ``actual=True`` (the 12C ``DeltaDYS`` default) this is the proleptic
    Gregorian actual-day count via :meth:`datetime.date.toordinal`; with
    ``actual=False`` it is the 30/360 count. Raises :class:`FinanceError` for an
    invalid calendar date.
    """
    if actual:
        return _to_date(d2).toordinal() - _to_date(d1).toordinal()
    return _days_360(d1, d2)


def date_plus_days(d: tuple[int, int, int], days: int) -> tuple[int, int, int]:
    """The date ``days`` days after ``d`` (``days`` may be negative).

    Raises :class:`FinanceError` for an invalid input date or a result outside
    the supported date range.
    """
    base = _to_date(d)
    try:
        result = base + datetime.timedelta(days=days)
    except (OverflowError, OSError) as exc:
        raise FinanceError(f"date out of range: {exc}") from exc
    return result.year, result.month, result.day
