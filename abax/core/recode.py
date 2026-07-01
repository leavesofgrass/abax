"""Column recode / clean engine — pure stdlib, so it lives in core.

The brain behind abax's "Recode / clean column" tool. Each operation here
takes ONE column as a ``list[str]`` of raw cell *texts* (the empty string is a
blank cell) and returns a NEW ``list[str]`` of recoded cell texts ready to be
written back. Every function is pure and non-mutating — the input list is left
untouched.

Conventions shared by every operation:

* A **blank** cell is the empty string ``""``. Blanks are preserved (left as
  ``""``) by every operation unless the operation's whole job is to fill them
  (:func:`fill_missing`).
* **Numeric** operations (:func:`fill_missing` with a numeric method,
  :func:`normalize`, :func:`clip`) parse cells with :func:`_to_number`, which
  treats blanks as *missing* (ignored) and raises :class:`RecodeError` if a
  non-blank cell is not numeric — except :func:`clip`, which is permissive and
  passes non-numeric cells through unchanged.
* Type coercion reuses :mod:`abax.core.typeinfer` (``coerce``) and re-renders
  the parsed value as canonical text.

The :data:`OPERATIONS` registry lets a GUI dialog enumerate the available
operations, with a label, a one-line doc, and whether the operation needs an
extra argument.
"""

from __future__ import annotations

from datetime import date, datetime

from . import typeinfer


class RecodeError(Exception):
    """Raised when a recode operation cannot produce a valid result."""


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #
def _to_number(value: str) -> float | None:
    """Parse a cell as a float for a numeric operation.

    Blank cells (``""``) return ``None`` (missing — ignored by callers). A
    non-blank cell that is not a plain number raises :class:`RecodeError`, so a
    numeric operation never silently mangles text data.
    """
    if value == "":
        return None
    if not typeinfer._is_float(value):
        raise RecodeError(f"non-numeric value in numeric column: {value!r}")
    return float(value)


def _numeric_column(values: list[str]) -> list[float]:
    """Return the non-blank cells of ``values`` as floats (blanks dropped).

    Raises :class:`RecodeError` via :func:`_to_number` on any non-numeric cell.
    """
    out: list[float] = []
    for v in values:
        n = _to_number(v)
        if n is not None:
            out.append(n)
    return out


def _fmt_number(x: float) -> str:
    """Render a float as compact ``%g``-ish text (``5.0`` -> ``"5"``)."""
    if x != x or x in (float("inf"), float("-inf")):
        return repr(x)
    text = f"{x:.12g}"
    return text


# Date input patterns: (regex/strptime format, builder). Tried in order; the
# first that parses wins. We accept the common spreadsheet-ish forms.
_DATE_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",      # 2020-01-02   (ISO)
    "%Y/%m/%d",      # 2020/01/02
    "%m/%d/%Y",      # 01/02/2020   (US)
    "%m/%d/%y",      # 1/2/20
    "%d-%b-%Y",      # 02-Jan-2020
    "%d-%b-%y",      # 02-Jan-20
    "%d %b %Y",      # 02 Jan 2020
    "%b %d, %Y",     # Jan 02, 2020
    "%B %d, %Y",     # January 02, 2020
    "%d/%m/%Y",      # 02/01/2020   (DMY — tried last, ambiguous)
    "%Y.%m.%d",      # 2020.01.02
    "%d.%m.%Y",      # 02.01.2020
)


def _parse_date(value: str) -> date | None:
    """Parse a date in one of :data:`_DATE_FORMATS`; ``None`` if none match."""
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except (TypeError, ValueError):
            continue
    return None


