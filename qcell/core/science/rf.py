"""RF / ham-radio engineering math — pure stdlib.

SI base units throughout (Hz, metre, watt, henry, farad, siemens/m), so the
functions stay unit-neutral; callers (the GUI RF tool, the formula layer) convert
to MHz / feet / etc. for display. Complex impedances are accepted where physically
meaningful (reflection coefficient, VSWR-from-Z); the spreadsheet-facing wrappers
pass real (resistive) values.

Domain errors raise :class:`ValueError` so the formula layer can map them to a
``CellError``.
"""

from __future__ import annotations

import math

C = 299_792_458.0           # speed of light, m/s
K_BOLTZMANN = 1.380649e-23  # J/K
MU0 = 4e-7 * math.pi        # vacuum permeability, H/m
COPPER_SIGMA = 5.8e7        # conductivity of copper, S/m


# --- power / level conversions --------------------------------------------

def dbm_to_w(dbm: float) -> float:
    return 10.0 ** ((dbm - 30.0) / 10.0)


def w_to_dbm(w: float) -> float:
    if w <= 0:
        raise ValueError("power must be > 0")
    return 30.0 + 10.0 * math.log10(w)


def dbw_to_w(dbw: float) -> float:
    return 10.0 ** (dbw / 10.0)


def w_to_dbw(w: float) -> float:
    if w <= 0:
        raise ValueError("power must be > 0")
    return 10.0 * math.log10(w)


def db_to_ratio(db: float) -> float:
    """dB → linear power ratio."""
    return 10.0 ** (db / 10.0)


def ratio_to_db(ratio: float) -> float:
    if ratio <= 0:
        raise ValueError("ratio must be > 0")
    return 10.0 * math.log10(ratio)


def db_add(d1: float, d2: float) -> float:
    """Combine two powers expressed in dB(m): incoherent sum in the linear domain."""
    return 10.0 * math.log10(10.0 ** (d1 / 10.0) + 10.0 ** (d2 / 10.0))


def dbuv_to_dbm(dbuv: float, z: float = 50.0) -> float:
    """dBµV (across ``z`` ohms) → dBm. For 50 Ω this is dBµV − 107."""
    if z <= 0:
        raise ValueError("impedance must be > 0")
    return dbuv - 90.0 - 10.0 * math.log10(z)


def s_unit_to_dbm(s: float) -> float:
    """HF S-meter reading → dBm (S9 = −73 dBm, 6 dB per S-unit)."""
    return -73.0 - (9.0 - s) * 6.0


# --- noise ----------------------------------------------------------------

def noise_floor_dbm(bandwidth_hz: float, temp_k: float = 290.0) -> float:
    """Thermal noise floor kTB in dBm (≈ −174 dBm/Hz at 290 K)."""
    if bandwidth_hz <= 0 or temp_k <= 0:
        raise ValueError("bandwidth and temperature must be > 0")
    return 10.0 * math.log10(K_BOLTZMANN * temp_k * bandwidth_hz / 1e-3)


def nf_to_noise_temp(nf_db: float, t0: float = 290.0) -> float:
    """Noise figure (dB) → equivalent noise temperature (K)."""
    return t0 * (10.0 ** (nf_db / 10.0) - 1.0)


def noise_temp_to_nf(temp_k: float, t0: float = 290.0) -> float:
    if temp_k < 0:
        raise ValueError("temperature must be >= 0")
    return 10.0 * math.log10(1.0 + temp_k / t0)


# --- wavelength / resonance / reactance -----------------------------------

def wavelength(freq_hz: float, velocity_factor: float = 1.0) -> float:
    if freq_hz <= 0:
        raise ValueError("frequency must be > 0")
    return C * velocity_factor / freq_hz


def freq_from_wavelength(wavelength_m: float, velocity_factor: float = 1.0) -> float:
    if wavelength_m <= 0:
        raise ValueError("wavelength must be > 0")
    return C * velocity_factor / wavelength_m


def dipole_length(freq_hz: float, k: float = 0.95) -> float:
    """Physical half-wave dipole length (m); ``k`` is the end-effect/velocity factor."""
    return k * 0.5 * wavelength(freq_hz)


def monopole_length(freq_hz: float, k: float = 0.95) -> float:
    """Physical quarter-wave monopole length (m)."""
    return k * 0.25 * wavelength(freq_hz)


def reactance_inductive(freq_hz: float, inductance_h: float) -> float:
    return 2.0 * math.pi * freq_hz * inductance_h


def reactance_capacitive(freq_hz: float, capacitance_f: float) -> float:
    if freq_hz <= 0 or capacitance_f <= 0:
        raise ValueError("frequency and capacitance must be > 0")
    return 1.0 / (2.0 * math.pi * freq_hz * capacitance_f)


def resonant_freq(inductance_h: float, capacitance_f: float) -> float:
    if inductance_h <= 0 or capacitance_f <= 0:
        raise ValueError("inductance and capacitance must be > 0")
    return 1.0 / (2.0 * math.pi * math.sqrt(inductance_h * capacitance_f))


