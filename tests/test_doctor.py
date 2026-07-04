"""``abax doctor`` — the aggregated health report must be crash-proof.

Every test here asserts two things at once: the report *emits* the section it
claims to, and the probe *survives* a hostile environment (missing dirs, a
corrupt ``settings.json``, a confinement selector that raises) without ever
raising — degrading to a non-zero exit code instead.

Pure stdlib + abax core; no optional deps, no Qt.
"""

from __future__ import annotations

import io

import pytest

from abax import doctor


def _run(monkeypatch, tmp_path, *, skip_mkdir=(), **overrides):
    """Run ``run_doctor`` with the runtime dirs redirected under *tmp_path*.

    By default every runtime dir points at a freshly-created, writable temp
    directory, so a bare call reflects a healthy environment. Individual dirs
    can be overridden (e.g. to a missing path) via keyword arguments naming the
    ``_runtime`` attribute; pass their attribute names in *skip_mkdir* to leave
    them absent on disk.
    """
    from abax import _runtime as rt

    defaults = {
        "CONFIG_DIR": tmp_path / "config",
        "DATA_DIR": tmp_path / "data",
        "CACHE_DIR": tmp_path / "cache",
        "LOG_DIR": tmp_path / "log",
        "EXCHANGE_DIR": tmp_path / "exchange",
    }
    defaults.update(overrides)
    for attr, path in defaults.items():
        # Create the dir unless the test explicitly wants it absent.
        if attr not in skip_mkdir:
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        monkeypatch.setattr(rt, attr, path, raising=False)

    buf = io.StringIO()
    code = doctor.run_doctor(stream=buf)
    return code, buf.getvalue()


def test_returns_zero_and_emits_key_sections(monkeypatch, tmp_path):
    """A healthy environment: exit 0 and every headline section present."""
    code, out = _run(monkeypatch, tmp_path)
    assert code == 0, out
    # The key sections the task requires.
    assert "Python & platform" in out
    assert "Optional dependencies" in out
    assert "Code isolation & sandbox" in out
    assert "Runtime directories" in out
    assert "Settings" in out
    # Concrete facts within them.
    assert "python" in out
    assert "level" in out            # isolation level line
    assert "confinement" in out      # sandbox confinement line
    assert "config" in out           # a runtime dir label
    assert "writable" in out         # the temp dirs probe as writable
    assert "Summary: OK" in out


def test_dependency_matrix_reuses_diagnostics(monkeypatch, tmp_path):
    """Every optional dep in the diagnostics registry appears in the report."""
    from abax import diagnostics

    _code, out = _run(monkeypatch, tmp_path)
    for name in diagnostics.OPTIONAL_DEPENDENCIES:
        assert name in out


def test_default_stream_is_stdout(monkeypatch, tmp_path, capsys):
    """``stream=None`` writes to stdout and still returns an int exit code."""
    from abax import _runtime as rt

    for attr in ("CONFIG_DIR", "DATA_DIR", "CACHE_DIR", "LOG_DIR", "EXCHANGE_DIR"):
        d = tmp_path / attr.lower()
        d.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(rt, attr, d, raising=False)

    code = doctor.run_doctor()  # no stream -> sys.stdout
    captured = capsys.readouterr()
    assert isinstance(code, int)
    assert "abax doctor" in captured.out


def test_missing_directory_is_reported_not_crashed(monkeypatch, tmp_path):
    """A missing runtime dir degrades to a non-zero exit, never a traceback."""
    missing = tmp_path / "does-not-exist"
    assert not missing.exists()

    code, out = _run(monkeypatch, tmp_path, CACHE_DIR=missing, skip_mkdir=("CACHE_DIR",))
    assert code != 0
    assert "MISSING" in out
    # The rest of the report still rendered.
    assert "Summary: problems detected" in out
    assert "Python & platform" in out


