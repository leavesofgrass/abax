"""Excel-style criteria matching, shared by the conditional functions.

``SUMIF``/``COUNTIF``/``AVERAGEIF`` and the ``*IFS`` family plus the database
(``D*``) functions all accept a *criterion* like ``">10"``, ``"<>0"``, ``"apple"``
or ``"a*"`` (wildcards ``*`` and ``?``). :func:`make_predicate` compiles one
criterion into a ``value -> bool`` test with Excel semantics:

* a bare number/text is an equality test (numbers compare numerically, text
  case-insensitively with ``*``/``?`` wildcards);
* a leading comparison operator (``<``, ``>``, ``<=``, ``>=``, ``<>``, ``=``)
  compares the cell against the rest.

Pure stdlib; depends only on the coercion helpers in
:mod:`abax.core.functions.helpers`.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Callable

from .functions.helpers import _text, _try_num


def cmp_op(op: str, a, b) -> bool:
    """Apply a comparison operator (``=``/``<>``/``<``/``>``/``<=``/``>=``)."""
    if op == "=":
        return a == b
    if op == "<>":
        return a != b
    if op == "<":
        return a < b
    if op == ">":
        return a > b
    if op == "<=":
        return a <= b
    if op == ">=":
        return a >= b
    return False


@lru_cache(maxsize=256)
def wildcard_re(pattern: str) -> re.Pattern:
    """Compile an Excel wildcard pattern (``*`` any run, ``?`` one char), anchored
    and case-insensitive."""
    out = ["(?i)^"]
    for ch in pattern:
        if ch == "*":
            out.append(".*")
        elif ch == "?":
            out.append(".")
        else:
            out.append(re.escape(ch))
    out.append("$")
    return re.compile("".join(out))


def make_predicate(criteria: Any) -> Callable[[Any], bool]:
    """Compile a single Excel criterion into a ``value -> bool`` predicate."""
    if isinstance(criteria, bool):
        return lambda v: isinstance(v, bool) and v == criteria
    if isinstance(criteria, (int, float)):
        target = float(criteria)
        return lambda v: (n := _try_num(v)) is not None and not isinstance(v, str) and n == target
    s = str(criteria).strip()
    m = re.match(r"^(<=|>=|<>|=|<|>)(.*)$", s)
    op, rest = ("=", s)
    if m:
        op, rest = m.group(1), m.group(2).strip()
    num = _try_num(rest) if rest != "" else None
    if num is not None:

        def num_pred(v, op=op, num=num):
            x = _try_num(v)
            if x is None or isinstance(v, str):
                return False
            return cmp_op(op, x, num)

        return num_pred

    pattern = wildcard_re(rest)

    def text_pred(v, op=op, pattern=pattern, rest=rest):
        s2 = _text(v)
        if op == "=":
            return pattern.match(s2) is not None
        if op == "<>":
            return pattern.match(s2) is None
        return cmp_op(op, s2.lower(), rest.lower())

    return text_pred
