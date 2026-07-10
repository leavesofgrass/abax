"""Tests for per-mode keybinding customization in :mod:`abax.userconfig`.

Covers the deeper-rebind surface added on top of the original normal-mode-only
support: binding in every real TUI mode, mode validation, key-name
normalization, and the ``bindings_for`` / ``all_bindings`` listing helpers.
"""

from __future__ import annotations

import pytest

from abax.userconfig import (
    BINDABLE_MODES,
    Binding,
    UserConfig,
    normalize_key,
)


def _noop(ed):  # a stand-in action; identity so callers can assert it ran
    return ed


# --------------------------------------------------------------------------- #
# Binding + lookup in every bindable mode
# --------------------------------------------------------------------------- #


def test_every_bindable_mode_binds_and_looks_up() -> None:
    """A binding can be registered and retrieved in each real TUI mode."""
    uc = UserConfig()
    for mode in BINDABLE_MODES:
        uc.bind_key(mode, "K", _noop, desc=f"{mode}-K")

    for mode in BINDABLE_MODES:
        binding = uc.keybinding(mode, "K")
        assert isinstance(binding, Binding)
        assert binding.mode == mode
        assert binding.key == "K"
        assert binding.desc == f"{mode}-K"
        assert binding.action("sentinel") == "sentinel"

    # Modes stay isolated: a key bound in one mode is not visible in another
    # unless it was bound there too.
    uc2 = UserConfig()
    uc2.bind_key("insert", "x", _noop)
    assert uc2.keybinding("insert", "x") is not None
    assert uc2.keybinding("normal", "x") is None


def test_bindable_modes_matches_expected_set() -> None:
    """The advertised bindable modes are exactly the real, rebindable ones."""
    assert BINDABLE_MODES == ("normal", "insert", "command", "rpn", "visual", "browser")


# --------------------------------------------------------------------------- #
# Unknown-mode validation
# --------------------------------------------------------------------------- #


def test_unknown_mode_raises_valueerror_listing_valid_modes() -> None:
    """Binding in a non-existent mode raises ValueError naming the valid modes."""
    uc = UserConfig()
    with pytest.raises(ValueError) as excinfo:
        uc.bind_key("bogus", "K", _noop)

    msg = str(excinfo.value)
    assert "bogus" in msg
    for mode in BINDABLE_MODES:
        assert mode in msg


def test_broken_mode_binding_does_not_affect_others() -> None:
    """A rejected bad-mode bind_key leaves previously-registered bindings intact."""
    uc = UserConfig()
    uc.bind_key("normal", "K", _noop, desc="good")

    with pytest.raises(ValueError):
        uc.bind_key("nonsense", "J", _noop)

    # The good binding survives; the bad one was never recorded.
    assert uc.keybinding("normal", "K") is not None
    assert uc.keybinding("nonsense", "J") is None
    assert ("nonsense", "J") not in uc.keybindings
    assert len(uc.keybindings) == 1


# --------------------------------------------------------------------------- #
# Key-name normalization
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("spelling", ["Ctrl+S", "ctrl+s", "C-s", "CTRL+S", "control+S"])
def test_three_spellings_resolve_to_one_binding(spelling: str) -> None:
    """Every accepted spelling of a chord resolves to the same canonical binding."""
    uc = UserConfig()
    uc.bind_key("normal", spelling, _noop, desc="save")

    # Stored under the canonical key, regardless of how it was written.
    assert uc.keybinding("normal", "ctrl+s") is not None
    assert uc.keybinding("normal", "Ctrl+S") is not None
    assert uc.keybinding("normal", "C-s") is not None
    assert uc.keybinding("normal", "ctrl+s").key == "ctrl+s"
    assert ("normal", "ctrl+s") in uc.keybindings


def test_normalize_key_canonical_form() -> None:
    """normalize_key folds spellings and orders modifiers, but preserves bare keys."""
    # The three required spellings collapse together.
    assert normalize_key("Ctrl+S") == "ctrl+s"
    assert normalize_key("ctrl+s") == "ctrl+s"
    assert normalize_key("C-s") == "ctrl+s"

    # Modifier order is canonical (ctrl, alt, shift, super) and duplicates drop.
    assert normalize_key("Alt+Ctrl+Del") == "ctrl+alt+del"
    assert normalize_key("C-M-x") == "ctrl+alt+x"

    # Bare, modifier-free keys are preserved verbatim so vi K != k.
    assert normalize_key("K") == "K"
    assert normalize_key("k") == "k"
    assert normalize_key("g") == "g"

    # Literal punctuation keys are not mistaken for chords.
    assert normalize_key("-") == "-"
    assert normalize_key("+") == "+"


def test_rebind_overrides_regardless_of_spelling() -> None:
    """A second bind to the same chord (different spelling) overrides the first."""
    uc = UserConfig()
    uc.bind_key("normal", "ctrl+s", _noop, desc="first")
    uc.bind_key("normal", "C-S", _noop, desc="second")

    assert len(uc.bindings_for("normal")) == 1
    assert uc.keybinding("normal", "Ctrl+S").desc == "second"


def test_case_significant_keys_stay_distinct() -> None:
    """Bare vi keys keep their case: K and k are independent bindings."""
    uc = UserConfig()
    uc.bind_key("normal", "K", _noop, desc="upper")
    uc.bind_key("normal", "k", _noop, desc="lower")

    assert uc.keybinding("normal", "K").desc == "upper"
    assert uc.keybinding("normal", "k").desc == "lower"
    assert len(uc.bindings_for("normal")) == 2


# --------------------------------------------------------------------------- #
# Listing helpers: bindings_for / all_bindings
# --------------------------------------------------------------------------- #


def test_bindings_for_returns_only_that_modes_rebinds() -> None:
    """bindings_for collects exactly one mode's bindings, keyed by canonical key."""
    uc = UserConfig()
    uc.bind_key("normal", "K", _noop)
    uc.bind_key("normal", "Ctrl+S", _noop)
    uc.bind_key("insert", "C-w", _noop)

    normal = uc.bindings_for("normal")
    assert set(normal) == {"K", "ctrl+s"}
    assert all(isinstance(b, Binding) for b in normal.values())

    assert set(uc.bindings_for("insert")) == {"ctrl+w"}

    # A mode with no rebinds yields an empty dict, never an error.
    assert uc.bindings_for("rpn") == {}
    assert uc.bindings_for("bogus") == {}


def test_all_bindings_groups_by_mode() -> None:
    """all_bindings groups every rebind under its mode; only used modes appear."""
    uc = UserConfig()
    uc.bind_key("normal", "K", _noop)
    uc.bind_key("insert", "C-w", _noop)
    uc.bind_key("browser", "r", _noop)

    grouped = uc.all_bindings()
    assert set(grouped) == {"normal", "insert", "browser"}
    assert set(grouped["normal"]) == {"K"}
    assert set(grouped["insert"]) == {"ctrl+w"}
    assert set(grouped["browser"]) == {"r"}
    assert isinstance(grouped["normal"]["K"], Binding)

    # Empty config -> empty grouping.
    assert UserConfig().all_bindings() == {}