# --- transmission line / matching -----------------------------------------

def reflection_coefficient(z_load: complex, z0: complex = 50.0) -> complex:
    """Voltage reflection coefficient Γ = (Zl − Z0) / (Zl + Z0)."""
    if z_load + z0 == 0:
        raise ValueError("Zload + Z0 must be nonzero")
    return (z_load - z0) / (z_load + z0)


def vswr_from_gamma(gamma_mag: float) -> float:
    g = abs(gamma_mag)
    if g >= 1.0:
        return math.inf
    return (1.0 + g) / (1.0 - g)


def vswr_from_z(z_load: complex, z0: complex = 50.0) -> float:
    return vswr_from_gamma(abs(reflection_coefficient(z_load, z0)))


def return_loss_db(gamma_mag: float) -> float:
    g = abs(gamma_mag)
    if g <= 0:
        return math.inf
    return -20.0 * math.log10(g)


def mismatch_loss_db(gamma_mag: float) -> float:
    g = abs(gamma_mag)
    if g >= 1.0:
        return math.inf
    return -10.0 * math.log10(1.0 - g * g)


def vswr_to_gamma(vswr: float) -> float:
    if vswr < 1.0:
        raise ValueError("VSWR must be >= 1")
    return (vswr - 1.0) / (vswr + 1.0)


def z0_coax(d_outer: float, d_inner: float, eps_r: float = 1.0) -> float:
    """Characteristic impedance of coax (Ω): (60/√εr)·ln(D/d)."""
    if d_inner <= 0 or d_outer <= d_inner or eps_r <= 0:
        raise ValueError("require d_outer > d_inner > 0 and eps_r > 0")
    return (60.0 / math.sqrt(eps_r)) * math.log(d_outer / d_inner)


def velocity_factor(eps_r: float) -> float:
    if eps_r <= 0:
        raise ValueError("eps_r must be > 0")
    return 1.0 / math.sqrt(eps_r)


# --- link budget / propagation --------------------------------------------

def fspl_db(distance_m: float, freq_hz: float) -> float:
    """Free-space path loss (dB) = 20·log10(4π·d·f / c)."""
    if distance_m <= 0 or freq_hz <= 0:
        raise ValueError("distance and frequency must be > 0")
    return 20.0 * math.log10(4.0 * math.pi * distance_m * freq_hz / C)


def friis_rx_dbm(ptx_dbm: float, gtx_dbi: float, grx_dbi: float,
                 distance_m: float, freq_hz: float) -> float:
    """Received power (dBm) from the Friis equation, free space."""
    return ptx_dbm + gtx_dbi + grx_dbi - fspl_db(distance_m, freq_hz)


def eirp_dbm(ptx_dbm: float, gain_dbi: float, loss_db: float = 0.0) -> float:
    return ptx_dbm + gain_dbi - loss_db


def fresnel_radius(d1_m: float, d2_m: float, freq_hz: float, n: int = 1) -> float:
    """Radius (m) of the n-th Fresnel zone at the point d1/d2 from each end."""
    if d1_m <= 0 or d2_m <= 0 or freq_hz <= 0 or n < 1:
        raise ValueError("d1, d2, freq must be > 0 and n >= 1")
    lam = wavelength(freq_hz)
    return math.sqrt(n * lam * d1_m * d2_m / (d1_m + d2_m))


def radio_horizon_km(h1_m: float, h2_m: float = 0.0) -> float:
    """Radio line-of-sight distance (km) over a 4/3-earth: 4.12·(√h1 + √h2), h in m."""
    if h1_m < 0 or h2_m < 0:
        raise ValueError("heights must be >= 0")
    return 4.12 * (math.sqrt(h1_m) + math.sqrt(h2_m))


def skin_depth(freq_hz: float, sigma: float = COPPER_SIGMA, mu_r: float = 1.0) -> float:
    """Skin depth (m): 1/√(π·f·µ·σ)."""
    if freq_hz <= 0 or sigma <= 0 or mu_r <= 0:
        raise ValueError("freq, sigma, mu_r must be > 0")
    return 1.0 / math.sqrt(math.pi * freq_hz * mu_r * MU0 * sigma)


# --- antenna gain reference -----------------------------------------------

def dbi_to_dbd(dbi: float) -> float:
    return dbi - 2.15


def dbd_to_dbi(dbd: float) -> float:
    return dbd + 2.15


# --- L-network impedance matching -----------------------------------------

