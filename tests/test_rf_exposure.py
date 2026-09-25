"""RF exposure estimates (abax.core.science.rf_exposure).

Besides spot values from 47 CFR § 1.1310 and § 1.1307, two independent checks
guard the transcription of the tables:

* plane-wave consistency — where § 1.1310 lists both an E-field and a power
  density, E²/377 Ω must equal the power density;
* the § 1.1307(b)(3)(i)(C) exemption table must equal the general-population
  power-density limit under full reflection applied to ERP:
  ERP = S·πR² / 1.64 (to the rule's rounding).
"""

from __future__ import annotations

import math

import pytest

from abax.core.science import rf_exposure as X


@pytest.mark.parametrize("f, tier, want", [
    (1.0, "uncontrolled", 100.0),
    (14.2, "uncontrolled", 180.0 / 14.2 ** 2),
    (14.2, "controlled", 900.0 / 14.2 ** 2),
    (50.0, "uncontrolled", 0.2), (146.0, "controlled", 1.0),
    (440.0, "uncontrolled", 440.0 / 1500.0), (440.0, "controlled", 440.0 / 300.0),
    (2400.0, "uncontrolled", 1.0), (10_368.0, "controlled", 5.0),
])
def test_mpe_power_density_table(f, tier, want):
    assert X.mpe_power_density(f, tier) == pytest.approx(want)


def test_mpe_boundary_uses_more_restrictive_row():
    # 1.34 MHz is in both general-population rows: 100 vs 180/1.34² = 100.25
    assert X.mpe_power_density(1.34, "uncontrolled") == 100.0
    assert X.mpe_power_density(300.0, "uncontrolled") == pytest.approx(0.2)


def test_mpe_fields_and_averaging():
    lim = X.mpe_limits(14.2, "general")
    assert lim["e_field"] == pytest.approx(824 / 14.2)
    assert lim["h_field"] == pytest.approx(2.19 / 14.2)
    assert lim["averaging_minutes"] == 30
    lim = X.mpe_limits(440.0, "occupational")
    assert lim["e_field"] is None and lim["h_field"] is None
    assert lim["averaging_minutes"] == 6


@pytest.mark.parametrize("f", [0.5, 2.0, 7.0, 14.2, 29.0, 50.0, 146.0, 222.0])
@pytest.mark.parametrize("tier", ["controlled", "uncontrolled"])
def test_plane_wave_consistency(f, tier):
    lim = X.mpe_limits(f, tier)
    s_from_e = lim["e_field"] ** 2 / 377.0 / 10.0      # W/m² -> mW/cm²
    assert s_from_e == pytest.approx(lim["power_density"], rel=0.01)


@pytest.mark.parametrize("f", [0.5, 1.0, 3.5, 7.0, 14.2, 28.0, 50.0, 146.0, 440.0,
                               902.0, 1296.0, 2400.0, 5760.0, 10_368.0])
def test_exemption_table_is_full_reflection_model(f):
    r = max(10.0, 2 * X.exemption_min_distance(f))
    s_w_m2 = 10.0 * X.mpe_power_density(f, "uncontrolled")
    model = s_w_m2 * math.pi * r * r / X.DIPOLE_GAIN
    assert X.exemption_threshold_erp(f, r) == pytest.approx(model, rel=0.005)


def test_exemption_threshold_values_and_limits():
    assert X.exemption_threshold_erp(146.0, 5.0) == pytest.approx(3.83 * 25)
    assert X.exemption_threshold_erp(14.2, 10.0) == pytest.approx(3450 * 100 / 14.2 ** 2)
    assert X.exemption_min_distance(14.2) == pytest.approx(3.36, abs=0.01)
    with pytest.raises(ValueError):                      # closer than λ/2π
        X.exemption_threshold_erp(14.2, 3.0)
    with pytest.raises(ValueError):                      # 2200 m band is below the table
        X.exemption_threshold_erp(0.1375, 1000.0)


def test_power_density_and_compliance_distance():
    assert X.power_density(100.0, 1.0) == pytest.approx(100 / (4 * math.pi) / 10)
    assert X.power_density(100.0, 1.0, 4.0) == pytest.approx(4 * X.power_density(100.0, 1.0))
    for tier in X.TIERS:
        r = X.compliance_distance(500.0, 28.4, tier, 4.0)
        assert X.power_density(500.0, r, 4.0) == pytest.approx(X.mpe_power_density(28.4, tier))
    # controlled limits are looser, so the controlled distance is shorter
    assert X.compliance_distance(500, 28.4, "controlled") < X.compliance_distance(500, 28.4)
    with pytest.raises(ValueError):
        X.power_density(1.0, 0.0)


def test_percent_of_mpe_and_five_percent_rule():
    lim = X.mpe_power_density(146.0, "uncontrolled")
    assert X.percent_of_mpe(lim * 0.05, 146.0) == pytest.approx(5.0)


def test_sar():
    assert X.sar_limit("uncontrolled", "whole_body") == 0.08
    assert X.sar_limit("general", "peak") == 1.6
    assert X.sar_limit("controlled", "extremity") == 20.0
    assert X.sar_limit("occupational", "1g") == 8.0
    assert X.sar(0.5, 40.0, 1000.0) == pytest.approx(0.8)
    with pytest.raises(ValueError):
        X.sar_limit("uncontrolled", "brain")
    with pytest.raises(ValueError):
        X.sar(0.5, 40.0, 0.0)


def test_average_power_and_tiers():
    assert X.average_power(100.0, 0.5, 0.5) == 25.0
    for bad in ((100, 1.5, 1), (100, 0.5, -0.1), (-1, 1, 1)):
        with pytest.raises(ValueError):
            X.average_power(*bad)
    assert X.normalize_tier("General Population") == "uncontrolled"
    assert X.normalize_tier("occupational/controlled") == "controlled"
    with pytest.raises(ValueError):
        X.normalize_tier("neighbor")
    with pytest.raises(ValueError):
        X.mpe_limits(0.1375, "uncontrolled")


def test_evaluate_station_chain():
    ev = X.evaluate_station(f_mhz=14.2, power_w=1500, feedline_loss_db=1.0, gain_dbi=8.0,
                            duty_cycle=0.5, tx_fraction=0.5, reflection=4.0,
                            distance_m=15.0)
    p_ant = 1500 * 0.25 * 10 ** (-0.1)
    assert ev["avg_power_w"] == pytest.approx(p_ant)
    assert ev["eirp_w"] == pytest.approx(p_ant * 10 ** 0.8)
    assert ev["erp_w"] == pytest.approx(ev["eirp_w"] / 1.64)
    assert ev["density"] == pytest.approx(X.power_density(ev["eirp_w"], 15.0, 4.0))
    assert ev["percent"]["uncontrolled"] > ev["percent"]["controlled"]
    assert ev["exempt"] is (ev["erp_w"] <= ev["exempt_threshold_erp_w"])
    near = X.evaluate_station(f_mhz=14.2, power_w=100, distance_m=1.0)
    assert near["exempt_threshold_erp_w"] is None and near["exempt"] is None
    with pytest.raises(ValueError):
        X.evaluate_station(f_mhz=14.2, power_w=100, feedline_loss_db=-1)
