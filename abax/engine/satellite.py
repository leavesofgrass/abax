"""SGP4/TLE satellite pass predictor — guarded ``sgp4`` propagation, stdlib look-angles.

A *pass* is an interval during which a satellite rises above an observer's local
horizon. Given a satellite's orbital elements (a two-line element set, "TLE") and
an observer on the ground (latitude, longitude, altitude), this module predicts
the passes over a time window: when the satellite rises, when it culminates
(reaches maximum elevation), when it sets, and the azimuths at each of those
moments.

Layering mirrors the other optional-dep adapters (see :mod:`abax.engine.necpy`,
:mod:`abax.engine.dbapi`): the heavyweight numerical *propagation* — turning a TLE
plus a timestamp into an Earth-Centered-Inertial (ECI / TEME) position — is done
by the optional **sgp4** library (Brandon Rhodes' pure-Python implementation of
the standard SGP4 model). Importing this module never fails; :func:`available`
reports whether the real propagation path can run, and any predictor call raises a
descriptive :class:`Sgp4Unavailable` with an "install sgp4" message when it is
absent.

Everything *after* propagation is pure stdlib :mod:`math`: converting the TEME
position to an Earth-fixed (ECEF) frame via Greenwich sidereal time, then to the
observer's topocentric South-East-Zenith frame to obtain azimuth and elevation.
That geometry is exercised by tests even without sgp4 installed (see
:func:`observer_ecef`, :func:`look_angle`, :func:`gmst_rad`, :func:`eci_to_ecef`).

TLE format. ``predict_passes`` accepts the classic three-line form (an optional
name line followed by the two 69-column data lines) or the bare two-line form.
Whitespace around lines is tolerated; the two data lines must start with ``"1 "``
and ``"2 "`` respectively.

All datetimes are treated as UTC. Naive datetimes are assumed to be UTC;
timezone-aware datetimes are converted to UTC. Returned pass dictionaries carry
timezone-aware UTC datetimes.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence, Tuple

# --- Earth / time constants (WGS-72, the datum SGP4/TLE are defined against) ---
_WGS72_A_KM = 6378.135          # equatorial radius, km
_WGS72_F = 1.0 / 298.26         # flattening
_E2 = _WGS72_F * (2.0 - _WGS72_F)  # first eccentricity squared
_OMEGA_EARTH = 7.292_115_146_706_979e-5  # Earth rotation rate, rad/s (WGS-72)
_DEG = 180.0 / math.pi
_RAD = math.pi / 180.0


class Sgp4Unavailable(RuntimeError):
    """Raised when SGP4 propagation is requested but the ``sgp4`` package is absent."""


_INSTALL_MSG = (
    "satellite pass prediction requires the 'sgp4' package for orbit "
    "propagation; install it with:\n"
    "    pip install sgp4"
)


def available() -> bool:
    """True iff the ``sgp4`` package can be imported (never raises)."""
    try:
        import sgp4.api  # noqa: F401
    except Exception:
        return False
    return True


# --------------------------------------------------------------------------- #
# TLE parsing (pure stdlib; always available)
# --------------------------------------------------------------------------- #
class Tle:
    """A parsed two-line element set: an optional name and the two data lines."""

    __slots__ = ("name", "line1", "line2")

    def __init__(self, name: str, line1: str, line2: str) -> None:
        self.name = name
        self.line1 = line1
        self.line2 = line2

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"Tle(name={self.name!r}, line1={self.line1!r}, line2={self.line2!r})"


def parse_tle(tle: str) -> Tle:
    """Parse a TLE string (three-line or bare two-line form) into a :class:`Tle`.

    Raises :class:`ValueError` when the two data lines cannot be identified. This
    is pure stdlib and runs whether or not ``sgp4`` is installed.
    """
    lines = [ln.rstrip() for ln in tle.splitlines() if ln.strip()]
    if len(lines) < 2:
        raise ValueError("TLE must contain at least two lines")

    # Locate the two data lines (start with '1 ' / '2 '); anything before is a name.
    idx1 = None
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("1 ") and i + 1 < len(lines) and lines[i + 1].lstrip().startswith("2 "):
            idx1 = i
            break
    if idx1 is None:
        raise ValueError(
            "could not find the two TLE data lines (expected lines starting "
            "with '1 ' and '2 ')"
        )
    line1 = lines[idx1].lstrip()
    line2 = lines[idx1 + 1].lstrip()
    name = lines[idx1 - 1].strip() if idx1 >= 1 else "SATELLITE"
    return Tle(name=name, line1=line1, line2=line2)


# --------------------------------------------------------------------------- #
# Time / frame geometry (pure stdlib; always available and tested)
# --------------------------------------------------------------------------- #
def _to_utc(dt: datetime) -> datetime:
    """Return *dt* as a timezone-aware UTC datetime (naive is assumed UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def julian_date(dt: datetime) -> float:
    """Julian Date (UT1~=UTC) for a UTC datetime, via the standard Fliegel algorithm."""
    dt = _to_utc(dt)
    y, m = dt.year, dt.month
    day = (
        dt.day
        + (dt.hour + (dt.minute + (dt.second + dt.microsecond / 1e6) / 60.0) / 60.0)
        / 24.0
    )
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return (
        math.floor(365.25 * (y + 4716))
        + math.floor(30.6001 * (m + 1))
        + day
        + b
        - 1524.5
    )


def gmst_rad(dt: datetime) -> float:
    """Greenwich Mean Sidereal Time (radians, in ``[0, 2*pi)``) for a UTC datetime.

    IAU-82 polynomial in the Julian centuries since J2000.0 (Vallado eq. 3-47).
    """
    jd = julian_date(dt)
    t = (jd - 2451545.0) / 36525.0
    gmst_sec = (
        67310.54841
        + (876600.0 * 3600.0 + 8640184.812866) * t
        + 0.093104 * t * t
        - 6.2e-6 * t * t * t
    )
    gmst = math.radians((gmst_sec % 86400.0) / 240.0)  # 240 s per degree
    return gmst % (2.0 * math.pi)


def observer_ecef(lat_deg: float, lon_deg: float, alt_m: float) -> Tuple[float, float, float]:
    """Observer position in the Earth-fixed (ECEF) frame, km, on the WGS-72 ellipsoid."""
    lat = lat_deg * _RAD
    lon = lon_deg * _RAD
    alt_km = alt_m / 1000.0
    sin_lat = math.sin(lat)
    n = _WGS72_A_KM / math.sqrt(1.0 - _E2 * sin_lat * sin_lat)
    x = (n + alt_km) * math.cos(lat) * math.cos(lon)
    y = (n + alt_km) * math.cos(lat) * math.sin(lon)
    z = (n * (1.0 - _E2) + alt_km) * sin_lat
    return (x, y, z)


def eci_to_ecef(
    r_eci: Sequence[float], gmst: float
) -> Tuple[float, float, float]:
    """Rotate an ECI/TEME position vector into ECEF by the GMST angle (about +Z)."""
    x, y, z = r_eci
    cos_g = math.cos(gmst)
    sin_g = math.sin(gmst)
    xf = cos_g * x + sin_g * y
    yf = -sin_g * x + cos_g * y
    return (xf, yf, z)


def look_angle(
    r_ecef_sat: Sequence[float],
    lat_deg: float,
    lon_deg: float,
    alt_m: float,
) -> Tuple[float, float, float]:
    """Topocentric look-angle from observer to a satellite ECEF position.

    Returns ``(azimuth_deg, elevation_deg, range_km)`` where azimuth is measured
    clockwise from true North in ``[0, 360)`` and elevation is the angle above the
    local horizontal (negative when below the horizon).

    The satellite vector relative to the observer is rotated into the local
    South-East-Zenith (SEZ) topocentric frame; azimuth/elevation follow directly.
    """
    obs = observer_ecef(lat_deg, lon_deg, alt_m)
    # Range vector (observer -> satellite) in ECEF.
    rx = r_ecef_sat[0] - obs[0]
    ry = r_ecef_sat[1] - obs[1]
    rz = r_ecef_sat[2] - obs[2]

    lat = lat_deg * _RAD
    lon = lon_deg * _RAD
    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    sin_lon = math.sin(lon)
    cos_lon = math.cos(lon)

    # Rotate ECEF range vector into SEZ (South, East, Zenith).
    south = sin_lat * cos_lon * rx + sin_lat * sin_lon * ry - cos_lat * rz
    east = -sin_lon * rx + cos_lon * ry
    zenith = cos_lat * cos_lon * rx + cos_lat * sin_lon * ry + sin_lat * rz

    rng = math.sqrt(rx * rx + ry * ry + rz * rz)
    if rng == 0.0:
        return (0.0, 90.0, 0.0)

    elevation = math.degrees(math.asin(max(-1.0, min(1.0, zenith / rng))))
    # Azimuth clockwise from North: atan2(East, -South) maps SEZ to N-referenced.
    azimuth = math.degrees(math.atan2(east, -south))
    if azimuth < 0.0:
        azimuth += 360.0
    return (azimuth % 360.0, elevation, rng)


# --------------------------------------------------------------------------- #
# Propagation (requires sgp4) + pass search
# --------------------------------------------------------------------------- #
def _make_satrec(tle: Tle):
    """Build an sgp4 Satrec from a parsed TLE, requiring the ``sgp4`` package."""
    try:
        from sgp4.api import Satrec
    except Exception as exc:  # ImportError or any load failure
        raise Sgp4Unavailable(_INSTALL_MSG) from exc
    return Satrec.twoline2rv(tle.line1, tle.line2)


def _propagate_ecef(satrec, dt: datetime) -> Tuple[float, float, float]:
    """Propagate to *dt* and return the satellite position in ECEF (km)."""
    from sgp4.api import jday

    dt = _to_utc(dt)
    jd, fr = jday(
        dt.year,
        dt.month,
        dt.day,
        dt.hour,
        dt.minute,
        dt.second + dt.microsecond / 1e6,
    )
    err, r_teme, _v = satrec.sgp4(jd, fr)
    if err != 0:
        raise ValueError(f"sgp4 propagation error code {err} at {dt.isoformat()}")
    return eci_to_ecef(r_teme, gmst_rad(dt))


def _elevation_at(satrec, dt: datetime, observer: Sequence[float]) -> Tuple[float, float, float]:
    """(azimuth_deg, elevation_deg, range_km) of the satellite from *observer* at *dt*."""
    r_ecef = _propagate_ecef(satrec, dt)
    return look_angle(r_ecef, observer[0], observer[1], observer[2])


def _refine_crossing(
    satrec,
    observer: Sequence[float],
    t_a: datetime,
    t_b: datetime,
    min_elev: float,
) -> datetime:
    """Bisect the time between two samples straddling the ``elevation == min_elev`` horizon.

    ``t_a`` and ``t_b`` bracket exactly one crossing (one sample above the
    threshold, the other below); direction (rise or set) is inferred from which
    endpoint is above. Returns the bracketed time nearest the crossing.
    """
    lo, hi = t_a, t_b
    _, el_lo, _ = _elevation_at(satrec, lo, observer)
    for _ in range(40):  # ~sub-second even for a multi-minute bracket
        mid = lo + (hi - lo) / 2
        _, el_mid, _r = _elevation_at(satrec, mid, observer)
        # Keep the sub-interval that still straddles the horizon.
        if (el_mid - min_elev >= 0.0) == (el_lo - min_elev >= 0.0):
            lo, el_lo = mid, el_mid
        else:
            hi = mid
    return hi


def predict_passes(
    tle,
    observer: Sequence[float],
    start: datetime,
    hours: float,
    min_elevation_deg: float = 10.0,
    step_seconds: float = 30.0,
) -> List[dict]:
    """Predict satellite passes over *observer* for a time window.

    Parameters
    ----------
    tle:
        A TLE as a string (three-line or two-line form) or a parsed :class:`Tle`.
    observer:
        ``(latitude_deg, longitude_deg, altitude_m)`` of the ground station.
    start:
        Window start (UTC; naive is assumed UTC).
    hours:
        Window length in hours (must be > 0).
    min_elevation_deg:
        A pass is only reported once the satellite rises above this elevation.
    step_seconds:
        Coarse sampling step used to bracket rise/set crossings (refined by
        bisection). Should be well under half the shortest pass; the 30 s default
        is safe for low-Earth-orbit satellites.

    Returns
    -------
    list of dict, each::

        {
          "satellite":     str,       # name from the TLE
          "rise":          datetime,  # UTC, aware — crosses up through min elev
          "culmination":   datetime,  # UTC, aware — maximum elevation
          "set":           datetime,  # UTC, aware — crosses down through min elev
          "max_elevation": float,     # degrees, at culmination
          "rise_azimuth":  float,     # degrees [0, 360)
          "max_azimuth":   float,     # degrees at culmination
          "set_azimuth":   float,     # degrees
          "duration_s":    float,     # set - rise, seconds
        }

    Raises :class:`Sgp4Unavailable` when ``sgp4`` is not installed, and
    :class:`ValueError` for a malformed TLE or non-positive window.
    """
    if hours <= 0.0:
        raise ValueError("hours must be positive")
    if isinstance(tle, Tle):
        parsed = tle
    else:
        parsed = parse_tle(str(tle))

    satrec = _make_satrec(parsed)  # requires sgp4 (raises Sgp4Unavailable if absent)

    start = _to_utc(start)
    end = start + timedelta(hours=hours)
    step = timedelta(seconds=step_seconds)

    passes: List[dict] = []
    t = start
    prev_t: Optional[datetime] = None
    prev_el: Optional[float] = None

    # State while inside a pass (elevation above threshold).
    in_pass = False
    rise_t: Optional[datetime] = None
    best_el = -90.0
    best_t: Optional[datetime] = None

    def _close_pass(set_t: datetime) -> None:
        assert rise_t is not None and best_t is not None
        r_az, _r_el, _rr = _elevation_at(satrec, rise_t, observer)
        m_az, m_el, _mr = _elevation_at(satrec, best_t, observer)
        s_az, _s_el, _sr = _elevation_at(satrec, set_t, observer)
        passes.append(
            {
                "satellite": parsed.name,
                "rise": rise_t,
                "culmination": best_t,
                "set": set_t,
                "max_elevation": m_el,
                "rise_azimuth": r_az,
                "max_azimuth": m_az,
                "set_azimuth": s_az,
                "duration_s": (set_t - rise_t).total_seconds(),
            }
        )

    while t <= end:
        _az, el, _rng = _elevation_at(satrec, t, observer)

        if not in_pass and el >= min_elevation_deg:
            # Rising edge: refine the crossing between prev sample and now.
            if prev_t is not None and prev_el is not None and prev_el < min_elevation_deg:
                rise_t = _refine_crossing(satrec, observer, prev_t, t, min_elevation_deg)
            else:
                rise_t = t  # already above at window start
            in_pass = True
            best_el = el
            best_t = t
        elif in_pass and el >= min_elevation_deg:
            if el > best_el:
                best_el = el
                best_t = t
        elif in_pass and el < min_elevation_deg:
            # Falling edge: refine the set crossing between the last above-horizon
            # sample (prev_t) and this below-horizon one (t), then close the pass.
            set_t = (
                _refine_crossing(satrec, observer, prev_t, t, min_elevation_deg)
                if prev_t is not None
                else t
            )
            _close_pass(set_t)
            in_pass = False
            rise_t = None
            best_t = None
            best_el = -90.0

        prev_t = t
        prev_el = el
        t = t + step

    # A pass still open at the window end: close it at the last sample.
    if in_pass and rise_t is not None and best_t is not None and prev_t is not None:
        _close_pass(prev_t)

    return passes
