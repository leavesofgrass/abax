"""User init.py key rebinds firing through the live TUI key dispatch.

The :mod:`abax.userconfig` unit tests prove bindings are *stored* and *looked
up* correctly; these prove :mod:`abax.tui.keys` actually *consults* them in
every mode, that rebinds win over built-ins, and that the ``:map`` command
lists what is bound.
"""

from __future__ import annotations

from abax.engine.document import Document
from abax.tui.editor import TuiEditor
from abax.tui.keys import _handle_key
from abax.userconfig import UserConfig


def _editor_with(uc: UserConfig) -> TuiEditor:
    ed = TuiEditor(Document())
    ed.user_config = uc          # swap in a config with our test bindings
    return ed


def _run(ed: TuiEditor, line: str) -> None:
    ed.command_buf = line
    ed.run_command()


def test_normal_rebind_wins_over_builtin() -> None:
    """A normal-mode rebind fires instead of the built-in for that key."""
    hits = []
    uc = UserConfig()
    uc.bind_key("normal", "K", lambda ed: hits.append("K"), desc="shout")
    ed = _editor_with(uc)

    _handle_key(ed, "K")
    assert hits == ["K"]


def test_rebind_fires_in_every_mode() -> None:
    """Each bindable mode consults user bindings before its built-in handling."""
    fired = {}
    uc = UserConfig()
    # A non-printable chord so insert/command bindings don't collide with typing.
    keys = {"normal": "Q", "visual": "Q", "rpn": "\x00",
            "insert": "\x00", "command": "\x00", "browser": "Q"}
    for mode, key in keys.items():
        uc.bind_key(mode, key, (lambda m: (lambda ed: fired.__setitem__(m, True)))(mode))

    for mode, key in keys.items():
        ed = _editor_with(uc)
        ed.mode = mode
        _handle_key(ed, key)
        assert fired.get(mode) is True, f"binding did not fire in {mode} mode"


def test_insert_printable_still_types_when_unbound() -> None:
    """An ordinary printable key in insert mode types normally, not intercepted."""
    uc = UserConfig()
    uc.bind_key("insert", "\x00", lambda ed: None)  # unrelated chord bound
    ed = _editor_with(uc)
    ed.begin_insert()
    for ch in "hi":
        _handle_key(ed, ch)
    assert ed.edit_buf.endswith("hi")


def test_map_command_lists_bindings() -> None:
    """``:map`` reports bound modes/keys; ``:map MODE`` narrows to one mode."""
    uc = UserConfig()
    uc.bind_key("normal", "K", lambda ed: None, desc="shout")
    uc.bind_key("insert", "ctrl+w", lambda ed: None, desc="delword")
    ed = _editor_with(uc)

    _run(ed, ":map")
    assert "normal:K" in ed.message and "insert:ctrl+w" in ed.message

    _run(ed, ":map normal")
    assert "K=shout" in ed.message and "ctrl+w" not in ed.message

    _run(ed, ":map bogus")
    assert "unknown mode" in ed.message


def test_map_command_empty_config() -> None:
    """``:map`` with no rebinds says so instead of erroring."""
    ed = _editor_with(UserConfig())
    _run(ed, ":map")
    assert "none" in ed.message
