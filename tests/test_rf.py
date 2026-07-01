"""RF / ham-radio math — validated against textbook values."""

from __future__ import annotations

import math

import pytest

from abax.core.science import rf

# --- power / level ---------------------------------------------------------

def test_power_level_conversions():
    assert rf.dbm_to_w(0.0) == pytest.approx(1e-3)
    assert rf.dbm_to_w(30.0) == pytest.approx(1.0)
    assert rf.w_to_dbm(1e-3) == pytest.approx(0.0)
    assert rf.w_to_dbm(1.0) == pytest.approx(30.0)
    assert rf.db_to_ratio(3.0) == pytest.approx(1.9953, abs=1e-3)
    assert rf.ratio_to_db(2.0) == pytest.approx(3.0103, abs=1e-3)
    assert rf.db_add(0.0, 0.0) == pytest.approx(3.0103, abs=1e-3)   # 1mW+1mW = 2mW
    assert rf.dbuv_to_dbm(106.9897, 50.0) == pytest.approx(0.0, abs=1e-3)  # exact 50Ω offset
    assert rf.s_unit_to_dbm(9) == pytest.approx(-73.0)
    assert rf.s_unit_to_dbm(1) == pytest.approx(-121.0)


def test_noise():
    assert rf.noise_floor_dbm(1.0, 290.0) == pytest.approx(-174.0, abs=0.1)
    assert rf.noise_floor_dbm(1e6, 290.0) == pytest.approx(-114.0, abs=0.1)
    # NF <-> noise temperature round-trip
    assert rf.noise_temp_to_nf(rf.nf_to_noise_temp(3.0)) == pytest.approx(3.0)


# --- wavelength / resonance / reactance ------------------------------------

def test_wavelength_and_resonance():
    assert rf.wavelength(rf.C) == pytest.approx(1.0)
    assert rf.wavelength(300e6) == pytest.approx(0.99931, abs=1e-4)
    assert rf.freq_from_wavelength(1.0) == pytest.approx(rf.C)
    # 40m dipole ~ 10 m
    assert rf.dipole_length(14.2e6, 0.95) == pytest.approx(10.03, abs=0.05)
    assert rf.reactance_inductive(1e6, 1e-6) == pytest.approx(2 * math.pi)
    assert rf.reactance_capacitive(1e6, 1e-9) == pytest.approx(159.155, abs=1e-2)
    assert rf.resonant_freq(1e-6, 1e-9) == pytest.approx(5.0329e6, rel=1e-4)


# --- transmission line / matching ------------------------------------------

def test_vswr_and_return_loss():
    assert rf.reflection_coefficient(75.0, 50.0) == pytest.approx(0.2)
    assert rf.vswr_from_z(75.0, 50.0) == pytest.approx(1.5)
    assert rf.vswr_from_gamma(0.2) == pytest.approx(1.5)
    assert rf.return_loss_db(0.2) == pytest.approx(13.979, abs=1e-3)
    assert rf.mismatch_loss_db(0.2) == pytest.approx(0.1773, abs=1e-3)
    assert rf.vswr_to_gamma(1.5) == pytest.approx(0.2)
    assert rf.vswr_from_z(50.0, 50.0) == pytest.approx(1.0)            # perfect match


def test_coax_and_velocity_factor():
    assert rf.z0_coax(math.e, 1.0, 1.0) == pytest.approx(60.0)         # ln(e)=1
    assert rf.velocity_factor(2.25) == pytest.approx(0.66667, abs=1e-4)  # solid PE


# --- link budget / propagation ---------------------------------------------

def test_fspl_and_link_budget():
    # cross-check against FSPL(dB) = 20log10(d_km) + 20log10(f_MHz) + 32.45
    assert rf.fspl_db(1000.0, 2.4e9) == pytest.approx(100.05, abs=0.05)
    assert rf.friis_rx_dbm(30.0, 10.0, 10.0, 1000.0, 2.4e9) == pytest.approx(-50.05, abs=0.05)
    assert rf.eirp_dbm(30.0, 12.0, 2.0) == pytest.approx(40.0)


def test_fresnel_horizon_skindepth():
    assert rf.fresnel_radius(1000.0, 1000.0, 2.4e9, 1) == pytest.approx(7.905, abs=0.02)
    assert rf.radio_horizon_km(100.0) == pytest.approx(41.2)
    # copper skin depth at 1 MHz ~ 66 µm
    assert rf.skin_depth(1e6) == pytest.approx(6.61e-5, rel=0.02)
    assert rf.dbi_to_dbd(2.15) == pytest.approx(0.0)
    assert rf.dbd_to_dbi(0.0) == pytest.approx(2.15)


