"""The CLI argv normalizer: a bare file path opens in the GUI by default."""

from __future__ import annotations

from abax.app import _normalize_argv


def test_bare_file_becomes_gui():
    assert _normalize_argv(["data.csv"]) == ["gui", "data.csv"]
    assert _normalize_argv(["/path/to/book.abax"]) == ["gui", "/path/to/book.abax"]


def test_subcommands_pass_through():
    for cmd in ("gui", "tui", "view", "convert", "get", "macro"):
        assert _normalize_argv([cmd, "x"]) == [cmd, "x"]


def test_flags_and_empty_pass_through():
    assert _normalize_argv([]) == []
    assert _normalize_argv(["--version"]) == ["--version"]
    assert _normalize_argv(["--macros", "m.py"]) == ["--macros", "m.py"]
