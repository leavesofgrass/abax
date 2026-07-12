"""Render statistical charts as standalone SVG files — no GUI, no deps.

abax's chart engine returns plain SVG strings, so a script can save a
histogram, a bar chart, and a scatter plot straight to disk.
"""

import random
from pathlib import Path

from abax.core.science.chartsvg import bar_svg, histogram_svg, scatter_svg

random.seed(42)

out = Path("out")
out.mkdir(exist_ok=True)

# 1. Histogram of 60 noisy measurements.
values = [random.gauss(100, 15) for _ in range(60)]
(out / "histogram.svg").write_text(
    histogram_svg(values, bins=12, title="Measurements (n=60)"),
    encoding="utf-8",
)

# 2. Bar chart of revenue by quarter.
(out / "bars.svg").write_text(
    bar_svg(["Q1", "Q2", "Q3", "Q4"], [412, 380, 505, 611],
            title="Revenue by quarter"),
    encoding="utf-8",
)

# 3. Scatter of correlated (x, y) pairs.
points = [(x, 2.0 * x + random.gauss(0, 8)) for x in range(40)]
(out / "scatter.svg").write_text(
    scatter_svg(points, title="y = 2x + noise"),
    encoding="utf-8",
)

for name in ("histogram.svg", "bars.svg", "scatter.svg"):
    size = (out / name).stat().st_size
    print(f"wrote out/{name}  ({size:,} bytes)")
print("\nOpen them in any browser or image viewer.")
