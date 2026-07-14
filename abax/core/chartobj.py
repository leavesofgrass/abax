"""Embedded chart objects: sheet-anchored charts persisted in the envelope.

A :class:`ChartObject` records *what* to draw (a chart kind from
``core/science/chartsvg.py``), *from where* (an A1 source range, optionally
sheet-qualified, resolved at render time so a recalc is all it takes to
refresh the picture), and *where it sits* (a cell anchor + pixel size).
The objects live on ``Sheet.charts`` and round-trip through the workbook
envelope (schema v3, additive — older files simply have none).

Rendering is pure: :func:`render_chart` reads current cell values through
the normal evaluation path and returns an SVG string. Nothing here caches,
so "re-render on recalc" is just calling it again.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .reference import parse_a1, to_a1

__all__ = ["CHART_KINDS", "ChartError", "ChartObject", "chart_data",
           "new_chart_id", "render_chart"]

# Kinds render through the matching *_svg function in core/science/chartsvg.py.
# sunburst/treemap need hierarchical input and sparkline is a formula function,
# so none of those are embeddable kinds.
CHART_KINDS = ("line", "bar", "scatter", "histogram", "box", "violin",
               "qq", "ecdf", "heatmap", "waterfall")

# Kind-specific options forwarded to the renderer (anything else is ignored,
# so an option written by a newer abax never breaks an older one).
_KIND_OPTIONS = {
    "histogram": ("bins",),
    "waterfall": ("total",),
}


class ChartError(ValueError):
    """A chart can't be rendered (unknown kind, missing sheet, dead range)."""


@dataclass
class ChartObject:
    """One embedded chart, anchored to a cell of its host sheet."""

    id: str
    kind: str                      # one of CHART_KINDS (validated at render)
    source: str                    # data range, e.g. "A1:C10" or "Data!A1:C10"
    title: str = ""
    labels: str = ""               # optional category/label range (bar/waterfall/heatmap)
    anchor: Tuple[int, int] = (0, 0)   # (row, col) the top-left corner floats over
    width: int = 480
    height: int = 320
    options: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d: dict = {
            "id": self.id,
            "kind": self.kind,
            "source": self.source,
            "anchor": [self.anchor[0], self.anchor[1]],
            "width": self.width,
            "height": self.height,
        }
        # Omitted when empty to keep files lean (older readers ignore extras).
        if self.title:
            d["title"] = self.title
        if self.labels:
            d["labels"] = self.labels
        if self.options:
            d["options"] = dict(self.options)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ChartObject":
        anchor = d.get("anchor") or [0, 0]
        return cls(
            id=str(d.get("id", "")),
            kind=str(d.get("kind", "")),
            source=str(d.get("source", "")),
            title=str(d.get("title", "")),
            labels=str(d.get("labels", "")),
            anchor=(int(anchor[0]), int(anchor[1])),
            width=int(d.get("width", 480)),
            height=int(d.get("height", 320)),
            options=dict(d.get("options", {})),
        )


def new_chart_id(existing: "list[ChartObject]") -> str:
    """Smallest unused ``chartN`` id among ``existing``."""
    taken = {ch.id for ch in existing}
    n = 1
    while f"chart{n}" in taken:
        n += 1
    return f"chart{n}"


# --- range resolution ------------------------------------------------------

def _split_range(ref: str, host_sheet: str) -> Tuple[str, str, str]:
    """``"Data!A1:C10"`` -> ``("Data", "A1", "C10")`` (host sheet when bare)."""
    sheet = host_sheet
    body = ref.strip()
    if "!" in body:
        sheet, body = body.rsplit("!", 1)
        sheet = sheet.strip("'")
    if ":" in body:
        a, b = body.split(":", 1)
    else:
        a = b = body
    return sheet, a.strip(), b.strip()


