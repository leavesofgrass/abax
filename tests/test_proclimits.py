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


# apply_posix_limits() is documented as running "in the current (child)
# process", and it must be tested in one — never in the pytest process itself.
# It lowers RLIMIT_AS / CPU / FSIZE / NPROC, and _set_rlimit lowers the *hard*
# limit alongside the soft one whenever the hard limit was infinite. An
# unprivileged process can never raise a hard limit back, so calling it here is
# not a leak that teardown could undo — it permanently caps the rest of the
# session, at the defaults (4 GB address space, 600 CPU-seconds) or lower.
#
# That went unnoticed for as long as it did because the thin CI install and a
# developer run stay far below those ceilings. With the science stack imported
# the process sits near the 2 GB cap the second test used to set, and the
# remainder of the suite starves: subprocess spawns fail with ENOMEM, shared
# objects fail to map, and the run wedges hard enough that even
# sys.unraisablehook cannot report it. Running the real thing in a child keeps
# the coverage and tests it the way production actually calls it.
_CHILD_PROBE = (
    "import json\n"
    "from abax import proclimits\n"
    "out = {'applied': proclimits.apply_posix_limits()}\n"
    "try:\n"
    "    import resource\n"
    "    soft, _hard = resource.getrlimit(resource.RLIMIT_AS)\n"
    "    out['as_soft'] = soft\n"
    "    out['as_infinite'] = soft == resource.RLIM_INFINITY\n"
    "except ImportError:\n"          # Windows has no `resource`
    "    pass\n"
    "print(json.dumps(out))\n"
)


def _apply_in_child(**env_overrides):
    """Run apply_posix_limits() in a fresh interpreter; return what it saw."""
    import json
    import os
    import subprocess

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([p for p in sys.path if p])
    env.update(env_overrides)
    r = subprocess.run([sys.executable, "-c", _CHILD_PROBE], capture_output=True,
                       text=True, timeout=120, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_apply_posix_limits_returns_bool():
    # Applies real rlimits on POSIX, no-op on Windows.
    assert _apply_in_child()["applied"] is (sys.platform != "win32")


@pytest.mark.skipif(sys.platform != "linux",
                    reason="RLIMIT_AS is only actually enforced on Linux (macOS ignores it)")
def test_posix_limits_actually_lower_address_space():
    out = _apply_in_child(ABAX_WORKER_MEM_MB="2048")
    assert out["as_infinite"] is False
    assert out["as_soft"] <= 2048 * 1024 * 1024


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
