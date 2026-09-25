"""RF exposure (MPE / SAR) estimates for amateur stations — pure stdlib.

What this module implements, and where each piece comes from:

* **MPE limits** — 47 CFR § 1.1310(e)(1), Table 1: E-field, H-field and power
  density by frequency for occupational/controlled and general-population/
  uncontrolled exposure, averaged over 6 and 30 minutes respectively.
* **SAR limits** — 47 CFR § 1.1310(a)–(c): whole-body, peak spatial-average
  (1 g) and extremity (10 g) limits for both tiers.
* **Exemption threshold** — 47 CFR § 1.1307(b)(3)(i)(C), Table 1: the ERP at or
  below which a fixed source at distance R is exempt from routine evaluation.
  It applies only at R ≥ λ/2π.
* **Power density** — the far-field relation S = F·EIRP / (4πR²), where F is a
  power-density reflection factor: 1 for free space, 4 for full in-phase
  ground reflection (the reflected field doubles the total field). The
  § 1.1307 exemption table is exactly this relation with F = 4 applied to ERP
  (EIRP = 1.64·ERP), which the tests check row by row.
* **SAR** — the definitional relation SAR = σ·E²/ρ.

Deliberately *not* included (not verified from primary sources when this was
written): the § 1.1307(b)(3)(i)(B) SAR-based threshold P_th for 0.5–40 cm
(the formula is an image in the eCFR), OET Bulletin 65 Supplement B's per-mode
duty factors and its ground-reflection factor, and ICNIRP reference levels.
The duty cycle is therefore an input, and any reflection factor other than
1 or 4 must be supplied by the caller.

These are **estimates**. They are not a substitute for a station evaluation
under 47 CFR § 97.13(c) and § 1.1307(b), and the far-field relation is not a
reliable measure close to the antenna (inside λ/2π).

Units: frequency in MHz where the FCC tables use MHz (``*_mhz``) — the formula
layer converts from Hz — power in watts, distance in metres, power density in
**mW/cm²** (the FCC table unit; 1 mW/cm² = 10 W/m²), fields in V/m and A/m,
SAR in W/kg.
"""

from __future__ import annotations

import math

C = 299_792_458.0            # speed of light, m/s
DIPOLE_GAIN = 1.64           # half-wave dipole gain, linear (47 CFR 1.1307(b)(3)(i)(C))
FULL_REFLECTION = 4.0        # power-density factor for full in-phase reflection

TIERS = ("controlled", "uncontrolled")
_TIER_ALIASES = {
    "controlled": "controlled", "occupational": "controlled", "c": "controlled",
    "uncontrolled": "uncontrolled", "general": "uncontrolled",
    "general population": "uncontrolled", "public": "uncontrolled", "u": "uncontrolled",
    # the FCC's own table labels, with the slash folded to a space
    "occupational controlled": "controlled",
    "general population uncontrolled": "uncontrolled",
}

# 47 CFR 1.1310(e)(1) Table 1. Rows: (f_lo, f_hi, E(f), H(f), S(f)) with f in MHz;
# E/H are None where the table leaves them blank. S in mW/cm².
_MPE_TABLE = {
    "controlled": (
        (0.3, 3.0, lambda f: 614.0, lambda f: 1.63, lambda f: 100.0),
        (3.0, 30.0, lambda f: 1842.0 / f, lambda f: 4.89 / f, lambda f: 900.0 / f ** 2),
        (30.0, 300.0, lambda f: 61.4, lambda f: 0.163, lambda f: 1.0),
        (300.0, 1500.0, None, None, lambda f: f / 300.0),
        (1500.0, 100000.0, None, None, lambda f: 5.0),
    ),
    "uncontrolled": (
        (0.3, 1.34, lambda f: 614.0, lambda f: 1.63, lambda f: 100.0),
        (1.34, 30.0, lambda f: 824.0 / f, lambda f: 2.19 / f, lambda f: 180.0 / f ** 2),
        (30.0, 300.0, lambda f: 27.5, lambda f: 0.073, lambda f: 0.2),
        (300.0, 1500.0, None, None, lambda f: f / 1500.0),
        (1500.0, 100000.0, None, None, lambda f: 1.0),
    ),
}
AVERAGING_MINUTES = {"controlled": 6.0, "uncontrolled": 30.0}

# 47 CFR 1.1310(b), (c): W/kg.
SAR_LIMITS = {
    "controlled": {"whole_body": 0.4, "peak_1g": 8.0, "extremity_10g": 20.0},
    "uncontrolled": {"whole_body": 0.08, "peak_1g": 1.6, "extremity_10g": 4.0},
}
_SAR_KIND_ALIASES = {
    "whole_body": "whole_body", "wholebody": "whole_body", "whole": "whole_body",
    "peak_1g": "peak_1g", "peak": "peak_1g", "1g": "peak_1g", "partial": "peak_1g",
    "extremity_10g": "extremity_10g", "extremity": "extremity_10g", "10g": "extremity_10g",
}

