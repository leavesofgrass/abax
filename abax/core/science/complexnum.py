"""Complex-number support, Excel ``IM*``-style.

Complex values live as **strings** in the ``"a+bi"`` form (``"3+4i"``,
``"-2.5-1.5i"``, pure-real ``"5"``, pure-imaginary ``"2i"``). :func:`parse`
turns such a string — or a plain ``int``/``float``/``complex`` — into a Python
:class:`complex`, and :func:`fmt` turns a :class:`complex` back into the string
form, dropping zero parts and trailing ``.0`` so the result round-trips through
:func:`parse`. The ``im_*`` helpers mirror Excel's engineering functions: they
take and return the string form, delegating the arithmetic to :mod:`cmath`.
Pure stdlib → core.
"""

from __future__ import annotations

import cmath
import math
import re

__all__ = [
    "ComplexError",
    "parse",
    "fmt",
    "complexnum",
    "im_sum",
    "im_sub",
    "im_product",
    "im_div",
    "im_abs",
    "im_real",
    "im_imaginary",
    "im_conjugate",
    "im_argument",
    "im_sqrt",
    "im_exp",
    "im_ln",
    "im_power",
    "im_sin",
    "im_cos",
]


class ComplexError(Exception):
    """Raised when a value cannot be parsed as, or operated on as, a complex."""


# A signed real, optionally followed by a signed imaginary part with an i/j
# suffix; or a bare imaginary part. Spaces are tolerated and stripped first.
_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_FULL_RE = re.compile(
    rf"^(?P<real>{_NUM})(?P<imag>[-+](?:(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)?)[ij]$"
)
_IMAG_ONLY_RE = re.compile(r"^(?P<imag>[-+]?(?:(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)?)[ij]$")
_REAL_ONLY_RE = re.compile(rf"^(?P<real>{_NUM})$")


def parse(s: object) -> complex:
    """Parse *s* into a :class:`complex`.

    Accepts a string in ``"a+bi"`` / ``"a+bj"`` / ``"a"`` / ``"bi"`` form
    (spaces tolerated, ``"i"`` meaning ``1i`` and ``"-i"`` meaning ``-1i``), or
    a plain ``int``/``float``/``complex``. Raises :class:`ComplexError` on bad
    input.
    """
    if isinstance(s, bool):  # bool is an int subclass; reject to avoid surprises
        raise ComplexError(f"cannot parse {s!r} as complex")
    if isinstance(s, complex):
        return s
    if isinstance(s, (int, float)):
        return complex(s)
    if not isinstance(s, str):
        raise ComplexError(f"cannot parse {s!r} as complex")

    text = s.replace(" ", "")
    if not text:
        raise ComplexError("cannot parse empty string as complex")

    m = _FULL_RE.match(text)
    if m:
        real = float(m.group("real"))
        imag = _imag_token(m.group("imag"))
        return complex(real, imag)

    m = _IMAG_ONLY_RE.match(text)
    if m:
        return complex(0.0, _imag_token(m.group("imag")))

    m = _REAL_ONLY_RE.match(text)
    if m:
        return complex(float(m.group("real")), 0.0)

    raise ComplexError(f"cannot parse {s!r} as complex")


def _imag_token(tok: str) -> float:
    """Turn an imaginary coefficient token into a float (``""``/``"+"``->1)."""
    if tok in ("", "+"):
        return 1.0
    if tok == "-":
        return -1.0
    return float(tok)


def _trim(x: float) -> str:
    """Render a float without a trailing ``.0`` (and normalise ``-0``)."""
    if x == 0:
        x = 0.0  # collapse -0.0
    if x == int(x) and not math.isinf(x):
        return str(int(x))
    return repr(x)


def fmt(z: complex, suffix: str = "i") -> str:
    """Format *z* as ``"a+bi"``, dropping zero parts and trailing ``.0``.

    ``complex(3, 0)`` -> ``"3"``, ``complex(0, 2)`` -> ``"2i"``,
    ``complex(3, -4)`` -> ``"3-4i"``. The *suffix* (``"i"`` or ``"j"``) is used
    for the imaginary unit and the result round-trips through :func:`parse`.
    """
    z = complex(z)
    real, imag = z.real, z.imag

    if imag == 0:
        return _trim(real)
    if real == 0:
        if imag == 1:
            return suffix
        if imag == -1:
            return f"-{suffix}"
        return f"{_trim(imag)}{suffix}"

    sign = "+" if imag >= 0 else "-"
    mag = abs(imag)
    if mag == 1:
        coeff = ""
    else:
        coeff = _trim(mag)
    return f"{_trim(real)}{sign}{coeff}{suffix}"


# --- Excel-style IM* functions ---------------------------------------------


def complexnum(real: float, imag: float, suffix: str = "i") -> str:
    """Build a complex string from *real* and *imag* parts (COMPLEX/IMAGINARY)."""
    if suffix not in ("i", "j"):
        raise ComplexError(f"suffix must be 'i' or 'j', got {suffix!r}")
    return fmt(complex(real, imag), suffix)


def im_sum(*args: object) -> str:
    """Sum of all complex arguments (IMSUM)."""
    total = 0j
    for a in args:
        total += parse(a)
    return fmt(total)


def im_sub(a: object, b: object) -> str:
    """``a - b`` (IMSUB)."""
    return fmt(parse(a) - parse(b))


def im_product(*args: object) -> str:
    """Product of all complex arguments (IMPRODUCT)."""
    total = 1 + 0j
    for a in args:
        total *= parse(a)
    return fmt(total)


def im_div(a: object, b: object) -> str:
    """``a / b`` (IMDIV); :class:`ComplexError` on divide by zero."""
    za, zb = parse(a), parse(b)
    if zb == 0:
        raise ComplexError("division by zero")
    return fmt(za / zb)


def im_abs(a: object) -> float:
    """Modulus ``|a|`` (IMABS)."""
    return abs(parse(a))


def im_real(a: object) -> float:
    """Real part (IMREAL)."""
    return parse(a).real


def im_imaginary(a: object) -> float:
    """Imaginary part (IMAGINARY)."""
    return parse(a).imag


def im_conjugate(a: object) -> str:
    """Complex conjugate (IMCONJUGATE)."""
    return fmt(parse(a).conjugate())


def im_argument(a: object) -> float:
    """Argument (phase angle) in radians (IMARGUMENT)."""
    return cmath.phase(parse(a))


def im_sqrt(a: object) -> str:
    """Principal square root (IMSQRT)."""
    return fmt(cmath.sqrt(parse(a)))


def im_exp(a: object) -> str:
    """``e ** a`` (IMEXP)."""
    return fmt(cmath.exp(parse(a)))


def im_ln(a: object) -> str:
    """Natural logarithm (IMLN); :class:`ComplexError` on ``ln(0)``."""
    z = parse(a)
    if z == 0:
        raise ComplexError("ln(0) is undefined")
    return fmt(cmath.log(z))


def im_power(a: object, n: object) -> str:
    """``a ** n`` (IMPOWER); *n* may itself be complex."""
    return fmt(parse(a) ** parse(n))


def im_sin(a: object) -> str:
    """Sine (IMSIN)."""
    return fmt(cmath.sin(parse(a)))


def im_cos(a: object) -> str:
    """Cosine (IMCOS)."""
    return fmt(cmath.cos(parse(a)))
