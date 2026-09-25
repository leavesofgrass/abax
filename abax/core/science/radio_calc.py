"""Radio-system calculations — pure stdlib.

The station- and system-level arithmetic of advanced amateur work: ERP/EIRP
through a chain of gains and losses, received level and link margin, noise
versus bandwidth, op-amp gain, FM modulation index and bandwidth, necessary
bandwidth of CW and FSK emissions, ADC resolution and sampling, sideband
band-edge limits, feed-line electrical length, stub reactance, antenna
efficiency, and receiver intermodulation / image arithmetic.

SI base units (Hz, W, m, Ω, V); levels in dB / dBm / dBi / dBd. Domain errors
raise :class:`ValueError`. Where a relation is what the FCC Amateur Extra
(Element 4, 2024–2028) question pool tests, the question IDs are noted so the
worked examples can be checked against the pool's answer key; where a formula
comes from an FCC rule, the rule is cited.
"""

from __future__ import annotations

import math
from typing import Iterable

C = 299_792_458.0  # speed of light, m/s


# --- power through a chain of gains and losses -----------------------------

def power_through_chain(power_w: float, gain_db: float, losses_db: Iterable[float] = ()) -> float:
    """Output power (W) after an antenna ``gain_db`` and positive ``losses_db``:
    P · 10^((gain − Σlosses)/10).

    With ``gain_db`` in dBd the result is ERP; in dBi it is EIRP.
    Pool: E9A02, E9A06 (ERP) and E9A07 (EIRP).
    """
    if power_w < 0:
        raise ValueError("power must be >= 0")
    net = gain_db - math.fsum(float(x) for x in losses_db)
    return power_w * 10.0 ** (net / 10.0)


def received_level_dbm(ptx_dbm: float, gtx_dbi: float, grx_dbi: float,
                       path_loss_db: float, cable_loss_db: float = 0.0) -> float:
    """Received signal level: Ptx + Gtx + Grx − path loss − cable loss (dBm).
    Pool: E4D12, E4D13."""
    return ptx_dbm + gtx_dbi + grx_dbi - path_loss_db - cable_loss_db


def link_margin_db(rx_dbm: float, mds_dbm: float, snr_db: float = 0.0) -> float:
    """Link margin: received level − (minimum discernible signal + required
    SNR), dB. Pool: E4D12."""
    return rx_dbm - (mds_dbm + snr_db)


def noise_bandwidth_change_db(bw_from_hz: float, bw_to_hz: float) -> float:
    """Change in noise power (dB) when the receive bandwidth changes:
    10·log10(B₂/B₁). Pool: E4C06."""
    if bw_from_hz <= 0 or bw_to_hz <= 0:
        raise ValueError("bandwidths must be > 0")
    return 10.0 * math.log10(bw_to_hz / bw_from_hz)


# --- op-amps ------------------------------------------------------------------

def opamp_inverting_gain(rf_ohm: float, rin_ohm: float) -> float:
    """Inverting op-amp voltage gain −Rf/Rin (the sign marks the 180° phase
    inversion). Pool: E7G07, E7G09, E7G10, E7G11."""
    if rin_ohm <= 0 or rf_ohm < 0:
        raise ValueError("Rin must be > 0 and Rf >= 0")
    return -rf_ohm / rin_ohm


def opamp_noninverting_gain(rf_ohm: float, rin_ohm: float) -> float:
    """Non-inverting op-amp voltage gain 1 + Rf/Rin."""
    if rin_ohm <= 0 or rf_ohm < 0:
        raise ValueError("Rin must be > 0 and Rf >= 0")
    return 1.0 + rf_ohm / rin_ohm


# --- FM / PM ------------------------------------------------------------------

def modulation_index(deviation_hz: float, modulating_hz: float) -> float:
    """FM modulation index m = Δf / fm. With the peak deviation and the highest
    modulating frequency it is the *deviation ratio*. Pool: E8B01, E8B03–E8B06,
    E8B09."""
    if modulating_hz <= 0 or deviation_hz < 0:
        raise ValueError("modulating frequency must be > 0 and deviation >= 0")
    return deviation_hz / modulating_hz


def carson_bandwidth(deviation_hz: float, modulating_hz: float) -> float:
    """Carson's rule FM bandwidth 2·(Δf + fm), Hz. This is also the 47 CFR
    § 2.202(g) necessary bandwidth for FM telephony, Bn = 2M + 2DK, with the
    rule's typical K = 1."""
    if modulating_hz < 0 or deviation_hz < 0:
        raise ValueError("deviation and modulating frequency must be >= 0")
    return 2.0 * (deviation_hz + modulating_hz)


