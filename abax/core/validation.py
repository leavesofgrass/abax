"""Data-validation rules — dropdown lists and input constraints for cells.

A :class:`ValidationRule` is an immutable description of what a cell is allowed
to contain: a fixed dropdown list of values, or a numeric / text-length
constraint expressed as an operator against one or two operands. :func:`validate`
checks a candidate value against a rule and returns an ``(ok, message)`` pair.

This module is the data model plus a pure checker (no Qt) and is part of the
stdlib-only ``core`` package.
"""

from __future__ import annotations

from dataclasses import dataclass

KINDS = ("list", "whole", "decimal", "textlen")
OPS = ("between", "notbetween", "eq", "ne", "gt", "lt", "ge", "le")


@dataclass(frozen=True)
class ValidationRule:
    kind: str  # one of KINDS
    op: str = "between"  # for whole/decimal/textlen (ignored for list)
    p1: str = ""  # operand / lower bound
    p2: str = ""  # upper bound (for between/notbetween)
    values: tuple[str, ...] = ()  # for kind="list" (allowed dropdown values)
    ignore_blank: bool = True
    message: str = ""  # optional custom error message

    def to_dict(self) -> dict:
        """Emit only non-default fields (compact JSON for the envelope)."""
        default = ValidationRule(kind=self.kind)
        out: dict = {"kind": self.kind}
        if self.op != default.op:
            out["op"] = self.op
        if self.p1 != default.p1:
            out["p1"] = self.p1
        if self.p2 != default.p2:
            out["p2"] = self.p2
        if self.values != default.values:
            out["values"] = list(self.values)
        if self.ignore_blank != default.ignore_blank:
            out["ignore_blank"] = self.ignore_blank
        if self.message != default.message:
            out["message"] = self.message
        return out

    @classmethod
    def from_dict(cls, d: dict) -> "ValidationRule":
        """Build from a dict; missing keys -> default; ``values`` -> tuple."""
        return cls(
            kind=d["kind"],
            op=d.get("op", "between"),
            p1=d.get("p1", ""),
            p2=d.get("p2", ""),
            values=tuple(d.get("values", ())),
            ignore_blank=bool(d.get("ignore_blank", True)),
            message=d.get("message", ""),
        )


# --- constructors ---------------------------------------------------------


def list_rule(values, ignore_blank: bool = True) -> ValidationRule:
    """A dropdown rule allowing exactly ``values`` (coerced to a tuple)."""
    return ValidationRule(
        kind="list",
        values=tuple(str(v) for v in values),
        ignore_blank=ignore_blank,
    )


def number_rule(
    kind: str, op: str, p1: str, p2: str = "", *, ignore_blank: bool = True
) -> ValidationRule:
    """A numeric rule (``kind`` in ``"whole"``/``"decimal"``) with operator ``op``."""
    if kind not in ("whole", "decimal"):
        raise ValueError(f"invalid number kind: {kind!r} (expected 'whole' or 'decimal')")
    if op not in OPS:
        raise ValueError(f"invalid op: {op!r} (expected one of {OPS})")
    return ValidationRule(
        kind=kind, op=op, p1=str(p1), p2=str(p2), ignore_blank=ignore_blank
    )


# --- numeric comparison ---------------------------------------------------


def _apply_op(x: float, op: str, a: float, b: float) -> bool:
    """Compare ``x`` against operand(s) ``a`` (and ``b`` for ranges) by ``op``."""
    if op == "between":
        lo, hi = (a, b) if a <= b else (b, a)
        return lo <= x <= hi
    if op == "notbetween":
        lo, hi = (a, b) if a <= b else (b, a)
        return not (lo <= x <= hi)
    if op == "eq":
        return x == a
    if op == "ne":
        return x != a
    if op == "gt":
        return x > a
    if op == "lt":
        return x < a
    if op == "ge":
        return x >= a
    if op == "le":
        return x <= a
    raise ValueError(f"invalid op: {op!r} (expected one of {OPS})")


def _num(s: str) -> float:
    """Parse an operand to float (empty -> 0.0)."""
    s = str(s).strip()
    if s == "":
        return 0.0
    return float(s)


_OP_WORD = {
    "between": "between",
    "notbetween": "not between",
    "eq": "equal to",
    "ne": "not equal to",
    "gt": "greater than",
    "lt": "less than",
    "ge": "greater than or equal to",
    "le": "less than or equal to",
}


def _default_message(rule: ValidationRule) -> str:
    """A sensible human-readable failure message for ``rule``."""
    if rule.kind == "list":
        return "must be one of: " + ", ".join(rule.values)
    noun = {
        "whole": "a whole number",
        "decimal": "a number",
        "textlen": "text length",
    }[rule.kind]
    if rule.op in ("between", "notbetween"):
        word = "between" if rule.op == "between" else "not between"
        return f"{noun} must be {word} {rule.p1} and {rule.p2}"
    return f"{noun} must be {_OP_WORD[rule.op]} {rule.p1}"


# --- validation -----------------------------------------------------------


def validate(value: str, rule: ValidationRule) -> tuple[bool, str]:
    """Check ``value`` against ``rule``; return ``(ok, message)``.

    On success the message is ``""``. On failure it is ``rule.message`` when set,
    else a sensible default. Raises :class:`ValueError` for an unknown kind or op.
    """
    if rule.kind not in KINDS:
        raise ValueError(f"invalid kind: {rule.kind!r} (expected one of {KINDS})")
    if rule.kind != "list" and rule.op not in OPS:
        raise ValueError(f"invalid op: {rule.op!r} (expected one of {OPS})")

    text = str(value).strip()

    if text == "" and rule.ignore_blank:
        return (True, "")

    def fail() -> tuple[bool, str]:
        return (False, rule.message or _default_message(rule))

    if rule.kind == "list":
        return (True, "") if value in rule.values else fail()

    if rule.kind == "whole":
        try:
            x = int(text)
        except (ValueError, TypeError):
            return fail()
    elif rule.kind == "decimal":
        try:
            x = float(text)
        except (ValueError, TypeError):
            return fail()
    else:  # textlen
        x = len(str(value))

    a = _num(rule.p1)
    b = _num(rule.p2)
    return (True, "") if _apply_op(float(x), rule.op, a, b) else fail()
