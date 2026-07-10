"""Data profiling and formula-recalc profiling for a spreadsheet.

Pure standard library (``statistics``, ``collections``, ``time``). Two distinct
"profilers" live here:

* **Data profiling** — a "describe" for cell values. Given a list of cell values
  (as produced by :meth:`Sheet.get_value`), :func:`profile_column` infers a dtype
  and computes summary statistics; :func:`profile_sheet` runs it over every used
  column of a sheet, labelling each with a name.

* **Recalc profiling** — a "where is the time going" for formulas.
  :func:`profile_recalc` times a single evaluation of every populated formula
  cell so a technical user can find the slow ones; :func:`slowest` and
  :func:`format_report` package that for ``abax doctor`` and a GUI dialog, and
  :func:`dependency_svg` draws a cell's precedent/dependent DAG (from
  :mod:`abax.core.deptrace`) as a self-contained, layered SVG.

Dtype inference treats ``None`` and ``""`` as *missing*. A column is numeric
(``bool``/``int``/``float``) only when *every* non-missing value parses as that
type; ``bool`` is tried before ``int`` (a bool is an ``int`` in Python, so the
order matters). Anything else is ``text``. A column with no non-missing values
is ``empty``.
"""

from __future__ import annotations

import statistics
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any

from .reference import index_to_col, to_a1

_MISSING = (None, "")


def _is_missing(value: Any) -> bool:
    return value is None or value == ""


