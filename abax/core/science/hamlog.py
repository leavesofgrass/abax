"""Amateur-radio contest / POTA / SOTA logging helpers (pure stdlib).

This module gives the spreadsheet three logging primitives, all backed by plain
Python so they live in the pure-stdlib :mod:`abax.core` layer:

* **Duplicate detection** — :func:`is_dupe` / :func:`find_dupes`. A *dupe* is a
  second (or later) contact with the same station that no longer counts for
  points. What "same" means is set by a :class:`ContestRules` *dupe key*: by
  convention a call may be worked once **per band per mode** during a single
  contest period or POTA/SOTA activation (POTA General Rules 3.6; SOTA GR 3.7.1
  — a chaser scores a summit once per UTC day). Callsigns are normalised first
  (uppercased, portable ``/P`` and prefix/suffix decorations stripped) so
  ``W1AW`` and ``w1aw/p`` collide.

* **Point / multiplier tallying** — :func:`score_log` walks a log in order,
  marks each QSO as a new contact or a dupe, applies the ruleset's per-QSO point
  value (mode-dependent by default: CW/data 2 pts, phone 1 pt — ARRL Field Day
  Rule 7.3.1 and the ARRL/CQ contest conventions), counts multipliers, and
  returns a :class:`ScoreResult` with the running and final totals.

* **Contest scaffolding** — :class:`ContestRules` bundles the dupe key, the
  points function and the multiplier key; :func:`ruleset` returns a named
  preset (``"pota"``, ``"sota"``, ``"fieldday"``, ``"arrl-dx"``, ``"generic"``).

A *log* here is a sequence of QSO mappings. Recognised keys (case-insensitive)
are ``call``/``callsign``, ``band``, ``mode``, ``time``/``qso_date``,
``mult``/``multiplier`` and ``points`` (an explicit override). ADIF field names
(``CALL``, ``BAND``, ``MODE``, ``TIME_ON``) work unchanged, so a log parsed by
:mod:`abax.core.io.adif_io` can be scored directly.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Callable, Optional

# --- callsign / field normalisation ---------------------------------------

# Common portable / operating decorations appended with a slash that do not
# change the identity of the station for dupe purposes.
_DROP_SUFFIXES = frozenset({
    "P", "M", "MM", "AM", "QRP", "A", "R", "B",
})


def normalize_call(call: object) -> str:
    """Return ``call`` upper-cased and stripped of portable decorations.

    A callsign is often logged as ``W1AW/P`` (portable), ``VE3/W1AW`` (foreign
    prefix) or ``W1AW/QRP``. For duplicate checking these all refer to the same
    station, so we reduce to the *base* call: split on ``/``, drop empty and
    known operating suffixes (``P``, ``M``, ``MM``, ``QRP`` …), and of the
    remaining fragments keep the longest (the base call is longer than a bare
    prefix like ``VE3`` or a region digit). Whitespace is trimmed. A blank or
    non-string input yields ``""``.
    """
    if call is None:
        return ""
    text = str(call).strip().upper()
    if not text:
        return ""
    parts = [p for p in text.split("/") if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    # Drop pure operating suffixes; from the rest keep the longest fragment,
    # which is the base call (a prefix/region fragment is shorter).
    kept = [p for p in parts if p not in _DROP_SUFFIXES]
    if not kept:
        kept = parts
    return max(kept, key=len)


def _norm_field(value: object) -> str:
    """Uppercase, trim a band/mode token; ``None``/blank become ``""``."""
    if value is None:
        return ""
    return str(value).strip().upper()


# Fold ADIF sub-modes and common variants onto a canonical mode family so that,
# e.g., ``USB``/``LSB``/``SSB`` all count as phone and ``PSK31``/``FT8`` as data.
_MODE_ALIASES = {
    "USB": "SSB", "LSB": "SSB", "FM": "FM", "AM": "AM",
    "SSB": "SSB", "CW": "CW",
    "FT8": "DATA", "FT4": "DATA", "PSK": "DATA", "PSK31": "DATA",
    "RTTY": "DATA", "JT65": "DATA", "JT9": "DATA", "MFSK": "DATA",
    "DATA": "DATA", "DIGITAL": "DATA", "DIGI": "DATA",
}

# Mode families the contest world scores as "phone" vs "CW/digital".
_PHONE_MODES = frozenset({"SSB", "FM", "AM", "PHONE"})
_CW_DATA_MODES = frozenset({"CW", "DATA"})


def canonical_mode(mode: object) -> str:
    """Canonicalise a mode token (``USB``->``SSB``, ``FT8``->``DATA`` …).

    Unknown tokens are returned upper-cased unchanged, so a novel mode still
    participates in dupe checks (it just forms its own family)."""
    token = _norm_field(mode)
    return _MODE_ALIASES.get(token, token)


def mode_category(mode: object) -> str:
    """Classify a mode as ``"phone"``, ``"cw"`` (CW *or* digital) or ``"other"``.

    Contest point schedules almost always split "CW/digital" from "phone"; this
    is the split used by :func:`points_by_mode`."""
    fam = canonical_mode(mode)
    if fam in _PHONE_MODES:
        return "phone"
    if fam in _CW_DATA_MODES:
        return "cw"
    return "other"


# --- QSO access ------------------------------------------------------------

# Accept a spread of field spellings, including ADIF's, for each logical field.
_CALL_KEYS = ("call", "callsign", "worked", "station")
_BAND_KEYS = ("band",)
_MODE_KEYS = ("mode",)
_TIME_KEYS = ("time", "time_on", "qso_date", "date", "when")
_MULT_KEYS = ("mult", "multiplier", "section", "state", "dxcc", "entity")
_POINT_KEYS = ("points", "point", "pts", "qso_points")


def _get(qso: Mapping, keys: Sequence[str]) -> object:
    """First present value among ``keys`` (case-insensitive), else ``None``."""
    # Build a lower-cased view once per lookup; QSO dicts are small.
    lower = {str(k).lower(): v for k, v in qso.items()}
    for k in keys:
        if k in lower:
            return lower[k]
    return None


def qso_call(qso: Mapping) -> str:
    return normalize_call(_get(qso, _CALL_KEYS))


def qso_band(qso: Mapping) -> str:
    return _norm_field(_get(qso, _BAND_KEYS))


def qso_mode(qso: Mapping) -> str:
    return canonical_mode(_get(qso, _MODE_KEYS))


# --- keys ------------------------------------------------------------------


def dupe_key(qso: Mapping, *, by_band: bool = True, by_mode: bool = True) -> tuple:
    """The tuple that must be unique for a QSO to count.

    Defaults to *call + band + mode* (the POTA/contest "once per band per mode"
    convention). Set ``by_band``/``by_mode`` False to collapse those dimensions
    (SOTA scores a summit once per day regardless of band/mode)."""
    key: list = [qso_call(qso)]
    if by_band:
        key.append(qso_band(qso))
    if by_mode:
        key.append(qso_mode(qso))
    return tuple(key)


# --- point schedules -------------------------------------------------------


def points_by_mode(qso: Mapping, *, phone: int = 1, cw: int = 2) -> int:
    """CW/digital QSOs are worth ``cw`` points, phone worth ``phone``.

    Matches ARRL Field Day Rule 7.3.1 (CW/digital 2 pts, phone 1 pt) and the
    common ARRL/CQ contest split. An unrecognised mode scores ``phone``. The
    QSO's mode is read from its ``mode`` field (any of the recognised spellings)."""
    return cw if mode_category(_get(qso, _MODE_KEYS)) == "cw" else phone


