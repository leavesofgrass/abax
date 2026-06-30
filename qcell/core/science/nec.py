"""Read and write NEC ``.nec`` antenna decks and solve them with the built-in MoM.

Pure stdlib. NEC is the lingua franca of wire-antenna modeling. This module parses
the geometry and excitation of a NEC2 deck into the wavelength-normalized form
:mod:`qcell.core.science.wire_mom` understands, and writes one back out, so qcell
can exchange models with NEC tools (4nec2, EZNEC, xnec2c, ...).

Supported cards: ``GW`` (wire geometry), ``GE`` (geometry end), ``EX`` (voltage
excitation, type 0), ``FR`` (frequency), ``CM``/``CE`` (comments), ``EN`` (end).
Other cards (``GN``, ``LD``, ``RP`` ...) are recognized and ignored with a note.

Units: NEC coordinates and radii are in **metres** at the deck frequency; we
convert to wavelengths via lambda = c / f. NEC excites a *segment*; the built-in
node-based solver feeds the nearest node, so a half-segment offset is possible --
fine for engineering use, and exact when a node lands on the feed (even segment
counts). The solution is the built-in MoM; for reference-grade accuracy run the
same deck through NEC/PyNEC.
"""

from __future__ import annotations

import math

_C = 299_792_458.0          # m/s


class NecModel:
    """A parsed deck: wires (polylines in wavelengths), feeds, frequency, notes."""
    __slots__ = ("wires", "radii_wl", "feeds", "frequency_mhz", "comments",
                 "ignored", "_seg_counts")

    def __init__(self):
        self.wires: list[list[tuple]] = []        # each: list of (x,y,z) in wl
        self.radii_wl: list[float] = []           # one radius per wire
        self.feeds: list[tuple] = []              # (wire_index, node_index, volts)
        self.frequency_mhz: float = 0.0
        self.comments: list[str] = []
        self.ignored: list[str] = []
        self._seg_counts: list[int] = []          # segments per wire (NEC ns)


def _fields(line: str) -> list[str]:
    """Split a NEC card body into fields (comma and/or whitespace delimited)."""
    return line.replace(",", " ").split()


def parse_nec(text: str) -> NecModel:
    """Parse NEC deck text into a :class:`NecModel`.

    The frequency card is needed to scale metres to wavelengths; if absent the
    geometry is left in metres (frequency 0) and solving will raise.
    """
    raw_gw: list[tuple] = []      # (tag, ns, p1_m, p2_m, radius_m)
    raw_ex: list[tuple] = []      # (tag, seg, volts)
    freq_mhz = 0.0
    comments: list[str] = []
    ignored: list[str] = []

    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        card = s[:2].upper()
        body = s[2:]
        if card in ("CM", "CE"):
            comments.append(body.strip())
            continue
        f = _fields(body)
        if card == "GW":
            if len(f) < 9:
                raise ValueError(f"GW card needs 9 fields: {s!r}")
            tag = int(float(f[0]))
            ns = int(float(f[1]))
            p1 = (float(f[2]), float(f[3]), float(f[4]))
            p2 = (float(f[5]), float(f[6]), float(f[7]))
            raw_gw.append((tag, ns, p1, p2, float(f[8])))
        elif card == "EX":
            if f and int(float(f[0])) == 0 and len(f) >= 3:
                tag = int(float(f[1]))
                seg = int(float(f[2]))
                vr = float(f[4]) if len(f) > 4 else 1.0
                vi = float(f[5]) if len(f) > 5 else 0.0
                raw_ex.append((tag, seg, complex(vr, vi)))
            else:
                ignored.append(card)
        elif card == "FR":
            if len(f) >= 5:
                freq_mhz = float(f[4])
        elif card in ("GE", "EN"):
            continue
        else:
            ignored.append(card)

    model = NecModel()
    model.frequency_mhz = freq_mhz
    model.comments = comments
    model.ignored = sorted(set(ignored))
    if freq_mhz <= 0.0:
        # leave geometry in metres; mark unscaled by storing wavelength 1 m later
        lam = 1.0
    else:
        lam = _C / (freq_mhz * 1e6)

    tag_to_index = {}
    for (tag, ns, p1, p2, radius_m) in raw_gw:
        ns = max(1, ns)
        pts = []
        for i in range(ns + 1):
            t = i / ns
            pts.append(tuple((p1[d] + (p2[d] - p1[d]) * t) / lam for d in range(3)))
        tag_to_index[tag] = len(model.wires)
        model.wires.append(pts)
        model.radii_wl.append(radius_m / lam)
        model._seg_counts.append(ns)

    for (tag, seg, volts) in raw_ex:
        if tag not in tag_to_index:
            model.ignored.append("EX(no-wire)")
            continue
        wi = tag_to_index[tag]
        ns = model._seg_counts[wi]
        node = min(max(seg, 1), ns - 1) if ns >= 2 else 1   # nearest interior node
        model.feeds.append((wi, node, volts))
    return model


