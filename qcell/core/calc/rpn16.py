"""A pure-Python HP-16C "programmer" integer RPN calculator engine.

Models the HP-16C Voyager as a ROM-free integer RPN engine for use inside
qcell. Like :mod:`qcell.core.rpn`, it has the classic four-level HP stack
labeled X, Y, Z, T (X is the displayed value, ``stack[0]``) with automatic
stack lift, so a number always lifts the stack.

Unlike the float engine, every value is an integer stored *unsigned* and
masked to ``word_size`` bits (two's-complement wrap). The current number
``base`` (16, 10, 8, or 2) controls how digits are parsed and how
:meth:`RPN16.display` formats X; when ``signed`` is set and the high bit of X
is set, the display shows the negative two's-complement value.

Tokens are case-insensitive and whitespace-separated; see :meth:`RPN16.feed`
for the full vocabulary (integer arithmetic, bitwise ops, single-bit shifts and
rotates, stack manipulation, base switches, ``wsize``, and ``sto``/``rcl``).

The :class:`Voyager16Keypad` maps HP-16C button presses (with f/g shift) onto
the engine, mirroring the 15C keypad in :mod:`qcell.core.voyager`.
"""

from __future__ import annotations


class RPN16Error(Exception):
    """Raised on any calculator error (bad token, divide by zero, bad base)."""


# Stack levels in serialized order. Index 0 is X (the displayed value).
STACK_LABELS: tuple[str, ...] = ("X", "Y", "Z", "T")

# Number base -> the single base letter shown after the value in display().
_BASE_LETTER: dict[int, str] = {16: "h", 10: "d", 8: "o", 2: "b"}

# Number base -> the keypad legend that selects it.
_BASE_NAMES: dict[str, int] = {"hex": 16, "dec": 10, "oct": 8, "bin": 2}