# --------------------------------------------------------------------------- #
# operations                                                                   #
# --------------------------------------------------------------------------- #
def retype(values: list[str], target: str) -> list[str]:
    """Coerce each cell to ``target`` and re-render it as canonical text.

    ``target`` is one of ``"int"``, ``"float"``, ``"bool"``, ``"date"`` or
    ``"text"``. Coercion goes through :func:`typeinfer.coerce`; the parsed value
    is re-rendered canonically:

    * ``int``   -> ``"42"``        (``"1.0"`` retypes to ``"1"``)
    * ``float`` -> ``"3.14"``      (compact ``%g``)
    * ``bool``  -> ``"True"`` / ``"False"``
    * ``date``  -> ISO ``"YYYY-MM-DD"``
    * ``text``  -> the string itself

    Blanks stay ``""``. A cell that cannot be parsed as ``target`` is left
    unchanged.
    """
    if target not in ("int", "float", "bool", "date", "text"):
        raise RecodeError(f"unknown target type: {target!r}")
    out: list[str] = []
    for v in values:
        if v == "":
            out.append("")
            continue
        if target == "text":
            out.append(v)
            continue
        # `int` should accept "1.0" -> 1; coerce() with "int" would fail on it,
        # so try float-then-int for ints.
        parsed: object
        if target == "int":
            if typeinfer._is_int(v):
                parsed = int(v)
            elif typeinfer._is_float(v):
                f = float(v)
                parsed = int(f) if f == int(f) else v
            else:
                parsed = v
        else:
            parsed = typeinfer.coerce(v, target)
        if isinstance(parsed, str):
            # Unparseable — coerce returned the original string. Leave as-is.
            out.append(parsed)
        elif isinstance(parsed, bool):
            out.append("True" if parsed else "False")
        elif isinstance(parsed, int):
            out.append(str(parsed))
        elif isinstance(parsed, float):
            out.append(_fmt_number(parsed))
        elif isinstance(parsed, date):
            out.append(parsed.isoformat())
        else:  # pragma: no cover - defensive
            out.append(str(parsed))
    return out


def fill_missing(values: list[str], method: str = "value", fill: str = "") -> list[str]:
    """Fill blank cells; non-blank cells are left untouched.

    ``method``:

    * ``"value"`` — use the literal ``fill`` string.
    * ``"zero"``  — use ``"0"``.
    * ``"mean"`` / ``"median"`` — numeric columns only; fill with the mean or
      median of the non-blank values, rendered as compact text. Raises
      :class:`RecodeError` on a non-numeric column.
    * ``"ffill"`` — carry the last non-blank value above downward.
    * ``"bfill"`` — carry the next non-blank value below upward.
    """
    if method in ("value", "zero"):
        token = "0" if method == "zero" else fill
        return [token if v == "" else v for v in values]

    if method in ("mean", "median"):
        nums = _numeric_column(values)
        if not nums:
            raise RecodeError(f"{method} fill needs at least one numeric value")
        if method == "mean":
            stat = sum(nums) / len(nums)
        else:
            ordered = sorted(nums)
            n = len(ordered)
            mid = n // 2
            stat = ordered[mid] if n % 2 == 1 else 0.5 * (ordered[mid - 1] + ordered[mid])
        token = _fmt_number(stat)
        return [token if v == "" else v for v in values]

    if method == "ffill":
        out: list[str] = []
        last = ""
        for v in values:
            if v != "":
                last = v
                out.append(v)
            else:
                out.append(last)
        return out

    if method == "bfill":
        out = [""] * len(values)
        nxt = ""
        for i in range(len(values) - 1, -1, -1):
            v = values[i]
            if v != "":
                nxt = v
                out[i] = v
            else:
                out[i] = nxt
        return out

    raise RecodeError(f"unknown fill method: {method!r}")


def strip_whitespace(values: list[str]) -> list[str]:
    """Trim leading/trailing whitespace from each cell."""
    return [v.strip() for v in values]


def to_case(values: list[str], case: str) -> list[str]:
    """Recase each cell. ``case`` is ``"upper"``, ``"lower"`` or ``"title"``."""
    if case == "upper":
        return [v.upper() for v in values]
    if case == "lower":
        return [v.lower() for v in values]
    if case == "title":
        return [v.title() for v in values]
    raise RecodeError(f"unknown case: {case!r}")


def standardize_dates(values: list[str], out_fmt: str = "%Y-%m-%d") -> list[str]:
    """Parse common date forms and re-emit them in ``out_fmt``.

    Blanks stay ``""``; cells that match no known date form are left unchanged.
    """
    out: list[str] = []
    for v in values:
        if v == "":
            out.append("")
            continue
        parsed = _parse_date(v)
        out.append(parsed.strftime(out_fmt) if parsed is not None else v)
    return out


