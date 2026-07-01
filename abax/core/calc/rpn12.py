"""HP-12C financial-calculator keypad logic — drives the float RPN engine.

Models the HP-12C Voyager (the *financial* member of the family) as a keypad
over :class:`abax.core.rpn.RPN`, mirroring the 15C keypad in
:mod:`abax.core.voyager` and the 16C keypad in :mod:`abax.core.rpn16`. This is
the pure-Python, testable half: it maps 12C button presses (with f/g shift) onto
float RPN operations, tracks live digit entry, and adds the five Time-Value-of-
Money (TVM) registers ``n``, ``i_pct``, ``PV``, ``PMT``, ``FV``.

The 12C reuses the same 4×10 Voyager button grid (:data:`BUTTONS` / :func:`grid_pos`
from :mod:`abax.core.voyager`); only the legends differ (:data:`LEGENDS_12C`).

TVM convention (end-of-period payments, the 12C default)::

    PV + PMT * (1 - (1 + r) ** -n) / r + FV * (1 + r) ** -n == 0,   r = i_pct / 100

with the HP cash-flow sign convention: money received is positive, money paid
out is negative. A TVM key (``n``/``i``/``PV``/``PMT``/``FV``) **stores** X into
its register when a number was just entered, otherwise **solves** for that
register from the other four and shows the result in X. Only the financial /
statistical legends beyond TVM are unimplemented (they set ``message`` rather
than raising).
"""

from __future__ import annotations

import datetime
import math

from .rpn import RPN, RPNError
from .voyager import BUTTONS, grid_pos


def parse_12c_date(value: float, mode: str = "MDY") -> tuple[int, int, int]:
    """Decode an HP-12C date keyed as ``MM.DDYYYY`` (M.DY mode) or ``DD.MMYYYY``
    (D.MY mode) into a ``(year, month, day)`` tuple. e.g. ``4.152024`` (M.DY) is
    15 April 2024; ``15.042024`` (D.MY) is the same date."""
    whole = int(value)
    digits = round((value - whole) * 1_000_000)
    tail, year = divmod(digits, 10000)
    if mode == "DMY":
        return (year, tail, whole)        # whole=day, tail=month
    return (year, whole, tail)            # whole=month, tail=day


def format_12c_date(d: tuple[int, int, int], mode: str = "MDY") -> float:
    """Encode ``(year, month, day)`` back to the HP-12C display float."""
    year, month, day = d
    lead, second = (day, month) if mode == "DMY" else (month, day)
    return lead + second / 100.0 + year / 1_000_000.0


def weekday_12c(d: tuple[int, int, int]) -> str:
    """The three-letter weekday for a date (the 12C shows 1=Mon..7=Sun)."""
    return datetime.date(d[0], d[1], d[2]).strftime("%a")

__all__ = [
    "LEGENDS_12C",
    "BUTTONS",
    "grid_pos",
    "Voyager12Keypad",
]