class RPN16:
    """A four-level HP-16C integer RPN stack (word size, base, registers)."""

    def __init__(self, word_size: int = 16, base: int = 16, signed: bool = True) -> None:
        self.stack: list[int] = [0, 0, 0, 0]  # index 0 = X, then Y, Z, T
        self.last_x: int = 0
        self.regs: dict[str, int] = {}
        self.word_size = word_size  # bits
        self.base = base  # 16, 10, 8, or 2
        self.signed = signed  # two's-complement interpretation for display

    # -- stack accessors ---------------------------------------------------

    @property
    def x(self) -> int:
        return self.stack[0]

    @property
    def y(self) -> int:
        return self.stack[1]

    @property
    def z(self) -> int:
        return self.stack[2]

    @property
    def t(self) -> int:
        return self.stack[3]

    # -- word-size helpers -------------------------------------------------

    def _mask(self) -> int:
        """The all-ones bit mask for the current word size."""
        return (1 << self.word_size) - 1

    def _wrap(self, v: int) -> int:
        """Mask ``v`` to ``word_size`` bits, storing it unsigned (0..2^w-1)."""
        return int(v) & self._mask()

    def _signed_value(self, v: int) -> int:
        """Interpret unsigned ``v`` as a two's-complement signed integer."""
        if self.signed and (v >> (self.word_size - 1)) & 1:
            return v - (1 << self.word_size)
        return v

    # -- stack mechanics ---------------------------------------------------

    def push(self, value: int) -> None:
        """Lift the stack and drop ``value`` into X (T<-Z, Z<-Y, Y<-X, X=value)."""
        self.stack = [self._wrap(value), self.stack[0], self.stack[1], self.stack[2]]

    def enter(self) -> None:
        """Duplicate X upward (HP ENTER): T<-Z, Z<-Y, Y<-X, X unchanged."""
        self.push(self.stack[0])

    def _drop(self) -> None:
        """Drop the stack after a binary op: Y<-Z, Z<-T, T unchanged."""
        self.stack = [self.stack[0], self.stack[2], self.stack[3], self.stack[3]]

    # -- token application -------------------------------------------------

    def feed(self, token: str) -> None:
        """Apply a single token (number, operator, op word, or mode word).

        ``sto``/``rcl`` need a following register name and so are only fully
        handled by :meth:`eval_line`; the single-token forms ``sto0``..``sto9``
        and ``rcl0``..``rcl9`` are accepted here.
        """
        if token is None:
            raise RPN16Error("empty token")
        raw = token.strip()
        if not raw:
            raise RPN16Error("empty token")
        key = raw.lower()

        # Operator/mode keywords take precedence over number parsing, because
        # words like "dec"/"bin"/"oct" are otherwise valid hexadecimal digits.
        if key in _BINARY:
            self._apply_binary(key)
            return

        if key in _UNARY:
            self._apply_unary(key)
            return

        if key in _STACK_OPS:
            _STACK_OPS[key](self)
            return

        if key in _BASE_NAMES:
            self.base = _BASE_NAMES[key]
            return

        # A digit string valid for the current base always lifts the stack.
        number = self._parse_number(raw)
        if number is not None:
            self.push(number)
            return

        # Single-token register forms: sto0..sto9 / rcl0..rcl9.
        if (key.startswith("sto") or key.startswith("rcl")) and key[3:].isdigit():
            name = _normalize_reg(key[3:])
            if key.startswith("sto"):
                self._sto(name)
            else:
                self._rcl(name)
            return

        raise RPN16Error(f"unknown token: {token!r}")

    def eval_line(self, line: str) -> int:
        """Evaluate whitespace-separated ``line`` token by token; return X.

        ``sto``/``rcl`` consume the following token as a register name (a bare
        digit ``n`` normalizes to ``Rn``); ``wsize`` consumes the following
        token as a decimal bit count.
        """
        tokens = line.split()
        i = 0
        while i < len(tokens):
            token = tokens[i]
            key = token.lower()
            if key in ("sto", "rcl"):
                if i + 1 >= len(tokens):
                    raise RPN16Error(f"{key} requires a register name")
                name = _normalize_reg(tokens[i + 1])
                if key == "sto":
                    self._sto(name)
                else:
                    self._rcl(name)
                i += 2
                continue
            if key == "wsize":
                if i + 1 >= len(tokens):
                    raise RPN16Error("wsize requires a bit count")
                self.set_word_size(int(tokens[i + 1], 10))
                i += 2
                continue
            self.feed(token)
            i += 1
        return self.stack[0]

    # -- operation implementations -----------------------------------------

    def _apply_binary(self, key: str) -> None:
        x = self.stack[0]
        y = self.stack[1]
        result = _BINARY[key](self, y, x)
        self._drop()
        self.stack[0] = self._wrap(result)
        self.last_x = x

    def _apply_unary(self, key: str) -> None:
        x = self.stack[0]
        self.stack[0] = self._wrap(_UNARY[key](self, x))
        self.last_x = x

    def _sto(self, name: str) -> None:
        self.regs[name] = self.stack[0]

    def _rcl(self, name: str) -> None:
        self.push(self.regs.get(name, 0))

    def set_word_size(self, bits: int) -> None:
        """Set the word size and re-mask every stack level to ``bits``."""
        if bits < 1:
            raise RPN16Error("word size must be at least 1 bit")
        self.word_size = int(bits)
        self.stack = [self._wrap(v) for v in self.stack]
        self.last_x = self._wrap(self.last_x)
        self.regs = {k: self._wrap(v) for k, v in self.regs.items()}

    # -- number parsing / formatting ---------------------------------------

    def _parse_number(self, token: str) -> "int | None":
        """Parse ``token`` as an integer in the current base, or return None."""
        digits = "0123456789abcdef"[: self.base]
        text = token.lower()
        sign = 1
        if text.startswith("-"):
            sign, text = -1, text[1:]
        if not text or any(ch not in digits for ch in text):
            return None
        return sign * int(text, self.base)

    def display(self) -> str:
        """Format X in the current base plus its base letter (e.g. ``"FF h"``)."""
        letter = _BASE_LETTER.get(self.base)
        if letter is None:
            raise RPN16Error(f"bad base: {self.base!r}")
        raw = self.stack[0]  # unsigned bit pattern
        if self.base == 10:
            # Decimal shows the signed two's-complement value with a sign.
            value = self._signed_value(raw)
            return f"{value} {letter}"
        # Hex/octal/binary show the raw two's-complement bit pattern.
        if self.base == 16:
            body = format(raw, "X")
        elif self.base == 8:
            body = format(raw, "o")
        else:  # base 2
            body = format(raw, "b")
        return f"{body} {letter}"

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize to ``{"stack": [X,Y,Z,T], "registers": {...}, ...}``."""
        return {
            "stack": list(self.stack),
            "registers": dict(self.regs),
            "word_size": self.word_size,
            "base": self.base,
            "signed": self.signed,
            "last_x": self.last_x,
        }

    def load_dict(self, d: dict) -> None:
        """Restore from a dict, tolerating missing keys and odd stack lengths."""
        self.word_size = int(d.get("word_size", 16))
        self.base = int(d.get("base", 16))
        self.signed = bool(d.get("signed", True))
        stack = [self._wrap(int(v)) for v in (d.get("stack") or [])]
        stack = (stack + [0, 0, 0, 0])[:4]
        self.stack = stack
        self.regs = {str(k): self._wrap(int(v)) for k, v in (d.get("registers") or {}).items()}
        self.last_x = self._wrap(int(d.get("last_x", 0)))

    def reset(self) -> None:
        """Clear the stack, registers, and last_x (word size/base preserved)."""
        self.stack = [0, 0, 0, 0]
        self.last_x = 0
        self.regs = {}


# -- token helpers ---------------------------------------------------------


def _normalize_reg(name: str) -> str:
    """Normalize a register name: a bare digit ``n`` becomes ``Rn``."""
    name = name.strip()
    if name.isdigit():
        return f"R{name}"
    return name.upper()


def _safe_div(self: RPN16, y: int, x: int) -> int:
    if x == 0:
        raise RPN16Error("division by zero")
    # Integer division on the signed interpretation, truncating toward zero.
    sy, sx = self._signed_value(y), self._signed_value(x)
    q = abs(sy) // abs(sx)
    return q if (sy < 0) == (sx < 0) else -q


_BINARY: dict[str, "callable"] = {
    "+": lambda self, y, x: self._signed_value(y) + self._signed_value(x),
    "-": lambda self, y, x: self._signed_value(y) - self._signed_value(x),
    "*": lambda self, y, x: self._signed_value(y) * self._signed_value(x),
    "/": _safe_div,
    "and": lambda self, y, x: y & x,
    "or": lambda self, y, x: y | x,
    "xor": lambda self, y, x: y ^ x,
}


def _shift_left(self: RPN16, x: int) -> int:
    return x << 1


def _shift_right(self: RPN16, x: int) -> int:
    return x >> 1  # logical: X is stored unsigned


def _rotate_left(self: RPN16, x: int) -> int:
    w = self.word_size
    top = (x >> (w - 1)) & 1
    return (x << 1) | top


def _rotate_right(self: RPN16, x: int) -> int:
    w = self.word_size
    bottom = x & 1
    return (x >> 1) | (bottom << (w - 1))


_UNARY: dict[str, "callable"] = {
    "chs": lambda self, x: -self._signed_value(x),
    "neg": lambda self, x: -self._signed_value(x),
    "not": lambda self, x: ~x,
    "sl": _shift_left,
    "sr": _shift_right,
    "rl": _rotate_left,
    "rr": _rotate_right,
}


def _swap(self: RPN16) -> None:
    self.stack[0], self.stack[1] = self.stack[1], self.stack[0]


def _rdn(self: RPN16) -> None:
    """Roll down: X<-Y, Y<-Z, Z<-T, T<-old X."""
    a, b, c, d = self.stack
    self.stack = [b, c, d, a]


def _rup(self: RPN16) -> None:
    """Roll up: X<-T, Y<-X, Z<-Y, T<-Z."""
    a, b, c, d = self.stack
    self.stack = [d, a, b, c]


_STACK_OPS: dict[str, "callable"] = {
    "swap": _swap,
    "x<>y": _swap,
    "rdn": _rdn,
    "rup": _rup,
    "clx": lambda self: self.stack.__setitem__(0, 0),
    "lastx": lambda self: self.push(self.last_x),
}


# -- HP-16C keypad ---------------------------------------------------------

# Button number -> (primary, gold-f, blue-g) legend, HP-16C (the programmer
# Voyager). The HP-16C primary / gold-f / blue-g legend table.
LEGENDS_16C: dict[int, tuple[str, str, str]] = {
    10: ('divide', 'XOR', 'DBL div'),
    11: ('A', 'SL', 'LJ'),
    12: ('B', 'SR', 'ASR'),
    13: ('C', 'RL', 'RLC'),
    14: ('D', 'RR', 'RRC'),
    15: ('E', 'RLn', 'RLCn'),
    16: ('F', 'RRn', 'RRCn'),
    17: ('7', 'MASKL', '#B'),
    18: ('8', 'MASKR', 'ABS'),
    19: ('9', 'RMD', 'DBLR'),
    20: ('multiply', 'AND', 'dbl mult'),
    21: ('GSB', 'x<>(i)', 'RTN'),
    22: ('GTO', 'x<>I', 'LBL'),
    23: ('HEX', 'SHOW HEX', 'DSZ'),
    24: ('DEC', 'SHOW DEC', 'ISZ'),
    25: ('OCT', 'SHOW OCT', 'sqrt'),
    26: ('BIN', 'SHOW BIN', '1/x'),
    27: ('4', 'SB', 'SF'),
    28: ('5', 'CB', 'CF'),
    29: ('6', 'B?', 'F?'),
    30: ('subtract', 'NOT', 'x>0'),
    31: ('R/S', '(i)', 'P/R'),
    32: ('SST', 'I', 'BST'),
    33: ('Rdn', 'CLR PRGM', 'Rup'),
    34: ('x<>y', 'CLR REG', 'PSE'),
    35: ('backspace', 'CLR PREFIX CLx', ''),
    36: ('ENTER', 'WINDOW', 'LSTx'),
    37: ('1', "1's comp", 'x<=y'),
    38: ('2', "2's comp", 'x<0'),
    39: ('3', 'UNSIGN', 'x>y'),
    40: ('add', 'OR', 'x=0'),
    41: ('ON', '', ''),
    42: ('f', '', ''),
    43: ('g', '', ''),
    44: ('STO', 'WSIZE', 'disp <'),
    45: ('RCL', 'FLOAT', 'disp >'),
    47: ('0', 'MEM', 'x/=y'),
    48: ('decimal', 'STATUS', 'x/=0'),
    49: ('CHS', 'EEX', 'x=y'),
}


def grid_pos(number: int) -> tuple[int, int]:
    """Voyager button number -> (row, col) in the 4×10 matrix (row 0 at top)."""
    row = number // 10 - 1
    col = (number % 10) - 1 if number % 10 else 9
    return row, col


BUTTONS: list[int] = sorted(LEGENDS_16C)

# Legend text -> RPN16 token understood by RPN16.feed.
_TOKEN: dict[str, str] = {
    "divide": "/", "multiply": "*", "subtract": "-", "add": "+",
    "XOR": "xor", "AND": "and", "OR": "or", "NOT": "not",
    "SL": "sl", "SR": "sr", "RL": "rl", "RR": "rr",
    "CHS": "chs", "Rdn": "rdn", "Rup": "rup", "x<>y": "swap", "LSTx": "lastx",
    "HEX": "hex", "DEC": "dec", "OCT": "oct", "BIN": "bin",
}
_HEX_DIGITS = set("0123456789ABCDEF")


class Voyager16Keypad:
    """Stateful HP-16C keypad over an :class:`RPN16` (live entry + f/g shift)."""

    def __init__(self, rpn: RPN16 | None = None) -> None:
        self.rpn = rpn or RPN16()
        self.entry = ""
        self.shift = ""  # "", "f", or "g"
        self.pending = ""  # "sto" / "rcl" awaiting a register digit
        self.message = ""

    # --- queries ----------------------------------------------------------

    def display(self) -> str:
        if self.entry:
            return self.entry
        return self.rpn.display()

    def label_for(self, number: int) -> tuple[str, str, str]:
        return LEGENDS_16C.get(number, ("", "", ""))

    # --- input ------------------------------------------------------------

    def press(self, number: int) -> None:
        self.message = ""
        primary, gold, blue = LEGENDS_16C.get(number, ("", "", ""))
        if primary == "f":
            self.shift = "" if self.shift == "f" else "f"
            return
        if primary == "g":
            self.shift = "" if self.shift == "g" else "g"
            return
        label = gold if self.shift == "f" else blue if self.shift == "g" else primary
        self.shift = ""
        self._apply(label)

    def _entry_valid(self) -> bool:
        return self.entry not in ("", "-")

    def _commit_entry(self) -> None:
        if self._entry_valid():
            self.rpn.push(int(self.entry, self.rpn.base))
        self.entry = ""

    def _apply(self, label: str) -> None:
        if self.pending in ("sto", "rcl") and label in _HEX_DIGITS:
            reg = f"R{label}"
            if self.pending == "sto":
                self._commit_entry()
                self.rpn.regs[reg] = self.rpn.x
            else:
                self.rpn.push(self.rpn.regs.get(reg, 0))
            self.pending = ""
            return
        self.pending = ""

        # Live digit entry: a digit legend valid for the current base.
        if label in _HEX_DIGITS:
            digits = "0123456789ABCDEF"[: self.rpn.base]
            if label not in digits:
                self.message = f"{label}: not valid in current base"
                return
            self.entry += label
            return
        if label == "ENTER":
            if self._entry_valid():
                self.rpn.push(int(self.entry, self.rpn.base))
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
        token = _TOKEN.get(label)
        if token is None:
            self.message = f"{label}: not implemented"
            return
        self._commit_entry()
        try:
            self.rpn.feed(token)
        except RPN16Error as exc:
            self.message = str(exc)
