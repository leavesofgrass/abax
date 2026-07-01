"""Algebraic (infix) scientific calculator engine for abax (pure-stdlib).

A standard non-RPN calculator: an expression is built up as a string and
evaluated on demand, in contrast to ``core/rpn.py`` (the HP-style RPN engine).

Two layers:

* :func:`evaluate` — a pure function that parses and evaluates an infix
  expression string. It tokenizes the input, converts it to RPN via the
  shunting-yard algorithm, then evaluates that RPN. It never calls ``eval`` on
  the raw string; only names in :data:`SAFE_FUNCTIONS` / :data:`SAFE_CONSTS`
  (plus ``Ans`` and ``M``) resolve, so no attribute access or arbitrary names
  are reachable.
* :class:`AlgebraicCalc` — a stateful calculator an algebraic faceplate (GUI /
  TUI) drives: :meth:`~AlgebraicCalc.input` appends tokens, :meth:`equals`
  evaluates, and a small memory register (``M``) plus a last-answer register
  (``Ans``) are maintained.

Operators: ``+ - * / ^`` (and ``**``), ``%`` (modulo), unary ``-``/``+``, and
parentheses. ``^`` is power and right-associative. Trig honors a degree mode
when requested. ``Ans`` resolves to the last answer and ``M`` to the memory
register.

Percent semantics: ``%`` is the binary modulo operator (``10 % 3 == 1``). A
trailing ``%`` after a value as the *percent of a number* shorthand is NOT
supported — ``%`` always means modulo here.
"""

from __future__ import annotations

import math
from typing import Callable


class AlgebraicError(Exception):
    """Raised on any syntax error, unknown name, or domain error."""


def _factorial(x: float) -> float:
    """Factorial for non-negative integers (tolerating float inputs like ``5.0``)."""
    n = int(x)
    if n < 0 or n != x:
        raise AlgebraicError(f"fact() needs a non-negative integer, got {x!r}")
    return float(math.factorial(n))


# name -> callable. One-argument numeric functions exposed to expressions.
SAFE_FUNCTIONS: dict[str, Callable[[float], float]] = {
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "sinh": math.sinh,
    "cosh": math.cosh,
    "tanh": math.tanh,
    "ln": math.log,
    "log": math.log10,
    "log2": math.log2,
    "sqrt": math.sqrt,
    "cbrt": lambda v: math.copysign(abs(v) ** (1.0 / 3.0), v),
    "exp": math.exp,
    "abs": abs,
    "floor": lambda v: float(math.floor(v)),
    "ceil": lambda v: float(math.ceil(v)),
    "round": lambda v: float(round(v)),
    "fact": _factorial,
}

# name -> constant value, resolved as bare identifiers in an expression.
SAFE_CONSTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}

# Trig functions that take an angle (degree-wrapped when in degree mode).
_ANGLE_IN = {"sin", "cos", "tan"}
# Inverse trig functions that return an angle (degree-wrapped in degree mode).
_ANGLE_OUT = {"asin", "acos", "atan"}


# -- tokenizer ------------------------------------------------------------

# Token kinds: ("num", float), ("name", str), ("op", str), ("lparen", "("),
# ("rparen", ")").
Token = tuple[str, "float | str"]

_OPERATORS = {"+", "-", "*", "/", "^", "%"}


def _tokenize(expr: str) -> list[Token]:
    """Split ``expr`` into number / name / operator / paren tokens.

    Numbers may include a decimal point and an exponent (``1.5e3``, ``2E-4``).
    ``**`` collapses to the single ``^`` power operator. Raises
    :class:`AlgebraicError` on an unrecognized character.
    """
    tokens: list[Token] = []
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isdigit() or ch == ".":
            j = i
            seen_dot = False
            seen_exp = False
            while j < n:
                c = expr[j]
                if c.isdigit():
                    j += 1
                elif c == "." and not seen_dot and not seen_exp:
                    seen_dot = True
                    j += 1
                elif c in "eE" and not seen_exp and j > i:
                    seen_exp = True
                    j += 1
                    if j < n and expr[j] in "+-":
                        j += 1
                else:
                    break
            text = expr[i:j]
            try:
                value = float(text)
            except ValueError as exc:
                raise AlgebraicError(f"bad number {text!r}") from exc
            tokens.append(("num", value))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (expr[j].isalnum() or expr[j] == "_"):
                j += 1
            tokens.append(("name", expr[i:j]))
            i = j
            continue
        if ch == "*" and i + 1 < n and expr[i + 1] == "*":
            tokens.append(("op", "^"))
            i += 2
            continue
        if ch in _OPERATORS:
            tokens.append(("op", ch))
            i += 1
            continue
        if ch == "(":
            tokens.append(("lparen", "("))
            i += 1
            continue
        if ch == ")":
            tokens.append(("rparen", ")"))
            i += 1
            continue
        raise AlgebraicError(f"unexpected character {ch!r} in {expr!r}")
    return tokens