def points_flat(_qso: Mapping, *, value: int = 1) -> int:
    """Every QSO is worth ``value`` points (POTA/SOTA: 1 point each)."""
    return value


# --- contest ruleset -------------------------------------------------------


@dataclass(frozen=True)
class ContestRules:
    """A scoring ruleset: how to key dupes, value QSOs, and count multipliers.

    ``dupe_by_band`` / ``dupe_by_mode`` shape the dupe key. ``points_fn`` maps a
    QSO to its point value (before dupe suppression). ``mult_keys`` names the
    fields whose distinct non-blank values are multipliers (e.g. ARRL sections);
    an empty tuple means the log has no multipliers and the final score equals
    the point total.
    """

    name: str = "generic"
    dupe_by_band: bool = True
    dupe_by_mode: bool = True
    points_fn: Callable[[Mapping], int] = points_flat
    mult_keys: tuple = ()
    dupes_score_zero: bool = True

    def key_for(self, qso: Mapping) -> tuple:
        return dupe_key(qso, by_band=self.dupe_by_band, by_mode=self.dupe_by_mode)

    def points_for(self, qso: Mapping) -> int:
        """Point value of ``qso``, honouring an explicit ``points`` override."""
        override = _get(qso, _POINT_KEYS)
        if override is not None and str(override).strip() != "":
            try:
                return int(float(override))
            except (TypeError, ValueError):
                pass
        return int(self.points_fn(qso))

    def mult_for(self, qso: Mapping) -> Optional[str]:
        """The multiplier token for ``qso`` (first non-blank ``mult_keys`` field),
        or ``None`` when this ruleset has no multipliers / the fields are blank."""
        for key in self.mult_keys:
            val = _get(qso, (key,))
            token = _norm_field(val)
            if token:
                return token
        return None


