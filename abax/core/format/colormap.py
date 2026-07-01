"""Perceptual colormaps for heatmaps (stdlib-only, Qt-free).

Maps a scalar to an ``(r, g, b)`` 0–255 tuple by linear interpolation between a
handful of control stops. Kept in ``core`` so the mapping is unit-testable without
Qt; the GUI heatmap (spectrogram) and any future colour grid use it.
"""

from __future__ import annotations

# 5-stop approximations of well-known perceptually-ordered colormaps.
PALETTES: dict[str, list[tuple[int, int, int]]] = {
    "viridis": [
        (68, 1, 84), (59, 82, 139), (33, 145, 140), (94, 201, 98), (253, 231, 37)],
    "magma": [
        (0, 0, 4), (81, 18, 124), (183, 55, 121), (252, 137, 97), (252, 253, 191)],
    "inferno": [
        (0, 0, 4), (87, 16, 110), (188, 55, 84), (249, 142, 9), (252, 255, 164)],
    "gray": [(0, 0, 0), (255, 255, 255)],
}


def colorize(value: float, vmin: float, vmax: float,
             palette: str = "viridis") -> tuple[int, int, int]:
    """Map ``value`` in ``[vmin, vmax]`` to an ``(r, g, b)`` colour.

    ``value`` is clamped to the range; an empty/zero range maps to the first stop.
    Unknown palette names fall back to ``"viridis"``.
    """
    stops = PALETTES.get(palette, PALETTES["viridis"])
    if vmax <= vmin:
        return stops[0]
    t = (value - vmin) / (vmax - vmin)
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    pos = t * (len(stops) - 1)
    i = int(pos)
    if i >= len(stops) - 1:
        return stops[-1]
    frac = pos - i
    a, b = stops[i], stops[i + 1]
    return (
        round(a[0] + (b[0] - a[0]) * frac),
        round(a[1] + (b[1] - a[1]) * frac),
        round(a[2] + (b[2] - a[2]) * frac),
    )
