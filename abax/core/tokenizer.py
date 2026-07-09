"""Formula tokenizer.

Splits a formula body (text after ``=``) into a flat token stream. Recognizes
numbers, quoted strings, A1 references and ranges, function names, operators,
and parentheses/commas. Deliberately small and dependency-free.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from .errors import FormulaError


class Token(NamedTuple):
    kind: str  # NUMBER STRING REF RANGE NAME OP LPAREN RPAREN COMMA
    value: str


# Order matters: longer operators before their prefixes.
_OPERATORS = ("<=", ">=", "<>", "+", "-", "*", "/", "^", "%", "&", "=", "<", ">", "@")

# A sheet qualifier is a bare name (Sheet2) or a quoted name ('My Sheet'),
# followed by '!'. Quoted names may contain '' as an escaped apostrophe. A bare
# name may carry a bracketed external-workbook prefix ([Book.abax]Sheet1); the
# quoted form ('[Book.abax]Sheet1') is already covered by the quoted alternative.
_SHEET = r"(?:'(?:[^']|'')*'|(?:\[[^\]\r\n]+\])?[A-Za-z_][A-Za-z0-9_.]*)!"

_TOKEN_RE = re.compile(
    r"""
      (?P<WS>\s+)
    | (?P<STRING>"(?:[^"]|"")*")
    | (?P<ERROR>\#(?:DIV/0!|NAME\?|VALUE!|REF!|NUM!|N/A|CIRC!|NULL!))
    | (?P<QRANGE>"""
    + _SHEET
    + r"""\$?[A-Za-z]+\$?[0-9]+:\$?[A-Za-z]+\$?[0-9]+)
    | (?P<QSPILL>"""
    + _SHEET
    + r"""\$?[A-Za-z]+\$?[0-9]+\#)
    | (?P<QREF>"""
    + _SHEET
    + r"""\$?[A-Za-z]+\$?[0-9]+)(?![A-Za-z0-9_.])
    | (?P<RANGE>\$?[A-Za-z]+\$?[0-9]+:\$?[A-Za-z]+\$?[0-9]+)
    | (?P<SPILL>\$?[A-Za-z]+\$?[0-9]+\#)
    | (?P<REFLIKE>\$?[A-Za-z]+\$?[0-9]+)(?![A-Za-z0-9_.])
    | (?P<NUMBER>[0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?)
    | (?P<NAME>[A-Za-z_][A-Za-z0-9_.]*)
    | (?P<OP><=|>=|<>|[+\-*/^%&=<>@])
    | (?P<LPAREN>\()
    | (?P<RPAREN>\))
    | (?P<LBRACE>\{)
    | (?P<RBRACE>\})
    | (?P<SEMI>;)
    | (?P<COMMA>,)
    """,
    re.VERBOSE,
)


def _next_nonspace(s: str, i: int) -> str:
    while i < len(s) and s[i].isspace():
        i += 1
    return s[i] if i < len(s) else ""


def tokenize(formula: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    n = len(formula)
    while pos < n:
        m = _TOKEN_RE.match(formula, pos)
        if not m:
            raise FormulaError(f"unexpected character at {pos}: {formula[pos]!r}")
        pos = m.end()
        kind = m.lastgroup
        text = m.group()
        if kind == "WS":
            continue
        if kind == "STRING":
            tokens.append(Token("STRING", text[1:-1].replace('""', '"')))
        elif kind == "ERROR":
            tokens.append(Token("ERROR", text))
        elif kind == "QRANGE":
            tokens.append(Token("RANGE", text))  # value keeps the Sheet! prefix
        elif kind in ("QSPILL", "SPILL"):
            tokens.append(Token("SPILL", text[:-1]))  # drop the trailing '#'
        elif kind == "QREF":
            tokens.append(Token("REF", text))
        elif kind == "RANGE":
            tokens.append(Token("RANGE", text))
        elif kind == "REFLIKE":
            # A token like A1 / $A$1 is a cell reference — unless it ends in
            # digits AND is immediately called, which means it's a function
            # name (e.g. LOG10(...), ATAN2(...)). A '$' is never in a name.
            if "$" not in text and _next_nonspace(formula, pos) == "(":
                tokens.append(Token("NAME", text))
            else:
                tokens.append(Token("REF", text))
        elif kind == "NUMBER":
            tokens.append(Token("NUMBER", text))
        elif kind == "NAME":
            tokens.append(Token("NAME", text))
        elif kind == "OP":
            tokens.append(Token("OP", text))
        elif kind == "LPAREN":
            tokens.append(Token("LPAREN", text))
        elif kind == "RPAREN":
            tokens.append(Token("RPAREN", text))
        elif kind == "LBRACE":
            tokens.append(Token("LBRACE", text))
        elif kind == "RBRACE":
            tokens.append(Token("RBRACE", text))
        elif kind == "SEMI":
            tokens.append(Token("SEMI", text))
        elif kind == "COMMA":
            tokens.append(Token("COMMA", text))
    return tokens