# Named presets. POTA/SOTA are "activation" logs (1 pt/QSO, no multipliers);
# the contest presets use the mode-based point split and section/DXCC mults.
_PRESETS: dict[str, ContestRules] = {
    "generic": ContestRules(name="generic"),
    "pota": ContestRules(name="pota", points_fn=points_flat),
    "sota": ContestRules(
        name="sota", dupe_by_band=False, dupe_by_mode=False, points_fn=points_flat),
    "fieldday": ContestRules(
        name="fieldday", points_fn=points_by_mode, mult_keys=()),
    "arrl-dx": ContestRules(
        name="arrl-dx", points_fn=lambda q: 3, mult_keys=("dxcc", "entity", "mult")),
}


def ruleset(name: str = "generic") -> ContestRules:
    """Return a named :class:`ContestRules` preset.

    Known names: ``generic``, ``pota``, ``sota``, ``fieldday``, ``arrl-dx``
    (case-insensitive). Unknown names fall back to ``generic``."""
    return _PRESETS.get(str(name).strip().lower(), _PRESETS["generic"])


def available_rulesets() -> list[str]:
    """Sorted names of the built-in presets (for menus / dialogs)."""
    return sorted(_PRESETS)


# --- dupe detection --------------------------------------------------------


def is_dupe(
    qso: Mapping,
    prior: Iterable[Mapping],
    *,
    by_band: bool = True,
    by_mode: bool = True,
) -> bool:
    """True if ``qso`` duplicates any contact in ``prior``.

    ``prior`` is the contacts logged *before* this one; the current QSO is not
    counted against itself. Comparison uses the normalised dupe key, so
    ``W1AW`` vs ``w1aw/p`` and ``USB`` vs ``SSB`` collide. A blank callsign is
    never a dupe (there is nothing to match)."""
    key = dupe_key(qso, by_band=by_band, by_mode=by_mode)
    if not key[0]:
        return False
    seen = {dupe_key(p, by_band=by_band, by_mode=by_mode) for p in prior}
    return key in seen


def find_dupes(
    log: Sequence[Mapping],
    *,
    by_band: bool = True,
    by_mode: bool = True,
) -> list[bool]:
    """One flag per QSO in ``log``: True where it repeats an earlier key.

    The *first* time a key appears it is a new contact (False); every later
    appearance is a dupe (True). Blank-call rows are always False."""
    seen: set[tuple] = set()
    flags: list[bool] = []
    for qso in log:
        key = dupe_key(qso, by_band=by_band, by_mode=by_mode)
        if not key[0]:
            flags.append(False)
            continue
        flags.append(key in seen)
        seen.add(key)
    return flags


# --- scoring ---------------------------------------------------------------


@dataclass
class ScoredQso:
    """One row of a scored log."""

    index: int
    call: str
    band: str
    mode: str
    is_dupe: bool
    points: int          # points credited (0 if a dupe under this ruleset)
    running_qsos: int    # count of non-dupe QSOs through this row
    running_points: int  # cumulative credited points through this row


@dataclass
class ScoreResult:
    """The outcome of scoring a whole log against a :class:`ContestRules`."""

    rules: ContestRules
    rows: list[ScoredQso] = field(default_factory=list)
    qso_count: int = 0        # non-dupe QSOs
    dupe_count: int = 0
    point_total: int = 0      # sum of credited points
    multipliers: int = 0      # distinct multiplier tokens among credited QSOs
    mult_values: tuple = ()   # the distinct tokens, sorted

    @property
    def score(self) -> int:
        """Final score = credited points x multipliers (x1 if no multipliers)."""
        return self.point_total * self.multipliers if self.multipliers else self.point_total