# Button number -> (primary, gold-f, blue-g) legend, HP-12C (the financial Voyager).
LEGENDS_12C: dict[int, tuple[str, str, str]] = {
    10: ('divide', '', ''), 11: ('n', 'AMORT', '12x'), 12: ('i', 'INT', '12div'),
    13: ('PV', 'NPV', 'CF0'), 14: ('PMT', 'RND', 'CFj'), 15: ('FV', 'IRR', 'Nj'),
    16: ('CHS', 'DATE', ''), 17: ('7', 'BEG', ''), 18: ('8', 'END', ''),
    19: ('9', 'MEM', ''), 20: ('multiply', '', ''), 21: ('y^x', 'BOND PRICE sqrt', ''),
    22: ('1/x', 'BOND YTM', 'e^x'), 23: ('%T', 'DEPR SL', 'LN'), 24: ('Delta%', 'DEPR SOYD', 'FRAC'),
    25: ('%', 'DEPR DB', 'INTG'), 26: ('EEX', 'DeltaDYS', ''), 27: ('4', 'D.MY', ''),
    28: ('5', 'M.DY', ''), 29: ('6', 'weighted avg', ''), 30: ('subtract', '', ''),
    31: ('R/S', 'P/R', 'PSE'), 32: ('SST', 'CL Sigma', 'BST'), 33: ('Rdn', 'CL PRGM', 'GTO'),
    34: ('x<>y', 'CL FIN', 'x<=y'), 35: ('CLx', 'CL REG', 'x=0'), 36: ('ENTER', 'CL PREFIX', 'LSTx'),
    37: ('1', 'lin est x', ''), 38: ('2', 'lin est y', ''), 39: ('3', 'n!', ''),
    40: ('add', '', ''), 41: ('ON', '', ''), 42: ('f', '', ''), 43: ('g', '', ''),
    44: ('STO', '', ''), 45: ('RCL', '', ''), 47: ('0', 'mean', ''),
    48: ('decimal', 'std dev', ''), 49: ('Sigma+', 'Sigma-', ''),
}

# Legend text -> RPN token understood by abax.core.rpn.RPN.
_TOKEN: dict[str, str] = {
    "divide": "/", "multiply": "*", "subtract": "-", "add": "+",
    "y^x": "^", "1/x": "inv", "e^x": "exp", "LN": "ln",
    "CHS": "chs", "Rdn": "rdn", "x<>y": "swap", "LSTx": "lastx",
    "n!": "fact", "FRAC": "frac", "INTG": "int", "%": "pct",
}
_DIGITS = set("0123456789")

# The five TVM registers, keyed by their primary legend.
_TVM_KEYS: tuple[str, ...] = ("n", "i", "PV", "PMT", "FV")


