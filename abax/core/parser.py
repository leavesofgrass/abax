"""Recursive-descent / precedence-climbing parser.

Grammar (lowest to highest precedence)::

    comparison := concat ( (= <> < > <= >=) concat )*
    concat     := additive ( & additive )*
    additive   := term ( (+ -) term )*
    term       := factor ( (* / %) factor )*
    factor     := unary ( ^ factor )?            # ^ is right-associative
    unary      := (+ -) unary | primary
    primary    := NUMBER | STRING | REF | RANGE
                | NAME '(' args ')' | '(' comparison ')'

Returns an AST built from :mod:`abax.core.ast_nodes`.
"""

from __future__ import annotations

from . import ast_nodes as A
from .errors import FormulaError
from .tokenizer import Token, tokenize


def _split_sheet(text: str) -> tuple[str, str]:
    """``"Sheet2!A1"`` -> ``("Sheet2", "A1")``; ``"A1"`` -> ``("", "A1")``.

    Handles quoted names: ``"'My Sheet'!A1"`` -> ``("My Sheet", "A1")``.
    """
    if "!" not in text:
        return "", text
    sheet, ref = text.rsplit("!", 1)
    sheet = sheet.strip()
    if len(sheet) >= 2 and sheet[0] == "'" and sheet[-1] == "'":
        sheet = sheet[1:-1].replace("''", "'")
    return sheet, ref


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.toks = tokens
        self.i = 0

    def peek(self) -> Token | None:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def next(self) -> Token:
        tok = self.toks[self.i]
        self.i += 1
        return tok

    def expect(self, kind: str) -> Token:
        tok = self.peek()
        if tok is None or tok.kind != kind:
            raise FormulaError(f"expected {kind}, got {tok}")
        return self.next()

    def parse(self):
        node = self.comparison()
        if self.peek() is not None:
            raise FormulaError(f"unexpected trailing token: {self.peek()}")
        return node

    def comparison(self):
        node = self.concat()
        while (t := self.peek()) and t.kind == "OP" and t.value in (
            "=", "<>", "<", ">", "<=", ">=",
        ):
            op = self.next().value
            node = A.Binary(op, node, self.concat())
        return node

    def concat(self):
        node = self.additive()
        while (t := self.peek()) and t.kind == "OP" and t.value == "&":
            self.next()
            node = A.Binary("&", node, self.additive())
        return node

    def additive(self):
        node = self.term()
        while (t := self.peek()) and t.kind == "OP" and t.value in ("+", "-"):
            op = self.next().value
            node = A.Binary(op, node, self.term())
        return node

    def term(self):
        node = self.factor()
        while (t := self.peek()) and t.kind == "OP" and t.value in ("*", "/", "%"):
            op = self.next().value
            node = A.Binary(op, node, self.factor())
        return node

    def factor(self):
        node = self.unary()
        if (t := self.peek()) and t.kind == "OP" and t.value == "^":
            self.next()
            # right-associative
            node = A.Binary("^", node, self.factor())
        return node

    def unary(self):
        t = self.peek()
        if t and t.kind == "OP" and t.value in ("+", "-"):
            op = self.next().value
            return A.Unary(op, self.unary())
        return self.primary()

    def primary(self):
        t = self.peek()
        if t is None:
            raise FormulaError("unexpected end of formula")
        if t.kind == "NUMBER":
            self.next()
            return A.Number(float(t.value))
        if t.kind == "STRING":
            self.next()
            return A.String(t.value)
        if t.kind == "ERROR":
            self.next()
            return A.Error(t.value)
        if t.kind == "RANGE":
            self.next()
            sheet, ref = _split_sheet(t.value)
            return A.Range(ref, sheet)
        if t.kind == "REF":
            self.next()
            sheet, ref = _split_sheet(t.value)
            return A.Ref(ref, sheet)
        if t.kind == "NAME":
            name = self.next().value
            nxt = self.peek()
            if nxt is not None and nxt.kind == "LPAREN":
                self.expect("LPAREN")
                args = self.arglist()
                self.expect("RPAREN")
                return A.Func(name.upper(), tuple(args))
            # Bare identifier: TRUE / FALSE / a named constant.
            return A.Name(name.upper())
        if t.kind == "LPAREN":
            self.next()
            node = self.comparison()
            self.expect("RPAREN")
            return node
        raise FormulaError(f"unexpected token: {t}")

    def arglist(self):
        args = []
        if (t := self.peek()) and t.kind == "RPAREN":
            return args
        args.append(self.comparison())
        while (t := self.peek()) and t.kind == "COMMA":
            self.next()
            args.append(self.comparison())
        return args


def parse(formula: str):
    """Parse a formula body (without leading ``=``) into an AST."""
    tokens = tokenize(formula)
    if not tokens:
        raise FormulaError("empty formula")
    return _Parser(tokens).parse()
