"""A pure-Python HP-style RPN calculator engine (ROM-free, float scientific).

Models the HP-Voyager calculator (``qrpn``) as a stateless-free, float-only
scientific engine for use inside qcell. The stack is the classic four-level HP
stack labeled X, Y, Z, T, where X is the displayed value (``stack[0]``). New
numbers always lift the stack (automatic stack lift), so an interleaved entry
such as ``3 4 + 5 *`` evaluates to ``35.0``.

State serializes to / from the same ``{"stack": [...], "registers": {...}}``
dict that ``qrpn.stackio`` produces (stack ordered X, Y, Z, T; registers keyed
by name, e.g. ``"R0"``), with ``angle`` and ``last_x`` added so a calculation
can be round-tripped exactly. ``load_dict`` tolerates missing keys and a stack
list that is shorter or longer than four levels (it pads with 0.0 / truncates).

Tokens are case-insensitive and whitespace-separated; see :meth:`RPN.feed` for
the full vocabulary (binary ops, unary functions honoring the DEG/RAD angle
mode, stack manipulation, constants, mode switches, and ``sto``/``rcl``).
"""

from __future__ import annotations

import math


class RPNError(Exception):
    """Raised on any calculator error (bad token, domain error, divide by zero)."""


# Stack levels in serialized order. Index 0 is X (the displayed value).
STACK_LABELS: tuple[str, ...] = ("X", "Y", "Z", "T")


