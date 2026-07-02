"""OS resource limits for the code-execution worker (sandbox Phase 2)."""

from __future__ import annotations

import sys

import pytest

from abax import proclimits


def test_limits_from_env_defaults(monkeypatch):
    for k in ("ABAX_WORKER_MEM_MB", "ABAX_WORKER_CPU_S", "ABAX_WORKER_FSIZE_MB",
              "ABAX_WORKER_PROCS", "ABAX_WORKER_NPROC"):
        monkeypatch.delenv(k, raising=False)
    lim = proclimits.limits_from_env()
    assert lim["mem_mb"] == proclimits.DEFAULT_MEM_MB
    assert lim["cpu_s"] == proclimits.DEFAULT_CPU_S
    assert lim["procs"] == proclimits.DEFAULT_PROCS


def test_limits_from_env_override_and_bad_value(monkeypatch):
    monkeypatch.setenv("ABAX_WORKER_MEM_MB", "512")
    monkeypatch.setenv("ABAX_WORKER_CPU_S", "not-a-number")   # falls back to default
    lim = proclimits.limits_from_env()
    assert lim["mem_mb"] == 512
    assert lim["cpu_s"] == proclimits.DEFAULT_CPU_S


def test_apply_posix_limits_returns_bool():
    # Always safe to call: applies real rlimits on POSIX, no-op on Windows.
    result = proclimits.apply_posix_limits()
    assert result is (sys.platform != "win32")


@pytest.mark.skipif(sys.platform != "linux",
                    reason="RLIMIT_AS is only actually enforced on Linux (macOS ignores it)")
def test_posix_limits_actually_lower_address_space(monkeypatch):
    import resource

    monkeypatch.setenv("ABAX_WORKER_MEM_MB", "2048")
    proclimits.apply_posix_limits()
    soft, _hard = resource.getrlimit(resource.RLIMIT_AS)
    assert soft != resource.RLIM_INFINITY
    assert soft <= 2048 * 1024 * 1024


@pytest.mark.skipif(sys.platform != "win32", reason="Job Objects are Windows-only")
def test_windows_job_assigns_and_closes():
    import subprocess

    # A short-lived real process to assign to a job, then tear the job down.
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        job = proclimits.assign_windows_job(int(proc._handle))  # noqa: SLF001
        assert job is not None
        proclimits.close_windows_job(job)   # KILL_ON_JOB_CLOSE terminates the worker
        assert proc.wait(timeout=5) is not None
    finally:
        if proc.poll() is None:
            proc.kill()


def test_windows_stubs_are_noops_on_posix():
    if sys.platform == "win32":
        pytest.skip("POSIX-only check")
    # On POSIX the Job Object API is a harmless no-op.
    assert proclimits.assign_windows_job(0) is None
    proclimits.close_windows_job(None)   # does not raise