# -- shunting-yard --------------------------------------------------------

# Binary operator precedence; higher binds tighter. Unary minus is handled
# separately (see ``u-`` / ``u+`` below).
_BINARY_PREC = {
    "+": 1,
    "-": 1,
    "*": 2,
    "/": 2,
    "%": 2,
    "^": 4,
}
_RIGHT_ASSOC = {"^"}
# Unary operators bind tighter than ``*``/``/`` but looser than ``^`` so that
# ``-2^2`` parses as ``-(2^2) == -4`` (matching Python / most calculators).
_UNARY_PREC = 3


def _to_rpn(tokens: list[Token]) -> list[Token]:
    """Convert a token list to RPN via shunting-yard.

    Distinguishes unary ``-``/``+`` (emitted as ``u-`` / ``u+``) from binary
    operators by tracking whether a value may begin here. Function names are
    pushed as operators when followed by ``(``; bare names are constants/values.
    Raises :class:`AlgebraicError` on mismatched parens.
    """
    output: list[Token] = []
    stack: list[Token] = []
    # ``expect_value`` is True when the next token should start an operand
    # (i.e. at the start, after an operator, or after a ``(``); a ``-``/``+``
    # in that position is unary.
    expect_value = True

    for idx, (kind, val) in enumerate(tokens):
        if kind == "num":
            output.append((kind, val))
            expect_value = False
        elif kind == "name":
            name = str(val)
            is_func = idx + 1 < len(tokens) and tokens[idx + 1][0] == "lparen"
            if is_func:
                stack.append(("func", name))
                expect_value = True
            else:
                output.append(("name", name))
                expect_value = False
        elif kind == "op":
            op = str(val)
            if expect_value and op in ("+", "-"):
                # Unary operator.
                u = "u" + op
                # Unary is right-associative; only pop other unaries / higher.
                while stack and stack[-1][0] == "op":
                    top = str(stack[-1][1])
                    top_prec = _UNARY_PREC if top in ("u-", "u+") else _BINARY_PREC[top]
                    if top_prec > _UNARY_PREC:
                        output.append(stack.pop())
                    else:
                        break
                stack.append(("op", u))
                expect_value = True
            else:
                if expect_value:
                    raise AlgebraicError(f"unexpected operator {op!r}")
                prec = _BINARY_PREC[op]
                while stack and stack[-1][0] == "op":
                    top = str(stack[-1][1])
                    top_prec = _UNARY_PREC if top in ("u-", "u+") else _BINARY_PREC[top]
                    if top_prec > prec or (
                        top_prec == prec and op not in _RIGHT_ASSOC
                    ):
                        output.append(stack.pop())
                    else:
                        break
                stack.append(("op", op))
                expect_value = True
        elif kind == "lparen":
            stack.append(("lparen", "("))
            expect_value = True
        elif kind == "rparen":
            while stack and stack[-1][0] != "lparen":
                output.append(stack.pop())
            if not stack:
                raise AlgebraicError("mismatched parentheses")
            stack.pop()  # discard the lparen
            if stack and stack[-1][0] == "func":
                output.append(stack.pop())
            expect_value = False
        else:  # pragma: no cover - defensive
            raise AlgebraicError(f"bad token {kind!r}")

    while stack:
        top = stack.pop()
        if top[0] in ("lparen", "rparen"):
            raise AlgebraicError("mismatched parentheses")
        output.append(top)
    return output


