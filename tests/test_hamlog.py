"""Tests for abax.core.science.hamlog — dupe detection, points, scoring.

Oracle sources cited inline. Point schedules follow ARRL Field Day Rule 7.3.1
(CW/digital 2 pts, phone 1 pt); the once-per-band-per-mode dupe convention is
POTA General Rules 3.6; SOTA's once-per-summit-per-day chaser rule is SOTA GR
3.7.1. Callsign normalisation follows the standard portable-decoration handling
(base call = the longest non-suffix fragment of a slashed call).
"""

from __future__ import annotations

from abax.core.science import hamlog as H

# --- callsign normalisation ------------------------------------------------


def test_normalize_portable_and_prefix():
    # /P, /M, /QRP are operating decorations -> stripped to the base call.
    assert H.normalize_call("W1AW/P") == "W1AW"
    assert H.normalize_call("w1aw/qrp") == "W1AW"
    assert H.normalize_call("K1ABC/M") == "K1ABC"
    # Foreign-prefix form VE3/W1AW: base call (longer fragment) wins.
    assert H.normalize_call("VE3/W1AW") == "W1AW"
    # Bare call is unchanged (upper-cased, trimmed).
    assert H.normalize_call("  n0call ") == "N0CALL"
    assert H.normalize_call(None) == ""
    assert H.normalize_call("") == ""


def test_mode_canonicalisation():
    # USB/LSB fold onto SSB (phone); digital sub-modes fold onto DATA.
    assert H.canonical_mode("USB") == "SSB"
    assert H.canonical_mode("lsb") == "SSB"
    assert H.canonical_mode("FT8") == "DATA"
    assert H.canonical_mode("PSK31") == "DATA"
    assert H.mode_category("SSB") == "phone"
    assert H.mode_category("FM") == "phone"
    assert H.mode_category("CW") == "cw"
    assert H.mode_category("FT8") == "cw"     # digital counts with CW for points
    assert H.mode_category("SSTV") == "other"


# --- dupe detection --------------------------------------------------------


def test_is_dupe_same_call_band_mode():
    prior = [{"call": "W1AW", "band": "20M", "mode": "SSB"}]
    # Same station, same band, phone family (USB==SSB) -> dupe.
    assert H.is_dupe({"call": "w1aw/p", "band": "20M", "mode": "USB"}, prior) is True
    # Different band -> not a dupe (worked again is allowed per band).
    assert H.is_dupe({"call": "W1AW", "band": "40M", "mode": "SSB"}, prior) is False
    # Different mode family -> not a dupe (per mode).
    assert H.is_dupe({"call": "W1AW", "band": "20M", "mode": "CW"}, prior) is False


def test_is_dupe_blank_call_never_dupes():
    prior = [{"call": "", "band": "20M", "mode": "SSB"}]
    assert H.is_dupe({"call": "", "band": "20M", "mode": "SSB"}, prior) is False


def test_find_dupes_flags_first_seen_false():
    log = [
        {"call": "W1AW", "band": "20M", "mode": "SSB"},   # new
        {"call": "K1ABC", "band": "20M", "mode": "SSB"},  # new
        {"call": "W1AW", "band": "20M", "mode": "USB"},   # dupe of #0 (SSB family)
        {"call": "W1AW", "band": "40M", "mode": "SSB"},   # new (band changed)
        {"call": "k1abc", "band": "20M", "mode": "SSB"},  # dupe of #1
    ]
    assert H.find_dupes(log) == [False, False, True, False, True]


def test_find_dupes_collapsed_band_mode_for_sota():
    # SOTA: a chaser scores a summit once per day regardless of band/mode, so
    # collapsing band+mode makes any re-work of the same call a dupe.
    log = [
        {"call": "W1AW", "band": "20M", "mode": "SSB"},
        {"call": "W1AW", "band": "40M", "mode": "CW"},   # different band+mode
    ]
    assert H.find_dupes(log, by_band=False, by_mode=False) == [False, True]


# --- point schedules -------------------------------------------------------


