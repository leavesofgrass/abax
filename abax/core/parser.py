"""Recursive-descent / precedence-climbing parser.

Grammar (lowest to highest precedence)::

    comparison := concat ( (= <> < > <= >=) concat )*
    concat     := additive ( & additive )*
    additive   := term ( (+ -) term )*
    term       := factor ( (* / %) factor )*
    factor     := unary ( ^ factor )?            # ^ is right-associative
    unary      := (+ -) unary | primary
    postfix    := primary ( '(' args ')' )*      # direct application -> Call
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
        # '@' is the implicit-intersection prefix (take a single value from an
        # array/range); '+'/'-' are the arithmetic signs.
        if t and t.kind == "OP" and t.value in ("+", "-", "@"):
            op = self.next().value
            return A.Unary(op, self.unary())
        return self.postfix()

    def postfix(self):
        """A primary expression followed by zero or more ``(`` args ``)``
        *applications* — the direct-call seam, e.g. ``LAMBDA(x, x*x)(5)`` or the
        chain ``f(a)(b)``. Each trailing ``(`` wraps the value produced so far in
        a :class:`~abax.core.ast_nodes.Call`. Note ``SUM(A1:A3)`` never reaches
        here as a call: a bare NAME directly followed by ``(`` is consumed inside
        :meth:`primary` as a ``Func``, so only a ``(`` after a *value* applies."""
        node = self.primary()
        while (t := self.peek()) and t.kind == "LPAREN":
            self.expect("LPAREN")
            args = self.arglist()
            self.expect("RPAREN")
            node = A.Call(node, tuple(args))
        return node

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
        if t.kind == "SPILL":
            self.next()
            sheet, ref = _split_sheet(t.value)
            return A.SpillRef(ref, sheet)
        if t.kind == "STRUCTREF":
            # A structured (table) reference — carried verbatim; the Sheet
            # rewrites it against the workbook's TableRegistry pre-evaluation.
            self.next()
            return A.StructRef(t.value)
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
        if t.kind == "LBRACE":
            return self.array_literal()
        raise FormulaError(f"unexpected token: {t}")

    def array_literal(self):
        """Parse ``{ row (; row)* }`` where a row is ``elem (, elem)*``. Commas
        separate columns, semicolons separate rows (Excel array constants)."""
        self.expect("LBRACE")
        rows = [tuple(self._array_row())]
        while (t := self.peek()) and t.kind == "SEMI":
            self.next()
            rows.append(tuple(self._array_row()))
        self.expect("RBRACE")
        width = len(rows[0])
        if any(len(r) != width for r in rows):
            raise FormulaError("array constant rows must be the same length")
        return A.ArrayLiteral(tuple(rows))

    def _array_row(self):
        elems = [self.unary()]
        while (t := self.peek()) and t.kind == "COMMA":
            self.next()
            elems.append(self.unary())
        return elems

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
