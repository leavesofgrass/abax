"""Oracle tests for the pure-stdlib Smith-chart SVG generator.

The z -> Gamma -> (x, y) mapping must be exactly right: z=1 lands at the chart
centre, a short (z=0) at the left edge, an open (z->inf) at the right edge, and a
known z=2 case one third of the way out on the positive real axis.
"""

from __future__ import annotations

import math

from abax.core.science import smithsvg

# A concrete chart geometry to map into (matches smith_svg's defaults).
_SIZE = 360
_MARGIN = 18
_CX = _CY = _SIZE / 2.0
_RADIUS = _SIZE / 2.0 - _MARGIN


def _xy(z, z0=50.0):
    return smithsvg.impedance_to_xy(z, z0, _CX, _CY, _RADIUS)


def test_matched_load_maps_to_centre():
    # z = 1 (Z = Z0 = 50) -> Gamma = 0 -> chart centre.
    x, y = _xy(50.0)
    assert math.isclose(x, _CX, abs_tol=1e-9)
    assert math.isclose(y, _CY, abs_tol=1e-9)


def test_short_maps_to_left_edge():
    # z = 0 (Z = 0) -> Gamma = -1 -> left edge of the unit circle.
    x, y = _xy(0.0)
    assert math.isclose(x, _CX - _RADIUS, abs_tol=1e-9)
    assert math.isclose(y, _CY, abs_tol=1e-9)


def test_open_maps_to_right_edge():
    # z -> inf (large resistance) -> Gamma ~ +1 -> right edge.
    x, y = _xy(1e6)
    # z = 1e6/50 = 20000 -> Gamma ~ 0.9999, essentially the right edge.
    assert math.isclose(x, _CX + _RADIUS, abs_tol=0.05)
    assert x < _CX + _RADIUS  # strictly inside the unit circle
    assert math.isclose(y, _CY, abs_tol=1e-9)


def test_z_equals_two_maps_to_one_third():
    # z = 2 -> Gamma = (2-1)/(2+1) = 1/3 on the positive real axis.
    x, y = _xy(100.0)  # Z = 100 on Z0 = 50 => z = 2
    assert math.isclose(x, _CX + _RADIUS / 3.0, abs_tol=1e-9)
    assert math.isclose(y, _CY, abs_tol=1e-9)


def test_gamma_to_xy_imag_axis_points_up():
    # +j Gamma must plot upward (smaller SVG y).
    x, y = smithsvg.gamma_to_xy(complex(0.0, 0.5), _CX, _CY, _RADIUS)
    assert math.isclose(x, _CX, abs_tol=1e-9)
    assert y < _CY  # up on screen


def test_accepts_rx_pair_and_complex_equivalently():
    a = _xy(complex(75.0, 25.0))
    b = _xy((75.0, 25.0))
    assert math.isclose(a[0], b[0], abs_tol=1e-9)
    assert math.isclose(a[1], b[1], abs_tol=1e-9)


def test_returns_nonempty_svg_string():
    svg = smithsvg.smith_svg([complex(75.0, 25.0)], z0=50.0, show_vswr=True,
                             title="test")
    assert isinstance(svg, str) and svg
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    # The plotted load should appear as a marker circle in the output.
    assert "<circle" in svg


def test_empty_points_still_draws_the_grid():
    svg = smithsvg.smith_svg([], z0=50.0)
    assert svg.startswith("<svg")
    # Outer unit circle + resistance/reactance grid are always present.
    assert svg.count("<circle") >= len(smithsvg._R_CIRCLES)


def test_vswr_circle_radius_matches_gamma_magnitude():
    # A load giving |Gamma| = 1/3 should draw a VSWR circle of radius R/3.
    svg = smithsvg.smith_svg([100.0], z0=50.0, show_vswr=True)
    assert f'r="{_RADIUS / 3.0:.2f}"' in svg