def test_l_match_returns_two_solutions():
    sols = rf.l_match(50.0, 200.0, 7e6)
    assert len(sols) == 2
    assert sols[0]["q"] == pytest.approx(math.sqrt(200 / 50 - 1))     # Q = sqrt(Rhi/Rlo - 1) = sqrt(3)
    # one solution is series-L/shunt-C, the other the mirror
    types = {(s["series"]["type"], s["shunt"]["type"]) for s in sols}
    assert ("L", "C") in types and ("C", "L") in types


# --- Maidenhead grid locator -----------------------------------------------

def test_maidenhead_known_vectors():
    # Munich, DL — the canonical JN58td example
    assert rf.grid_square(48.14666, 11.60833) == "JN58td"
    assert rf.grid_square(48.14666, 11.60833, precision=4) == "JN58"
    lat, lon = rf.grid_to_latlon("JN58td")
    assert lat == pytest.approx(48.146, abs=0.03)
    assert lon == pytest.approx(11.604, abs=0.05)


@pytest.mark.parametrize("lat,lon", [
    (0.0, 0.0), (40.7128, -74.0060), (-33.8688, 151.2093),
    (51.5074, -0.1278), (-90.0 + 0.1, 179.9),
])
def test_maidenhead_roundtrip_within_cell(lat, lon):
    g = rf.grid_square(lat, lon, precision=6)
    rlat, rlon = rf.grid_to_latlon(g)
    # 6-char cell is 5'×2.5' -> within ~0.05° lat, ~0.09° lon of the input
    assert rlat == pytest.approx(lat, abs=0.05)
    assert rlon == pytest.approx(lon, abs=0.09)


def test_grid_distance_and_bearing():
    assert rf.grid_distance_km("JN58td", "JN58td") == pytest.approx(0.0, abs=1.0)
    # Munich (JN58) to London (IO91) ~ 920 km
    d = rf.grid_distance_km("JN58td", "IO91wm")
    assert d == pytest.approx(920.0, abs=40.0)
    b = rf.grid_bearing_deg("JN58td", "IO91wm")
    assert 290.0 <= b <= 320.0                       # roughly WNW
    assert rf.grid_distance_km("JN58td", "IO91wm") == pytest.approx(
        rf.grid_distance_km("IO91wm", "JN58td"))


# --- error handling --------------------------------------------------------

def test_domain_errors_raise_valueerror():
    for call in (lambda: rf.w_to_dbm(0.0),
                 lambda: rf.wavelength(0.0),
                 lambda: rf.z0_coax(1.0, 2.0),          # inner >= outer
                 lambda: rf.grid_square(200.0, 0.0),    # lat out of range
                 lambda: rf.grid_to_latlon("ZZ99zz!")): # malformed
        with pytest.raises(ValueError):
            call()


# --- formula-layer registration --------------------------------------------

def test_rf_functions_registered_and_callable():
    from abax.core.errors import CellError
    from abax.core.functions import FUNCTIONS

    assert FUNCTIONS["DBM2W"]([0.0]) == pytest.approx(1e-3)
    assert FUNCTIONS["FSPL"]([1000.0, 2.4e9]) == pytest.approx(100.05, abs=0.05)
    assert FUNCTIONS["VSWR"]([75.0]) == pytest.approx(1.5)            # default z0=50
    assert FUNCTIONS["VSWR"]([75.0, 50.0]) == pytest.approx(1.5)
    assert FUNCTIONS["WAVELENGTH"]([300e6]) == pytest.approx(0.99931, abs=1e-4)
    assert FUNCTIONS["GRIDSQUARE"]([48.14666, 11.60833]) == "JN58td"
    assert FUNCTIONS["GRIDDIST"](["JN58td", "JN58td"]) == pytest.approx(0.0, abs=1.0)
    # error paths return a CellError, never raise
    assert isinstance(FUNCTIONS["W2DBM"]([0.0]), CellError)           # log(0) domain
    assert isinstance(FUNCTIONS["VSWR"]([]), CellError)              # missing required arg
    assert isinstance(FUNCTIONS["GRIDLAT"](["nonsense!"]), CellError)


def test_rf_functions_have_signatures():
    from abax.core.completion import signature

    assert "freq_hz" in signature("FSPL")
    assert "z0" in signature("VSWR")
    assert "lat" in signature("GRIDSQUARE")