# 47 CFR 1.1307(b)(3)(i)(C) Table 1: threshold ERP (W), R in m, f in MHz.
_EXEMPT_TABLE = (
    (0.3, 1.34, lambda f, r: 1920.0 * r * r),
    (1.34, 30.0, lambda f, r: 3450.0 * r * r / (f * f)),
    (30.0, 300.0, lambda f, r: 3.83 * r * r),
    (300.0, 1500.0, lambda f, r: 0.0128 * r * r * f),
    (1500.0, 100000.0, lambda f, r: 19.2 * r * r),
)


def normalize_tier(tier: str) -> str:
    """``"controlled"`` / ``"occupational"`` or ``"uncontrolled"`` / ``"general"``."""
    key = str(tier).strip().lower().replace("/", " ").replace("-", " ")
    key = " ".join(key.split())
    if key in _TIER_ALIASES:
        return _TIER_ALIASES[key]
    raise ValueError(f"unknown exposure tier {tier!r} (use controlled or uncontrolled)")


def _rows_for(table, f_mhz: float):
    """Every table row whose closed range contains ``f_mhz`` (two at a boundary)."""
    rows = [row for row in table if row[0] <= f_mhz <= row[1]]
    if not rows:
        raise ValueError("frequency is outside the FCC table (0.3 MHz – 100 GHz)")
    return rows


def mpe_limits(f_mhz: float, tier: str = "uncontrolled") -> dict:
    """MPE limits at ``f_mhz`` for ``tier`` (47 CFR § 1.1310 Table 1).

    Returns ``{"power_density": mW/cm², "e_field": V/m or None, "h_field": A/m
    or None, "averaging_minutes": 6 or 30}``. At a boundary frequency that the
    table lists in two rows, the more restrictive value of each is used.
    """
    t = normalize_tier(tier)
    rows = _rows_for(_MPE_TABLE[t], f_mhz)

    def pick(idx):
        vals = [row[idx](f_mhz) for row in rows if row[idx] is not None]
        return min(vals) if vals else None

    return {"power_density": pick(4), "e_field": pick(2), "h_field": pick(3),
            "averaging_minutes": AVERAGING_MINUTES[t]}


def mpe_power_density(f_mhz: float, tier: str = "uncontrolled") -> float:
    """The MPE power-density limit in mW/cm²."""
    return mpe_limits(f_mhz, tier)["power_density"]


def sar_limit(tier: str = "uncontrolled", kind: str = "whole_body") -> float:
    """SAR limit in W/kg (47 CFR § 1.1310(b), (c)). ``kind``: ``whole_body``,
    ``peak_1g`` (any 1 g cube) or ``extremity_10g`` (any 10 g cube)."""
    t = normalize_tier(tier)
    k = _SAR_KIND_ALIASES.get(str(kind).strip().lower())
    if k is None:
        raise ValueError(f"unknown SAR kind {kind!r}")
    return SAR_LIMITS[t][k]


def sar(conductivity_s_per_m: float, e_rms_v_per_m: float, density_kg_m3: float) -> float:
    """Specific absorption rate, W/kg: SAR = σ·E²/ρ (E is the RMS field inside
    the tissue). Pool: E0A08 (SAR is the rate at which the body absorbs RF energy)."""
    if conductivity_s_per_m < 0 or density_kg_m3 <= 0:
        raise ValueError("conductivity must be >= 0 and density > 0")
    return conductivity_s_per_m * e_rms_v_per_m ** 2 / density_kg_m3


def average_power(peak_w: float, duty_cycle: float = 1.0, tx_fraction: float = 1.0) -> float:
    """Time-averaged power, W: peak (PEP) × mode duty cycle × fraction of the
    averaging period spent transmitting. Both fractions are 0 … 1."""
    if peak_w < 0:
        raise ValueError("power must be >= 0")
    if not 0.0 <= duty_cycle <= 1.0 or not 0.0 <= tx_fraction <= 1.0:
        raise ValueError("duty cycle and transmit fraction must be in [0, 1]")
    return peak_w * duty_cycle * tx_fraction


def eirp_w(power_at_antenna_w: float, gain_dbi: float) -> float:
    """EIRP (W) from the power delivered to the antenna and its gain in dBi."""
    return power_at_antenna_w * 10.0 ** (gain_dbi / 10.0)


