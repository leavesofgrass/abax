"""Autofill series — extend a seed sequence (the gnumeric "fill series" feature).

Given the non-blank seed cells of a selection, predict the continuation:

* numbers       -> arithmetic progression (step from the last two, else +1)
* ISO dates     -> day progression
* weekday names -> Mon, Tue, … / Monday, Tuesday, … (cyclic, case-preserving)
* month names   -> Jan, Feb, … / January, February, …
* text + number -> "Item 1", "Item 2", …
* anything else -> cyclic repeat of the seeds

Pure stdlib → core. Used by :mod:`abax.core.fill`.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

WEEKDAYS_FULL = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WEEKDAYS_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS_FULL = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
MONTHS_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

_TEXT_NUM = re.compile(r"^(.*?)(\d+)$")


def _fmt_num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


def _try_floats(seeds: list[str]) -> list[float] | None:
    out = []
    for s in seeds:
        try:
            out.append(float(s))
        except (TypeError, ValueError):
            return None
    return out


def _try_dates(seeds: list[str]) -> list[date] | None:
    out = []
    for s in seeds:
        try:
            out.append(date.fromisoformat(s.strip()))
        except (TypeError, ValueError):
            return None
    return out


def _match_cycle(seeds: list[str], names: list[str]) -> list[int] | None:
    lower = [n.lower() for n in names]
    idxs = []
    for s in seeds:
        try:
            idxs.append(lower.index(s.strip().lower()))
        except ValueError:
            return None
    return idxs


def _apply_case(template: str, source: str) -> str:
    if source.isupper():
        return template.upper()
    if source.islower():
        return template.lower()
    return template  # names are already Title case


def extend_series(seeds: list[str], count: int) -> list[str]:
    """Return the next ``count`` values continuing ``seeds``."""
    if count <= 0:
        return []
    seeds = [s for s in seeds if s != ""]
    if not seeds:
        return [""] * count

    nums = _try_floats(seeds)
    if nums is not None:
        step = (nums[-1] - nums[-2]) if len(nums) >= 2 else 1.0
        last = nums[-1]
        out = []
        for _ in range(count):
            last += step
            out.append(_fmt_num(last))
        return out

    dates = _try_dates(seeds)
    if dates is not None:
        step = (dates[-1] - dates[-2]).days if len(dates) >= 2 else 1
        step = step or 1
        last = dates[-1]
        out = []
        for _ in range(count):
            last = last + timedelta(days=step)
            out.append(last.isoformat())
        return out

    for names in (WEEKDAYS_FULL, WEEKDAYS_ABBR, MONTHS_FULL, MONTHS_ABBR):
        idxs = _match_cycle(seeds, names)
        if idxs is not None:
            n = len(names)
            step = ((idxs[-1] - idxs[-2]) % n) if len(idxs) >= 2 else 1
            step = step or 1
            last = idxs[-1]
            out = []
            for _ in range(count):
                last = (last + step) % n
                out.append(_apply_case(names[last], seeds[-1]))
            return out

    m = _TEXT_NUM.match(seeds[-1])
    if m:
        prefix, num = m.group(1), int(m.group(2))
        step = 1
        if len(seeds) >= 2:
            m2 = _TEXT_NUM.match(seeds[-2])
            if m2 and m2.group(1) == prefix:
                step = num - int(m2.group(2))
        step = step or 1
        out = []
        n = num
        for _ in range(count):
            n += step
            out.append(f"{prefix}{n}")
        return out

    # Fallback: cycle the seeds.
    return [seeds[i % len(seeds)] for i in range(count)]