def map_values(
    values: list[str], mapping: dict[str, str], default: str | None = None
) -> list[str]:
    """Replace exact cell text per ``mapping``.

    A cell whose text is a key of ``mapping`` becomes the mapped value. An
    unmapped cell becomes ``default`` when ``default`` is given, otherwise it is
    left unchanged.
    """
    out: list[str] = []
    for v in values:
        if v in mapping:
            out.append(mapping[v])
        elif default is not None:
            out.append(default)
        else:
            out.append(v)
    return out


def normalize(values: list[str], method: str = "minmax") -> list[str]:
    """Numerically normalize a column; blanks stay ``""``.

    ``method``:

    * ``"minmax"`` — rescale to ``[0, 1]`` via ``(x - min) / (max - min)``. A
      constant column (min == max) maps every value to ``"0"``.
    * ``"zscore"`` — standardize via ``(x - mean) / std`` using the *sample*
      standard deviation (``n - 1``). Needs at least two values; a zero-variance
      column maps every value to ``"0"``.

    Raises :class:`RecodeError` if the column is non-numeric.
    """
    nums = _numeric_column(values)
    if not nums:
        raise RecodeError("normalize needs at least one numeric value")

    if method == "minmax":
        lo, hi = min(nums), max(nums)
        span = hi - lo

        def conv(x: float) -> float:
            return 0.0 if span == 0 else (x - lo) / span

    elif method == "zscore":
        n = len(nums)
        if n < 2:
            raise RecodeError("zscore needs at least two numeric values")
        m = sum(nums) / n
        ss = sum((x - m) ** 2 for x in nums)
        std = (ss / (n - 1)) ** 0.5

        def conv(x: float) -> float:
            return 0.0 if std == 0 else (x - m) / std

    else:
        raise RecodeError(f"unknown normalize method: {method!r}")

    out: list[str] = []
    for v in values:
        if v == "":
            out.append("")
        else:
            out.append(_fmt_number(conv(float(v))))
    return out


def clip(
    values: list[str], low: float | None = None, high: float | None = None
) -> list[str]:
    """Clamp numeric cells to ``[low, high]`` (``None`` = unbounded).

    Permissive: blanks and non-numeric cells pass through unchanged, so this is
    safe to run on a mixed column. A numeric cell below ``low`` becomes ``low``
    and above ``high`` becomes ``high``.
    """
    out: list[str] = []
    for v in values:
        if v == "" or not typeinfer._is_float(v):
            out.append(v)
            continue
        x = float(v)
        if low is not None and x < low:
            x = low
        if high is not None and x > high:
            x = high
        out.append(_fmt_number(x))
    return out


# --------------------------------------------------------------------------- #
# registry for the GUI dialog                                                  #
# --------------------------------------------------------------------------- #
OPERATIONS: dict[str, dict] = {
    "retype": {
        "label": "Re-type column",
        "doc": "Coerce every cell to int/float/bool/date/text and re-render it.",
        "needs_arg": True,
    },
    "fill_missing": {
        "label": "Fill missing",
        "doc": "Fill blank cells (value / mean / median / ffill / bfill / zero).",
        "needs_arg": True,
    },
    "strip_whitespace": {
        "label": "Strip whitespace",
        "doc": "Trim leading and trailing whitespace from each cell.",
        "needs_arg": False,
    },
    "to_case": {
        "label": "Change case",
        "doc": "Recase each cell (upper / lower / title).",
        "needs_arg": True,
    },
    "standardize_dates": {
        "label": "Standardize dates",
        "doc": "Parse common date forms and re-emit them in one format.",
        "needs_arg": True,
    },
    "map_values": {
        "label": "Map / replace values",
        "doc": "Replace exact cell text per a lookup; unmapped -> default.",
        "needs_arg": True,
    },
    "normalize": {
        "label": "Normalize",
        "doc": "Numeric rescale: minmax -> [0,1] or zscore -> (x-mean)/std.",
        "needs_arg": True,
    },
    "clip": {
        "label": "Clip / clamp",
        "doc": "Clamp numeric cells to a [low, high] range.",
        "needs_arg": True,
    },
}


__all__ = [
    "RecodeError",
    "retype",
    "fill_missing",
    "strip_whitespace",
    "to_case",
    "standardize_dates",
    "map_values",
    "normalize",
    "clip",
    "OPERATIONS",
]