def power_density(eirp_watts: float, distance_m: float, reflection: float = 1.0) -> float:
    """Far-field power density, mW/cm²: S = F·EIRP / (4πR²).

    ``reflection`` is the power-density factor F: 1 for free space, 4 for full
    in-phase reflection (field doubled). Requires distance > 0.
    """
    if distance_m <= 0:
        raise ValueError("distance must be > 0")
    if eirp_watts < 0 or reflection <= 0:
        raise ValueError("EIRP must be >= 0 and the reflection factor > 0")
    s_w_m2 = reflection * eirp_watts / (4.0 * math.pi * distance_m ** 2)
    return s_w_m2 / 10.0  # 1 mW/cm² = 10 W/m²


def compliance_distance(eirp_watts: float, f_mhz: float, tier: str = "uncontrolled",
                        reflection: float = 1.0) -> float:
    """Distance (m) beyond which the far-field power density is at or below the
    MPE limit: R = √(F·EIRP / (4π·S_limit))."""
    if eirp_watts < 0 or reflection <= 0:
        raise ValueError("EIRP must be >= 0 and the reflection factor > 0")
    s_limit_w_m2 = 10.0 * mpe_power_density(f_mhz, tier)
    return math.sqrt(reflection * eirp_watts / (4.0 * math.pi * s_limit_w_m2))


def percent_of_mpe(density_mw_cm2: float, f_mhz: float, tier: str = "uncontrolled") -> float:
    """A power density as a percent of the MPE limit. (At a multi-transmitter
    site, each licensee above 5 % shares responsibility — 47 CFR § 1.1307(b)(5);
    pool E0A04.)"""
    return 100.0 * density_mw_cm2 / mpe_power_density(f_mhz, tier)


def exemption_min_distance(f_mhz: float) -> float:
    """λ/2π in metres: the closest distance at which the § 1.1307(b)(3)(i)(C)
    exemption table may be used."""
    if f_mhz <= 0:
        raise ValueError("frequency must be > 0")
    return C / (f_mhz * 1e6) / (2.0 * math.pi)


def exemption_threshold_erp(f_mhz: float, distance_m: float) -> float:
    """Threshold ERP (W) from 47 CFR § 1.1307(b)(3)(i)(C) Table 1.

    A single fixed source whose ERP is no more than this at ``distance_m`` from
    any person is exempt from routine evaluation. Raises ValueError when the
    distance is under λ/2π (where the table does not apply) or the frequency is
    outside 0.3 MHz – 100 GHz. At a boundary frequency the smaller value is used.
    """
    if distance_m <= 0:
        raise ValueError("distance must be > 0")
    rows = _rows_for(_EXEMPT_TABLE, f_mhz)
    if distance_m < exemption_min_distance(f_mhz):
        raise ValueError("the exemption table applies only at distances of at least λ/2π")
    return min(row[2](f_mhz, distance_m) for row in rows)


def evaluate_station(*, f_mhz: float, power_w: float, feedline_loss_db: float = 0.0,
                     gain_dbi: float = 0.0, duty_cycle: float = 1.0,
                     tx_fraction: float = 1.0, reflection: float = 1.0,
                     distance_m: float | None = None) -> dict:
    """The whole chain for one station, as the RF exposure dialog shows it.

    Returns a dict with ``avg_power_w`` (at the antenna), ``eirp_w``,
    ``erp_w``, ``limits`` (per tier), ``compliance_m`` (per tier), and — when
    ``distance_m`` is given — ``density`` (mW/cm²), ``percent`` (per tier),
    ``exempt_threshold_erp_w`` (or None where the table does not apply) and
    ``exempt`` (True/False/None).
    """
    if feedline_loss_db < 0:
        raise ValueError("feed-line loss must be >= 0 dB")
    p_ant = average_power(power_w, duty_cycle, tx_fraction) * 10.0 ** (-feedline_loss_db / 10.0)
    eirp = eirp_w(p_ant, gain_dbi)
    out = {
        "avg_power_w": p_ant,
        "eirp_w": eirp,
        "erp_w": eirp / DIPOLE_GAIN,
        "limits": {t: mpe_limits(f_mhz, t) for t in TIERS},
        "compliance_m": {t: compliance_distance(eirp, f_mhz, t, reflection) for t in TIERS},
        "reflection": reflection,
        "min_exempt_distance_m": exemption_min_distance(f_mhz),
    }
    if distance_m is not None:
        s = power_density(eirp, distance_m, reflection)
        out["distance_m"] = distance_m
        out["density"] = s
        out["percent"] = {t: percent_of_mpe(s, f_mhz, t) for t in TIERS}
        try:
            thr = exemption_threshold_erp(f_mhz, distance_m)
        except ValueError:
            thr = None
        out["exempt_threshold_erp_w"] = thr
        out["exempt"] = None if thr is None else out["erp_w"] <= thr
    return out
