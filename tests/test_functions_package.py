"""Guard the functions package split: the two registries must stay complete and
the shared helpers must remain importable from the package root (macros and the
completion UI depend on both). This pins the exact function counts so a future
edit to a submodule cannot silently drop or duplicate a registration."""

from __future__ import annotations

import abax.core.functions as fns
from abax.core.functions import FUNCTIONS, LAZY_FUNCTIONS


def test_registry_sizes():
    assert len(FUNCTIONS) == 587
    assert len(LAZY_FUNCTIONS) == 6


def test_core_functions_present():
    for name in ("SUM", "AVERAGE", "VLOOKUP", "NORMDIST", "CONCAT", "DATE",
                 "AND", "XLOOKUP", "DXCC", "VSWR"):
        assert name in FUNCTIONS, name
    for name in ("IF", "IFERROR", "IFS", "SWITCH", "CHOOSE", "IFNA"):
        assert name in LAZY_FUNCTIONS, name


def test_helpers_reexported_for_macros():
    # abax.macros reaches these as functions._text etc.
    for h in ("_text", "_flatten", "_numbers", "_as_number", "_arg"):
        assert hasattr(fns, h), h


def test_every_entry_is_callable():
    for name, fn in {**FUNCTIONS, **LAZY_FUNCTIONS}.items():
        assert callable(fn), name


def test_no_duplicate_between_eager_and_lazy():
    assert not (set(FUNCTIONS) & set(LAZY_FUNCTIONS))
