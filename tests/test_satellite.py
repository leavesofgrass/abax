"""SGP4/TLE satellite pass predictor (abax.engine.satellite).

Two tiers of tests:

* The pure-stdlib TLE parsing and topocentric look-angle geometry are exercised
  WITHOUT ``sgp4`` installed — these run in the thin CI environment. Each expected
  value cites an independent source (WGS-72 datum constants, the standard GMST at
  J2000.0, and the definition of the topocentric SEZ frame).
* The end-to-end pass prediction requires ``sgp4`` and is guarded with
  ``pytest.importorskip("sgp4")`` so the thin CI (no sgp4) skips it cleanly. It
  asserts a known ISS element set yields plausible passes near its epoch
  (rise < culmination < set, azimuths in ``[0, 360)``, elevation >= min).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from abax.engine import satellite

# ISS (ZARYA) two-line element set, epoch day-of-year 173.5479 of 2024
# (~2024-06-21 13:09 UTC). Public element set from CelesTrak/Space-Track.
ISS_TLE = """ISS (ZARYA)
1 25544U 98067A   24173.54791435  .00016717  00000-0  30074-3 0  9993
2 25544  51.6402 210.0827 0004572  61.9772 298.1637 15.50186970    07"""

# Observer near New York City (lat, lon, alt_m).
NYC = (40.7128, -74.0060, 10.0)


# --------------------------------------------------------------------------- #
# Layering / availability (always run, no sgp4 needed)
# --------------------------------------------------------------------------- #
def test_module_api_present():
    assert hasattr(satellite, "predict_passes")
    assert hasattr(satellite, "available")
    assert hasattr(satellite, "parse_tle")
    assert issubclass(satellite.Sgp4Unavailable, RuntimeError)


def test_available_returns_bool():
    assert isinstance(satellite.available(), bool)


def test_predict_requires_sgp4_when_absent():
    # When sgp4 is not installed, prediction raises Sgp4Unavailable with a
    # helpful "install sgp4" message. When it IS installed this test is a no-op.
    if satellite.available():
        pytest.skip("sgp4 installed; unavailability path not exercised here")
    with pytest.raises(satellite.Sgp4Unavailable) as exc:
        satellite.predict_passes(
            ISS_TLE, NYC, datetime(2024, 6, 21, tzinfo=timezone.utc), 6.0
        )
    assert "sgp4" in str(exc.value).lower()


# --------------------------------------------------------------------------- #
# TLE parsing (pure stdlib, always run)
# --------------------------------------------------------------------------- #
def test_parse_tle_three_line():
    t = satellite.parse_tle(ISS_TLE)
    assert t.name == "ISS (ZARYA)"
    assert t.line1.startswith("1 25544U")
    assert t.line2.startswith("2 25544")


def test_parse_tle_two_line_only():
    two = "\n".join(ISS_TLE.splitlines()[1:])
    t = satellite.parse_tle(two)
    assert t.line1.startswith("1 ")
    assert t.line2.startswith("2 ")
    assert t.name == "SATELLITE"  # default when no name line


def test_parse_tle_rejects_garbage():
    with pytest.raises(ValueError):
        satellite.parse_tle("not a tle at all")
    with pytest.raises(ValueError):
        satellite.parse_tle("only one line")


# --------------------------------------------------------------------------- #
# Time / frame geometry (pure stdlib, always run) — each cites its source.
# --------------------------------------------------------------------------- #
def test_julian_date_j2000():
    # J2000.0 epoch is 2000-01-01 12:00:00 UTC == Julian Date 2451545.0
    # (IAU definition of the J2000.0 reference epoch).
    dt = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert satellite.julian_date(dt) == pytest.approx(2451545.0, abs=1e-6)


def test_gmst_at_j2000():
    # Greenwich Mean Sidereal Time at J2000.0 is 280.4606 deg (18h 41m 50.548s),
    # the standard reference value (Vallado, "Fundamentals of Astrodynamics",
    # IAU-82 GMST polynomial).
    dt = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    gmst_deg = math.degrees(satellite.gmst_rad(dt)) % 360.0
    assert gmst_deg == pytest.approx(280.4606, abs=1e-3)


def test_observer_ecef_equator_and_pole_radii():
    # WGS-72 datum: equatorial radius 6378.135 km; the polar radius equals
    # a*(1-f) = 6378.135 * (1 - 1/298.26) = 6356.751 km.
    eq = satellite.observer_ecef(0.0, 0.0, 0.0)
    pole = satellite.observer_ecef(90.0, 0.0, 0.0)
    assert math.dist(eq, (0, 0, 0)) == pytest.approx(6378.135, abs=1e-3)
    assert math.dist(pole, (0, 0, 0)) == pytest.approx(6356.751, abs=1e-2)


def test_observer_ecef_equator_prime_meridian_on_x_axis():
    # (0N, 0E) at sea level lies on the +X axis in ECEF, by definition of the
    # Earth-fixed frame (X through the equator/prime-meridian intersection).
    x, y, z = satellite.observer_ecef(0.0, 0.0, 0.0)
    assert x == pytest.approx(6378.135, abs=1e-3)
    assert y == pytest.approx(0.0, abs=1e-6)
    assert z == pytest.approx(0.0, abs=1e-6)


def test_look_angle_straight_overhead_is_90_elevation():
    # A point directly above an observer (along the local zenith / +X at (0,0))
    # has elevation 90 deg; range equals the height above the site.
    obs = satellite.observer_ecef(0.0, 0.0, 0.0)
    overhead = (obs[0] + 400.0, obs[1], obs[2])
    az, el, rng = satellite.look_angle(overhead, 0.0, 0.0, 0.0)
    assert el == pytest.approx(90.0, abs=1e-6)
    assert rng == pytest.approx(400.0, abs=1e-6)


def test_look_angle_cardinal_azimuths():
    # In the topocentric SEZ frame, azimuth is measured clockwise from true North.
    # A target displaced along the local-north tangent reads azimuth 0 deg and
    # ~0 elevation; along the local-east tangent reads azimuth 90 deg.
    lat = 45.0
    obs = satellite.observer_ecef(lat, 0.0, 0.0)
    lr = math.radians(lat)
    # Local north unit vector at (lat, lon=0): (-sin lat, 0, cos lat).
    north = (-math.sin(lr), 0.0, math.cos(lr))
    north_pt = tuple(obs[i] + north[i] * 1000.0 for i in range(3))
    az_n, el_n, _ = satellite.look_angle(north_pt, lat, 0.0, 0.0)
    assert az_n == pytest.approx(0.0, abs=1e-3)
    assert el_n == pytest.approx(0.0, abs=1e-3)

    # Local east unit vector at lon=0: (0, 1, 0).
    east_pt = (obs[0], obs[1] + 1000.0, obs[2])
    az_e, el_e, _ = satellite.look_angle(east_pt, lat, 0.0, 0.0)
    assert az_e == pytest.approx(90.0, abs=1e-3)
    assert el_e == pytest.approx(0.0, abs=1e-3)


def test_look_angle_below_horizon_is_negative_elevation():
    # A target on the opposite side of the Earth is below the local horizon:
    # elevation must be negative (the predictor uses this to reject sub-horizon
    # geometry).
    az, el, rng = satellite.look_angle((-7000.0, 0.0, 0.0), 0.0, 0.0, 0.0)
    assert el < 0.0
    assert 0.0 <= az < 360.0
    assert rng > 0.0


def test_eci_to_ecef_zero_gmst_is_identity():
    # With GMST == 0 the ECI and ECEF frames coincide (no rotation applied).
    v = (1234.0, -567.0, 890.0)
    assert satellite.eci_to_ecef(v, 0.0) == pytest.approx(v)


# --------------------------------------------------------------------------- #
# End-to-end prediction (requires sgp4 — skipped in thin CI)
# --------------------------------------------------------------------------- #
def test_predict_iss_passes_plausible():
    pytest.importorskip("sgp4")

    # Predict over a 24-hour window starting near the TLE epoch.
    start = datetime(2024, 6, 21, 0, 0, 0, tzinfo=timezone.utc)
    passes = satellite.predict_passes(
        ISS_TLE, NYC, start, 24.0, min_elevation_deg=10.0
    )

    # A low-Earth-orbit satellite like the ISS produces several above-horizon
    # passes per day at mid-latitudes — expect a handful, not zero and not dozens.
    assert 2 <= len(passes) <= 12

    for p in passes:
        assert p["satellite"] == "ISS (ZARYA)"
        # Temporal ordering: rise strictly before culmination before set.
        assert p["rise"] < p["culmination"] < p["set"]
        # Azimuths are compass bearings in [0, 360).
        for key in ("rise_azimuth", "max_azimuth", "set_azimuth"):
            assert 0.0 <= p[key] < 360.0
        # Max elevation must clear the requested minimum.
        assert p["max_elevation"] >= 10.0
        # Elevation cannot exceed the zenith.
        assert p["max_elevation"] <= 90.0
        # Duration is positive and consistent with rise/set.
        assert p["duration_s"] > 0.0
        assert p["duration_s"] == pytest.approx(
            (p["set"] - p["rise"]).total_seconds(), abs=1e-6
        )
        # ISS passes last on the order of minutes, not hours.
        assert p["duration_s"] < 20 * 60


def test_predict_higher_min_elevation_is_subset():
    pytest.importorskip("sgp4")

    start = datetime(2024, 6, 21, 0, 0, 0, tzinfo=timezone.utc)
    low = satellite.predict_passes(ISS_TLE, NYC, start, 24.0, min_elevation_deg=10.0)
    high = satellite.predict_passes(ISS_TLE, NYC, start, 24.0, min_elevation_deg=40.0)
    # Requiring a higher culmination can only keep or drop passes, never add them.
    assert len(high) <= len(low)
    for p in high:
        assert p["max_elevation"] >= 40.0


def test_predict_rejects_nonpositive_window():
    # Validated before sgp4 is required, so this holds with or without sgp4.
    with pytest.raises(ValueError):
        satellite.predict_passes(
            ISS_TLE, NYC, datetime(2024, 6, 21, tzinfo=timezone.utc), 0.0
        )


def test_predict_accepts_parsed_tle_object():
    pytest.importorskip("sgp4")

    tle = satellite.parse_tle(ISS_TLE)
    start = datetime(2024, 6, 21, 0, 0, 0, tzinfo=timezone.utc)
    passes = satellite.predict_passes(tle, NYC, start, 6.0, min_elevation_deg=10.0)
    assert isinstance(passes, list)
