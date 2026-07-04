"""Third-party plugin discovery via ``importlib.metadata`` entry points.

abax can be extended by *installed* Python packages that advertise user-defined
functions (UDFs) or file-format importers/exporters through entry points. This
module finds and loads them — **but only with the user's consent**.

.. WARNING::
    Loading a plugin runs third-party code with your full privileges. A plugin
    is an installed package's ``entry_points``; importing it executes that
    package's module top-level. That is exactly the untrusted-code risk the
    console/macros carry, so plugin loading is **off by default** and gated on
    the ``plugins_enabled`` setting. :func:`load_plugins` refuses to import
    anything unless the caller passes ``enabled=True`` (which the GUI wires to
    ``settings.plugins_enabled``). Discovery — merely *listing* what is
    advertised — is always safe (it reads metadata without importing), so
    :func:`discovered` works regardless of consent.

Entry-point groups
------------------
* ``abax.udfs``    — a callable (or a module exposing ``register(registry)``)
  contributing formula/console user-defined functions.
* ``abax.formats`` — an importer/exporter contributing a file format.

A third-party package opts in via its packaging metadata, e.g. in
``pyproject.toml``::

    [project.entry-points."abax.udfs"]
    myfuncs = "mypkg.abax_udfs"

Nothing here is a security boundary: a loaded plugin is ordinary in-process
code. Consent is the gate; isolation of what a plugin then does is out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

__all__ = [
    "UDF_GROUP",
    "FORMAT_GROUP",
    "PLUGIN_GROUPS",
    "Plugin",
    "LoadResult",
    "discovered",
    "load_plugins",
    "settings_enabled",
]

UDF_GROUP = "abax.udfs"
FORMAT_GROUP = "abax.formats"
PLUGIN_GROUPS = (UDF_GROUP, FORMAT_GROUP)


@dataclass(frozen=True)
class Plugin:
    """One advertised entry point, described *without* importing its target.

    ``name`` is the entry-point name, ``group`` the group it was found in,
    ``value`` the ``module:attr`` reference string. ``load()`` imports and
    returns the target object — call it only after consent.
    """

    name: str
    group: str
    value: str
    _entry: Any = field(default=None, repr=False, compare=False)

    def load(self) -> Any:
        """Import and return the entry point's target object.

        Executes third-party code; only call when plugins are enabled. Raises
        whatever the import raises (surface it to the user rather than swallow).
        """
        if self._entry is None:  # pragma: no cover - constructed only from real entries
            raise RuntimeError(f"plugin {self.name!r} has no loadable entry point")
        return self._entry.load()


@dataclass
class LoadResult:
    """Outcome of a :func:`load_plugins` call.

    ``loaded`` maps ``"group/name"`` to the imported object. ``errors`` maps the
    same key to the exception raised while importing that plugin (one bad plugin
    never aborts the rest). ``skipped`` is True when consent was withheld and
    nothing was imported at all.
    """

    loaded: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)
    skipped: bool = False


def _iter_entry_points(group: str):
    """Yield entry points for *group*, tolerant of the two importlib.metadata APIs.

    Python 3.10+ exposes ``entry_points(group=...)``; older stdlib returns a
    dict keyed by group. We support both so abax runs across versions without a
    hard version check.
    """
    from importlib import metadata

    try:
        eps = metadata.entry_points(group=group)  # 3.10+ selectable API
    except TypeError:  # pragma: no cover - only on <3.10
        eps = metadata.entry_points().get(group, [])  # type: ignore[union-attr]
    return list(eps)


def discovered(groups: "tuple[str, ...] | None" = None) -> "list[Plugin]":
    """List advertised plugins **without importing** any of them.

    Reads installed-package metadata only, so it is always safe to call — no
    consent required, no third-party code executed. ``groups`` defaults to both
    :data:`UDF_GROUP` and :data:`FORMAT_GROUP`. Returns a list of :class:`Plugin`
    descriptors (empty when nothing is installed). Never raises for a missing
    group; a broken metadata store yields an empty list rather than an error.
    """
    groups = groups or PLUGIN_GROUPS
    out: list[Plugin] = []
    for group in groups:
        try:
            entries = _iter_entry_points(group)
        except Exception:  # noqa: BLE001 - a broken metadata store => nothing found
            continue
        for ep in entries:
            out.append(Plugin(name=ep.name, group=group, value=ep.value, _entry=ep))
    return out


def settings_enabled(settings: Any) -> bool:
    """Read the consent flag off a settings object, defaulting to *off*.

    Uses ``getattr(settings, "plugins_enabled", False)`` so a settings struct
    that predates the field (or a plain ``None``) safely reads as disabled —
    plugins never load by accident.
    """
    return bool(getattr(settings, "plugins_enabled", False))


def load_plugins(
    *,
    enabled: bool,
    groups: "tuple[str, ...] | None" = None,
    on_load: "Callable[[Plugin, Any], None] | None" = None,
) -> LoadResult:
    """Import the advertised plugins — **only** when ``enabled`` is True.

    This is the consent gate. When ``enabled`` is False, nothing is imported and
    the result has ``skipped=True`` with empty ``loaded``/``errors``: no
    third-party code runs. When True, every discovered plugin in ``groups`` is
    imported; a plugin that fails to import is recorded in ``errors`` and the
    rest still load (one bad plugin can't disable the feature). ``on_load`` is
    called ``(plugin, obj)`` for each successful import so the caller can
    register the UDF/format however it likes.

    Wire ``enabled`` to ``settings.plugins_enabled`` (see :func:`settings_enabled`).
    """
    if not enabled:
        return LoadResult(skipped=True)

    result = LoadResult()
    for plugin in discovered(groups):
        key = f"{plugin.group}/{plugin.name}"
        try:
            obj = plugin.load()
        except Exception as exc:  # noqa: BLE001 - isolate one plugin's failure
            result.errors[key] = exc
            continue
        result.loaded[key] = obj
        if on_load is not None:
            try:
                on_load(plugin, obj)
            except Exception as exc:  # noqa: BLE001 - a bad callback != a load failure
                result.errors[key] = exc
    return result
