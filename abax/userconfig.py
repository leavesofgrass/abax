"""User ``init.py`` bootstrap — power-user key rebinds and macro-menu entries.

abax reads an optional Python file at ``CONFIG_DIR / "init.py"`` (see
:mod:`abax._runtime`) on startup, letting power users rebind TUI keys and
register macro-menu commands without editing the app itself.

A user's init file looks like::

    # ~/.config/abax/init.py
    def save(ed):
        ed.run_command_str(":w")

    abax.bind_key("normal", "ctrl+s", save, desc="save")
    abax.register_macro_menu("Reformat", lambda ed: ...)

    def my_double(args):
        return (args[0] or 0) * 2
    abax.register_function("DOUBLE", my_double)              # plain fn(args)
    abax.register_function("MYIF", my_if, kind="lazy")       # fn(arg_nodes, ev)
    abax.register_function("MYROW", my_row, kind="context")  # fn(arg_nodes, ctx)

The ``abax`` name injected into the init file is a lightweight *facade*
(:class:`_ConfigFacade`) — NOT the real :mod:`abax` package — so a user cannot
accidentally clobber the package by assigning to it. The facade forwards
``bind_key`` / ``register_macro_menu`` / ``register_function`` to a fresh
:class:`UserConfig` and exposes ``abax.__version__`` for display.

Registered functions are only *collected* by :func:`load_user_config` — loading
never touches the live engine registries in :mod:`abax.core.functions` (so tests
can load throwaway init files without polluting global state). The frontends
(GUI/TUI) opt in explicitly by calling :func:`apply_user_functions` on the
trusted init-file path, which merges the collected ``functions`` /
``lazy_functions`` / ``context_functions`` into ``FUNCTIONS`` /
``LAZY_FUNCTIONS`` / ``CONTEXT_FUNCTIONS`` (last-write-wins, so a user function
may deliberately shadow a built-in).

SECURITY
--------
``init.py`` is the user's OWN, trusted configuration file — exactly like a
``.vimrc``, ``.pythonrc``, or a shell ``rc`` file. It is executed with the
user's full privileges, *by design*, as arbitrary Python. This is NOT the
sandboxed / untrusted-code path: abax's formula/expression sandbox is a
separate mechanism. Do not route untrusted input through :func:`load_user_config`;
loading someone else's ``init.py`` is equivalent to running their program.

The loader never lets a broken init file crash startup: any exception raised
while importing/executing it is captured into ``config.errors`` and a partial
:class:`UserConfig` is returned.

Kept intentionally light: only the stdlib is imported at module top so this is
cheap to pull in from ``abax``'s top level and from the TUI key handler.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

__all__ = [
    "FUNCTION_KINDS",
    "Binding",
    "MacroEntry",
    "UserConfig",
    "load_user_config",
]

# An editor-facing action: called with the active editor/app object. The exact
# object passed is the integrator's concern; the registry stays agnostic.
Action = Callable[..., object]

# Calling conventions a user-registered formula function may declare. These
# mirror the three engine registries in :mod:`abax.core.functions`:
#   "plain"   -> FUNCTIONS         : fn(args) -> value   (args already evaluated)
#   "lazy"    -> LAZY_FUNCTIONS    : fn(arg_nodes, ev)   (control-flow; unevaluated)
#   "context" -> CONTEXT_FUNCTIONS : fn(arg_nodes, ctx)  (sees refs + EvalContext)
FUNCTION_KINDS: tuple[str, ...] = ("plain", "lazy", "context")


@dataclass(frozen=True)
class Binding:
    """A single keybinding recorded by the user's ``init.py``.

    Attributes:
        mode: TUI mode the binding applies to, e.g. ``"normal"`` or ``"insert"``.
        key: Key spec as a string, e.g. ``"ctrl+s"`` or ``"K"``.
        action: Callable invoked when the key fires (typically ``action(editor)``).
        desc: Optional human-readable description for help/menus.
    """

    mode: str
    key: str
    action: Action
    desc: str = ""


@dataclass(frozen=True)
class MacroEntry:
    """A named macro-menu entry recorded by the user's ``init.py``.

    Attributes:
        name: Label shown in the macro menu.
        action: Callable invoked when the entry is chosen (typically ``action(editor)``).
        desc: Optional human-readable description for help/menus.
    """

    name: str
    action: Action
    desc: str = ""


@dataclass
class UserConfig:
    """Registry populated by the user's ``init.py``.

    Instances start empty. The loader hands the user's init file a facade whose
    ``bind_key`` / ``register_macro_menu`` forward here, so after
    :func:`load_user_config` this holds whatever the init file registered.

    Attributes:
        keybindings: Map of ``(mode, key)`` to the :class:`Binding` recorded for it.
            A later ``bind_key`` for the same ``(mode, key)`` overrides an earlier one.
        macro_menu: Ordered list of :class:`MacroEntry`, in registration order.
        functions: Map of ``NAME`` to a plain formula function ``fn(args) -> value``.
            Merges into the engine's ``FUNCTIONS`` registry on the trusted path.
        lazy_functions: Map of ``NAME`` to a control-flow function ``fn(arg_nodes, ev)``.
            Merges into the engine's ``LAZY_FUNCTIONS`` registry.
        context_functions: Map of ``NAME`` to a reference-aware function
            ``fn(arg_nodes, ctx)``. Merges into the engine's ``CONTEXT_FUNCTIONS``.
        errors: Human-readable strings describing anything that went wrong while
            loading the init file (empty on success).
    """

    keybindings: dict[tuple[str, str], Binding] = field(default_factory=dict)
    macro_menu: list[MacroEntry] = field(default_factory=list)
    functions: dict[str, Action] = field(default_factory=dict)
    lazy_functions: dict[str, Action] = field(default_factory=dict)
    context_functions: dict[str, Action] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def bind_key(self, mode: str, key: str, action: Action, *, desc: str = "") -> None:
        """Record a keybinding for ``(mode, key)``.

        Args:
            mode: TUI mode, e.g. ``"normal"`` / ``"insert"``.
            key: Key spec string, e.g. ``"ctrl+s"`` or ``"K"``.
            action: Callable invoked when the key fires.
            desc: Optional description for help/menus.
        """
        self.keybindings[(mode, key)] = Binding(mode, key, action, desc)

    def register_macro_menu(self, name: str, action: Action, *, desc: str = "") -> None:
        """Record a named macro-menu entry.

        Args:
            name: Label shown in the macro menu.
            action: Callable invoked when the entry is chosen.
            desc: Optional description for help/menus.
        """
        self.macro_menu.append(MacroEntry(name, action, desc))

    def register_function(self, name: str, fn: Action, *, kind: str = "plain") -> None:
        """Record a custom formula function under ``name``.

        The function is only *collected* here; abax never mutates the live engine
        registries from this module. On the trusted init-file path the integrator
        merges :attr:`functions` / :attr:`lazy_functions` / :attr:`context_functions`
        into the engine's ``FUNCTIONS`` / ``LAZY_FUNCTIONS`` / ``CONTEXT_FUNCTIONS``.

        Args:
            name: Formula name as used in a cell, e.g. ``"DOUBLE"`` or ``"MY.FUNC"``.
                Must be a non-empty, UPPERCASE identifier; ``.`` is allowed between
                identifier segments (so ``"MY.FUNC"`` is valid, ``"my.func"`` is not).
            fn: The callable implementing the function. Its calling convention must
                match ``kind`` (see below). Registering the same ``name`` again for
                the same ``kind`` overrides the earlier one.
            kind: Which calling convention/registry the function uses:

                * ``"plain"`` (default) — ``fn(args) -> value``; args are already
                  evaluated (a range arrives as a ``RangeValue``). Goes to
                  :attr:`functions`.
                * ``"lazy"`` — ``fn(arg_nodes, ev)``; receives unevaluated argument
                  AST nodes for control flow (untaken branches never run). Goes to
                  :attr:`lazy_functions`.
                * ``"context"`` — ``fn(arg_nodes, ctx)``; receives the raw argument
                  nodes plus an ``EvalContext`` so it can see references, not just
                  values. Goes to :attr:`context_functions`.

        Raises:
            ValueError: If ``name`` is not a non-empty UPPERCASE identifier (dots
                allowed between segments), ``fn`` is not callable, or ``kind`` is
                not one of :data:`FUNCTION_KINDS`.
        """
        _validate_function_name(name)
        if not callable(fn):
            raise ValueError(f"register_function: fn must be callable, got {type(fn).__name__}")
        registry = {
            "plain": self.functions,
            "lazy": self.lazy_functions,
            "context": self.context_functions,
        }.get(kind)
        if registry is None:
            raise ValueError(
                f"register_function: kind must be one of {FUNCTION_KINDS}, got {kind!r}"
            )
        registry[name] = fn

    def keybinding(self, mode: str, key: str) -> Optional[Binding]:
        """Return the :class:`Binding` registered for ``(mode, key)``, or ``None``.

        Args:
            mode: TUI mode to look up.
            key: Key spec string to look up.

        Returns:
            The recorded :class:`Binding`, or ``None`` if nothing is bound.
        """
        return self.keybindings.get((mode, key))


def _validate_function_name(name: str) -> None:
    """Raise :class:`ValueError` unless ``name`` is a valid formula-function name.

    A valid name is a non-empty string that is fully UPPERCASE and whose
    ``.``-separated segments are each a Python identifier — so ``"DOUBLE"``,
    ``"LOG10"`` and ``"MY.FUNC"`` pass, while ``""``, ``"my.func"`` (lowercase),
    ``"MY..FUNC"`` (empty segment) and ``".FUNC"`` (leading dot) are rejected.

    Args:
        name: Candidate formula name to validate.

    Raises:
        ValueError: If ``name`` is not a non-empty UPPERCASE dotted identifier.
    """
    if not isinstance(name, str) or not name:
        raise ValueError(f"register_function: name must be a non-empty string, got {name!r}")
    if name != name.upper():
        raise ValueError(f"register_function: name must be UPPERCASE, got {name!r}")
    if any(not segment.isidentifier() for segment in name.split(".")):
        raise ValueError(
            f"register_function: name must be an identifier (dots allowed), got {name!r}"
        )


class _ConfigFacade:
    """Lightweight ``abax`` object exposed to the user's ``init.py``.

    Proxies the registration API to a backing :class:`UserConfig` and exposes
    ``__version__`` for display. Deliberately *not* the real :mod:`abax`
    package, so a user assigning to ``abax`` in their init file cannot clobber
    the installed package.
    """

    def __init__(self, config: UserConfig, version: str) -> None:
        self._config = config
        self.__version__ = version

    def bind_key(self, mode: str, key: str, action: Action, *, desc: str = "") -> None:
        """Proxy to :meth:`UserConfig.bind_key`."""
        self._config.bind_key(mode, key, action, desc=desc)

    def register_macro_menu(self, name: str, action: Action, *, desc: str = "") -> None:
        """Proxy to :meth:`UserConfig.register_macro_menu`."""
        self._config.register_macro_menu(name, action, desc=desc)

    def register_function(self, name: str, fn: Action, *, kind: str = "plain") -> None:
        """Proxy to :meth:`UserConfig.register_function`."""
        self._config.register_function(name, fn, kind=kind)


def _init_path(path: Optional[str]) -> Path:
    """Resolve the init-file path: explicit ``path`` arg, else ``CONFIG_DIR/init.py``."""
    if path is not None:
        return Path(path)
    # Import lazily so importing this module never triggers _runtime's
    # directory-creation side effects until a config load is actually requested.
    from abax._runtime import CONFIG_DIR

    return Path(CONFIG_DIR) / "init.py"


def _app_version() -> str:
    """Best-effort abax version string for the facade (never raises)."""
    try:
        from abax import __version__

        return __version__
    except Exception:
        return "unknown"


def load_user_config(path: Optional[str] = None) -> UserConfig:
    """Load the user's ``init.py`` into a fresh :class:`UserConfig`.

    Locates the init file from ``path`` if given, otherwise
    ``CONFIG_DIR / "init.py"``. A missing file yields an empty config (this is
    the normal case for users who never wrote one). A file that raises during
    execution yields a *partial* config whose ``errors`` list records the
    failure — a broken init file must NEVER crash startup.

    Args:
        path: Explicit path to an init file, or ``None`` to use the per-user
            ``CONFIG_DIR / "init.py"`` location.

    Returns:
        A :class:`UserConfig`. Empty when the file is absent; partial with a
        recorded ``errors`` entry when the file raised; fully populated on success.

    Note:
        SECURITY — this executes the file as arbitrary Python with the user's
        privileges, by design (see the module docstring). It is the trusted
        power-user config path, not a sandbox.
    """
    config = UserConfig()
    init_file = _init_path(path)

    try:
        source = init_file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return config
    except OSError as exc:
        config.errors.append(f"could not read {init_file}: {exc}")
        return config

    facade = _ConfigFacade(config, _app_version())
    namespace: dict[str, object] = {
        "__name__": "abax_init",
        "__file__": str(init_file),
        "abax": facade,
    }

    try:
        compiled = compile(source, str(init_file), "exec")
        exec(compiled, namespace)  # noqa: S102 — trusted user config, by design.
    except BaseException as exc:  # noqa: BLE001 — never let init.py crash startup.
        tb = traceback.format_exc()
        config.errors.append(f"{type(exc).__name__} in {init_file}: {exc}\n{tb}")

    return config


def apply_user_functions(config: UserConfig) -> int:
    """Merge *config*'s collected UDFs into the live formula registries.

    The explicit opt-in step the frontends call after :func:`load_user_config`
    on the trusted init-file path. Kept separate from loading so that merely
    *loading* an init file (tests, tooling) never mutates global engine state.

    Merging is ``dict.update`` per registry — last-write-wins, so a user
    function may deliberately shadow a built-in of the same name. Idempotent:
    re-applying the same config is a no-op.

    Returns:
        The number of function names merged (across all three registries).
    """
    if not (config.functions or config.lazy_functions or config.context_functions):
        return 0
    # Imported lazily: the registries transitively import the whole function
    # engine, which this light module must not pull in at import time.
    from .core.functions import CONTEXT_FUNCTIONS, FUNCTIONS, LAZY_FUNCTIONS

    FUNCTIONS.update(config.functions)
    LAZY_FUNCTIONS.update(config.lazy_functions)
    CONTEXT_FUNCTIONS.update(config.context_functions)
    return len(config.functions) + len(config.lazy_functions) + len(config.context_functions)