def l_match(z_source: complex, z_load: complex, freq_hz: float) -> list[dict]:
    """Two L-network solutions matching ``z_source`` to ``z_load`` at ``freq_hz``.

    Returns up to two dicts with series/shunt reactances (Ω) and the equivalent
    component value (H for +X, F for −X). Resistive endpoints assumed for the
    classic two-solution form; works for Rs != Rl.
    """
    rs, rl = z_source.real, z_load.real
    if rs <= 0 or rl <= 0 or freq_hz <= 0:
        raise ValueError("source/load resistance and freq must be > 0")
    hi, lo = (rs, rl) if rs >= rl else (rl, rs)
    q = math.sqrt(hi / lo - 1.0)
    w = 2.0 * math.pi * freq_hz
    sols = []
    for sign in (1.0, -1.0):
        xs = sign * q * lo            # series reactance (on the low-R side)
        xp = -sign * hi / q           # shunt reactance (on the high-R side)
        sols.append({
            "q": q,
            "series_x": xs,
            "shunt_x": xp,
            "series": _x_to_component(xs, w),
            "shunt": _x_to_component(xp, w),
        })
    return sols


def _x_to_component(x: float, w: float) -> dict:
    """Reactance (Ω) → an inductor (X>0) or capacitor (X<0) at angular freq ``w``."""
    if abs(x) < 1e-12:
        return {"type": "none", "value": 0.0}
    if x > 0:
        return {"type": "L", "henrys": x / w}
    return {"type": "C", "farads": 1.0 / (-x * w)}


# --- Maidenhead grid locator ----------------------------------------------

def grid_square(lat: float, lon: float, precision: int = 6) -> str:
    """(lat, lon) in degrees → Maidenhead locator (e.g. ``FN31pr``).

    ``precision`` is the character count: 4 (square), 6 (subsquare, default),
    or 8 (extended square).
    """
    if not -90.0 <= lat <= 90.0:
        raise ValueError("latitude must be in [-90, 90]")
    if not -180.0 <= lon <= 180.0:
        raise ValueError("longitude must be in [-180, 180]")
    if precision not in (2, 4, 6, 8):
        raise ValueError("precision must be 2, 4, 6, or 8")

    adj_lon = min((lon + 180.0) % 360.0, 359.999999)
    adj_lat = min(lat + 90.0, 179.999999)

    out = [chr(ord("A") + int(adj_lon // 20)), chr(ord("A") + int(adj_lat // 10))]
    rlon, rlat = adj_lon % 20.0, adj_lat % 10.0
    if precision >= 4:
        out += [str(int(rlon // 2)), str(int(rlat // 1))]
        rlon, rlat = rlon % 2.0, rlat % 1.0
    if precision >= 6:
        out += [chr(ord("a") + int(rlon * 12)), chr(ord("a") + int(rlat * 24))]
        rlon, rlat = (rlon * 12) % 1.0, (rlat * 24) % 1.0
    if precision >= 8:
        out += [str(int(rlon * 10)), str(int(rlat * 10))]
    return "".join(out)


def grid_to_latlon(grid: str) -> tuple[float, float]:
    """Maidenhead locator → (lat, lon) of the cell *centre*, in degrees."""
    g = grid.strip()
    if len(g) < 2 or len(g) % 2 != 0 or len(g) > 8:
        raise ValueError(f"invalid grid locator: {grid!r}")
    try:
        lon, lat = -180.0, -90.0
        lon += (ord(g[0].upper()) - ord("A")) * 20.0
        lat += (ord(g[1].upper()) - ord("A")) * 10.0
        lon_size, lat_size = 20.0, 10.0
        if len(g) >= 4:
            lon += int(g[2]) * 2.0
            lat += int(g[3]) * 1.0
            lon_size, lat_size = 2.0, 1.0
        if len(g) >= 6:
            lon += (ord(g[4].lower()) - ord("a")) * (2.0 / 24.0)
            lat += (ord(g[5].lower()) - ord("a")) * (1.0 / 24.0)
            lon_size, lat_size = 2.0 / 24.0, 1.0 / 24.0
        if len(g) >= 8:
            lon += int(g[6]) * (2.0 / 240.0)
            lat += int(g[7]) * (1.0 / 240.0)
            lon_size, lat_size = 2.0 / 240.0, 1.0 / 240.0
    except (ValueError, IndexError) as exc:
        raise ValueError(f"invalid grid locator: {grid!r}") from exc
    return (lat + lat_size / 2.0, lon + lon_size / 2.0)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088  # mean earth radius, km
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlam = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2.0 * r * math.asin(min(1.0, math.sqrt(a)))


def _initial_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlam = math.radians(lon2 - lon1)
    y = math.sin(dlam) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlam)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def grid_distance_km(grid_a: str, grid_b: str) -> float:
    la1, lo1 = grid_to_latlon(grid_a)
    la2, lo2 = grid_to_latlon(grid_b)
    return _haversine_km(la1, lo1, la2, lo2)


def grid_bearing_deg(grid_a: str, grid_b: str) -> float:
    """Initial great-circle bearing (degrees) from grid_a to grid_b."""
    la1, lo1 = grid_to_latlon(grid_a)
    la2, lo2 = grid_to_latlon(grid_b)
    return _initial_bearing(la1, lo1, la2, lo2)
