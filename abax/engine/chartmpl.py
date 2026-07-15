"""Matplotlib rendering backend for embedded charts — optional, with a fallback.

Renders the same :class:`~abax.core.chartobj.ChartObject` model as the
pure-stdlib SVG renderer, drawing from the identical
:func:`~abax.core.chartobj.chart_data` shaping pass — so the two backends
always show the same data, and a workbook authored with matplotlib installed
still renders everywhere else via the SVG path.

If matplotlib is not installed, :func:`render_chart_mpl` raises a descriptive
``RuntimeError`` telling the user how to enable it (the ``charts`` extra).
The engine layer never hard-requires it (see docs/architecture.md). Rendering
uses the object-oriented ``Figure`` API with an Agg canvas — no ``pyplot``,
no global state, safe off the GUI thread.
"""

from __future__ import annotations

import io
import math
import statistics

from ..core.chartobj import ChartError, ChartObject, chart_data

try:
    from matplotlib.backends.backend_agg import FigureCanvasAgg  # type: ignore
    from matplotlib.figure import Figure  # type: ignore

    HAS_MATPLOTLIB = True
except Exception:  # pragma: no cover - depends on the environment
    FigureCanvasAgg = None  # type: ignore
    Figure = None  # type: ignore
    HAS_MATPLOTLIB = False

_FALLBACK_MSG = (
    "Matplotlib chart rendering requires the 'matplotlib' package. "
    "Install it with:  pip install \"abax[charts]\"  (or pip install matplotlib). "
    "Charts still render everywhere via the built-in SVG renderer."
)

__all__ = ["HAS_MATPLOTLIB", "render_chart_mpl"]


def render_chart_mpl(workbook, host_sheet: str, chart: "ChartObject",
                     fmt: str = "png") -> "bytes | str":
    """Render ``chart`` with matplotlib; PNG bytes (default) or SVG text.

    Same contract as the stdlib renderer: pure, uncached, resolves ranges at
    call time (call again after a recalc), raises
    :class:`~abax.core.chartobj.ChartError` for model problems and
    ``RuntimeError`` when matplotlib is missing.
    """
    if not HAS_MATPLOTLIB:
        raise RuntimeError(_FALLBACK_MSG)
    if fmt not in ("png", "svg"):
        raise ValueError(f"fmt must be 'png' or 'svg', not {fmt!r}")

    data = chart_data(workbook, host_sheet, chart)
    fig = Figure(figsize=(data["width"] / 100, data["height"] / 100), dpi=100)
    FigureCanvasAgg(fig)  # attach a canvas; print_figure handles both formats
    ax = fig.subplots()
    _draw(ax, fig, data)
    if data["title"]:
        ax.set_title(data["title"])
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format=fmt)
    raw = buf.getvalue()
    return raw.decode("utf-8") if fmt == "svg" else raw


def _draw(ax, fig, data: dict) -> None:
    kind = data["kind"]
    if kind == "line":
        for name, pts in data["series"]:
            if pts:
                xs, ys = zip(*pts)
                ax.plot(xs, ys, label=name)
        if data["series"]:
            ax.legend(fontsize="small")
        ax.grid(True, alpha=0.3)
    elif kind == "bar":
        ax.bar(range(len(data["values"])), data["values"])
        _categories(ax, data["categories"], len(data["values"]))
    elif kind == "scatter":
        if data["points"]:
            xs, ys = zip(*data["points"])
            ax.scatter(xs, ys, s=12)
        ax.grid(True, alpha=0.3)
    elif kind == "histogram":
        if data["values"]:
            ax.hist(data["values"], bins=int(data.get("bins", 10)))
    elif kind == "box":
        names = [n for n, _v in data["series"]]
        ax.boxplot([v for _n, v in data["series"]] or [[]])
        _categories(ax, names, len(names), start=1)
    elif kind == "violin":
        series = [(n, v) for n, v in data["series"] if v]
        if series:
            ax.violinplot([v for _n, v in series], showmedians=True)
            _categories(ax, [n for n, _v in series], len(series), start=1)
    elif kind == "qq":
        _qq(ax, data["values"])
    elif kind == "ecdf":
        for name, vals in data["series"]:
            if vals:
                xs = sorted(vals)
                ys = [(i + 1) / len(xs) for i in range(len(xs))]
                ax.step(xs, ys, where="post", label=name)
        if data["series"]:
            ax.legend(fontsize="small")
        ax.set_ylim(0, 1.05)
        ax.grid(True, alpha=0.3)
    elif kind == "heatmap":
        im = ax.imshow(data["matrix"], cmap="viridis", aspect="auto")
        fig.colorbar(im, ax=ax, shrink=0.8)
        labels = data.get("labels")
        if labels:
            n = len(labels)
            ax.set_yticks(range(n), labels)
            ax.set_xticks(range(n), labels, rotation=45, ha="right")
    elif kind == "waterfall":
        _waterfall(ax, data["categories"], data["values"],
                   total=bool(data.get("total", True)))
    else:  # unreachable: chart_data validated the kind already
        raise ChartError(f"unknown chart kind {kind!r}")


def _categories(ax, labels, n: int, start: int = 0) -> None:
    """Category tick labels, thinned so long axes stay readable."""
    if not n:
        return
    step = max(1, math.ceil(n / 20))
    idx = list(range(0, n, step))
    ax.set_xticks([i + start for i in idx],
                  [str(labels[i]) for i in idx], rotation=45, ha="right")


def _qq(ax, values) -> None:
    """Normal Q-Q: sample quantiles against theoretical normal quantiles."""
    vals = sorted(values)
    n = len(vals)
    if n < 2:
        return
    nd = statistics.NormalDist(statistics.fmean(vals), statistics.stdev(vals))
    theo = [nd.inv_cdf((i + 0.5) / n) for i in range(n)]
    ax.scatter(theo, vals, s=12)
    lo, hi = min(theo[0], vals[0]), max(theo[-1], vals[-1])
    ax.plot([lo, hi], [lo, hi], linewidth=1)
    ax.set_xlabel("theoretical")
    ax.set_ylabel("sample")
    ax.grid(True, alpha=0.3)


def _waterfall(ax, labels, deltas, *, total: bool) -> None:
    labs = [str(x) for x in labels][:len(deltas)]
    running = 0.0
    for i, d in enumerate(deltas):
        bottom = running if d >= 0 else running + d
        ax.bar(i, abs(d), bottom=bottom,
               color="#2a7" if d >= 0 else "#c44")
        running += d
    if total:
        ax.bar(len(deltas), abs(running),
               bottom=min(0.0, running), color="#579")
        labs.append("total")
    ax.axhline(0, linewidth=0.8, color="#666")
    _categories(ax, labs, len(labs))
