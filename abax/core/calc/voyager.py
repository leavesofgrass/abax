"""HP-15C Voyager keypad logic — drives the ROM-free RPN engine.

Derived from the author's earlier calculator project: the functional key
legends and the 4×10 button grid. This module is the *pure-Python, testable*
half — it maps Voyager button presses (with f/g shift) onto :class:`abax.core.rpn.RPN`
operations and tracks live digit entry. The Qt vector faceplate (``gui/faceplate``)
is a thin drawing layer on top of this.
"""

from __future__ import annotations

from .rpn import RPN, RPNError

# Button number -> (primary, gold-f, blue-g) legend, HP-15C (the scientific Voyager).
LEGENDS_15C: dict[int, tuple[str, str, str]] = {
    10: ("divide", "SOLVE", "x<=y"), 11: ("sqrt", "A", "x^2"), 12: ("e^x", "B", "LN"),
    13: ("10^x", "C", "LOG"), 14: ("y^x", "D", "%"), 15: ("1/x", "E", "Delta%"),
    16: ("CHS", "MATRIX", "ABS"), 17: ("7", "FIX", "DEG"), 18: ("8", "SCI", "RAD"),
    19: ("9", "ENG", "GRD"), 20: ("multiply", "INTEGRATE", "x=0"), 21: ("SST", "LBL", "BST"),
    22: ("GTO", "HYP", "HYP-1"), 23: ("SIN", "DIM", "SIN-1"), 24: ("COS", "(i)", "COS-1"),
    25: ("TAN", "I", "TAN-1"), 26: ("EEX", "RESULT", "Pi"), 27: ("4", "x<>", "SF"),
    28: ("5", "DSE", "CF"), 29: ("6", "ISG", "F?"), 30: ("subtract", "Re<>Im", "TEST"),
    31: ("R/S", "PSE", "P/R"), 32: ("GSB", "CL Sigma", "RTN"), 33: ("Rdn", "CL PRGM", "Rup"),
    34: ("x<>y", "CL REG", "RND"), 35: ("backspace", "CL PREFIX", "CLx"),
    36: ("ENTER", "RAN#", "LSTx"), 37: ("1", "->R", "->P"), 38: ("2", "->H.MS", "->H"),
    39: ("3", "->RAD", "->DEG"), 40: ("add", "Py,x", "Cy,x"), 41: ("ON", "", ""),
    42: ("f", "", ""), 43: ("g", "", ""), 44: ("STO", "FRAC", "INT"),
    45: ("RCL", "USER", "MEM"), 47: ("0", "x!", "mean"), 48: ("decimal", "lin est,r", "std dev"),
    49: ("Sigma+", "L.R.", "Sigma-"),
}


def grid_pos(number: int) -> tuple[int, int]:
    """Voyager button number -> (row, col) in the 4×10 matrix (row 0 at top)."""
    row = number // 10 - 1
    col = (number % 10) - 1 if number % 10 else 9
    return row, col


BUTTONS: list[int] = sorted(LEGENDS_15C)

# Legend text -> RPN token understood by core.rpn.RPN.
_TOKEN = {
    "divide": "/", "multiply": "*", "subtract": "-", "add": "+",
    "sqrt": "sqrt", "e^x": "exp", "10^x": "10^x", "y^x": "^", "1/x": "inv",
    "x^2": "sq", "LN": "ln", "LOG": "log", "CHS": "chs",
    "SIN": "sin", "COS": "cos", "TAN": "tan",
    "SIN-1": "asin", "COS-1": "acos", "TAN-1": "atan",
    "Rdn": "rdn", "Rup": "rup", "x<>y": "swap", "Pi": "pi", "LSTx": "lastx",
    "%": "pct", "ABS": "abs", "INT": "int", "FRAC": "frac", "x!": "fact",
    "RND": "int", "DEG": "deg", "RAD": "rad", "GRD": "grd", "CLx": "clx",
    "Cy,x": "comb", "Py,x": "perm",
}
_DIGITS = set("0123456789")

# HYP / HYP-1 prefixes combine with SIN/COS/TAN for the hyperbolic family.
_HYP: dict[str, dict[str, str]] = {
    "f": {"SIN": "sinh", "COS": "cosh", "TAN": "tanh"},
    "g": {"SIN": "asinh", "COS": "acosh", "TAN": "atanh"},
}

# Keys that need program memory or a solver/matrix subsystem the immediate-mode
# keypad doesn't provide — reported distinctly from a genuinely unknown key.
_PROGRAM_KEYS: frozenset = frozenset({
    "SOLVE", "INTEGRATE", "MATRIX", "DIM", "RESULT", "GTO", "GSB", "LBL", "RTN",
    "SST", "BST", "R/S", "P/R", "PSE", "DSE", "ISG", "TEST", "SF", "CF",
    "F?", "USER", "MEM", "(i)", "I",
})

# HP-15C statistics keys (Σ+/Σ-/mean/std dev/L.R./lin est,r). These accumulate
# the same running sums as the 12C and delegate to :class:`science.financial.Stats`.
_STAT_LABELS: frozenset = frozenset({
    "Sigma+", "Sigma-", "mean", "std dev", "L.R.", "lin est,r",
})