def test_points_by_mode_arrl_fieldday():
    # ARRL Field Day Rule 7.3.1: phone = 1 pt, CW/digital = 2 pts.
    assert H.points_by_mode({"mode": "SSB"}) == 1
    assert H.points_by_mode({"mode": "FM"}) == 1
    assert H.points_by_mode({"mode": "CW"}) == 2
    assert H.points_by_mode({"mode": "FT8"}) == 2


def test_points_flat_one_each():
    assert H.points_flat({"mode": "SSB"}) == 1
    assert H.points_flat({"mode": "CW"}) == 1


# --- ruleset presets -------------------------------------------------------


def test_ruleset_presets_exist():
    for name in ("generic", "pota", "sota", "fieldday", "arrl-dx"):
        assert name in H.available_rulesets()
    assert H.ruleset("POTA").name == "pota"          # case-insensitive
    assert H.ruleset("nonsense").name == "generic"   # fallback


# --- scoring ---------------------------------------------------------------


def _log():
    return [
        {"call": "W1AW", "band": "20M", "mode": "SSB"},   # phone
        {"call": "w1aw/p", "band": "20M", "mode": "USB"},  # dupe
        {"call": "W1AW", "band": "40M", "mode": "CW"},    # CW
        {"call": "K1ABC", "band": "20M", "mode": "CW"},   # CW
    ]


def test_score_log_pota_one_point_each():
    # POTA: 1 pt per valid QSO, dupe scores 0, no multipliers.
    r = H.score_log(_log(), "pota")
    assert r.qso_count == 3
    assert r.dupe_count == 1
    assert r.point_total == 3     # 3 valid QSOs x 1 pt
    assert r.multipliers == 0
    assert r.score == 3           # x1 when no multipliers


def test_score_log_fieldday_mode_points():
    # Field Day: SSB=1, the two CW QSOs = 2 each; dupe SSB = 0.
    r = H.score_log(_log(), "fieldday")
    assert r.qso_count == 3
    assert r.point_total == 1 + 2 + 2          # 5
    assert r.score == 5
    # Per-row running totals: 1, 1 (dupe), 3, 5.
    running = [row.running_points for row in r.rows]
    assert running == [1, 1, 3, 5]
    # Dupe row is flagged and credited 0.
    assert r.rows[1].is_dupe is True and r.rows[1].points == 0


def test_score_log_multipliers():
    # ARRL-DX style: 3 pts/QSO, multipliers = distinct DXCC entities among
    # credited QSOs. Two entities worked, one dupe -> 2 QSOs x 3 = 6, x2 = 12.
    log = [
        {"call": "DL1AB", "band": "20M", "mode": "CW", "dxcc": "Germany"},
        {"call": "G3XYZ", "band": "20M", "mode": "CW", "dxcc": "England"},
        {"call": "DL1AB", "band": "20M", "mode": "CW", "dxcc": "Germany"},  # dupe
    ]
    r = H.score_log(log, "arrl-dx")
    assert r.qso_count == 2
    assert r.point_total == 6
    assert r.multipliers == 2
    assert r.mult_values == ("ENGLAND", "GERMANY")
    assert r.score == 12


def test_score_log_explicit_points_override():
    # An explicit `points` field overrides the ruleset's schedule.
    log = [{"call": "W1AW", "band": "20M", "mode": "SSB", "points": 5}]
    r = H.score_log(log, "pota")
    assert r.point_total == 5


def test_score_log_skips_blank_call_rows():
    log = [
        {"call": "", "band": "20M", "mode": "SSB"},       # skipped entirely
        {"call": "W1AW", "band": "20M", "mode": "SSB"},
    ]
    r = H.score_log(log, "pota")
    assert r.qso_count == 1
    assert len(r.rows) == 1        # the blank row produced no scored row


def test_score_log_adif_field_names():
    # ADIF field spellings (CALL/BAND/MODE) score identically to the lowercase
    # keys, so a log parsed by adif_io can be scored directly.
    log = [
        {"CALL": "W1AW", "BAND": "20M", "MODE": "SSB"},
        {"CALL": "W1AW", "BAND": "20M", "MODE": "SSB"},
    ]
    r = H.score_log(log, "pota")
    assert r.qso_count == 1 and r.dupe_count == 1
