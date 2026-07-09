"""Tests for :mod:`abax.userconfig` — the ``init.py`` bootstrap loader."""

from __future__ import annotations

from pathlib import Path

from abax.userconfig import (
    Binding,
    MacroEntry,
    UserConfig,
    load_user_config,
)


def _write(tmp_path: Path, name: str, body: str) -> str:
    """Write an init file into ``tmp_path`` and return its path as a string."""
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return str(p)


def test_load_captures_bindings_and_macros(tmp_path: Path) -> None:
    """A well-formed init.py populates keybindings and the macro menu."""
    init = _write(
        tmp_path,
        "init.py",
        (
            "def save(ed):\n"
            "    return ed\n"
            "\n"
            "abax.bind_key('normal', 'ctrl+s', save, desc='save')\n"
            "abax.register_macro_menu('X', save, desc='run X')\n"
        ),
    )

    config = load_user_config(path=init)

    assert config.errors == []

    # Keybinding captured under (mode, key) and lookup helper works.
    binding = config.keybinding("normal", "ctrl+s")
    assert isinstance(binding, Binding)
    assert binding.mode == "normal"
    assert binding.key == "ctrl+s"
    assert binding.desc == "save"
    assert callable(binding.action)
    assert binding.action("sentinel") == "sentinel"
    assert config.keybindings[("normal", "ctrl+s")] is binding

    # Macro entry captured in order.
    assert len(config.macro_menu) == 1
    entry = config.macro_menu[0]
    assert isinstance(entry, MacroEntry)
    assert entry.name == "X"
    assert entry.desc == "run X"
    assert entry.action("sentinel") == "sentinel"


def test_lookup_miss_returns_none(tmp_path: Path) -> None:
    """Looking up an unbound (mode, key) returns None."""
    init = _write(tmp_path, "init.py", "abax.bind_key('normal', 'K', lambda ed: None)\n")
    config = load_user_config(path=init)
    assert config.keybinding("insert", "K") is None
    assert config.keybinding("normal", "ctrl+s") is None
    assert config.keybinding("normal", "K") is not None


def test_broken_init_records_error_and_does_not_raise(tmp_path: Path) -> None:
    """A raising init.py yields a config with an error, never an exception."""
    init = _write(
        tmp_path,
        "init.py",
        (
            "abax.bind_key('normal', 'ctrl+s', lambda ed: None)\n"
            "raise ValueError('boom')\n"
        ),
    )

    config = load_user_config(path=init)

    assert isinstance(config, UserConfig)
    assert config.errors, "expected a recorded error"
    assert "ValueError" in config.errors[0]
    assert "boom" in config.errors[0]
    # Registrations made before the exception are still captured (partial config).
    assert config.keybinding("normal", "ctrl+s") is not None


def test_syntax_error_is_captured(tmp_path: Path) -> None:
    """A syntactically invalid init.py is captured, not raised."""
    init = _write(tmp_path, "init.py", "this is not valid python !!!\n")
    config = load_user_config(path=init)
    assert config.errors
    assert config.keybindings == {}
    assert config.macro_menu == []


def test_missing_path_returns_empty_config(tmp_path: Path) -> None:
    """A non-existent init file yields an empty, error-free config."""
    missing = str(tmp_path / "does_not_exist.py")
    config = load_user_config(path=missing)
    assert isinstance(config, UserConfig)
    assert config.keybindings == {}
    assert config.macro_menu == []
    assert config.errors == []


def test_facade_exposes_version(tmp_path: Path) -> None:
    """The injected ``abax`` facade exposes __version__ for display."""
    init = _write(
        tmp_path,
        "init.py",
        "abax.register_macro_menu('ver', lambda ed: None, desc=abax.__version__)\n",
    )
    config = load_user_config(path=init)
    assert config.errors == []
    assert config.macro_menu[0].desc  # non-empty version string
