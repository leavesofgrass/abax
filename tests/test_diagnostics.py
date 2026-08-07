"""``abax --deps`` — the optional-dependency registry and its rendered report.

Two contracts are under test. The **registry** must describe every optional
package honestly: a real import name (a pip distribution name where an import
name belongs is the classic bug, so the flags are cross-checked against the
independently maintained :mod:`abax.autodeps` table), plus a fallback sentence
for the degraded path. The **report** must render that registry in a fixed,
aligned shape, must survive a probe that blows up (pandoc, PTY, autodeps are
all consulted defensively), and — being a fast path — must never install
anything or touch a directory other than ``abax._runtime``'s.

Every rendering test pins the registry and the three external probes to fixed
values, so the assertions hold on a bare stdlib-only machine and on a fully
loaded one alike.

Pure stdlib + abax core; no optional deps, no Qt.
"""

from __future__ import annotations

import importlib
import sys

import pytest

from abax import autodeps, diagnostics

# A deterministic stand-in for OPTIONAL_DEPENDENCIES: one present entry, one
# absent, names of deliberately different length (8 vs 22) so the column
# alignment is observable.
_FAKE_REGISTRY = {
    "shortdep": {
        "available": True,
        "fallback": "a fallback nobody should be shown",
        "purpose": "the installed one",
    },
    "a-much-longer-dep-name": {
        "available": False,
        "fallback": "pure-Python slow path",
        "purpose": "the absent one",
    },
}


def _pin(monkeypatch, *, registry=_FAKE_REGISTRY, pandoc=True, pty=True):
    """Freeze the registry and the two external-tool probes format_deps calls."""
    from abax.core import pandoc as pandoc_mod
    from abax.core import ptyterm

    if registry is not None:
        monkeypatch.setattr(diagnostics, "OPTIONAL_DEPENDENCIES", registry)
    monkeypatch.setattr(pandoc_mod, "available", pandoc if callable(pandoc) else lambda: pandoc)
    monkeypatch.setattr(ptyterm, "pty_available", pty if callable(pty) else lambda: pty)


def _rows(text):
    """The dependency lines of a report (``  [OK ] name  status``)."""
    return [ln for ln in text.splitlines() if ln.startswith("  [")]


def _row(text, name):
    """The single dependency row for *name* (the name field starts at col 8)."""
    hits = [ln for ln in _rows(text) if ln[8:].startswith(name)]
    assert len(hits) == 1, f"expected exactly one {name!r} row, got {hits!r}"
    return hits[0]


def _boom(*_args, **_kwargs):
    raise RuntimeError("probe exploded")


@pytest.fixture()
def autoinstall_default(monkeypatch):
    """Neutral auto-install state: no env kill-switch, no forced override."""
    monkeypatch.delenv("ABAX_NO_AUTOINSTALL", raising=False)
    autodeps.set_enabled(None)
    yield
    autodeps.set_enabled(None)


# --- _has: detection without import ----------------------------------------

def test_has_reports_importability():
    """A stdlib module is found; a name nobody ships is not."""
    assert diagnostics._has("json") is True
    assert diagnostics._has("abax_no_such_optional_dep_xyz") is False


