"""Plugin discovery + consent gating (:mod:`abax.plugins`).

Consent is the whole point: nothing third-party is imported unless
``plugins_enabled`` (mapped to the ``enabled`` argument) is True. We fake entry
points so the tests don't need a real installed plugin package.
"""

from __future__ import annotations

from abax import plugins


class _FakeEntry:
    """Stands in for an importlib.metadata EntryPoint: name/value + load()."""

    def __init__(self, name, value, target=None, boom=None):
        self.name = name
        self.value = value
        self._target = target
        self._boom = boom
        self.loaded = False

    def load(self):
        self.loaded = True
        if self._boom is not None:
            raise self._boom
        return self._target


def _fake_discovered(*entries):
    """Build a `discovered`-compatible list of Plugin descriptors from entries."""
    return [
        plugins.Plugin(name=e.name, group=plugins.UDF_GROUP, value=e.value, _entry=e)
        for e in entries
    ]


# --- the consent gate ---------------------------------------------------------


def test_load_plugins_disabled_imports_nothing(monkeypatch):
    marker = _FakeEntry("evil", "pkg:evil", target=object())

    def _should_not_run(*a, **k):  # discovery shouldn't even be consulted-to-load
        return _fake_discovered(marker)

    monkeypatch.setattr(plugins, "discovered", _should_not_run)
    result = plugins.load_plugins(enabled=False)
    assert result.skipped is True
    assert result.loaded == {}
    assert result.errors == {}
    # Crucially: the entry's load() was never called -> no third-party code ran.
    assert marker.loaded is False


def test_settings_enabled_defaults_off():
    class _NoField:
        pass

    class _On:
        plugins_enabled = True

    class _Off:
        plugins_enabled = False

    # Missing field reads as disabled (safe default for pre-field settings).
    assert plugins.settings_enabled(_NoField()) is False
    assert plugins.settings_enabled(_On()) is True
    assert plugins.settings_enabled(_Off()) is False


def test_load_plugins_disabled_via_settings(monkeypatch):
    entry = _FakeEntry("f", "pkg:f", target=lambda: 1)
    monkeypatch.setattr(plugins, "discovered", lambda *a, **k: _fake_discovered(entry))

    class _Settings:
        plugins_enabled = False

    result = plugins.load_plugins(enabled=plugins.settings_enabled(_Settings()))
    assert result.skipped is True
    assert entry.loaded is False


# --- loading when enabled -----------------------------------------------------


def test_load_plugins_enabled_imports_targets(monkeypatch):
    obj = {"kind": "udf"}
    entry = _FakeEntry("myudf", "pkg:myudf", target=obj)
    monkeypatch.setattr(plugins, "discovered", lambda *a, **k: _fake_discovered(entry))

    seen = []
    result = plugins.load_plugins(
        enabled=True, on_load=lambda p, o: seen.append((p.name, o))
    )
    assert result.skipped is False
    key = f"{plugins.UDF_GROUP}/myudf"
    assert result.loaded[key] is obj
    assert entry.loaded is True
    assert seen == [("myudf", obj)]


def test_one_bad_plugin_does_not_block_the_rest(monkeypatch):
    good = _FakeEntry("good", "pkg:good", target="ok")
    bad = _FakeEntry("bad", "pkg:bad", boom=ImportError("no module"))
    monkeypatch.setattr(
        plugins, "discovered", lambda *a, **k: _fake_discovered(good, bad)
    )

    result = plugins.load_plugins(enabled=True)
    assert result.loaded[f"{plugins.UDF_GROUP}/good"] == "ok"
    assert isinstance(result.errors[f"{plugins.UDF_GROUP}/bad"], ImportError)


def test_on_load_failure_is_recorded_not_raised(monkeypatch):
    entry = _FakeEntry("f", "pkg:f", target="obj")
    monkeypatch.setattr(plugins, "discovered", lambda *a, **k: _fake_discovered(entry))

    def _boom(plugin, obj):
        raise ValueError("callback failed")

    result = plugins.load_plugins(enabled=True, on_load=_boom)
    # The import succeeded...
    assert result.loaded[f"{plugins.UDF_GROUP}/f"] == "obj"
    # ...but the callback error is captured, not propagated.
    assert isinstance(result.errors[f"{plugins.UDF_GROUP}/f"], ValueError)


# --- real discovery is safe & side-effect-free --------------------------------


def test_discovered_returns_a_list_without_importing():
    # Reads metadata only; must never raise even with no abax plugins installed.
    result = plugins.discovered()
    assert isinstance(result, list)
    for p in result:
        assert p.group in plugins.PLUGIN_GROUPS
        assert isinstance(p.name, str)


def test_plugin_groups_are_the_two_advertised():
    assert plugins.UDF_GROUP == "abax.udfs"
    assert plugins.FORMAT_GROUP == "abax.formats"
    assert set(plugins.PLUGIN_GROUPS) == {"abax.udfs", "abax.formats"}