# -- RPN evaluation -------------------------------------------------------


def _eval_rpn(
    rpn: list[Token],
    *,
    degrees: bool,
    ans: float,
    memory: float,
) -> float:
    """Evaluate an RPN token list to a single float."""
    stack: list[float] = []

    def call_func(name: str, arg: float) -> float:
        fn = SAFE_FUNCTIONS.get(name)
        if fn is None:
            raise AlgebraicError(f"unknown function {name!r}")
        if degrees and name in _ANGLE_IN:
            arg = math.radians(arg)
        try:
            result = float(fn(arg))
        except (ValueError, ZeroDivisionError, OverflowError, ArithmeticError) as exc:
            raise AlgebraicError(f"{name}() domain error: {exc}") from exc
        if degrees and name in _ANGLE_OUT:
            result = math.degrees(result)
        return result

    for kind, val in rpn:
        if kind == "num":
            stack.append(float(val))  # type: ignore[arg-type]
        elif kind == "name":
            name = str(val)
            if name in SAFE_CONSTS:
                stack.append(SAFE_CONSTS[name])
            elif name == "Ans":
                stack.append(ans)
            elif name == "M":
                stack.append(memory)
            else:
                raise AlgebraicError(f"unknown name {name!r}")
        elif kind == "func":
            if not stack:
                raise AlgebraicError("missing function argument")
            stack.append(call_func(str(val), stack.pop()))
        elif kind == "op":
            op = str(val)
            if op in ("u-", "u+"):
                if not stack:
                    raise AlgebraicError("missing operand for unary operator")
                a = stack.pop()
                stack.append(-a if op == "u-" else a)
                continue
            if len(stack) < 2:
                raise AlgebraicError(f"missing operand for {op!r}")
            b = stack.pop()
            a = stack.pop()
            try:
                if op == "+":
                    stack.append(a + b)
                elif op == "-":
                    stack.append(a - b)
                elif op == "*":
                    stack.append(a * b)
                elif op == "/":
                    stack.append(a / b)
                elif op == "%":
                    stack.append(math.fmod(a, b))
                elif op == "^":
                    stack.append(a ** b)
                else:  # pragma: no cover - defensive
                    raise AlgebraicError(f"unknown operator {op!r}")
            except ZeroDivisionError as exc:
                raise AlgebraicError("division by zero") from exc
            except (ValueError, OverflowError, ArithmeticError) as exc:
                raise AlgebraicError(f"arithmetic error: {exc}") from exc
        else:  # pragma: no cover - defensive
            raise AlgebraicError(f"bad token {kind!r}")

    if len(stack) != 1:
        raise AlgebraicError("malformed expression")
    result = stack[0]
    if isinstance(result, complex) or not math.isfinite(result):
        raise AlgebraicError("non-finite result")
    return result


def evaluate(
    expr: str,
    *,
    degrees: bool = False,
    ans: float = 0.0,
    memory: float = 0.0,
) -> float:
    """Evaluate an infix expression ``expr`` to a float.

    Supports ``+ - * / ^`` (and ``**``), ``%`` (modulo), unary ``-``/``+``,
    parentheses, the constants in :data:`SAFE_CONSTS`, the functions in
    :data:`SAFE_FUNCTIONS`, and the symbols ``Ans`` (resolving to ``ans``) and
    ``M`` (resolving to ``memory``). ``^`` is power and right-associative.

    When ``degrees`` is True, ``sin``/``cos``/``tan`` take degrees and
    ``asin``/``acos``/``atan`` return degrees.

    Raises :class:`AlgebraicError` on a syntax error, an unknown name, or a
    domain / arithmetic error. Never calls ``eval`` on the raw string.
    """
    if not expr or not expr.strip():
        raise AlgebraicError("empty expression")
    tokens = _tokenize(expr)
    if not tokens:
        raise AlgebraicError("empty expression")
    rpn = _to_rpn(tokens)
    return _eval_rpn(rpn, degrees=degrees, ans=ans, memory=memory)


# -- stateful calculator --------------------------------------------------


