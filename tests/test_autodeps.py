"""On-demand optional-dependency auto-installer (no real pip is ever run)."""

from __future__ import annotations

import pytest

from abax import autodeps


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Isolate markers + capture install calls instead of running pip."""
    calls = []
    monkeypatch.setattr(autodeps, "_MARKER_DIR", str(tmp_path))
    monkeypatch.setattr(autodeps, "_INSTALL_FN", lambda pip, **kw: calls.append(pip) or True)
    autodeps._attempted_session.clear()
    autodeps.set_enabled(None)
    monkeypatch.delenv("ABAX_NO_AUTOINSTALL", raising=False)
    yield calls
    autodeps.set_enabled(None)
    autodeps._attempted_session.clear()


def test_installed_present_module_is_skipped(sandbox):
    # 'json' is always importable -> nothing attempted
    assert autodeps.ensure([("json-pkg", "json")], background=False) == []
    assert sandbox == []


def test_missing_module_is_installed_once(sandbox):
    pkg = [("totally-bogus-dist", "abax_no_such_module_xyz")]
    assert autodeps.ensure(pkg, background=False) == ["totally-bogus-dist"]
    assert sandbox == ["totally-bogus-dist"]
    # a second call is a no-op (marker recorded)
    assert autodeps.ensure(pkg, background=False) == []
    assert sandbox == ["totally-bogus-dist"]


def test_force_ignores_marker(sandbox):
    pkg = [("bogus2", "abax_missing_mod_2")]
    autodeps.ensure(pkg, background=False)
    assert autodeps.ensure(pkg, background=False, force=True) == ["bogus2"]
    assert sandbox == ["bogus2", "bogus2"]


def test_marker_file_written(sandbox, tmp_path):
    autodeps.ensure([("markme", "abax_missing_mod_3")], background=False)
    assert (tmp_path / "markme.attempted").exists()


def test_disabled_via_setter(sandbox):
    autodeps.set_enabled(False)
    assert autodeps.ensure([("x", "abax_missing_mod_4")], background=False) == []
    assert sandbox == []


def test_disabled_via_env(sandbox, monkeypatch):
    monkeypatch.setenv("ABAX_NO_AUTOINSTALL", "1")
    assert autodeps.ensure([("x", "abax_missing_mod_5")], background=False) == []
    assert sandbox == []


def test_ensure_feature_resolves_packages(sandbox):
    # 'excel' -> openpyxl; pretend it's missing by using its real import name only if absent
    attempted = autodeps.ensure_feature("excel", background=False)
    if autodeps.installed("openpyxl"):
        assert attempted == []                       # already present here
    else:
        assert attempted == ["openpyxl"]
    assert autodeps.ensure_feature("does-not-exist", background=False) == []


def test_registry_is_well_formed():
    for key, pkgs in autodeps.FEATURES.items():
        assert pkgs, key
        for pip, mod in pkgs:
            assert isinstance(pip, str) and isinstance(mod, str)
    assert ("numpy", "numpy") in autodeps.ALL
    assert autodeps.ALL[-1] == ("pymc", "pymc")             # heaviest, installed last
    # pymc is split into its own `bayes` feature but stays in the full-fat set
    assert ("pymc", "pymc") in autodeps.FEATURES["bayes"]
    assert ("pymc", "pymc") not in autodeps.FEATURES["science"]
    assert ("pymc", "pymc") in autodeps.ALL
    # PySide6 is deliberately NOT auto-installed (it's the entry binding)
    assert all(pip != "PySide6" for pip, _ in autodeps.ALL)


def test_presets_and_feature_info():
    assert set(autodeps.preset("thin")) == {"fast-io", "excel", "terminal", "tui"}
    assert set(autodeps.preset("all")) == set(autodeps.FEATURES)
    assert autodeps.preset("nonsense") == []
    # every feature has a chooser description (label, detail, size_mb)
    for key in autodeps.FEATURES:
        assert key in autodeps.FEATURE_INFO
        label, detail, mb = autodeps.FEATURE_INFO[key]
        assert label and detail and isinstance(mb, int)
    # thin excludes the heavy stacks
    assert "science" not in autodeps.preset("thin")
    assert "bayes" not in autodeps.preset("thin")


def test_missing_helper(sandbox):
    pairs = [("json-pkg", "json"), ("nope", "abax_missing_mod_6")]
    miss = autodeps.missing(pairs)
    assert miss == [("nope", "abax_missing_mod_6")]