def _as_bool(value: Any) -> bool | None:
    """Return the bool value, or None if ``value`` is not a clean bool.

    Accepts genuine ``bool`` objects and the strings ``TRUE``/``FALSE``
    (case-insensitive) — the textual form :meth:`Sheet.format_value` emits.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low == "true":
            return True
        if low == "false":
            return False
    return None


def _as_int(value: Any) -> int | None:
    """Return the int value, or None. Rejects bools (handled separately)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _as_float(value: Any) -> float | None:
    """Return the float value, or None. Rejects bools."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _infer_dtype(present: list[Any]) -> str:
    """Pick a dtype for the non-missing values.

    ``bool`` before ``int`` before ``float``; each requires *every* value to
    parse. Falls back to ``text``.
    """
    if not present:
        return "empty"
    if all(_as_bool(v) is not None for v in present):
        return "bool"
    if all(_as_int(v) is not None for v in present):
        return "int"
    if all(_as_float(v) is not None for v in present):
        return "float"
    return "text"


def _numeric_stats(nums: list[float]) -> dict:
    """min/max/mean/median/std/q1/q3 over a non-empty numeric list."""
    stats: dict[str, Any] = {
        "min": min(nums),
        "max": max(nums),
        "mean": statistics.mean(nums),
        "median": statistics.median(nums),
        # Population standard deviation; 0.0 for a single value.
        "std": statistics.pstdev(nums) if len(nums) >= 2 else 0.0,
    }
    if len(nums) >= 2:
        # statistics.quantiles(n=4) → the three cut points [q1, q2, q3].
        q1, _q2, q3 = statistics.quantiles(nums, n=4)
        stats["q1"] = q1
        stats["q3"] = q3
    else:
        stats["q1"] = nums[0]
        stats["q3"] = nums[0]
    return stats


def profile_column(values: list[Any]) -> dict:
    """Profile a single column given its list of cell values.

    ``None`` and ``""`` count as missing. Always returns ``dtype``, ``count``
    (non-missing), ``missing``, ``unique`` (distinct non-missing). Numeric
    dtypes add ``min/max/mean/median/std/q1/q3``; ``text`` adds ``max_len`` and
    ``top`` (up to five most-common ``(value, count)`` pairs, ties broken by
    first appearance).
    """
    present = [v for v in values if not _is_missing(v)]
    dtype = _infer_dtype(present)

    profile: dict[str, Any] = {
        "dtype": dtype,
        "count": len(present),
        "missing": len(values) - len(present),
        "unique": len(set(present)),
    }

    if dtype in ("bool", "int", "float"):
        if dtype == "bool":
            nums = [1.0 if _as_bool(v) else 0.0 for v in present]
        elif dtype == "int":
            nums = [float(_as_int(v)) for v in present]
        else:
            nums = [_as_float(v) for v in present]
        profile.update(_numeric_stats(nums))
    elif dtype == "text":
        texts = [str(v) for v in present]
        profile["max_len"] = max((len(t) for t in texts), default=0)
        # Counter.most_common is insertion-ordered on ties (Python 3.7+),
        # which gives the required "first appearance" tie-break.
        profile["top"] = Counter(texts).most_common(5)

    return profile


def profile_sheet(sheet, header_row: bool = True) -> list[dict]:
    """Profile every used column of ``sheet``, one dict per column.

    Each dict is a :func:`profile_column` result plus a ``"name"`` key. When
    ``header_row`` is True the first row supplies column names and is excluded
    from the profiled data; otherwise names are the column letters (A, B, …).
    """
    nrows, ncols = sheet.used_bounds()
    data_start = 1 if header_row else 0

    profiles: list[dict] = []
    for col in range(ncols):
        values = [sheet.get_value(row, col) for row in range(data_start, nrows)]
        profile = profile_column(values)

        if header_row:
            header = sheet.get_value(0, col)
            name = str(header) if not _is_missing(header) else index_to_col(col)
        else:
            name = index_to_col(col)
        profile["name"] = name
        profiles.append(profile)

    return profiles


# ---------------------------------------------------------------------------
# Recalc profiling — find the slow formula cells.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CellTiming:
    """One formula cell's measured evaluation cost.

    ``sheet`` is the sheet name; ``row``/``col`` the 0-based coordinates; ``a1``
    the A1 label; ``seconds`` the (average) time a single
    :meth:`Sheet.get_value` took; ``formula`` the cell's raw source text.
    """

    sheet: str
    row: int
    col: int
    a1: str
    seconds: float
    formula: str

    @property
    def ms(self) -> float:
        """The timing in milliseconds."""
        return self.seconds * 1000.0

    @property
    def ref(self) -> str:
        """Fully-qualified reference ``Sheet!A1``."""
        return f"{self.sheet}!{self.a1}"


def _target_sheets(workbook, sheet) -> list:
    """Resolve the ``sheet`` selector to a list of Sheet objects.

    ``None`` means every sheet; a ``str`` is looked up by name (empty list if
    unknown); anything else is assumed to already be a Sheet.
    """
    if sheet is None:
        return list(workbook.sheets)
    if isinstance(sheet, str):
        found = workbook.get_sheet(sheet)
        return [found] if found is not None else []
    return [sheet]


def profile_recalc(workbook, *, sheet=None, repeat: int = 1) -> list[CellTiming]:
    """Measure per-cell evaluation cost, slowest first.

    Every populated *formula* cell (across all sheets, or just ``sheet`` — a
    Sheet or a sheet name) is timed with :func:`time.perf_counter` around a
    single :meth:`Sheet.get_value`. The value caches are cleared once per pass
    (``workbook.invalidate_caches()``) before timing begins, so the first cell
    touched pays the full cold cost and a cell already computed as a *precedent*
    of an earlier-timed cell registers only its cached-lookup cost. In practice
    that measures each cell's **marginal** cost given what sits above it in
    iteration order — which is exactly what you want for "which formula is
    expensive", but note the number depends on evaluation order and is inherently
    **noisy** (sub-millisecond timings especially). Pass ``repeat=N`` to average
    N passes for a steadier estimate.

    Returns a list of :class:`CellTiming` sorted by ``seconds`` descending. An
    empty (or formula-free) selection yields an empty list. ``seconds`` is always
    non-negative (``perf_counter`` is monotonic).
    """
    passes = max(1, int(repeat))
    order = [
        (sh, r, c, cell.raw)
        for sh in _target_sheets(workbook, sheet)
        for r, c, cell in sh.iter_cells()
        if cell.is_formula
    ]
    totals: dict[tuple[str, int, int], float] = {
        (sh.name, r, c): 0.0 for sh, r, c, _raw in order
    }
    for _ in range(passes):
        workbook.invalidate_caches()
        for sh, r, c, _raw in order:
            start = time.perf_counter()
            sh.get_value(r, c)
            totals[(sh.name, r, c)] += time.perf_counter() - start

    timings = [
        CellTiming(
            sheet=sh.name,
            row=r,
            col=c,
            a1=to_a1(r, c),
            seconds=totals[(sh.name, r, c)] / passes,
            formula=raw,
        )
        for sh, r, c, raw in order
    ]
    timings.sort(key=lambda t: t.seconds, reverse=True)
    return timings


def slowest(workbook, n: int = 10) -> list[CellTiming]:
    """The ``n`` slowest formula cells in ``workbook`` (see :func:`profile_recalc`)."""
    return profile_recalc(workbook)[: max(0, n)]


def _truncate(text: str, width: int) -> str:
    """Collapse whitespace and cap ``text`` to ``width`` chars with an ellipsis."""
    text = " ".join(text.split())
    if len(text) > width:
        return text[: width - 1] + "…"
    return text


def format_report(timings: list[CellTiming], limit: int = 20) -> str:
    """Render ``timings`` as a fixed-width table: rank, cell, time (ms), formula.

    Suitable for ``abax doctor`` output or a GUI text pane. Shows at most
    ``limit`` rows. An empty list yields a short "nothing to profile" line.
    """
    if not timings:
        return "No formula cells to profile."
    rows = timings[: max(0, limit)] if limit else list(timings)

    refs = [t.ref for t in rows]
    ref_w = max(4, *(len(r) for r in refs))
    header = f"{'#':>3}  {'Cell':<{ref_w}}  {'Time (ms)':>10}  Formula"
    lines = [header, "-" * len(header)]
    for rank, t in enumerate(rows, start=1):
        lines.append(
            f"{rank:>3}  {t.ref:<{ref_w}}  {t.ms:>10.4f}  {_truncate(t.formula, 50)}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dependency-graph SVG — draw a cell's precedent/dependent DAG.
# ---------------------------------------------------------------------------


def _xml_escape(text: str) -> str:
    """Escape the five XML-significant characters for use in SVG text/attrs."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def dependency_svg(
    sheet,
    row: int,
    col: int,
    *,
    direction: str = "precedents",
    max_depth: int = 6,
    width: int = 640,
) -> str:
    """Render a cell's dependency DAG as a self-contained, layered SVG string.

    ``direction`` is ``"precedents"`` (what feeds this cell — the default) or
    ``"dependents"`` (what this cell feeds); the tree is built by
    :func:`abax.core.deptrace.trace_precedents` /
    :func:`~abax.core.deptrace.trace_dependents` and capped at ``max_depth``.
    Nodes are drawn as labelled boxes laid out in horizontal layers by depth
    (the traced cell on top), edges as straight lines from each parent to its
    children. A cell reached by two paths appears once per path (the tracer
    yields a tree); a cycle-closing node is tagged ``(cycle)``. No Qt — the
    result is a plain ``<svg>…</svg>`` string a caller can paint with
    ``QSvgRenderer`` or write to a file.
    """
    if direction not in ("precedents", "dependents"):
        raise ValueError(
            f"direction must be 'precedents' or 'dependents', got {direction!r}"
        )
    from .deptrace import trace_dependents, trace_precedents

    tracer = trace_precedents if direction == "precedents" else trace_dependents
    root = tracer(sheet, row, col, max_depth=max_depth)

    # Group nodes into layers by BFS depth. Each DepNode is a distinct box (a
    # shared cell reached twice sits on two paths, so it draws twice).
    layers: list[list] = []
    frontier = [root]
    while frontier:
        layers.append(frontier)
        nxt: list = []
        for node in frontier:
            nxt.extend(node.children)
        frontier = nxt

    pad = 24
    node_h = 30
    vgap = 46
    width = max(120, int(width))
    usable = max(1, width - 2 * pad)
    height = pad * 2 + len(layers) * node_h + max(0, len(layers) - 1) * vgap

    # Position every node: centre-x spread evenly across its layer, top-y by depth.
    pos: dict[int, tuple[float, float]] = {}
    for depth, layer in enumerate(layers):
        n = len(layer)
        y = pad + depth * (node_h + vgap)
        for i, node in enumerate(layer):
            cx = pad + usable * (i + 0.5) / n
            pos[id(node)] = (cx, y)

    edges: list[str] = []
    boxes: list[str] = []
    for depth, layer in enumerate(layers):
        n = len(layer)
        slot = usable / n
        box_w = max(40.0, min(132.0, slot - 12.0))
        for node in layer:
            cx, y = pos[id(node)]
            # Edges to children (drawn first, so boxes paint over the line ends).
            for child in node.children:
                ccx, cy = pos[id(child)]
                edges.append(
                    f'<line x1="{cx:.1f}" y1="{y + node_h:.1f}" '
                    f'x2="{ccx:.1f}" y2="{cy:.1f}" '
                    f'stroke="#9aa7b5" stroke-width="1.5" />'
                )
            x = cx - box_w / 2
            is_root = node is root
            fill = "#3b6fb5" if is_root else ("#fbeced" if node.cyclic else "#eef3fb")
            text_fill = "#ffffff" if is_root else "#1b2430"
            stroke = "#b54b53" if node.cyclic else "#3b6fb5"
            label = node.a1 + (" (cycle)" if node.cyclic else "")
            tooltip = _xml_escape(node.raw) if node.raw else _xml_escape(node.a1)
            boxes.append(
                f'<g><title>{tooltip}</title>'
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{box_w:.1f}" '
                f'height="{node_h}" rx="5" fill="{fill}" stroke="{stroke}" '
                f'stroke-width="1.5" />'
                f'<text x="{cx:.1f}" y="{y + node_h / 2 + 4:.1f}" '
                f'text-anchor="middle" font-size="13" fill="{text_fill}">'
                f'{_xml_escape(label)}</text></g>'
            )

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        f'font-family="sans-serif">',
        *edges,
        *boxes,
        "</svg>",
    ]
    return "\n".join(parts)
