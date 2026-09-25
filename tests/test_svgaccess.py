"""Accessible SVG output: the helper and the radio charts that use it."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest

from abax.core.science import antenna, smithsvg
from abax.core.science.svgaccess import make_accessible

NS = "{http://www.w3.org/2000/svg}"


def _root(svg: str):
    return ET.fromstring(svg)


def _check(svg: str, title: str, desc_part: str) -> None:
    root = _root(svg)                                  # still well-formed XML
    assert root.get("role") == "img"
    ids = root.get("aria-labelledby").split()
    t, d = root[0], root[1]
    assert t.tag == NS + "title" and t.text == title and t.get("id") == ids[0]
    assert d.tag == NS + "desc" and desc_part in d.text and d.get("id") == ids[1]


def test_make_accessible_basic_and_escaping():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect/></svg>'
    out = make_accessible(svg, 'A & B "chart"', "x < y")
    _check(out, 'A & B "chart"', "x < y")
    assert "&amp;" in out and "&lt;" in out


def test_make_accessible_self_closing_and_title_only():
    out = make_accessible('<svg xmlns="http://www.w3.org/2000/svg"/>', "Empty")
    root = _root(out)
    assert root.get("aria-labelledby").count(" ") == 0 and root[0].text == "Empty"
    with pytest.raises(ValueError):
        make_accessible("<g/>", "x")
    with pytest.raises(ValueError):
        make_accessible("<svg/>", "  ")


def test_ids_differ_between_charts():
    a = smithsvg.smith_svg([(75, 25)], 50)
    b = smithsvg.smith_svg([(25, -10)], 50)
    ids = [re.search(r'aria-labelledby="([^"]+)"', s).group(1) for s in (a, b)]
    assert ids[0] != ids[1]


def test_smith_svg_is_described():
    svg = smithsvg.smith_svg([(75, 25)], 50, show_vswr=True)
    _check(svg, "Smith chart", "75 plus j25 ohms")
    assert "VSWR 1.77 to 1" in svg
    custom = smithsvg.smith_svg([], 50, title="Empty chart", description="Nothing here.")
    _check(custom, "Empty chart", "Nothing here.")


def test_polar_svg_linear_and_db_descriptions_agree():
    lin = antenna.pattern_samples(antenna.half_wave_dipole())
    db = antenna.pattern_samples(antenna.half_wave_dipole(), decibels=True)
    t_lin = antenna.describe_polar(lin)
    t_db = antenna.describe_polar(db, decibels=True)
    cover = re.compile(r"over about (\d+) degrees")
    # both scalings measure the same −3 dB (half-power) coverage
    assert cover.search(t_lin).group(1) == cover.search(t_db).group(1)
    assert "Maximum 0.0 dB at 90 degrees" in t_db and "-0.0" not in t_db
    _check(antenna.polar_svg(lin, title="Half-wave dipole"), "Half-wave dipole",
           "Maximum 1.00 at 90 degrees")
    assert antenna.describe_polar([]) == "Polar radiation pattern with no data."