def test_has_finds_a_module_without_importing_it(tmp_path, monkeypatch):
    """Detection is spec-based: the module body must never run.

    ``--deps`` reports on heavyweights (pymc, PyNEC, matplotlib); importing them
    to find out whether they exist would blow the fast path's whole budget.
    """
    (tmp_path / "abax_probe_optional_dep.py").write_text(
        "raise RuntimeError('importing this module is a bug')\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()

    assert diagnostics._has("abax_probe_optional_dep") is True   # would raise if imported
    assert "abax_probe_optional_dep" not in sys.modules


def test_has_swallows_malformed_names():
    """Bad names answer False rather than propagating out of the fast path."""
    assert diagnostics._has("") is False                    # ValueError: empty name
    assert diagnostics._has("json.decoder.nope") is False   # parent is not a package


# --- the registry itself ----------------------------------------------------

def test_registry_entries_have_the_documented_shape():
    """Every entry carries exactly available/fallback/purpose, all populated."""
    assert diagnostics.OPTIONAL_DEPENDENCIES, "registry must not be empty"
    for name, info in diagnostics.OPTIONAL_DEPENDENCIES.items():
        assert set(info) == {"available", "fallback", "purpose"}, name
        assert isinstance(info["available"], bool), name
        assert info["fallback"].strip(), name
        assert info["purpose"].strip(), name


def test_registry_availability_agrees_with_autodeps():
    """The flags must match autodeps, which knows each package's *import* name.

    autodeps stores (pip name, import name) pairs; diagnostics hardcodes the
    import name it probes. A mismatch here means diagnostics is probing a pip
    distribution name (``scikit-learn``, ``PyMySQL``) that is never importable,
    so the dep would be reported missing forever.
    """
    def norm(pip_name):
        return pip_name.split("[")[0].replace("_", "-").lower()

    import_names = {norm(pip): mod for pip, mod in autodeps.ALL}
    checked = 0
    for name, info in diagnostics.OPTIONAL_DEPENDENCIES.items():
        mod = import_names.get(norm(name))
        if mod is None:
            continue        # e.g. the Qt binding, deliberately never auto-installed
        assert info["available"] == autodeps.installed(mod), f"{name} -> {mod}"
        checked += 1
    assert checked >= 20, f"only {checked} entries cross-checked; registries drifted apart"


def test_qt_flag_is_pinned_where_the_autodeps_cross_check_stops():
    """Qt is the one entry the cross-check above skips, so probe it here.

    autodeps deliberately never lists the GUI binding (you need Qt installed
    before you can launch the GUI at all), and the cross-check just ``continue``s
    past anything autodeps doesn't know. So that silent skip is pinned to exactly
    one name — a new entry missing from autodeps.ALL would otherwise slip through
    unchecked — and that name's flag is measured against an independent probe of
    *both* accepted bindings, which fails if _runtime's detection stops honouring
    PyQt6 or the entry hardcodes an answer.
    """
    from importlib.util import find_spec

    def norm(pip_name):
        return pip_name.split("[")[0].replace("_", "-").lower()

    listed = {norm(pip) for pip, _mod in autodeps.ALL}
    unchecked = [n for n in diagnostics.OPTIONAL_DEPENDENCIES if norm(n) not in listed]
    assert unchecked == ["Qt (PySide6/PyQt6)"], (
        f"invisible to the autodeps cross-check: {unchecked} — only the Qt "
        "binding may be; add new deps to autodeps.ALL, or probe them here")

    entry = diagnostics.OPTIONAL_DEPENDENCIES["Qt (PySide6/PyQt6)"]
    assert entry["available"] == (find_spec("PySide6") is not None
                                  or find_spec("PyQt6") is not None)


# --- rendering --------------------------------------------------------------

def test_renders_available_and_missing_rows(monkeypatch):
    """Present deps get ``[OK ]``; absent ones get ``[-- ]`` plus the fallback."""
    _pin(monkeypatch)
    rows = _rows(diagnostics.format_deps())

    assert rows[0] == "  [OK ] shortdep                available"
    assert rows[1] == ("  [-- ] a-much-longer-dep-name  missing  "
                       "(fallback: pure-Python slow path)")
    # An available dep never advertises the fallback it isn't using.
    assert "a fallback nobody should be shown" not in "\n".join(rows)


def test_status_column_is_aligned(monkeypatch):
    """Names are padded to the widest one, so every status starts in one column."""
    _pin(monkeypatch, pandoc=True, pty=False)
    rows = _rows(diagnostics.format_deps())

    assert len(rows) == 4        # 2 fake deps + pandoc + PTY
    starts = {ln.index("available") if "available" in ln else ln.index("missing")
              for ln in rows}
    assert len(starts) == 1, rows


def test_header_reports_the_running_python(monkeypatch):
    """The first line names the interpreter the report was produced under."""
    _pin(monkeypatch)
    first = diagnostics.format_deps().splitlines()[0]

    assert first.startswith("abax optional dependencies")
    assert f"Python {sys.version_info.major}.{sys.version_info.minor}" in first


def test_lists_every_dependency_once_in_registry_order():
    """The real registry renders one row per entry, in order, then pandoc + PTY."""
    text = diagnostics.format_deps()
    rows = _rows(text)

    assert len(rows) == len(diagnostics.OPTIONAL_DEPENDENCIES) + 2
    positions = []
    for name in diagnostics.OPTIONAL_DEPENDENCIES:
        hits = [i for i, ln in enumerate(rows) if ln[8:].startswith(name)]
        assert len(hits) == 1, name
        positions.append(hits[0])
    assert positions == sorted(positions), "registry order not preserved"
    # The two non-pip probes are appended after the package matrix.
    assert rows[-2][8:].startswith("pandoc")
    assert rows[-1][8:].startswith("PTY (pyte)")


# --- external probes --------------------------------------------------------

@pytest.mark.parametrize("present", [True, False])
def test_pandoc_row_tracks_detection(monkeypatch, present):
    """pandoc is an external binary, not a package; its row follows available()."""
    _pin(monkeypatch, pandoc=present)
    row = _row(diagnostics.format_deps(), "pandoc")

    if present:
        assert row.endswith("available")
        assert "[OK ]" in row
    else:
        assert "[-- ]" in row
        assert row.endswith("missing  (fallback: built-in subset MathML)")


def test_pandoc_probe_failure_reads_as_missing(monkeypatch):
    """A raising probe degrades to 'missing', it does not abort the report."""
    _pin(monkeypatch, pandoc=_boom)
    text = diagnostics.format_deps()

    assert "[-- ] pandoc" in text
    assert "built-in subset MathML" in text
    assert _row(text, "PTY (pyte)")        # later sections still rendered


@pytest.mark.parametrize("present", [True, False])
def test_pty_row_tracks_detection(monkeypatch, present):
    """The true-terminal row follows ptyterm.pty_available() and is annotated."""
    _pin(monkeypatch, pty=present)
    row = _row(diagnostics.format_deps(), "PTY (pyte)")

    assert row.endswith("(true terminal)")
    if present:
        assert "[OK ]" in row
    else:
        assert "[-- ]" in row
        assert "fallback: line-oriented terminal" in row


def test_pty_probe_failure_reads_as_missing(monkeypatch):
    """pyte/pywinpty exploding on probe is reported, not raised."""
    _pin(monkeypatch, pty=_boom)
    row = _row(diagnostics.format_deps(), "PTY (pyte)")

    assert "[-- ]" in row
    assert "line-oriented terminal" in row


def test_autoinstall_row_counts_present_packages(monkeypatch, autoinstall_default):
    """The summary counts how many of autodeps.ALL are importable right now."""
    _pin(monkeypatch)
    monkeypatch.setattr(autodeps, "ALL", [("json-pkg", "json"), ("sys-pkg", "sys"),
                                          ("nope", "abax_missing_pkg_xyz")])
    line = [ln for ln in diagnostics.format_deps().splitlines() if "auto-install:" in ln]

    assert len(line) == 1
    assert "(2/3 optional packages present" in line[0]
    assert "run 'abax deps' to fetch the rest" in line[0]


def test_autoinstall_row_reports_enabled_state(monkeypatch, autoinstall_default):
    """on/off follows autodeps.enabled(), and the env kill-switch outranks it."""
    _pin(monkeypatch)
    autodeps.set_enabled(True)
    assert "auto-install: on  (" in diagnostics.format_deps()

    autodeps.set_enabled(False)
    assert "auto-install: off  (" in diagnostics.format_deps()

    # ABAX_NO_AUTOINSTALL wins even over an explicit set_enabled(True).
    autodeps.set_enabled(True)
    monkeypatch.setenv("ABAX_NO_AUTOINSTALL", "1")
    assert "auto-install: off  (" in diagnostics.format_deps()


def test_autoinstall_row_omitted_when_autodeps_breaks(monkeypatch):
    """A broken autodeps costs the report that one line and nothing else."""
    _pin(monkeypatch)
    monkeypatch.setattr(autodeps, "installed", _boom)
    text = diagnostics.format_deps()

    assert "auto-install:" not in text
    assert len(_rows(text)) == 4           # the dependency matrix survived
    assert "  config: " in text            # so did the trailing path block


# --- paths and purity -------------------------------------------------------

def test_paths_section_follows_runtime_dirs(monkeypatch, tmp_path):
    """The four user-state dirs are read from _runtime at call time.

    conftest redirects them per test; the report must show the redirect rather
    than a path baked in at import (that is what keeps ``--deps`` honest inside
    a sandbox, and the suite out of the developer's profile).
    """
    from abax import _runtime as rt

    _pin(monkeypatch)
    dirs = {}
    for attr in ("CONFIG_DIR", "DATA_DIR", "CACHE_DIR", "LOG_DIR"):
        d = tmp_path / attr.lower()
        d.mkdir()
        monkeypatch.setattr(rt, attr, d)
        dirs[attr] = d

    lines = diagnostics.format_deps().splitlines()
    assert f"  config: {dirs['CONFIG_DIR']}" in lines
    assert f"  data:   {dirs['DATA_DIR']}" in lines
    assert f"  cache:  {dirs['CACHE_DIR']}" in lines
    assert f"  log:    {dirs['LOG_DIR']}" in lines


def test_report_is_repeatable_and_installs_nothing(monkeypatch):
    """``--deps`` is a read-only fast path: no pip, no venv, no accumulation."""
    from abax.core import pandoc as pandoc_mod

    _pin(monkeypatch)
    monkeypatch.setattr(autodeps, "ensure", _boom)
    monkeypatch.setattr(autodeps, "prefetch_all", _boom)
    monkeypatch.setattr(autodeps, "ensure_feature", _boom)
    monkeypatch.setattr(pandoc_mod, "ensure", _boom)

    first = diagnostics.format_deps()
    second = diagnostics.format_deps()

    assert first == second                 # no module-level state grows per call
    assert isinstance(first, str)
    assert not first.endswith("\n")        # app.py print() supplies the newline


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