class VoyagerKeypad:
    """Stateful HP-15C keypad over an :class:`RPN` (live entry + f/g shift)."""

    def __init__(self, rpn: RPN | None = None) -> None:
        self.rpn = rpn or RPN()
        self.entry = ""
        self.shift = ""  # "", "f", or "g"
        self.pending = ""  # "sto" / "rcl" awaiting a register digit
        self.hyp = ""  # "", "f" (HYP), or "g" (HYP-1) awaiting SIN/COS/TAN
        self.message = ""

    # --- queries ----------------------------------------------------------

    def display(self) -> str:
        if self.entry:
            return self.entry

        v = self.rpn.x
        return str(int(v)) if isinstance(v, float) and v.is_integer() else f"{v:.10g}"

    def label_for(self, number: int) -> tuple[str, str, str]:
        return LEGENDS_15C.get(number, ("", "", ""))

    # --- input ------------------------------------------------------------

    def press(self, number: int) -> None:
        self.message = ""
        primary, gold, blue = LEGENDS_15C.get(number, ("", "", ""))
        if primary == "f":
            self.shift = "" if self.shift == "f" else "f"
            return
        if primary == "g":
            self.shift = "" if self.shift == "g" else "g"
            return
        label = gold if self.shift == "f" else blue if self.shift == "g" else primary
        self.shift = ""
        self._apply(label)

    def _commit_entry(self) -> None:
        if self.entry not in ("", "-", ".", "-."):
            self.rpn.push(float(self.entry))
        self.entry = ""

    def _apply(self, label: str) -> None:
        if self.pending in ("sto", "rcl") and label in _DIGITS:
            reg = f"R{label}"
            if self.pending == "sto":
                self._commit_entry()
                self.rpn.regs[reg] = self.rpn.x
            else:
                self.rpn.push(self.rpn.regs.get(reg, 0.0))
            self.pending = ""
            return
        self.pending = ""
        if label in _DIGITS:
            self.entry += label
            return
        if label == "decimal":
            if "." not in self.entry:
                self.entry = (self.entry or "0") + "."
            return
        if label == "ENTER":
            if self.entry not in ("", "-", ".", "-."):
                self.rpn.push(float(self.entry))
                self.entry = ""
            else:
                self.rpn.push(self.rpn.x)
            return
        if label == "backspace":
            self.entry = self.entry[:-1] if self.entry else ""
            if not self.entry:
                self.rpn.feed("clx")
            return
        if label in ("STO", "RCL"):
            self._commit_entry()
            self.pending = label.lower()
            return
        # HYP / HYP-1 are prefixes: arm the hyperbolic mode, then the next
        # SIN/COS/TAN resolves to sinh/cosh/tanh (or the inverse).
        if label in ("HYP", "HYP-1"):
            self.hyp = "g" if label == "HYP-1" else "f"
            return
        if self.hyp and label in ("SIN", "COS", "TAN"):
            token = _HYP[self.hyp][label]
            self.hyp = ""
            self._commit_entry()
            try:
                self.rpn.feed(token)
            except RPNError as exc:
                self.message = str(exc)
            return
        self.hyp = ""

        if label in _STAT_LABELS:
            self._handle_stats(label)
            return

        token = _TOKEN.get(label)
        if token is None:
            if label in _PROGRAM_KEYS:
                self.message = f"{label}: needs program/solver memory (use the console)"
            else:
                self.message = f"{label}: not implemented"
            return
        self._commit_entry()
        try:
            self.rpn.feed(token)
        except RPNError as exc:
            self.message = str(exc)

    # --- statistics registers (via science.financial.Stats) ---------------

    def _handle_stats(self, label: str) -> None:
        """HP-15C Σ/statistics keys, delegating to the shared ``Stats`` sums.

        The 15C keeps the running sums n, Σx, Σy, Σx², Σy², Σxy (its R2–R7). A
        data point is (x = X register, y = Y register); ``Σ+`` accumulates it and
        ``Σ-`` removes it, both leaving n in X. ``mean`` returns x̄ (X) / ȳ (Y);
        ``std dev`` the sample sₓ (X) / s_y (Y); ``L.R.`` the y-intercept (X) and
        slope (Y); ``lin est,r`` the forecast ŷ (X) for the x in X and the
        correlation r (Y).
        """
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
                xbar, ybar = self.stats.mean()
                self.rpn.push(ybar)
                self.rpn.push(xbar)
            elif label == "std dev":
                sx, sy = self.stats.stdev()
                self.rpn.push(sy)
                self.rpn.push(sx)
            elif label == "L.R.":
                slope, intercept = self.stats.linear_regression()
                self.rpn.push(slope)
                self.rpn.push(intercept)
            elif label == "lin est,r":
                yhat = self.stats.linear_estimate(st[0])  # forecast from x in X
                r = self.stats.correlation()
                self.rpn.push(r)     # r -> X, ŷ (old x) drops to Y
                self.rpn.push(yhat)  # ŷ -> X, r -> Y
        except F.FinanceError as exc:
            self.message = str(exc)
