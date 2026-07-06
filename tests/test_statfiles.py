"""Tests for abax.engine.statfiles — Stata (.dta) / SPSS (.sav) import.

The round-trip test requires the optional 'pyreadstat' package (plus pandas) and
skips cleanly when they are absent, so the suite still passes with zero optional
packages installed (a core invariant). The graceful-missing-dep message path and
the extension routing/registration are ALWAYS exercised — they need no dep.
"""

from __future__ import annotations

import pytest

from abax import autodeps, diagnostics
from abax.engine import statfiles
from abax.engine.statfiles import StatFileError

# --- no-dep-required tests --------------------------------------------------


def test_available_returns_bool():
    # Importable without any optional dep; available() is always a plain bool.
    assert isinstance(statfiles.available(), bool)


def test_module_imports_without_pyreadstat():
    # The module and StatFileError exist regardless of pyreadstat being installed.
    assert issubclass(StatFileError, Exception)


def test_missing_dep_raises_clear_message(tmp_path, monkeypatch):
    """When pyreadstat is absent, loading raises a StatFileError that points at
    the 'abax[stats-io]' extra — the graceful-fallback contract. We force the
    absent path by making the lazy import raise, so this runs with OR without
    the real package installed."""
    def _boom():
        raise StatFileError(statfiles._FALLBACK_MSG)

    monkeypatch.setattr(statfiles, "_import_pyreadstat", _boom)
    path = tmp_path / "data.dta"
    path.write_bytes(b"")  # a real .dta extension; content never read (import fails first)
    with pytest.raises(StatFileError) as exc:
        statfiles.load_statfile(path)
    msg = str(exc.value)
    assert "pyreadstat" in msg
    assert "abax[stats-io]" in msg


def test_unsupported_extension_raises():
    # An extension statfiles doesn't handle is rejected before any import.
    with pytest.raises(StatFileError) as exc:
        statfiles.load_statfile("data.xlsx")
    assert ".xlsx" in str(exc.value)


def test_document_routes_dta_and_sav(monkeypatch):
    """The Document.open dispatch routes .dta/.sav/.zsav/.por into statfiles."""
    from abax.engine import document

    seen = []

    def _fake_load(path):
        seen.append(str(path))
        from abax.core.workbook import Workbook

        return Workbook()

    monkeypatch.setattr(statfiles, "load_statfile", _fake_load)
    for ext in (".dta", ".sav", ".zsav", ".por"):
        document.Document.open(f"stats{ext}")
    # All four statistical extensions were dispatched to statfiles.load_statfile.
    assert len(seen) == 4
    assert all(p.startswith("stats.") for p in seen)


def test_registered_in_autodeps():
    # Feature registered, present in the full-fat ALL set, and NOT in thin.
    assert ("pyreadstat", "pyreadstat") in autodeps.FEATURES["stats-io"]
    assert ("pyreadstat", "pyreadstat") in autodeps.ALL
    assert "stats-io" in autodeps.FEATURE_INFO
    assert "stats-io" in autodeps.preset("all")
    assert "stats-io" not in autodeps.preset("thin")
    # PyNEC must remain the last (compiled) install even after we inserted ours.
    assert autodeps.ALL[-1] == ("PyNEC", "PyNEC")


def test_registered_in_diagnostics():
    assert "pyreadstat" in diagnostics.OPTIONAL_DEPENDENCIES
    entry = diagnostics.OPTIONAL_DEPENDENCIES["pyreadstat"]
    assert isinstance(entry["available"], bool)
    assert entry["fallback"] and entry["purpose"]


# --- round-trip (requires the real optional dep) ----------------------------


def test_dta_roundtrip(tmp_path):
    pytest.importorskip("pyreadstat")
    pd = pytest.importorskip("pandas")

    df = pd.DataFrame({"name": ["Alice", "Bob"], "age": [30.0, 25.0]})
    path = tmp_path / "data.dta"
    import pyreadstat

    pyreadstat.write_dta(df, str(path))
    assert path.exists()

    wb = statfiles.load_statfile(path)
    sheet = wb.sheet
    # Header (variable names) survive.
    assert sheet.get_raw(0, 0) == "name"
    assert sheet.get_raw(0, 1) == "age"
    # Values survive as cell text; whole floats collapse to ints.
    assert sheet.get_raw(1, 0) == "Alice"
    assert sheet.get_raw(1, 1) == "30"
    assert sheet.get_raw(2, 0) == "Bob"
    assert sheet.get_raw(2, 1) == "25"


def test_sav_roundtrip(tmp_path):
    pytest.importorskip("pyreadstat")
    pd = pytest.importorskip("pandas")

    df = pd.DataFrame({"city": ["Oslo", "Bergen"], "pop": [700.0, 280.0]})
    path = tmp_path / "data.sav"
    import pyreadstat

    pyreadstat.write_sav(df, str(path))
    assert path.exists()

    wb = statfiles.load_statfile(path)
    sheet = wb.sheet
    assert sheet.get_raw(0, 0) == "city"
    assert sheet.get_raw(1, 0) == "Oslo"
    assert sheet.get_raw(2, 1) == "280"