# --- necessary bandwidth (47 CFR § 2.202(g)) ---------------------------------

# 47 CFR 2.202(g) gives no general words-per-minute → baud conversion. Its CW
# worked example pairs 25 wpm with B = 20 baud, i.e. 0.8 baud per wpm, and the
# Extra pool (E8C05, 13 wpm → 52 Hz) uses the same ratio with K = 5.
WPM_TO_BAUD = 0.8


def cw_bandwidth(wpm: float, k: float = 5.0) -> float:
    """Necessary bandwidth of Morse CW, Hz: Bn = B·K (47 CFR § 2.202(g)), with
    B = 0.8·wpm (the ratio in that rule's worked example). K = 5 for fading
    circuits, 3 for non-fading. Pool: E8C05."""
    if wpm <= 0 or k <= 0:
        raise ValueError("wpm and K must be > 0")
    return WPM_TO_BAUD * wpm * k


def fsk_bandwidth(shift_hz: float, baud: float, k: float = 1.2) -> float:
    """Necessary bandwidth of frequency-shift keying, Hz (47 CFR § 2.202(g)):
    Bn = 2M + 2DK with M = B/2 and D = shift/2, i.e. B + K·shift. K = 1.2 is
    the rule's typical value. Pool: E8C07."""
    if shift_hz < 0 or baud <= 0 or k <= 0:
        raise ValueError("shift must be >= 0, baud and K > 0")
    return baud + k * shift_hz


# --- sampling / ADC -----------------------------------------------------------

def adc_bits(range_v: float, resolution_v: float) -> int:
    """Minimum ADC bits to resolve ``resolution_v`` across ``range_v``:
    the smallest N with 2^N ≥ range/resolution. Pool: E7F06."""
    if range_v <= 0 or resolution_v <= 0:
        raise ValueError("range and resolution must be > 0")
    steps = range_v / resolution_v
    n = max(0, math.ceil(math.log2(steps)))
    # Guard floating-point at exact powers of two (e.g. 1024 → 10, not 11).
    if n > 0 and 2 ** (n - 1) >= steps * (1 - 1e-12):
        n -= 1
    return n


def adc_levels(bits: float) -> int:
    """Number of discrete levels of an N-bit converter: 2^N. Pool: E8A09."""
    n = int(bits)
    if n != bits or n < 0:
        raise ValueError("bits must be a non-negative integer")
    return 2 ** n


def adc_lsb(reference_v: float, bits: float) -> float:
    """Size of one least-significant bit: Vref / 2^N (volts). Pool: E7F11."""
    return reference_v / adc_levels(bits)


def adc_ideal_snr_db(bits: float) -> float:
    """Ideal quantization SNR of an N-bit converter for a full-scale sine wave:
    20·log10(2^N) + 10·log10(1.5) ≈ 6.02·N + 1.76 dB."""
    n = adc_levels(bits)
    return 20.0 * math.log10(n) + 10.0 * math.log10(1.5)


def nyquist_rate(max_freq_hz: float) -> float:
    """Minimum sampling rate that can represent ``max_freq_hz``: 2·fmax.
    Pool: E7F05 (and E7F10: an SDR's bandwidth is at most fs/2)."""
    if max_freq_hz < 0:
        raise ValueError("frequency must be >= 0")
    return 2.0 * max_freq_hz


# --- sideband band edges ------------------------------------------------------

def usb_max_carrier(upper_edge_hz: float, bandwidth_hz: float = 3000.0) -> float:
    """Highest displayed (carrier) frequency for an upper-sideband signal to
    stay inside ``upper_edge_hz``: USB occupies f to f + BW, so f ≤ edge − BW.
    Pool: E1A01, E1A03."""
    if bandwidth_hz < 0:
        raise ValueError("bandwidth must be >= 0")
    return upper_edge_hz - bandwidth_hz


def lsb_min_carrier(lower_edge_hz: float, bandwidth_hz: float = 3000.0) -> float:
    """Lowest displayed (carrier) frequency for a lower-sideband signal to stay
    inside ``lower_edge_hz``: LSB occupies f − BW to f, so f ≥ edge + BW.
    Pool: E1A02, E1A04."""
    if bandwidth_hz < 0:
        raise ValueError("bandwidth must be >= 0")
    return lower_edge_hz + bandwidth_hz


