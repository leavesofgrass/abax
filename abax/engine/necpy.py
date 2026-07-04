"""PyNEC adapter — the reference-grade optional solver for NEC antenna decks.

The middle-layer (engine) counterpart to the built-in Method-of-Moments solver in
:mod:`abax.core.science.nec` / :mod:`abax.core.science.wire_mom`. Those are pure
stdlib and always available; this module instead drives **PyNEC** (the Python
binding for the classic NEC2 kernel), which is the community reference for
wire-antenna accuracy but is a heavyweight, optional native dependency.

PyNEC is almost never installed, so the import is guarded: importing this module
never fails, and :func:`available` reports whether the real solve path can run.
The parse / serialise / metadata plumbing (via :mod:`abax.core.science.nec`) is
pure stdlib and always exercised; only the actual field solve needs PyNEC.

Units: abax keeps geometry in **wavelengths**; PyNEC (like NEC itself) works in
**metres** at a real frequency. We convert with ``lam = c / f`` before feeding the
kernel. NEC excites a *segment*; we pass the feed segment straight through.
"""

from __future__ import annotations

import math

from abax.core.science import nec

_C = 299_792_458.0          # m/s
_TWO_PI = 2.0 * math.pi


class PyNecUnavailable(RuntimeError):
    """Raised when a PyNEC solve is requested but PyNEC is not installed."""


def available() -> bool:
    """True iff PyNEC can be imported (does not raise)."""
    try:
        import PyNEC  # noqa: F401
    except Exception:
        return False
    return True


def solve_deck(nec_text: str) -> dict:
    """Solve a NEC deck string with PyNEC and return a result dict.

    Result::

        {
          "source": "pynec",
          "frequency_mhz": float,
          "feed_impedance": complex,   # input impedance at the first excitation
          "n_segments": int,
        }

    Ordering matters: the deck is parsed and its geometry/excitation validated
    **first** (raising :class:`ValueError` on an empty deck, no ``GW`` geometry,
    or no ``EX`` excitation), and only then is PyNEC required (raising
    :class:`PyNecUnavailable` when absent). This keeps both failure modes
    deterministic whether or not PyNEC happens to be installed.
    """
    # --- parse + validate geometry/excitation FIRST (stdlib, always runs) ---
    model = nec.parse_nec(nec_text)
    if not model.wires:
        raise ValueError("deck has no GW (wire geometry) card")
    if model.frequency_mhz <= 0.0:
        raise ValueError("deck has no FR (frequency) card; cannot scale geometry")
    if not model.feeds:
        raise ValueError("deck has no EX (excitation) card")

    freq_mhz = float(model.frequency_mhz)
    n_segments = sum(model._seg_counts) if model._seg_counts else 0

    # --- now require PyNEC ---
    try:
        import PyNEC
    except Exception as exc:  # ImportError and any native load failure
        raise PyNecUnavailable(
            "PyNEC is not installed; install the 'PyNEC' package to use the "
            "reference solver, or fall back to abax.core.science.nec.solve"
        ) from exc

    lam = _C / (freq_mhz * 1e6)

    # PyNEC's high-level context API is version-sensitive; drive it defensively
    # so a mismatched build surfaces as PyNecUnavailable rather than AttributeError.
    try:
        context = PyNEC.nec_context()
        geo = context.get_geometry()

        # Add each wire as a straight NEC segment run, converting wl -> metres.
        tag = 0
        for wi, pts in enumerate(model.wires):
            if len(pts) < 2:
                continue
            nseg = model._seg_counts[wi] if wi < len(model._seg_counts) else 1
            nseg = max(1, int(nseg))
            radius_m = (model.radii_wl[wi] if wi < len(model.radii_wl) else 1e-3) * lam
            p1 = pts[0]
            p2 = pts[-1]
            x1, y1, z1 = (c * lam for c in p1)
            x2, y2, z2 = (c * lam for c in p2)
            tag += 1
            # geo.wire(tag, nseg, x1,y1,z1, x2,y2,z2, radius, rdel, rrad)
            geo.wire(tag, nseg, x1, y1, z1, x2, y2, z2, radius_m, 1.0, 1.0)

        context.geometry_complete(0)

        # Frequency card: fr_card(ifrq, nfrq, freq_mhz, del_freq)
        context.fr_card(0, 1, freq_mhz, 0.0)

        # Excitation: use the first feed. NEC segments are 1-based; our node index
        # is an interior node, which maps directly onto a segment number.
        feed_wi, feed_node, feed_volts = model.feeds[0]
        ex_tag = feed_wi + 1
        ex_seg = max(1, int(feed_node))
        volts = complex(feed_volts)
        # ex_card(type, tag, seg, cnt, vr, vi, ...)
        context.ex_card(0, ex_tag, ex_seg, 0, volts.real, volts.imag, 0.0, 0.0, 0.0, 0.0)

        # Run the frequency sweep (execute) and read input parameters.
        context.xq_card(0)
        ipt = context.get_input_parameters(0)
        z_arr = ipt.get_impedance()
        z0 = z_arr[0]
        feed_impedance = complex(z0)
    except PyNecUnavailable:
        raise
    except Exception as exc:
        raise PyNecUnavailable(
            "the installed PyNEC has an unexpected API "
            f"({type(exc).__name__}: {exc})"
        ) from exc

    return {
        "source": "pynec",
        "frequency_mhz": freq_mhz,
        "feed_impedance": feed_impedance,
        "n_segments": int(n_segments),
    }