def test_broken_settings_json_is_reported_not_crashed(monkeypatch, tmp_path):
    """A corrupt settings.json is flagged (non-zero) without raising."""
    config = tmp_path / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "settings.json").write_text("{ this is not valid json ", encoding="utf-8")

    code, out = _run(monkeypatch, tmp_path, CONFIG_DIR=config)
    assert code != 0
    assert "does NOT parse" in out


def test_absent_settings_is_ok(monkeypatch, tmp_path):
    """No settings.json is fine (defaults get written on first run) -> exit 0."""
    code, out = _run(monkeypatch, tmp_path)  # temp config has no settings.json
    assert code == 0
    assert "absent" in out


def test_survives_broken_confinement_selector(monkeypatch, tmp_path):
    """If sandbox.select_confinement raises, doctor still finishes the report."""
    from abax import sandbox

    def _boom():
        raise RuntimeError("confinement subsystem exploded")

    monkeypatch.setattr(sandbox, "select_confinement", _boom)

    code, out = _run(monkeypatch, tmp_path)
    # A broken selector is not, by itself, a doctor failure (deps/dirs decide
    # the exit code), but the section must render and must not crash.
    assert isinstance(code, int)
    assert "Code isolation & sandbox" in out
    assert "selection failed" in out
    # Later sections still ran.
    assert "Runtime directories" in out


def test_survives_broken_dependency_matrix(monkeypatch, tmp_path):
    """A blown-up diagnostics import is caught and the report continues."""
    from abax import diagnostics

    # Replace the mapping with an object whose iteration raises.
    class _Hostile:
        def __iter__(self):
            raise RuntimeError("registry unavailable")

    monkeypatch.setattr(diagnostics, "OPTIONAL_DEPENDENCIES", _Hostile())

    code, out = _run(monkeypatch, tmp_path)
    assert isinstance(code, int)
    assert "could not read dependency matrix" in out
    # Everything after the dependency section still rendered.
    assert "Runtime directories" in out
    assert "Settings" in out


def test_strict_without_confinement_warns(monkeypatch, tmp_path):
    """Strict isolation selected + no available confinement -> a WARNING line."""
    from abax import sandbox

    monkeypatch.setattr(doctor, "_read_isolation_level", lambda: "strict")

    class _Unavailable:
        name = "none"

        def available(self):
            return False

        def describe(self):
            return "no OS sandbox available on this platform"

    monkeypatch.setattr(sandbox, "select_confinement", lambda: _Unavailable())

    code, out = _run(monkeypatch, tmp_path)
    assert isinstance(code, int)
    assert "WARNING" in out
    assert "strict" in out


def test_writable_probe_classifies_states(tmp_path):
    """The low-level dir probe distinguishes writable / missing / not-a-dir."""
    good = tmp_path / "good"
    good.mkdir()
    assert doctor._probe_writable(good) == "writable"

    assert "MISSING" in doctor._probe_writable(tmp_path / "nope")

    a_file = tmp_path / "afile"
    a_file.write_text("x", encoding="utf-8")
    assert "NOT A DIRECTORY" in doctor._probe_writable(a_file)


def test_run_doctor_never_raises_even_fully_broken(monkeypatch, tmp_path):
    """Belt-and-suspenders: even if _runtime dirs are nonsense, no exception."""
    from abax import _runtime as rt

    # Point every dir at a path under a file (so mkdir + stat both misbehave).
    a_file = tmp_path / "blocker"
    a_file.write_text("x", encoding="utf-8")
    bogus = a_file / "under-a-file"
    for attr in ("CONFIG_DIR", "DATA_DIR", "CACHE_DIR", "LOG_DIR", "EXCHANGE_DIR"):
        monkeypatch.setattr(rt, attr, bogus, raising=False)

    buf = io.StringIO()
    code = doctor.run_doctor(stream=buf)  # must not raise
    assert isinstance(code, int)
    assert code != 0
    assert "Summary" in buf.getvalue()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