# --- feed lines & stubs ---------------------------------------------------------

def line_length(freq_hz: float, fraction_wl: float, velocity_factor: float = 1.0) -> float:
    """Physical length (m) of a line that is ``fraction_wl`` wavelengths long
    electrically: VF · (c/f) · fraction. Pool: E9F06."""
    if freq_hz <= 0 or velocity_factor <= 0 or fraction_wl < 0:
        raise ValueError("frequency and velocity factor must be > 0, fraction >= 0")
    return velocity_factor * C / freq_hz * fraction_wl


def electrical_length_deg(length_m: float, freq_hz: float, velocity_factor: float = 1.0) -> float:
    """Electrical length in degrees of a physical line: 360 · length / (VF·λ)."""
    if freq_hz <= 0 or velocity_factor <= 0 or length_m < 0:
        raise ValueError("frequency and velocity factor must be > 0, length >= 0")
    return 360.0 * length_m * freq_hz / (velocity_factor * C)


def stub_reactance(z0_ohm: float, electrical_length_deg: float, open_end: bool = False) -> float:
    """Input reactance (Ω) of a lossless stub.

    Shorted: X = Z0·tan(βl) — λ/8 is inductive (+Z0), λ/4 is an open circuit,
    λ/2 a short. Open: X = −Z0·cot(βl) — λ/8 is capacitive (−Z0), λ/4 a short.
    Positive X is inductive. Raises ValueError at the ideal poles (infinite
    reactance). Pool: E9F04, E9F09–E9F12.
    """
    if z0_ohm <= 0:
        raise ValueError("characteristic impedance must be > 0")
    bl = math.radians(electrical_length_deg)
    s, c = math.sin(bl), math.cos(bl)
    if open_end:
        if abs(s) < 1e-12:
            raise ValueError("open stub at a multiple of λ/2 has infinite reactance")
        return -z0_ohm * c / s
    if abs(c) < 1e-12:
        raise ValueError("shorted stub at an odd multiple of λ/4 has infinite reactance")
    return z0_ohm * s / c


# --- antennas -------------------------------------------------------------------

def antenna_efficiency(r_radiation_ohm: float, r_loss_ohm: float) -> float:
    """Antenna efficiency η = Rrad / (Rrad + Rloss), 0 … 1. Pool: E9A09."""
    if r_radiation_ohm <= 0 or r_loss_ohm < 0:
        raise ValueError("radiation resistance must be > 0 and loss resistance >= 0")
    return r_radiation_ohm / (r_radiation_ohm + r_loss_ohm)


# --- receiver performance -------------------------------------------------------

def imd3_products(f1_hz: float, f2_hz: float) -> tuple[float, float]:
    """The two third-order intermodulation products of two tones, low then
    high: (2f₁ − f₂, 2f₂ − f₁) with f₁ < f₂. They fall close to the tones —
    why odd-order IMD matters (pool: E4D11)."""
    lo, hi = sorted((float(f1_hz), float(f2_hz)))
    return 2.0 * lo - hi, 2.0 * hi - lo


def third_order_intercept_dbm(tone_dbm: float, im3_dbm: float) -> float:
    """Third-order intercept point from a two-tone test: P_tone + (P_tone −
    P_IM3)/2, dBm. With output-referred levels it is OIP3; subtract the gain
    for IIP3. (IM3 rises 3 dB per 1 dB of drive; the extrapolated lines meet
    at the intercept — pool: E4D10.)"""
    return tone_dbm + (tone_dbm - im3_dbm) / 2.0


def sfdr_db(ip3_dbm: float, noise_floor_dbm: float) -> float:
    """Spurious-free (third-order) dynamic range, dB: (2/3)·(IP3 − noise
    floor), with both referred to the same point (input or output)."""
    return 2.0 * (ip3_dbm - noise_floor_dbm) / 3.0


def image_frequency(signal_hz: float, if_hz: float, high_side_lo: bool = True) -> float:
    """Image frequency of a superhet: signal + 2·IF when the local oscillator is
    above the signal (high-side injection), signal − 2·IF when below."""
    if signal_hz <= 0 or if_hz <= 0:
        raise ValueError("signal and IF must be > 0")
    image = signal_hz + 2.0 * if_hz if high_side_lo else signal_hz - 2.0 * if_hz
    if image <= 0:
        raise ValueError("image frequency would be <= 0")
    return image