class Voyager12Keypad:
    """Stateful HP-12C keypad over an :class:`RPN` (live entry, f/g shift, TVM)."""

    def __init__(self, rpn: RPN | None = None) -> None:
        self.rpn = rpn if rpn is not None else RPN()
        self.entry = ""
        self.shift = ""  # "", "f", or "g"
        self.pending = ""  # "sto" / "rcl" awaiting a register digit
        self.message = ""
        # TVM registers. ``i`` is the per-period rate in percent, as entered.
        self.n = 0.0
        self.i_pct = 0.0
        self.PV = 0.0
        self.PMT = 0.0
        self.FV = 0.0
        # Whether X currently holds a freshly entered/typed number, which makes a
        # TVM key store (rather than solve).
        self._just_entered = False

    # --- queries ----------------------------------------------------------

    def display(self) -> str:
        if self.entry:
            return self.entry
        v = self.rpn.x
        return str(int(v)) if isinstance(v, float) and v.is_integer() else f"{v:.10g}"

    def label_for(self, number: int) -> str:
        """The active legend for a button given the current shift state."""
        primary, gold, blue = LEGENDS_12C.get(number, ("", "", ""))
        if self.shift == "f":
            return gold
        if self.shift == "g":
            return blue
        return primary

    # --- input ------------------------------------------------------------

    def press(self, number: int) -> None:
        self.message = ""
        primary, gold, blue = LEGENDS_12C.get(number, ("", "", ""))
        if primary == "f":
            self.shift = "" if self.shift == "f" else "f"
            return
        if primary == "g":
            self.shift = "" if self.shift == "g" else "g"
            return
        if primary == "ON":
            self.shift = ""
            return
        label = gold if self.shift == "f" else blue if self.shift == "g" else primary
        self.shift = ""
        self._apply(label)

    # --- entry helpers ----------------------------------------------------

    def _entry_valid(self) -> bool:
        return self.entry not in ("", "-", ".", "-.")

    def _commit_entry(self) -> None:
        if self._entry_valid():
            self.rpn.push(float(self.entry))
        self.entry = ""

    # --- dispatch ---------------------------------------------------------

    def _apply(self, label: str) -> None:
        # STO/RCL register digit consumption.
        if self.pending in ("sto", "rcl") and label in _DIGITS:
            reg = f"R{label}"
            if self.pending == "sto":
                self._commit_entry()
                self.rpn.regs[reg] = self.rpn.x
            else:
                self.rpn.push(self.rpn.regs.get(reg, 0.0))
                self._just_entered = True
            self.pending = ""
            return
        self.pending = ""

        if label in _DIGITS:
            self.entry += label
            self._just_entered = True
            return
        if label == "decimal":
            if "." not in self.entry:
                self.entry = (self.entry or "0") + "."
            self._just_entered = True
            return
        if label == "CHS":
            if self.entry:
                self.entry = self.entry[1:] if self.entry.startswith("-") else "-" + self.entry
            else:
                self._commit_entry()
                try:
                    self.rpn.feed("chs")
                except RPNError as exc:
                    self.message = str(exc)
            self._just_entered = True
            return
        if label == "ENTER":
            if self._entry_valid():
                self.rpn.push(float(self.entry))
                self.entry = ""
            else:
                self.rpn.push(self.rpn.x)
            self._just_entered = False
            return
        if label == "CLx":
            self.entry = ""
            self.rpn.feed("clx")
            self._just_entered = False
            return
        if label in ("STO", "RCL"):
            self._commit_entry()
            self.pending = label.lower()
            return
        if label in _TVM_KEYS:
            self._tvm(label)
            return
        if self._handle_financial(label):
            return
        if self._handle_advanced(label):
            return

        token = _TOKEN.get(label)
        if token is None:
            self.message = f"{label}: not implemented (try the financial module in the Python console)"
            return
        self._commit_entry()
        self._just_entered = False
        try:
            self.rpn.feed(token)
        except RPNError as exc:
            self.message = str(exc)

    # --- statistics / percent / factorial (via core.financial) ------------

    _FIN_LABELS = frozenset({
        "Sigma+", "Sigma-", "mean", "std dev", "lin est x", "lin est y",
        "n!", "%", "Delta%", "%T"})

    def _handle_financial(self, label: str) -> bool:
        if label not in self._FIN_LABELS:
            return False
        from ..science import financial as F

        if not hasattr(self, "stats"):
            self.stats = F.Stats()
        self._commit_entry()
        st = self.rpn.stack    # bind AFTER committing (push may rebind the list)
        try:
            if label == "Sigma+":
                self.rpn.push(float(self.stats.add(st[0], st[1])))
            elif label == "Sigma-":
                self.rpn.push(float(self.stats.remove(st[0], st[1])))
            elif label == "mean":
                self.rpn.push(self.stats.mean()[0])
            elif label == "std dev":
                self.rpn.push(self.stats.stdev()[0])
            elif label in ("lin est x", "lin est y"):
                st[0] = self.stats.linear_estimate(st[0])
            elif label == "n!":
                st[0] = F.factorial(st[0])
            elif label == "%":
                st[0] = F.percent(st[1], st[0])
            elif label == "Delta%":
                st[0] = F.percent_change(st[1], st[0])
            elif label == "%T":
                st[0] = F.percent_total(st[1], st[0])
        except F.FinanceError as exc:
            self.message = str(exc)
        self._just_entered = False
        return True

    # --- depreciation / cash-flow NPV·IRR / bond (via core.financial) -----

    _ADV_LABELS = frozenset({
        "DEPR SL", "DEPR SOYD", "DEPR DB", "CF0", "CFj", "Nj", "NPV", "IRR",
        "BOND PRICE sqrt", "BOND YTM", "DATE", "DeltaDYS", "D.MY", "M.DY"})

    def _handle_advanced(self, label: str) -> bool:
        if label not in self._ADV_LABELS:
            return False
        from ..science import financial as F

        if not hasattr(self, "date_mode"):
            self.date_mode = "MDY"          # HP-12C default date format
        if label in ("D.MY", "M.DY"):       # set the date-entry format (no stack change)
            self.date_mode = "DMY" if label == "D.MY" else "MDY"
            self.message = label
            return True
        if not hasattr(self, "cashflows"):
            self.cashflows = []
        self._commit_entry()
        st = self.rpn.stack
        x = self.rpn.x
        try:
            if label == "CF0":
                self.cashflows = [x]
            elif label == "CFj":
                self.cashflows.append(x)
            elif label == "Nj":
                if self.cashflows:
                    self.cashflows.extend([self.cashflows[-1]] * (int(x) - 1))
            elif label == "NPV":
                self.rpn.push(F.npv(self.i_pct, self.cashflows))
            elif label == "IRR":
                self.rpn.push(F.irr(self.cashflows))
            elif label.startswith("DEPR"):
                year = int(x)
                cost, salvage, life = self.PV, self.FV, self.n
                if label == "DEPR SL":
                    self.rpn.push(F.depreciation_sl(cost, salvage, life, year))
                elif label == "DEPR SOYD":
                    self.rpn.push(F.depreciation_soyd(cost, salvage, life, year))
                else:  # DEPR DB — declining-balance factor (%) lives in i
                    factor = self.i_pct / 100.0 if self.i_pct else 2.0
                    self.rpn.push(F.depreciation_db(cost, salvage, life, year, factor))
            elif label == "BOND PRICE sqrt":
                # yield in i, coupon in PMT; settlement in Y, maturity in X.
                settlement = parse_12c_date(st[1], self.date_mode)
                maturity = parse_12c_date(st[0], self.date_mode)
                price, accrued = F.bond_price_dated(
                    self.i_pct, self.PMT, settlement, maturity)
                st[1] = accrued      # accrued interest -> Y (press x<>y to read)
                st[0] = price        # clean price -> X (display)
            elif label == "BOND YTM":
                # price in PV, coupon in PMT; settlement in Y, maturity in X.
                settlement = parse_12c_date(st[1], self.date_mode)
                maturity = parse_12c_date(st[0], self.date_mode)
                st[0] = F.bond_ytm_dated(self.PV, self.PMT, settlement, maturity)
            elif label == "DeltaDYS":
                # date1 in Y, date2 in X -> actual days between (30/360 days into Y).
                d1 = parse_12c_date(st[1], self.date_mode)
                d2 = parse_12c_date(st[0], self.date_mode)
                st[1] = float(F.days_between(d1, d2, actual=False))
                st[0] = float(F.days_between(d1, d2, actual=True))
            elif label == "DATE":
                # date in Y, +days in X -> resulting date (+ weekday in the message).
                base = parse_12c_date(st[1], self.date_mode)
                result = F.date_plus_days(base, int(x))
                st[0] = format_12c_date(result, self.date_mode)
                self.message = weekday_12c(result)
        except (F.FinanceError, ValueError) as exc:
            self.message = str(exc)
        self._just_entered = False
        return True

    # --- TVM --------------------------------------------------------------

    def _tvm(self, key: str) -> None:
        """Store X into a TVM register, or solve for it from the other four."""
        if self._just_entered or self._entry_valid():
            # Store mode: commit the entry, then take X into the register.
            self._commit_entry()
            value = self.rpn.x
            self._set_tvm(key, value)
            self._just_entered = False
            return
        # Solve mode: compute this register from the other four; push to X.
        try:
            value = self._solve_tvm(key)
        except (ValueError, ZeroDivisionError, OverflowError):
            self.message = f"{key}: cannot solve"
            return
        self._set_tvm(key, value)
        self.rpn.push(value)
        self._just_entered = False

    def _set_tvm(self, key: str, value: float) -> None:
        if key == "n":
            self.n = value
        elif key == "i":
            self.i_pct = value
        elif key == "PV":
            self.PV = value
        elif key == "PMT":
            self.PMT = value
        elif key == "FV":
            self.FV = value

    def _solve_tvm(self, key: str) -> float:
        n, r, pv, pmt, fv = self.n, self.i_pct / 100.0, self.PV, self.PMT, self.FV
        if key == "PV":
            return _solve_pv(n, r, pmt, fv)
        if key == "FV":
            return _solve_fv(n, r, pv, pmt)
        if key == "PMT":
            return _solve_pmt(n, r, pv, fv)
        if key == "n":
            return _solve_n(r, pv, pmt, fv)
        if key == "i":
            return _solve_i(n, pv, pmt, fv) * 100.0
        raise ValueError(key)


