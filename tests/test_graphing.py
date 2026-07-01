"""HP-48 style function graphing (abax.core.graphing)."""

from __future__ import annotations

import math

import pytest

from abax.core.graphing import GraphError, braille_plot, compile_expr, sample

# -- compile_expr -----------------------------------------------------------


def test_caret_is_power():
    assert compile_expr("x^2")(3) == 9


def test_sin_of_zero():
    assert compile_expr("sin(x)")(0) == 0


def test_compile_constants_and_funcs():
    f = compile_expr("sqrt(x) + pi")
    assert f(4) == pytest.approx(2.0 + math.pi)


def test_bad_syntax_raises():
    with pytest.raises(GraphError):
        compile_expr("x +")


def test_import_raises():
    with pytest.raises(GraphError):
        compile_expr("import os")


def test_unknown_name_raises():
    with pytest.raises(GraphError):
        compile_expr("foobar(x)")


def test_domain_error_at_zero_still_compiles():
    # log(x) is undefined at x=0 but the expression is valid.
    f = compile_expr("log(x)")
    assert f(1) == pytest.approx(0.0)


# -- sample -----------------------------------------------------------------


def test_sample_has_none_at_singularity():
    pts = sample("1/x", -1, 1, 5)
    ys = [y for (_x, y) in pts]
    assert None in ys
    # The singularity sits at x == 0 (the middle of 5 points).
    mid_x, mid_y = pts[2]
    assert mid_x == pytest.approx(0.0)
    assert mid_y is None


def test_sample_identity():
    pts = sample("x", 0, 10, 11)
    assert len(pts) == 11
    for x, y in pts:
        assert y == pytest.approx(x)


def test_sample_endpoints():
    pts = sample("x", -5, 5, 11)
    assert pts[0][0] == pytest.approx(-5.0)
    assert pts[-1][0] == pytest.approx(5.0)


def test_sample_accepts_callable():
    f = compile_expr("x*2")
    pts = sample(f, 0, 3, 4)
    assert [y for (_x, y) in pts] == pytest.approx([0, 2, 4, 6])


# -- braille_plot -----------------------------------------------------------


def test_braille_plot_dimensions():
    out = braille_plot(sample("x^2", -3, 3, 120))
    lines = out.split("\n")
    assert len(lines) == 22  # default height
    for line in lines:
        assert len(line) <= 70  # default width


def test_braille_plot_custom_size():
    out = braille_plot(sample("x", -1, 1, 40), width=30, height=10)
    lines = out.split("\n")
    assert len(lines) == 10
    for line in lines:
        assert len(line) <= 30


def test_braille_plot_has_nonblank():
    out = braille_plot(sample("x^2", -3, 3, 120))
    assert any(ord(ch) > 0x2800 for ch in out)


def test_braille_plot_all_braille_chars():
    out = braille_plot(sample("sin(x)", -math.pi, math.pi, 80))
    for ch in out:
        if ch == "\n":
            continue
        assert 0x2800 <= ord(ch) <= 0x28FF


def test_braille_plot_empty_points():
    # No finite points: still returns a well-formed canvas.
    out = braille_plot([(0.0, None), (1.0, None)], width=20, height=6)
    lines = out.split("\n")
    assert len(lines) == 6
