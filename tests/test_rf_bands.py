"""Amateur band-plan + CTCSS reference data and the HAMBAND / CTCSS formulas."""

from __future__ import annotations

import pytest

from abax.core.science import rf_bands as B


def test_band_for_frequency_known_bands():
    assert B.band_for_frequency(14_100_000) == "20m"     # 20 m phone
    assert B.band_for_frequency(7_050_000) == "40m"
    assert B.band_for_frequency(146_520_000) == "2m"     # national simplex
    assert B.band_for_frequency(28_400_000) == "10m"
    assert B.band_for_frequency(1_800_000) == "160m"     # inclusive lower edge
    assert B.band_for_frequency(2_000_000) == "160m"     # inclusive upper edge


def test_band_for_frequency_outside_any_band():
    assert B.band_for_frequency(13_000_000) is None      # between 30 m and 20 m
    assert B.band_for_frequency(100_000) is None


def test_band_edges_roundtrip():
    assert B.band_edges("20m") == (14_000_000, 14_350_000)
    assert B.band_edges(" 2M ") == (144_000_000, 148_000_000)   # case/space tolerant
    with pytest.raises(ValueError):
        B.band_edges("11m")


def test_ctcss_tone_numbering():
    assert B.ctcss_tone(1) == 67.0
    assert B.ctcss_tone(13) == 100.0
    assert B.ctcss_tone(50) == 254.1
    assert len(B.CTCSS_TONES) == 50
    with pytest.raises(ValueError):
        B.ctcss_tone(0)
    with pytest.raises(ValueError):
        B.ctcss_tone(51)


def test_nearest_ctcss():
    assert B.nearest_ctcss(100.1) == 100.0
    assert B.nearest_ctcss(110.0) == 110.9    # 0.9 away beats 107.2 (2.8 away)
    assert B.nearest_ctcss(67.0) == 67.0
    assert B.nearest_ctcss(300.0) == 254.1    # clamps to the top tone


def test_formula_integration():
    from abax.core.functions import FUNCTIONS

    assert FUNCTIONS["HAMBAND"]([14_100_000]) == "20m"
    from abax.core.errors import CellError

    assert isinstance(FUNCTIONS["HAMBAND"]([13_000_000]), CellError)   # #N/A
    assert FUNCTIONS["CTCSSTONE"]([13]) == 100.0
    assert isinstance(FUNCTIONS["CTCSSTONE"]([99]), CellError)         # #NUM!
    assert FUNCTIONS["NEARESTCTCSS"]([100.1]) == 100.0