# -- TVM closed forms / root finders --------------------------------------


def _annuity_factor(n: float, r: float) -> float:
    """The present-value annuity factor ``(1 - (1 + r) ** -n) / r`` (r→0 safe)."""
    if abs(r) < 1e-12:
        return n
    return (1.0 - (1.0 + r) ** (-n)) / r


def _residual(n: float, r: float, pv: float, pmt: float, fv: float) -> float:
    """The TVM equation residual; zero at a consistent set of values."""
    if abs(r) < 1e-12:
        return pv + pmt * n + fv
    disc = (1.0 + r) ** (-n)
    return pv + pmt * (1.0 - disc) / r + fv * disc


def _solve_pv(n: float, r: float, pmt: float, fv: float) -> float:
    disc = 1.0 if abs(r) < 1e-12 else (1.0 + r) ** (-n)
    return -(pmt * _annuity_factor(n, r) + fv * disc)


def _solve_fv(n: float, r: float, pv: float, pmt: float) -> float:
    if abs(r) < 1e-12:
        return -(pv + pmt * n)
    grow = (1.0 + r) ** n
    # FV = -[PV + PMT*(1-(1+r)^-n)/r] * (1+r)^n
    return -(pv + pmt * _annuity_factor(n, r)) * grow


def _solve_pmt(n: float, r: float, pv: float, fv: float) -> float:
    af = _annuity_factor(n, r)
    if abs(af) < 1e-300:
        raise ZeroDivisionError("degenerate annuity factor")
    disc = 1.0 if abs(r) < 1e-12 else (1.0 + r) ** (-n)
    return -(pv + fv * disc) / af


