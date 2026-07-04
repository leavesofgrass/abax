"""Formula-layer tests for the ham-logging pack (ISDUPE / QSOPOINTS).

These exercise the self-registering pack directly (the wrappers in
``hamlog.register``) so they hold whether or not the engine __init__ has wired
the pack into the global FUNCTIONS table yet.
"""

from __future__ import annotations

from abax.core.errors import CellError
from abax.core.science import hamlog as H
from abax.core.values import RangeValue


def test_register_adds_two_eager_functions():
    fns: dict = {}
    H.register(fns)
    assert set(fns) == {"ISDUPE", "QSOPOINTS"}
    assert all(callable(f) for f in fns.values())
    assert set(H.SIGNATURES) == {"ISDUPE", "QSOPOINTS"}


def test_isdupe_over_log_range():
    log = RangeValue([["W1AW", "20M", "SSB"], ["K1ABC", "40M", "CW"]])
    # same call+band, phone family -> dupe
    assert H._fn_isdupe(["W1AW", "20M", "USB", log]) is True
    # portable decoration still collides
    assert H._fn_isdupe(["w1aw/p", "20M", "SSB", log]) is True
    # different band -> not a dupe
    assert H._fn_isdupe(["W1AW", "40M", "SSB", log]) is False
    # call not in the log at all
    assert H._fn_isdupe(["N0CALL", "20M", "SSB", log]) is False


def test_isdupe_empty_or_missing_log():
    assert H._fn_isdupe(["W1AW", "20M", "SSB", None]) is False
    assert H._fn_isdupe(["W1AW", "20M", "SSB"]) is False


def test_isdupe_blank_call_is_value_error():
    log = RangeValue([["W1AW", "20M", "SSB"]])
    res = H._fn_isdupe(["", "20M", "SSB", log])
    assert isinstance(res, CellError) and res.code == CellError.VALUE


def test_qsopoints_by_ruleset():
    # generic: 1 pt regardless of mode
    assert H._fn_qsopoints(["CW"]) == 1
    assert H._fn_qsopoints(["SSB"]) == 1
    # field day: CW/digital 2, phone 1 (ARRL FD 7.3.1)
    assert H._fn_qsopoints(["CW", "fieldday"]) == 2
    assert H._fn_qsopoints(["FT8", "fieldday"]) == 2
    assert H._fn_qsopoints(["SSB", "fieldday"]) == 1
    # unknown ruleset falls back to generic
    assert H._fn_qsopoints(["CW", "nonsense"]) == 1


def test_pack_registered_into_global_functions():
    # The integrator wires hamlog into the engine registry; whether it has yet or
    # not, applying the pack is idempotent and must expose both names.
    from abax.core.functions import FUNCTIONS

    H.register(FUNCTIONS)
    assert "ISDUPE" in FUNCTIONS and "QSOPOINTS" in FUNCTIONS
    assert FUNCTIONS["QSOPOINTS"](["CW", "fieldday"]) == 2