def _format(value: float) -> str:
    """Render ``value`` as a compact string (integers without a trailing .0)."""
    if math.isfinite(value) and value == int(value) and abs(value) < 1e16:
        return str(int(value))
    return repr(value)


class AlgebraicCalc:
    """A stateful infix calculator driven by an algebraic faceplate.

    Tokens are appended to an expression string via :meth:`input`; :meth:`equals`
    evaluates it, updating the displayed result and the ``Ans`` register. A
    memory register ``M`` is maintained via the ``memory_*`` methods.
    """

    def __init__(self, degrees: bool = False) -> None:
        self._expr: str = ""
        self._result: str | None = None  # last evaluated display, or None
        self._ans: float = 0.0
        self._memory: float = 0.0
        self._degrees: bool = bool(degrees)

    # -- read-only state ---------------------------------------------------

    @property
    def expression(self) -> str:
        """The current input expression string."""
        return self._expr

    @property
    def display(self) -> str:
        """The last result (after :meth:`equals`), else the expression or ``"0"``."""
        if self._result is not None:
            return self._result
        return self._expr if self._expr else "0"

    @property
    def ans(self) -> float:
        """The last successfully evaluated answer."""
        return self._ans

    @property
    def memory(self) -> float:
        """The value of the memory register ``M``."""
        return self._memory

    @property
    def degrees(self) -> bool:
        """Whether trig functions operate in degree mode."""
        return self._degrees

    # -- configuration -----------------------------------------------------

    def set_degrees(self, on: bool) -> None:
        """Set degree mode (True) or radian mode (False)."""
        self._degrees = bool(on)

    # -- input -------------------------------------------------------------

    def input(self, token: str) -> None:
        """Append ``token`` to the expression.

        ``token`` is any input chunk: a digit, ``"."``, an operator, ``"("``, a
        function-with-paren like ``"sin("``, or a name like ``"pi"``/``"Ans"``.
        If a result is currently shown, a digit / function / value-like token
        starts a fresh expression while an operator continues from the result.
        """
        if not token:
            return
        if self._result is not None:
            first = token[0]
            if first in "+-*/^%)":
                # Continue working with the previous answer.
                self._expr = "Ans"
            else:
                self._expr = ""
            self._result = None
        self._expr += token

    def backspace(self) -> None:
        """Remove the last character of the expression (clearing a shown result)."""
        if self._result is not None:
            self._result = None
            return
        self._expr = self._expr[:-1]

    def clear(self) -> None:
        """Clear the expression and any shown result."""
        self._expr = ""
        self._result = None

    def equals(self) -> str:
        """Evaluate the expression, update display + ``Ans``, and return the display.

        On any error, the display becomes ``"Error"`` and ``Ans`` is left
        unchanged. Never raises.
        """
        if not self._expr.strip():
            self._result = "0"
            return self._result
        try:
            value = evaluate(
                self._expr,
                degrees=self._degrees,
                ans=self._ans,
                memory=self._memory,
            )
        except AlgebraicError:
            self._result = "Error"
            return self._result
        self._ans = value
        self._result = _format(value)
        return self._result

    # -- memory ------------------------------------------------------------

    def _current_value(self) -> float:
        """The current numeric value (the shown result, else the evaluated expr)."""
        if self._result is not None and self._result not in ("Error",):
            try:
                return float(self._result)
            except ValueError:
                pass
        if not self._expr.strip():
            return 0.0
        return evaluate(
            self._expr,
            degrees=self._degrees,
            ans=self._ans,
            memory=self._memory,
        )

    def memory_store(self) -> None:
        """Set ``M`` to the current value (no change on an error)."""
        try:
            self._memory = self._current_value()
        except AlgebraicError:
            pass

    def memory_recall(self) -> None:
        """Append the memory symbol ``M`` to the expression."""
        self.input("M")

    def memory_add(self) -> None:
        """Add the current value to ``M`` (no change on an error)."""
        try:
            self._memory += self._current_value()
        except AlgebraicError:
            pass

    def memory_clear(self) -> None:
        """Reset ``M`` to zero."""
        self._memory = 0.0