def _load_grid(workbook, host_sheet: str, ref: str) -> List[List[Any]]:
    """Resolve an A1 range to a rectangle of computed cell values."""
    if not ref.strip():
        raise ChartError("chart has no source range (it may have been deleted)")
    sheet_name, a, b = _split_range(ref, host_sheet)
    sheet = workbook.get_sheet(sheet_name)
    if sheet is None:
        raise ChartError(f"chart source sheet {sheet_name!r} does not exist")
    try:
        r1, c1 = parse_a1(a)
        r2, c2 = parse_a1(b)
    except Exception:
        raise ChartError(f"chart source range {ref!r} is not a valid A1 range")
    if r2 < r1:
        r1, r2 = r2, r1
    if c2 < c1:
        c1, c2 = c2, c1
    return [[sheet.get_value(r, c) for c in range(c1, c2 + 1)]
            for r in range(r1, r2 + 1)]


def _num(v: Any) -> Optional[float]:
    """Coerce a cell value to float; ``None`` for text/blank/error values."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", "")) if v.strip() else None
        except ValueError:
            return None
    return None


def _has_header(grid: List[List[Any]]) -> bool:
    """First row is a header when it has text and no numbers."""
    if len(grid) < 2:
        return False
    first = grid[0]
    texts = [v for v in first if v not in (None, "")]
    return bool(texts) and all(_num(v) is None for v in texts)


def _column_series(grid: List[List[Any]]) -> List[Tuple[str, List[float]]]:
    """Each column becomes a named series of its numeric values."""
    if not grid:
        return []
    header = _has_header(grid)
    body = grid[1:] if header else grid
    ncols = max(len(r) for r in grid)
    series: List[Tuple[str, List[float]]] = []
    for c in range(ncols):
        if header and c < len(grid[0]) and grid[0][c] not in (None, ""):
            name = str(grid[0][c])
        else:
            name = to_a1(0, c).rstrip("1")  # bare column letter
        vals = [n for row in body
                if c < len(row) and (n := _num(row[c])) is not None]
        if vals:
            series.append((name, vals))
    return series


def _flat_numeric(grid: List[List[Any]]) -> List[float]:
    body = grid[1:] if _has_header(grid) else grid
    return [n for row in body for v in row if (n := _num(v)) is not None]


def _labels_or_default(workbook, host_sheet: str, chart: "ChartObject",
                       n: int) -> List[str]:
    """The labels range flattened to strings, else ``1..n``."""
    if chart.labels:
        grid = _load_grid(workbook, host_sheet, chart.labels)
        labs = [str(v) for row in grid for v in row if v not in (None, "")]
        if labs:
            return labs[:n] + [""] * max(0, n - len(labs))
    return [str(i + 1) for i in range(n)]


# --- data shaping ----------------------------------------------------------

def chart_data(workbook, host_sheet: str, chart: "ChartObject") -> Dict[str, Any]:
    """Resolve ``chart``'s ranges into render-ready data (backend-neutral).

    Every rendering backend (the stdlib SVG renderer here, the optional
    matplotlib backend in the engine layer, future exporters) draws from this
    one shaping pass, so they all show identical data. The returned dict
    always has ``kind``/``title``/``width``/``height`` plus the kind's shape:
    ``series`` (line: ``[(name, [(x, y), …])]``; box/violin/ecdf:
    ``[(name, values)]``), ``points`` (scatter), ``values`` (+ ``bins``)
    for histogram/qq, ``matrix`` + ``labels`` (heatmap), or ``categories`` +
    ``values`` (+ ``total``) for bar/waterfall.

    Raises :class:`ChartError` for an unknown kind, a missing sheet, or a
    dead source range.
    """
    if chart.kind not in CHART_KINDS:
        raise ChartError(f"unknown chart kind {chart.kind!r} "
                         f"(expected one of {', '.join(CHART_KINDS)})")
    grid = _load_grid(workbook, host_sheet, chart.source)
    out: Dict[str, Any] = {"kind": chart.kind, "title": chart.title or "",
                           "width": chart.width, "height": chart.height}
    for opt in _KIND_OPTIONS.get(chart.kind, ()):
        if opt in chart.options:
            out[opt] = chart.options[opt]

    if chart.kind == "line":
        series = _column_series(grid)
        pts = [(name, list(enumerate(vals, start=1))) for name, vals in series]
        if chart.options.get("first_col_x") and len(series) >= 2:
            xs = series[0][1]
            pts = [(name, list(zip(xs, vals))) for name, vals in series[1:]]
        out["series"] = pts
    elif chart.kind in ("box", "violin", "ecdf"):
        out["series"] = _column_series(grid)
    elif chart.kind == "scatter":
        body = grid[1:] if _has_header(grid) else grid
        out["points"] = [(x, y) for row in body
                         if len(row) >= 2
                         and (x := _num(row[0])) is not None
                         and (y := _num(row[1])) is not None]
    elif chart.kind in ("histogram", "qq"):
        out["values"] = _flat_numeric(grid)
    elif chart.kind == "heatmap":
        body = grid[1:] if _has_header(grid) else grid
        matrix = [[n if (n := _num(v)) is not None else 0.0 for v in row]
                  for row in body if any(_num(v) is not None for v in row)]
        if not matrix:
            raise ChartError("heatmap source range has no numeric data")
        width = max(len(r) for r in matrix)
        out["matrix"] = [r + [0.0] * (width - len(r)) for r in matrix]
        labels = None
        if chart.labels:
            labs = _labels_or_default(workbook, host_sheet, chart, len(matrix))
            labels = labs if len(labs) == len(matrix) else None
        out["labels"] = labels
    else:  # bar / waterfall: labels range, first text column, or 1..n
        body = grid[1:] if _has_header(grid) else grid
        first_col_text = (body and all(
            _num(row[0]) is None and row and row[0] not in (None, "")
            for row in body if row))
        if first_col_text and any(len(row) >= 2 for row in body):
            cats = [str(row[0]) for row in body if row]
            vals = [n for row in body
                    if len(row) >= 2 and (n := _num(row[1])) is not None]
            cats = cats[:len(vals)]
        else:
            vals = _flat_numeric(grid)
            cats = _labels_or_default(workbook, host_sheet, chart, len(vals))
        out["categories"] = cats
        out["values"] = vals
    return out


# --- rendering -------------------------------------------------------------

def render_chart(workbook, host_sheet: str, chart: "ChartObject") -> str:
    """Render ``chart`` against current cell values; returns SVG text.

    Pure and uncached: call again after a recalc for a fresh picture. Raises
    :class:`ChartError` for an unknown kind, a missing sheet, or a dead/empty
    source range — callers that must never fail (a paint loop) catch it and
    draw their own placeholder.
    """
    from .science import chartsvg

    data = chart_data(workbook, host_sheet, chart)
    kind = data["kind"]
    kw: Dict[str, Any] = {"title": data["title"],
                          "width": data["width"], "height": data["height"]}
    if kind == "line":
        return chartsvg.line_svg(data["series"], **kw)
    if kind in ("box", "violin", "ecdf"):
        return getattr(chartsvg, f"{kind}_svg")(data["series"], **kw)
    if kind == "scatter":
        return chartsvg.scatter_svg(data["points"], **kw)
    if kind == "histogram":
        return chartsvg.histogram_svg(data["values"],
                                      bins=data.get("bins", 10), **kw)
    if kind == "qq":
        return chartsvg.qq_svg(data["values"], **kw)
    if kind == "heatmap":
        return chartsvg.heatmap_svg(data["matrix"], data["labels"], **kw)
    if kind == "waterfall":
        return chartsvg.waterfall_svg(data["categories"], data["values"],
                                      total=data.get("total", True), **kw)
    return chartsvg.bar_svg(data["categories"], data["values"], **kw)