class RPN:
    """A four-level HP-style RPN stack with registers and an angle mode."""

    def __init__(self) -> None:
        self.stack: list[float] = [0.0, 0.0, 0.0, 0.0]  # index 0 = X, then Y, Z, T
        self.last_x: float = 0.0
        self.regs: dict[str, float] = {}
        self.angle: str = "DEG"  # or "RAD"

    # -- stack accessors ---------------------------------------------------

    @property
    def x(self) -> float:
        return self.stack[0]

    @property
    def y(self) -> float:
        return self.stack[1]

    @property
    def z(self) -> float:
        return self.stack[2]

    @property
    def t(self) -> float:
        return self.stack[3]

    # -- stack mechanics ---------------------------------------------------

    def push(self, value: float) -> None:
        """Lift the stack and drop ``value`` into X (T<-Z, Z<-Y, Y<-X, X=value)."""
        self.stack = [float(value), self.stack[0], self.stack[1], self.stack[2]]

    def enter(self) -> None:
        """Duplicate X upward (HP ENTER): T<-Z, Z<-Y, Y<-X, X unchanged."""
        self.push(self.stack[0])

    def _drop(self) -> None:
        """Drop the stack after a binary op: Y<-Z, Z<-T, T unchanged."""
        self.stack = [self.stack[0], self.stack[2], self.stack[3], self.stack[3]]

    # -- angle helpers -----------------------------------------------------

    def _to_radians(self, value: float) -> float:
        return math.radians(value) if self.angle == "DEG" else value

    def _from_radians(self, value: float) -> float:
        return math.degrees(value) if self.angle == "DEG" else value

    # -- token application -------------------------------------------------

    def feed(self, token: str) -> None:
        """Apply a single token (number, operator, function, or mode word).

        ``sto``/``rcl`` need a following register name and so are only fully
        handled by :meth:`eval_line`; the single-token forms ``sto0``..``sto9``
        and ``rcl0``..``rcl9`` are accepted here.
        """
        if token is None:
            raise RPNError("empty token")
        raw = token.strip()
        if not raw:
            raise RPNError("empty token")
        key = raw.lower()

        # A number always lifts the stack.
        number = _parse_number(raw)
        if number is not None:
            self.push(number)
            return

        handler = _UNARY.get(key)
        if handler is not None:
            self._apply_unary(handler)
            return

        if key in _BINARY:
            self._apply_binary(key)
            return

        if key in _STACK_OPS:
            _STACK_OPS[key](self)
            return

        if key in ("deg", "rad"):
            self.angle = key.upper()
            return

        # Single-token register forms: sto0..sto9 / rcl0..rcl9.
        if (key.startswith("sto") or key.startswith("rcl")) and key[3:].isdigit():
            name = _normalize_reg(key[3:])
            if key.startswith("sto"):
                self._sto(name)
            else:
                self._rcl(name)
            return

        raise RPNError(f"unknown token: {token!r}")

    def eval_line(self, line: str) -> float:
        """Evaluate whitespace-separated ``line`` token by token; return X.

        ``sto``/``rcl`` consume the following token as a register name (a bare
        digit ``n`` normalizes to ``Rn``).
        """
        tokens = line.split()
        i = 0
        while i < len(tokens):
            token = tokens[i]
            key = token.lower()
            if key in ("sto", "rcl"):
                if i + 1 >= len(tokens):
                    raise RPNError(f"{key} requires a register name")
                name = _normalize_reg(tokens[i + 1])
                if key == "sto":
                    self._sto(name)
                else:
                    self._rcl(name)
                i += 2
                continue
            self.feed(token)
            i += 1
        return self.stack[0]

    # -- operation implementations -----------------------------------------

    def _apply_binary(self, key: str) -> None:
        x = self.stack[0]
        y = self.stack[1]
        result = _BINARY[key](y, x)
        self._drop()
        self.stack[0] = result
        self.last_x = x

    def _apply_unary(self, func) -> None:
        x = self.stack[0]
        self.stack[0] = func(self, x)
        self.last_x = x

    def _sto(self, name: str) -> None:
        self.regs[name] = self.stack[0]

    def _rcl(self, name: str) -> None:
        self.push(self.regs.get(name, 0.0))

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize to ``{"stack": [X,Y,Z,T], "registers": {...}, ...}``."""
        return {
            "stack": list(self.stack),
            "registers": dict(self.regs),
            "angle": self.angle,
            "last_x": self.last_x,
        }

    def load_dict(self, d: dict) -> None:
        """Restore from a dict, tolerating missing keys and odd stack lengths."""
        stack = [float(v) for v in (d.get("stack") or [])]
        stack = (stack + [0.0, 0.0, 0.0, 0.0])[:4]
        self.stack = stack
        self.regs = {str(k): float(v) for k, v in (d.get("registers") or {}).items()}
        angle = str(d.get("angle", "DEG")).upper()
        self.angle = angle if angle in ("DEG", "RAD") else "DEG"
        self.last_x = float(d.get("last_x", 0.0))

    def reset(self) -> None:
        """Clear the stack, registers, last_x, and restore DEG mode."""
        self.stack = [0.0, 0.0, 0.0, 0.0]
        self.last_x = 0.0
        self.regs = {}
        self.angle = "DEG"


# -- token helpers ---------------------------------------------------------


def _parse_number(token: str) -> "float | None":
    """Parse ``token`` as a float (incl. ``1e3``, leading ``-``) or return None."""
    try:
        return float(token)
    except (ValueError, TypeError):
        return None


def _normalize_reg(name: str) -> str:
    """Normalize a register name: a bare digit ``n`` becomes ``Rn``."""
    name = name.strip()
    if name.isdigit():
        return f"R{name}"
    return name.upper()


def _safe_div(y: float, x: float) -> float:
    if x == 0.0:
        raise RPNError("division by zero")
    return y / x


_BINARY: dict[str, "callable"] = {
    "+": lambda y, x: y + x,
    "-": lambda y, x: y - x,
    "*": lambda y, x: y * x,
    "/": _safe_div,
    "^": lambda y, x: y ** x,
    "pow": lambda y, x: y ** x,
    "y^x": lambda y, x: y ** x,
    "mod": lambda y, x: math.fmod(y, x),
}


def _inv(self: RPN, x: float) -> float:
    if x == 0.0:
        raise RPNError("division by zero")
    return 1.0 / x


def _sqrt(self: RPN, x: float) -> float:
    if x < 0.0:
        raise RPNError("sqrt of negative")
    return math.sqrt(x)


def _ln(self: RPN, x: float) -> float:
    if x <= 0.0:
        raise RPNError("ln of non-positive")
    return math.log(x)


def _log10(self: RPN, x: float) -> float:
    if x <= 0.0:
        raise RPNError("log of non-positive")
    return math.log10(x)


def _fact(self: RPN, x: float) -> float:
    if x < 0.0 or x != int(x):
        raise RPNError("factorial requires a non-negative integer")
    return float(math.factorial(int(x)))


_UNARY: dict[str, "callable"] = {
    "chs": lambda self, x: -x,
    "neg": lambda self, x: -x,
    "inv": _inv,
    "1/x": _inv,
    "sqrt": _sqrt,
    "sq": lambda self, x: x * x,
    "x^2": lambda self, x: x * x,
    "ln": _ln,
    "log": _log10,
    "log10": _log10,
    "exp": lambda self, x: math.exp(x),
    "10^x": lambda self, x: 10.0 ** x,
    "abs": lambda self, x: abs(x),
    "int": lambda self, x: float(math.trunc(x)),
    "frac": lambda self, x: x - math.trunc(x),
    "fact": _fact,
    "!": _fact,
    "sin": lambda self, x: math.sin(self._to_radians(x)),
    "cos": lambda self, x: math.cos(self._to_radians(x)),
    "tan": lambda self, x: math.tan(self._to_radians(x)),
    "asin": lambda self, x: self._from_radians(math.asin(x)),
    "acos": lambda self, x: self._from_radians(math.acos(x)),
    "atan": lambda self, x: self._from_radians(math.atan(x)),
}


def _pct(self: RPN) -> None:
    """Y*X/100 in X, leaving Y unchanged; old X saved to last_x."""
    x = self.stack[0]
    self.stack[0] = self.stack[1] * x / 100.0
    self.last_x = x


def _swap(self: RPN) -> None:
    self.stack[0], self.stack[1] = self.stack[1], self.stack[0]


def _rdn(self: RPN) -> None:
    """Roll down: X<-Y, Y<-Z, Z<-T, T<-old X."""
    a, b, c, d = self.stack
    self.stack = [b, c, d, a]


def _rup(self: RPN) -> None:
    """Roll up: X<-T, Y<-X, Z<-Y, T<-Z."""
    a, b, c, d = self.stack
    self.stack = [d, a, b, c]


def _drop_op(self: RPN) -> None:
    """Drop X: Y<-Z, Z<-T, T unchanged."""
    self.last_x = self.stack[0]
    self.stack = [self.stack[1], self.stack[2], self.stack[3], self.stack[3]]


def _clst(self: RPN) -> None:
    self.stack = [0.0, 0.0, 0.0, 0.0]


_STACK_OPS: dict[str, "callable"] = {
    "swap": _swap,
    "x<>y": _swap,
    "rdn": _rdn,
    "rolldown": _rdn,
    "rup": _rup,
    "rollup": _rup,
    "drop": _drop_op,
    "clx": lambda self: self.stack.__setitem__(0, 0.0),
    "clst": _clst,
    "clear": _clst,
    "lastx": lambda self: self.push(self.last_x),
    "pi": lambda self: self.push(math.pi),
    "e": lambda self: self.push(math.e),
    "pct": _pct,
    "%": _pct,
}
