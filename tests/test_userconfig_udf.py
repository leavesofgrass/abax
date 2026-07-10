"""Tests for user-defined formula functions registered via ``init.py``.

Covers :meth:`abax.userconfig.UserConfig.register_function`, its validation,
and the ``abax`` facade forwarding (both directly and through
:func:`abax.userconfig.load_user_config`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from abax.userconfig import (
    FUNCTION_KINDS,
    UserConfig,
    _ConfigFacade,
    load_user_config,
)


def _write(tmp_path: Path, name: str, body: str) -> str:
    """Write an init file into ``tmp_path`` and return its path as a string."""
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return str(p)


# --- happy path: functions land in the right registry ----------------------


def test_plain_function_lands_in_functions_dict() -> None:
    """A default (plain) registration goes to ``functions`` only."""
    cfg = UserConfig()

    def double(args):
        return (args[0] or 0) * 2

    cfg.register_function("DOUBLE", double)

    assert cfg.functions == {"DOUBLE": double}
    assert cfg.functions["DOUBLE"] is double
    # Stored verbatim — plain calling convention fn(args) -> value is preserved.
    assert cfg.functions["DOUBLE"]([21]) == 42
    # Other registries untouched.
    assert cfg.lazy_functions == {}
    assert cfg.context_functions == {}


def test_lazy_function_lands_in_lazy_dict() -> None:
    """``kind="lazy"`` goes to ``lazy_functions`` only."""
    cfg = UserConfig()

    def my_if(arg_nodes, ev):
        return arg_nodes

    cfg.register_function("MYIF", my_if, kind="lazy")

    assert cfg.lazy_functions == {"MYIF": my_if}
    assert cfg.functions == {}
    assert cfg.context_functions == {}


def test_context_function_lands_in_context_dict() -> None:
    """``kind="context"`` goes to ``context_functions`` only."""
    cfg = UserConfig()

    def my_row(arg_nodes, ctx):
        return (arg_nodes, ctx)

    cfg.register_function("MYROW", my_row, kind="context")

    assert cfg.context_functions == {"MYROW": my_row}
    assert cfg.functions == {}
    assert cfg.lazy_functions == {}


def test_all_three_kinds_coexist() -> None:
    """Registering across all three kinds keeps them in separate dicts."""
    cfg = UserConfig()
    cfg.register_function("A", lambda args: 1)
    cfg.register_function("B", lambda arg_nodes, ev: 2, kind="lazy")
    cfg.register_function("C", lambda arg_nodes, ctx: 3, kind="context")

    assert set(cfg.functions) == {"A"}
    assert set(cfg.lazy_functions) == {"B"}
    assert set(cfg.context_functions) == {"C"}


def test_dotted_and_numeric_names_are_accepted() -> None:
    """Dotted (``MY.FUNC``) and digit-bearing (``LOG10``) names are valid."""
    cfg = UserConfig()
    cfg.register_function("MY.FUNC", lambda args: None)
    cfg.register_function("LOG10", lambda args: None)
    assert "MY.FUNC" in cfg.functions
    assert "LOG10" in cfg.functions


def test_reregister_same_name_overrides() -> None:
    """A later registration for the same (name, kind) overrides the earlier one."""
    cfg = UserConfig()
    first, second = (lambda args: 1), (lambda args: 2)
    cfg.register_function("DUP", first)
    cfg.register_function("DUP", second)
    assert cfg.functions["DUP"] is second
    assert len(cfg.functions) == 1


# --- validation: bad inputs raise ValueError -------------------------------


@pytest.mark.parametrize(
    "bad_name",
    [
        "",            # empty
        "lower",       # not uppercase
        "Mixed",       # not uppercase
        "MY FUNC",     # space is not an identifier char
        "MY-FUNC",     # hyphen is not an identifier char
        "1ABC",        # leading digit
        "MY..FUNC",    # empty segment between dots
        ".FUNC",       # leading dot -> empty leading segment
        "FUNC.",       # trailing dot -> empty trailing segment
    ],
)
def test_bad_name_raises_value_error(bad_name: str) -> None:
    """Invalid names are rejected with ValueError."""
    cfg = UserConfig()
    with pytest.raises(ValueError):
        cfg.register_function(bad_name, lambda args: None)
    # Nothing was recorded.
    assert cfg.functions == {}


def test_non_string_name_raises_value_error() -> None:
    """A non-string name is rejected with ValueError, not TypeError."""
    cfg = UserConfig()
    with pytest.raises(ValueError):
        cfg.register_function(123, lambda args: None)  # type: ignore[arg-type]


def test_non_callable_fn_raises_value_error() -> None:
    """A non-callable ``fn`` is rejected with ValueError."""
    cfg = UserConfig()
    with pytest.raises(ValueError):
        cfg.register_function("NOPE", 42)  # type: ignore[arg-type]
    assert cfg.functions == {}


def test_bad_kind_raises_value_error() -> None:
    """An unknown ``kind`` is rejected with ValueError and records nothing."""
    cfg = UserConfig()
    with pytest.raises(ValueError):
        cfg.register_function("X", lambda args: None, kind="eager")
    assert cfg.functions == {}
    assert cfg.lazy_functions == {}
    assert cfg.context_functions == {}


def test_function_kinds_constant() -> None:
    """The public kinds constant matches the three supported registries."""
    assert set(FUNCTION_KINDS) == {"plain", "lazy", "context"}


# --- facade forwarding ------------------------------------------------------


def test_facade_forwards_register_function() -> None:
    """The ``abax`` facade forwards register_function to its backing config."""
    cfg = UserConfig()
    facade = _ConfigFacade(cfg, "test-version")

    facade.register_function("DOUBLE", lambda args: (args[0] or 0) * 2)
    facade.register_function("MYIF", lambda arg_nodes, ev: None, kind="lazy")
    facade.register_function("MYROW", lambda arg_nodes, ctx: None, kind="context")

    assert "DOUBLE" in cfg.functions
    assert "MYIF" in cfg.lazy_functions
    assert "MYROW" in cfg.context_functions


def test_facade_forwards_validation_errors() -> None:
    """Validation still fires when called through the facade."""
    facade = _ConfigFacade(UserConfig(), "test-version")
    with pytest.raises(ValueError):
        facade.register_function("bad name", lambda args: None)


def test_load_user_config_captures_registered_functions(tmp_path: Path) -> None:
    """An init.py can register functions of every kind through ``abax``."""
    init = _write(
        tmp_path,
        "init.py",
        (
            "def double(args):\n"
            "    return (args[0] or 0) * 2\n"
            "\n"
            "abax.register_function('DOUBLE', double)\n"
            "abax.register_function('MYIF', lambda nodes, ev: nodes, kind='lazy')\n"
            "abax.register_function('MYROW', lambda nodes, ctx: ctx, kind='context')\n"
        ),
    )

    cfg = load_user_config(path=init)

    assert cfg.errors == []
    assert cfg.functions["DOUBLE"]([5]) == 10
    assert set(cfg.functions) == {"DOUBLE"}
    assert set(cfg.lazy_functions) == {"MYIF"}
    assert set(cfg.context_functions) == {"MYROW"}


def test_bad_registration_in_init_is_captured_not_raised(tmp_path: Path) -> None:
    """A ValueError from register_function is recorded, never crashing startup."""
    init = _write(
        tmp_path,
        "init.py",
        "abax.register_function('lower', lambda args: None)\n",
    )
    cfg = load_user_config(path=init)
    assert cfg.errors, "expected the ValueError to be captured"
    assert "ValueError" in cfg.errors[0]
    assert cfg.functions == {}


def test_udf_registration_is_additive_to_bindings(tmp_path: Path) -> None:
    """Registering functions does not disturb keybindings/macros (purely additive)."""
    init = _write(
        tmp_path,
        "init.py",
        (
            "abax.bind_key('normal', 'ctrl+s', lambda ed: ed, desc='save')\n"
            "abax.register_macro_menu('X', lambda ed: ed)\n"
            "abax.register_function('DOUBLE', lambda args: args[0] * 2)\n"
        ),
    )

    cfg = load_user_config(path=init)

    assert cfg.errors == []
    assert cfg.keybinding("normal", "ctrl+s") is not None
    assert len(cfg.macro_menu) == 1
    assert "DOUBLE" in cfg.functions


# --- apply_user_functions: the frontends' opt-in merge ----------------------


def test_apply_user_functions_end_to_end(tmp_path: Path) -> None:
    """A UDF loaded from init.py and applied evaluates in a real workbook."""
    from abax.core.functions import FUNCTIONS
    from abax.core.workbook import Workbook
    from abax.userconfig import apply_user_functions

    init = _write(
        tmp_path,
        "init.py",
        "def double(args):\n"
        "    return (args[0] or 0) * 2\n"
        "abax.register_function('UDFTESTDOUBLE', double)\n",
    )
    cfg = load_user_config(init)
    assert not cfg.errors
    # Loading alone must NOT touch the live registry.
    assert "UDFTESTDOUBLE" not in FUNCTIONS
    try:
        merged = apply_user_functions(cfg)
        assert merged == 1
        assert "UDFTESTDOUBLE" in FUNCTIONS
        wb = Workbook()
        wb.sheet.set_cell(0, 0, "=UDFTESTDOUBLE(21)")
        wb.recalculate()
        assert wb.sheet.get_value(0, 0) == 42
        # Idempotent re-apply.
        assert apply_user_functions(cfg) == 1
    finally:
        FUNCTIONS.pop("UDFTESTDOUBLE", None)  # never pollute the count canary


def test_apply_user_functions_empty_config_is_noop() -> None:
    from abax.userconfig import apply_user_functions

    assert apply_user_functions(UserConfig()) == 0
