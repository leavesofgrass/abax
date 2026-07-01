"""Tests for :mod:`abax.core.latexmath` — LaTeX → MathML / Unicode."""

from __future__ import annotations

from abax.core import latexmath

# --- to_unicode -------------------------------------------------------------

def test_unicode_superscript_digit() -> None:
    assert latexmath.to_unicode("x^2") == "x²"


def test_unicode_multi_digit_superscript() -> None:
    assert latexmath.to_unicode("x^{10}") == "x¹⁰"


def test_unicode_subscript_digit() -> None:
    assert latexmath.to_unicode("x_1") == "x₁"


def test_unicode_greek() -> None:
    assert latexmath.to_unicode("\\alpha") == "α"


def test_unicode_capital_greek() -> None:
    assert latexmath.to_unicode("\\Omega") == "Ω"


def test_unicode_frac_has_slash() -> None:
    assert "/" in latexmath.to_unicode("\\frac{a}{b}")


def test_unicode_sqrt_has_radical() -> None:
    assert "√" in latexmath.to_unicode("\\sqrt{x}")


def test_unicode_times() -> None:
    assert "×" in latexmath.to_unicode("a \\times b")


def test_unicode_assorted_operators() -> None:
    assert latexmath.to_unicode("\\le") == "≤"
    assert latexmath.to_unicode("\\ge") == "≥"
    assert latexmath.to_unicode("\\ne") == "≠"
    assert latexmath.to_unicode("\\approx") == "≈"
    assert latexmath.to_unicode("\\infty") == "∞"
    assert latexmath.to_unicode("\\pi") == "π"
    assert latexmath.to_unicode("\\div") == "÷"
    assert latexmath.to_unicode("\\cdot") == "·"
    assert latexmath.to_unicode("\\pm") == "±"
    assert latexmath.to_unicode("\\sum") == "∑"
    assert latexmath.to_unicode("\\int") == "∫"


def test_unicode_non_digit_superscript_falls_back() -> None:
    # multi-char / non-digit script renders as ^(...)
    assert latexmath.to_unicode("x^{a+b}") == "x^(a+b)"


def test_unicode_strips_braces() -> None:
    assert latexmath.to_unicode("{x}") == "x"


# --- to_mathml --------------------------------------------------------------

def test_mathml_contains_math_tag() -> None:
    assert "<math" in latexmath.to_mathml("x^2")


def test_mathml_falls_back_without_pandoc(monkeypatch) -> None:
    monkeypatch.setattr(latexmath, "pandoc_available", lambda: False)
    result = latexmath.to_mathml("x^2")
    assert "<math" in result
    assert "msup" in result


# --- _fallback_mathml -------------------------------------------------------

def test_fallback_superscript() -> None:
    assert "msup" in latexmath._fallback_mathml("x^2")


def test_fallback_subscript() -> None:
    assert "msub" in latexmath._fallback_mathml("x_1")


def test_fallback_frac() -> None:
    assert "mfrac" in latexmath._fallback_mathml("\\frac{a}{b}")


def test_fallback_sqrt() -> None:
    assert "msqrt" in latexmath._fallback_mathml("\\sqrt{x}")


def test_fallback_is_wellformed_math() -> None:
    out = latexmath._fallback_mathml("x^2")
    assert out.startswith("<math") and out.endswith("</math>")
    assert "mn" in out and "mi" in out


# --- pandoc_available -------------------------------------------------------

def test_pandoc_available_returns_bool() -> None:
    assert isinstance(latexmath.pandoc_available(), bool)
