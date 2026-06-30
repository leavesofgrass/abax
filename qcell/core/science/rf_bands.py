"""Amateur-radio reference data: US band plan and the standard CTCSS tones.

Pure stdlib, pure data + small lookups. Frequencies are in **hertz** to match the
rest of :mod:`qcell.core.science.rf` (the spreadsheet/GUI layers convert to MHz
for display). The band edges are the US amateur allocations (FCC Part 97, ITU
Region 2); the CTCSS list is the 50-tone EIA standard used by virtually every
amateur FM radio.

Domain errors raise :class:`ValueError` so the formula layer maps them to a
``CellError``.
"""

from __future__ import annotations

# (name, low_hz, high_hz) -- US amateur bands, lowest to highest. The 60 m band
# is channelized (five USB channels); the span from the lowest to the highest
# channel centre is shown so a frequency in that window still resolves to "60m".
US_AMATEUR_BANDS: tuple[tuple[str, int, int], ...] = (
    ("2200m", 135_700, 137_800),
    ("630m", 472_000, 479_000),
    ("160m", 1_800_000, 2_000_000),
    ("80m", 3_500_000, 4_000_000),
    ("60m", 5_330_500, 5_403_500),
    ("40m", 7_000_000, 7_300_000),
    ("30m", 10_100_000, 10_150_000),
    ("20m", 14_000_000, 14_350_000),
    ("17m", 18_068_000, 18_168_000),
    ("15m", 21_000_000, 21_450_000),
    ("12m", 24_890_000, 24_990_000),
    ("10m", 28_000_000, 29_700_000),
    ("6m", 50_000_000, 54_000_000),
    ("2m", 144_000_000, 148_000_000),
    ("1.25m", 222_000_000, 225_000_000),
    ("70cm", 420_000_000, 450_000_000),
    ("33cm", 902_000_000, 928_000_000),
    ("23cm", 1_240_000_000, 1_300_000_000),
)

# EIA standard CTCSS (PL) sub-audible tone frequencies, in hertz, tone 1..50.
CTCSS_TONES: tuple[float, ...] = (
    67.0, 69.3, 71.9, 74.4, 77.0, 79.7, 82.5, 85.4, 88.5, 91.5,
    94.8, 97.4, 100.0, 103.5, 107.2, 110.9, 114.8, 118.8, 123.0, 127.3,
    131.8, 136.5, 141.3, 146.2, 151.4, 156.7, 159.8, 162.2, 165.5, 167.9,
    171.3, 173.8, 177.3, 179.9, 183.5, 186.2, 189.9, 192.8, 196.6, 199.5,
    203.5, 206.5, 210.7, 218.1, 225.7, 229.1, 233.6, 241.8, 250.3, 254.1,
)


def band_for_frequency(hz: float) -> str | None:
    """The US amateur band name whose edges bracket ``hz``, or ``None``.

    Edges are inclusive; bands do not overlap, so the first match is the band.
    """
    for name, lo, hi in US_AMATEUR_BANDS:
        if lo <= hz <= hi:
            return name
    return None


def band_edges(name: str) -> tuple[int, int]:
    """``(low_hz, high_hz)`` for an amateur band name (e.g. ``"20m"``).

    Raises :class:`ValueError` for an unknown band.
    """
    key = name.strip().lower()
    for bname, lo, hi in US_AMATEUR_BANDS:
        if bname.lower() == key:
            return lo, hi
    raise ValueError(f"unknown amateur band: {name!r}")


def ctcss_tone(index: int) -> float:
    """The frequency (Hz) of the 1-based EIA CTCSS tone number (1..50)."""
    if not 1 <= index <= len(CTCSS_TONES):
        raise ValueError(f"CTCSS tone number must be 1..{len(CTCSS_TONES)}")
    return CTCSS_TONES[index - 1]


def nearest_ctcss(freq: float) -> float:
    """The standard CTCSS tone (Hz) closest to ``freq`` (ties pick the lower)."""
    return min(CTCSS_TONES, key=lambda t: (abs(t - freq), t))