def solve(model: NecModel, radius_default: float = 1e-3) -> dict:
    """Solve a parsed model with the built-in :mod:`wire_mom` MoM.

    Each wire uses its own radius (NEC per-wire radius). Returns the wire_mom
    result dict (``current``, ``feed_impedance``, ``n_basis``).
    """
    from . import wire_mom
    if not model.wires:
        raise ValueError("no wires to solve")
    if model.frequency_mhz <= 0.0:
        raise ValueError("deck has no FR (frequency) card; cannot scale geometry")
    if not model.feeds:
        raise ValueError("deck has no EX (excitation) card")
    radius = model.radii_wl[0] if model.radii_wl else radius_default
    return wire_mom.solve(model.wires, model.feeds, radius=radius)


def _straight_runs(points, tol=1e-9):
    """Yield (start_point, end_point, n_segments) for each maximal collinear run."""
    n = len(points) - 1
    if n < 1:
        return
    i = 0
    while i < n:
        j = i + 1
        # extend while the next segment is parallel to the first of this run
        def dirv(a, b):
            v = tuple(b[d] - a[d] for d in range(3))
            m = math.sqrt(sum(c * c for c in v)) or 1.0
            return tuple(c / m for c in v)
        d0 = dirv(points[i], points[i + 1])
        while j < n:
            dj = dirv(points[j], points[j + 1])
            if all(abs(dj[d] - d0[d]) < tol for d in range(3)):
                j += 1
            else:
                break
        yield points[i], points[j], (j - i)
        i = j


def to_nec(wires, feeds, frequency_mhz, radii_wl=None, comment="qcell model") -> str:
    """Write a NEC deck (string) for wires given in **wavelengths** at
    ``frequency_mhz``. Straight runs of a polyline collapse to one GW card.
    ``feeds`` is ``[(wire_index, node_index, volts), ...]``; ``radii_wl`` is an
    optional per-wire radius list (defaults to 1e-3 wl)."""
    if frequency_mhz <= 0.0:
        raise ValueError("frequency_mhz must be > 0")
    lam = _C / (frequency_mhz * 1e6)
    radii = radii_wl or [1e-3] * len(wires)
    lines = [f"CM {comment}", "CE"]

    # tag bookkeeping: one GW (and tag) per straight run; remember which (tag,seg)
    # a (wire,node) maps to for the EX cards.
    tag = 0
    node_to_tagseg = {}
    gw_lines = []
    for wi, pts in enumerate(wires):
        a = radii[wi] * lam
        base_node = 0
        for (p_start, p_end, nseg) in _straight_runs(pts):
            tag += 1
            x1, y1, z1 = (c * lam for c in p_start)
            x2, y2, z2 = (c * lam for c in p_end)
            gw_lines.append(
                f"GW {tag} {nseg} {x1:.6g} {y1:.6g} {z1:.6g} "
                f"{x2:.6g} {y2:.6g} {z2:.6g} {a:.6g}")
            for local in range(nseg + 1):
                node_to_tagseg[(wi, base_node + local)] = (tag, local)
            base_node += nseg
    lines += gw_lines
    lines.append("GE 0")
    for (wi, node, volts) in feeds:
        tagseg = node_to_tagseg.get((wi, node))
        if tagseg is None:
            continue
        t, seg = tagseg
        seg = max(1, seg)
        v = complex(volts)
        lines.append(f"EX 0 {t} {seg} 0 {v.real:.6g} {v.imag:.6g}")
    lines.append(f"FR 0 1 0 0 {frequency_mhz:.6g} 0")
    lines.append("EN")
    return "\n".join(lines) + "\n"
