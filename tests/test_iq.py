"""Tests for :mod:`abax.core.science.iq`: constellation, eye diagram, EVM, dBFS."""

from __future__ import annotations

import math

import pytest

from abax.core.science import iq

# --- constellation_points --------------------------------------------------


def test_constellation_points_basic():
    assert iq.constellation_points([1 + 1j, -1 - 1j]) == [(1.0, 1.0), (-1.0, -1.0)]


def test_constellation_points_empty():
    assert iq.constellation_points([]) == []


# --- eye_diagram -----------------------------------------------------------


def test_eye_diagram_ramp():
    samples = [complex(i) for i in range(16)]
    traces = iq.eye_diagram(samples, 4)
    # window = 8, step = 4: starts 0, 4, 8 -> 3 traces (start 12 needs 20).
    assert len(traces) == 3
    for t in traces:
        assert len(t) == 8
    assert traces[0] == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    assert traces[1] == [4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0]
    assert traces[2] == [8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0]


def test_eye_diagram_drops_trailing_partial():
    # 15 samples, sps=4 (window 8, step 4): starts 0, 4 -> 2 traces; start 8
    # would need index 15 (len 15 -> ok? 8+8=16 > 15) so dropped.
    samples = [complex(i) for i in range(15)]
    traces = iq.eye_diagram(samples, 4)
    assert len(traces) == 2


def test_eye_diagram_rejects_bad_sps():
    with pytest.raises(ValueError):
        iq.eye_diagram([1 + 0j], 0)
    with pytest.raises(ValueError):
        iq.eye_diagram([1 + 0j], -2)


# --- evm -------------------------------------------------------------------


def test_evm_identical_is_zero():
    seq = [1 + 1j, -1 + 0.5j, 0.25 - 0.75j]
    assert iq.evm(seq, seq) == pytest.approx(0.0)


def test_evm_known_offset():
    # Reference of unit-magnitude points; each measured point offset by 0.1
    # in-phase. mean(|err|^2) = 0.01, mean(|ref|^2) = 1.0 -> sqrt(0.01)*100 = 10%.
    reference = [1 + 0j, 0 + 1j, -1 + 0j, 0 - 1j]
    measured = [r + 0.1 for r in reference]
    assert iq.evm(measured, reference) == pytest.approx(10.0)


def test_evm_length_mismatch():
    with pytest.raises(ValueError):
        iq.evm([1 + 0j, 2 + 0j], [1 + 0j])


def test_evm_empty():
    with pytest.raises(ValueError):
        iq.evm([], [])


def test_evm_zero_power_reference():
    with pytest.raises(ValueError):
        iq.evm([1 + 0j, 2 + 0j], [0 + 0j, 0 + 0j])


# --- power_dbfs ------------------------------------------------------------


def test_power_dbfs_unit_magnitude_is_zero():
    # Unit-magnitude samples around the unit circle -> mean power 1.0 -> 0 dBFS.
    samples = [complex(math.cos(t), math.sin(t)) for t in (0.0, 1.0, 2.0, 3.0)]
    assert iq.power_dbfs(samples) == pytest.approx(0.0)


def test_power_dbfs_half_scale():
    # All samples magnitude 0.5 -> mean power 0.25 -> 10*log10(0.25) ~ -6.02 dB.
    samples = [0.5 + 0j] * 8
    assert iq.power_dbfs(samples) == pytest.approx(10.0 * math.log10(0.25))


def test_power_dbfs_all_zero_returns_floor():
    assert iq.power_dbfs([0 + 0j, 0 + 0j]) == -300.0


def test_power_dbfs_empty_returns_floor():
    assert iq.power_dbfs([]) == -300.0