def score_log(log: Sequence[Mapping], rules: ContestRules | str = "generic") -> ScoreResult:
    """Score ``log`` in order against ``rules`` (a preset name or object).

    Walks the log once. A QSO whose dupe key was already seen is a dupe and
    (when ``rules.dupes_score_zero``) earns 0 points; otherwise it earns
    ``rules.points_for(qso)``. Multipliers are the distinct non-blank
    ``mult_keys`` tokens among *credited* (non-dupe) QSOs. Blank-call rows are
    skipped entirely (neither QSO nor dupe)."""
    if isinstance(rules, str):
        rules = ruleset(rules)
    result = ScoreResult(rules=rules)
    seen: set[tuple] = set()
    mults: Counter = Counter()
    running_q = 0
    running_p = 0
    for i, qso in enumerate(log):
        key = rules.key_for(qso)
        call = key[0]
        if not call:
            continue
        dup = key in seen
        seen.add(key)
        if dup and rules.dupes_score_zero:
            pts = 0
            result.dupe_count += 1
        else:
            if dup:
                result.dupe_count += 1
            pts = rules.points_for(qso)
            running_q += 1
            running_p += pts
            mult = rules.mult_for(qso)
            if mult:
                mults[mult] += 1
        result.rows.append(ScoredQso(
            index=i, call=call, band=qso_band(qso), mode=qso_mode(qso),
            is_dupe=dup, points=pts,
            running_qsos=running_q, running_points=running_p,
        ))
    result.qso_count = running_q
    result.point_total = running_p
    result.mult_values = tuple(sorted(mults))
    result.multipliers = len(result.mult_values)
    return result


# ===========================================================================
# Formula layer — self-registering pack (finance_fns style)
# ===========================================================================
#
# ISDUPE(call, band, mode, log_range) and QSOPOINTS(...) are wrapped here and
# added to the engine FUNCTIONS table by :func:`register`, exactly like the
# finance / RF packs. ``log_range`` is a range of prior QSOs laid out one per
# row as ``call | band | mode`` (extra columns ignored); when omitted the
# functions treat the log as empty.


def _fn_isdupe(args):
    """ISDUPE(call, band, mode, [log_range]) -> TRUE if (call,band,mode) already
    appears in ``log_range`` (a call|band|mode range of prior QSOs)."""
    from ..errors import CellError
    from ..functions.helpers import _arg, _text
    from ..values import RangeValue

    call = _text(_arg(args, 0, ""))
    band = _text(_arg(args, 1, ""))
    mode = _text(_arg(args, 2, ""))
    if not normalize_call(call):
        return CellError(CellError.VALUE)
    qso = {"call": call, "band": band, "mode": mode}
    prior: list[dict] = []
    rng = _arg(args, 3, None)
    if isinstance(rng, RangeValue):
        for row in rng.grid:
            prior.append({
                "call": row[0] if len(row) > 0 else "",
                "band": row[1] if len(row) > 1 else "",
                "mode": row[2] if len(row) > 2 else "",
            })
    elif rng not in (None, ""):
        # A single scalar prior call with no band/mode context.
        prior.append({"call": rng, "band": "", "mode": ""})
    return is_dupe(qso, prior)


def _fn_qsopoints(args):
    """QSOPOINTS(mode, [ruleset]) -> point value of one QSO in ``mode``.

    ``ruleset`` names a preset (default ``generic`` = 1 pt/QSO). For the
    ``fieldday`` preset CW/digital scores 2 and phone 1 (ARRL FD 7.3.1)."""
    from ..errors import CellError
    from ..functions.helpers import _arg, _text

    mode = _text(_arg(args, 0, ""))
    rs_name = _text(_arg(args, 1, "generic")) or "generic"
    rules = ruleset(rs_name)
    try:
        return int(rules.points_for({"mode": mode}))
    except (TypeError, ValueError):
        return CellError(CellError.VALUE)


def register(functions: dict) -> None:
    """Additively register the ham-logging formula functions (finance-pack style)."""
    functions.update({
        "ISDUPE": _fn_isdupe,
        "QSOPOINTS": _fn_qsopoints,
    })


SIGNATURES = {
    "ISDUPE": "ISDUPE(call, band, mode, [log_range])",
    "QSOPOINTS": "QSOPOINTS(mode, [ruleset])",
}


__all__ = [
    "normalize_call",
    "canonical_mode",
    "mode_category",
    "qso_call",
    "qso_band",
    "qso_mode",
    "dupe_key",
    "points_by_mode",
    "points_flat",
    "ContestRules",
    "ruleset",
    "available_rulesets",
    "is_dupe",
    "find_dupes",
    "ScoredQso",
    "ScoreResult",
    "score_log",
    "register",
    "SIGNATURES",
]