def solve_model(model) -> dict:
    """Solve a abax :class:`~abax.core.science.nec.NecModel` via PyNEC.

    Serialises the model back to a NEC deck with
    :func:`abax.core.science.nec.to_nec` and defers to :func:`solve_deck`, so it
    shares the same validation order and failure modes.
    """
    deck = nec.to_nec(
        model.wires, model.feeds, model.frequency_mhz, radii_wl=model.radii_wl
    )
    return solve_deck(deck)


def pattern_cut(nec_text: str, plane: str = "azimuth", count: int = 361,
                decibels: bool = True, fixed_phi: float = 0.0,
                floor_db: float = -40.0):
    """Read a **free-space** radiation cut back from a solved deck via PyNEC.

    Emits an ``RP`` card over the requested principal plane and parses the
    resulting gains, returning ``[(angle_rad, value)]`` samples in exactly the
    shape :func:`abax.core.science.wire_mom.pattern_cut` produces (normalised to a
    peak of 1; 0..1 mapped from ``floor_db``..0 dB when ``decibels``), so the
    caller can prefer PyNEC when present and fall back to the built-in MoM
    otherwise. ``plane`` is ``"azimuth"`` (sweep φ at θ = 90°) or ``"elevation"``
    (sweep θ at φ = ``fixed_phi``).

    Ordering mirrors :func:`solve_deck`: geometry / frequency / excitation are
    parsed and validated **first** (raising :class:`ValueError`), and only then is
    PyNEC required (raising :class:`PyNecUnavailable` when absent or on a
    mismatched build). The far field is free space — the elevation cut is
    symmetric about the horizon and is *not* an installed-height take-off pattern.
    """
    if plane not in ("azimuth", "elevation"):
        raise ValueError("plane must be 'azimuth' or 'elevation'")
    if count < 2:
        raise ValueError("count must be >= 2")

    # --- parse + validate geometry/excitation FIRST (stdlib, always runs) ---
    model = nec.parse_nec(nec_text)
    if not model.wires:
        raise ValueError("deck has no GW (wire geometry) card")
    if model.frequency_mhz <= 0.0:
        raise ValueError("deck has no FR (frequency) card; cannot scale geometry")
    if not model.feeds:
        raise ValueError("deck has no EX (excitation) card")

    freq_mhz = float(model.frequency_mhz)

    # --- now require PyNEC ---
    try:
        import PyNEC
    except Exception as exc:  # ImportError and any native load failure
        raise PyNecUnavailable(
            "PyNEC is not installed; install the 'PyNEC' package to use the "
            "reference solver, or fall back to "
            "abax.core.science.wire_mom.pattern_cut"
        ) from exc

    lam = _C / (freq_mhz * 1e6)

    # NEC sweeps a grid of (theta, phi); we ask for a 1-D cut and read it back.
    # Angles are NEC-style degrees: theta from +z, phi from +x. A full 0..360
    # sweep needs `count` points including both endpoints, so the step spans the
    # (count-1) intervals.
    steps = count - 1
    if plane == "azimuth":
        # sweep phi at theta = 90 deg
        n_theta, n_phi = 1, count
        theta0, phi0 = 90.0, 0.0
        d_theta, d_phi = 0.0, 360.0 / steps
    else:
        # sweep theta at fixed phi
        n_theta, n_phi = count, 1
        theta0, phi0 = 0.0, math.degrees(fixed_phi)
        d_theta, d_phi = 360.0 / steps, 0.0

    try:
        context = PyNEC.nec_context()
        geo = context.get_geometry()

        tag = 0
        for wi, pts in enumerate(model.wires):
            if len(pts) < 2:
                continue
            nseg = model._seg_counts[wi] if wi < len(model._seg_counts) else 1
            nseg = max(1, int(nseg))
            radius_m = (model.radii_wl[wi] if wi < len(model.radii_wl) else 1e-3) * lam
            p1 = pts[0]
            p2 = pts[-1]
            x1, y1, z1 = (c * lam for c in p1)
            x2, y2, z2 = (c * lam for c in p2)
            tag += 1
            geo.wire(tag, nseg, x1, y1, z1, x2, y2, z2, radius_m, 1.0, 1.0)

        context.geometry_complete(0)
        context.fr_card(0, 1, freq_mhz, 0.0)

        feed_wi, feed_node, feed_volts = model.feeds[0]
        ex_tag = feed_wi + 1
        ex_seg = max(1, int(feed_node))
        volts = complex(feed_volts)
        context.ex_card(0, ex_tag, ex_seg, 0, volts.real, volts.imag, 0.0, 0.0, 0.0, 0.0)

        # rp_card(calc_mode, n_theta, n_phi, output_format, normalization,
        #         D, A, theta0, phi0, delta_theta, delta_phi, radial_distance,
        #         gain_norm). calc_mode 0 = free space (no ground).
        context.rp_card(0, n_theta, n_phi, 0, 0, 0, 0,
                        theta0, phi0, d_theta, d_phi, 0.0, 0.0)

        rpt = context.get_radiation_pattern(0)
        gains_db = rpt.get_gain()               # dBi grid, n_theta x n_phi
    except PyNecUnavailable:
        raise
    except Exception as exc:
        raise PyNecUnavailable(
            "the installed PyNEC has an unexpected API "
            f"({type(exc).__name__}: {exc})"
        ) from exc

    # Flatten the grid to a 1-D list of dBi following the sweep order, then map
    # onto the same normalised polar samples as the built-in MoM cut.
    flat = _flatten_gain(gains_db, count)
    return _gain_db_to_samples(flat, plane, count, fixed_phi, decibels, floor_db)


