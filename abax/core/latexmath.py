"""LaTeX → MathML / Unicode conversion for the equation editor.

Two outputs are offered. :func:`to_mathml` produces presentation MathML and
prefers **pandoc** (``pandoc -f markdown -t html --mathml``) for the full LaTeX
grammar, with a pure-Python :func:`_fallback_mathml` covering the common subset
so the editor still works without pandoc installed. :func:`to_unicode` is a
pandoc-free Unicode approximation used for live preview. Pure stdlib → core.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess


class LatexError(Exception):
    """Raised when a LaTeX snippet cannot be converted at all."""


# --- shared lookup tables ---------------------------------------------------

_SUPERSCRIPTS = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
    "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻", "(": "⁽", ")": "⁾", "n": "ⁿ",
}

_SUBSCRIPTS = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄",
    "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
    "+": "₊", "-": "₋", "(": "₍", ")": "₎",
}

# LaTeX control words → Unicode. Greek letters plus common symbols/operators.
_SYMBOLS = {
    "times": "×", "div": "÷", "cdot": "·", "pm": "±",
    "mp": "∓", "le": "≤", "leq": "≤", "ge": "≥",
    "geq": "≥", "ne": "≠", "neq": "≠", "approx": "≈",
    "infty": "∞", "sum": "∑", "int": "∫", "prod": "∏",
    "partial": "∂", "nabla": "∇", "to": "→", "rightarrow": "→",
    "leftarrow": "←", "Rightarrow": "⇒", "Leftarrow": "⇐",
    "leftrightarrow": "↔", "equiv": "≡", "propto": "∝",
    "in": "∈", "notin": "∉", "subset": "⊂", "supset": "⊃",
    "cup": "∪", "cap": "∩", "forall": "∀", "exists": "∃",
    # lowercase Greek
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ",
    "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ", "eta": "η",
    "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ",
    "omicron": "ο", "pi": "π", "varpi": "ϖ", "rho": "ρ",
    "varrho": "ϱ", "sigma": "σ", "varsigma": "ς", "tau": "τ",
    "upsilon": "υ", "phi": "φ", "varphi": "ϕ", "chi": "χ",
    "psi": "ψ", "omega": "ω",
    # uppercase Greek
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ",
    "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ",
    "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}

_MATH_NS = "http://www.w3.org/1998/Math/MathML"

# first <math ...>...</math> block in a string (DOTALL so it spans newlines)
_MATH_BLOCK = re.compile(r"<math\b.*?</math>", re.DOTALL)

# a LaTeX control word: backslash followed by letters
_CONTROL_WORD = re.compile(r"\\([A-Za-z]+)")


# --- pandoc detection / MathML ---------------------------------------------

def pandoc_available() -> bool:
    """True when a pandoc binary can be invoked, via ``$PANDOC`` or ``PATH``."""
    env = os.environ.get("PANDOC")
    if env and shutil.which(env):
        return True
    return shutil.which("pandoc") is not None


def _pandoc_binary() -> str:
    env = os.environ.get("PANDOC")
    if env and shutil.which(env):
        return env
    return shutil.which("pandoc") or "pandoc"


def to_mathml(latex: str) -> str:
    """Return presentation MathML (``<math ...>...</math>``) for *latex*.

    Uses pandoc when available; otherwise — or if pandoc fails for any reason —
    falls back to :func:`_fallback_mathml`. Always returns a string containing
    ``"<math"``. :class:`LatexError` is raised only when even the fallback
    cannot produce anything.
    """
    if pandoc_available():
        try:
            result = subprocess.run(
                [_pandoc_binary(), "-f", "markdown", "-t", "html", "--mathml"],
                input=f"${latex}$",
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                match = _MATH_BLOCK.search(result.stdout)
                if match:
                    return match.group(0)
        except (OSError, subprocess.SubprocessError):
            pass  # fall through to the pure-Python fallback
    return _fallback_mathml(latex)


# --- Unicode approximation --------------------------------------------------

def _script(text: str, table: dict[str, str], wrap: str) -> str:
    """Render *text* as a super/subscript. Single digits (etc.) use the
    Unicode combining-free script characters; anything else degrades to
    ``^(...)`` / ``_(...)`` form via *wrap* (``"^"`` or ``"_"``)."""
    if all(ch in table for ch in text) and text:
        return "".join(table[ch] for ch in text)
    return f"{wrap}({text})"


def _take_group(s: str, i: int) -> tuple[str, int]:
    """Read the argument starting at index *i*. ``{...}`` returns the brace
    body; otherwise a single character. Returns ``(content, next_index)``."""
    if i < len(s) and s[i] == "{":
        depth = 0
        j = i
        while j < len(s):
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
                if depth == 0:
                    return s[i + 1:j], j + 1
            j += 1
        return s[i + 1:], len(s)  # unbalanced: take the rest
    if i < len(s):
        return s[i], i + 1
    return "", i


def to_unicode(latex: str) -> str:
    """A pandoc-free Unicode approximation of *latex* for live preview."""
    # control words → symbols first (so \pi etc. survive sup/subscript scans)
    def _sym(m: re.Match[str]) -> str:
        name = m.group(1)
        return _SYMBOLS.get(name, m.group(0))

    s = _CONTROL_WORD.sub(_sym, latex)

    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "\\":
            # \frac{a}{b} and \sqrt{x}; other commands strip their backslash
            m = _CONTROL_WORD.match(s, i)
            if m:
                name = m.group(1)
                j = m.end()
                if name == "frac":
                    num, j = _take_group(s, j)
                    den, j = _take_group(s, j)
                    out.append(f"({to_unicode(num)})/({to_unicode(den)})")
                    i = j
                    continue
                if name == "sqrt":
                    rad, j = _take_group(s, j)
                    out.append(f"√({to_unicode(rad)})")
                    i = j
                    continue
                out.append(name)  # unknown command: keep the bare word
                i = j
                continue
            out.append(ch)
            i += 1
        elif ch == "^":
            arg, j = _take_group(s, i + 1)
            out.append(_script(to_unicode(arg), _SUPERSCRIPTS, "^"))
            i = j
        elif ch == "_":
            arg, j = _take_group(s, i + 1)
            out.append(_script(to_unicode(arg), _SUBSCRIPTS, "_"))
            i = j
        elif ch in "{}":
            i += 1  # strip remaining braces
        else:
            out.append(ch)
            i += 1
    return "".join(out)


# --- pure-Python fallback MathML -------------------------------------------

def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _atom_mathml(token: str) -> str:
    """Wrap a single token as ``<mn>`` (number), ``<mo>`` (operator) or
    ``<mi>`` (identifier)."""
    sym = _SYMBOLS.get(token.lstrip("\\")) if token.startswith("\\") else None
    if sym is not None:
        return f"<mo>{_escape(sym)}</mo>"
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", token):
        return f"<mn>{_escape(token)}</mn>"
    if re.fullmatch(r"[+\-*/=<>(),.|]", token):
        return f"<mo>{_escape(token)}</mo>"
    return f"<mi>{_escape(token)}</mi>"


def _row_mathml(latex: str) -> str:
    """Convert the common subset of *latex* into a sequence of MathML nodes."""
    out: list[str] = []
    i = 0
    n = len(latex)
    while i < n:
        ch = latex[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "\\":
            m = _CONTROL_WORD.match(latex, i)
            if m:
                name = m.group(1)
                j = m.end()
                if name == "frac":
                    num, j = _take_group(latex, j)
                    den, j = _take_group(latex, j)
                    out.append(
                        f"<mfrac>{_wrap_row(num)}{_wrap_row(den)}</mfrac>"
                    )
                    i = j
                    continue
                if name == "sqrt":
                    rad, j = _take_group(latex, j)
                    out.append(f"<msqrt>{_row_mathml(rad)}</msqrt>")
                    i = j
                    continue
                out.append(_atom_mathml("\\" + name))
                i = j
                continue
            i += 1
            continue
        if ch in "^_":
            # base is the previous emitted node; combine into msup/msub
            base = out.pop() if out else "<mrow></mrow>"
            arg, j = _take_group(latex, i + 1)
            tag = "msup" if ch == "^" else "msub"
            out.append(f"<{tag}>{base}{_wrap_row(arg)}</{tag}>")
            i = j
            continue
        if ch in "{}":
            i += 1
            continue
        out.append(_atom_mathml(ch))
        i += 1
    return "".join(out)


def _wrap_row(latex: str) -> str:
    """Render a sub-expression, wrapping in ``<mrow>`` when it has multiple
    nodes so super/subscript bases stay well-formed."""
    inner = _row_mathml(latex)
    # crude node count: an mrow is needed when more than one top-level element
    if inner.count("<") > 2 and not inner.startswith("<mrow>"):
        return f"<mrow>{inner}</mrow>"
    return inner or "<mrow></mrow>"


def _fallback_mathml(latex: str) -> str:
    """Minimal presentation MathML for the common LaTeX subset.

    Best-effort: handles ``^``/``_`` (msup/msub), ``\\frac`` (mfrac),
    ``\\sqrt`` (msqrt), identifiers (mi), numbers (mn) and operators (mo).
    """
    body = _row_mathml(latex)
    return f'<math xmlns="{_MATH_NS}"><mrow>{body}</mrow></math>'