def _solve_n(r: float, pv: float, pmt: float, fv: float) -> float:
    if abs(r) < 1e-12:
        if abs(pmt) < 1e-300:
            raise ZeroDivisionError("cannot solve n")
        return -(pv + fv) / pmt
    # From PV + PMT*(1-(1+r)^-n)/r + FV*(1+r)^-n = 0, isolate (1+r)^-n.
    a = pmt / r
    num = a - pv
    den = a + fv
    if den == 0 or num / den <= 0:
        raise ValueError("no real n")
    disc = num / den  # = (1+r)^-n
    return -math.log(disc) / math.log(1.0 + r)


def _solve_i(n: float, pv: float, pmt: float, fv: float) -> float:
    """Solve for the per-period rate ``r`` by bisection on the residual."""
    f = lambda r: _residual(n, r, pv, pmt, fv)
    # Bracket a sign change scanning a wide range of plausible rates.
    lo, hi = -0.9999, 1.0
    flo = f(lo)
    bracket: tuple[float, float] | None = None
    steps = 2000
    prev_r, prev_v = lo, flo
    for k in range(1, steps + 1):
        r = lo + (hi - lo) * k / steps
        v = f(r)
        if v == 0.0:
            return r
        if (prev_v < 0) != (v < 0):
            bracket = (prev_r, r)
            break
        prev_r, prev_v = r, v
    if bracket is None:
        raise ValueError("no rate bracket")
    a, b = bracket
    fa = f(a)
    for _ in range(200):
        m = 0.5 * (a + b)
        fm = f(m)
        if abs(fm) < 1e-12 or (b - a) < 1e-15:
            return m
        if (fa < 0) != (fm < 0):
            b = m
        else:
            a, fa = m, fm
    return 0.5 * (a + b)