def _flatten_gain(gains_db, count: int) -> list:
    """Flatten a PyNEC gain grid (nested sequence or flat) to a list of ``count``
    dBi values in sweep order, tolerating numpy arrays and Python lists."""
    vals: list = []
    for row in gains_db:
        if hasattr(row, "__len__") and not isinstance(row, (str, bytes)):
            vals.extend(float(v) for v in row)
        else:
            vals.append(float(row))
    if len(vals) < count and vals:
        # Some builds return a single row/column; repeat-safe pad to length.
        vals = (vals * ((count // len(vals)) + 1))[:count]
    return vals[:count]


def _gain_db_to_samples(gain_db, plane: str, count: int, fixed_phi: float,
                        decibels: bool, floor_db: float) -> list:
    """Map a 1-D list of dBi gains to ``[(angle_rad, value 0..1)]`` samples
    matching :func:`abax.core.science.wire_mom.pattern_cut`."""
    steps = count - 1
    gmax = max(gain_db) if gain_db else 0.0
    out = []
    for i in range(count):
        angle = _TWO_PI * i / steps
        gdb = gain_db[i] if i < len(gain_db) else floor_db
        # dBi -> relative dB (peak 0), then either back to a linear field ratio or
        # the 0..1 floor mapping used for the polar plot.
        rel_db = gdb - gmax
        if decibels:
            lin = max(0.0, (rel_db - floor_db) / (-floor_db))
        else:
            lin = 10.0 ** (rel_db / 20.0)
        out.append((angle, lin))
    return out
