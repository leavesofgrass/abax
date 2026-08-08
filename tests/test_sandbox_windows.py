"""Tests for the Windows AppContainer confinement (:mod:`abax.sandbox_windows`).

Windows is abax's primary desktop platform and the only one whose strategy needs
a bespoke launcher (``custom_spawn`` -> ``CreateProcessW`` with a
security-capabilities proc-thread attribute) rather than an argv wrapper, so
this file covers three tiers:

* **Interface** — the frozen :class:`abax.sandbox.Confinement` surface, the
  argv/env contract, and the fail-closed capability probe.
* **ACL bookkeeping** — the ``icacls`` grants really are *additive* and really
  are *exactly* reverted, and every failure mode (missing path, missing tool)
  degrades to "not granted" instead of raising.
* **End-to-end** — one real AppContainer-confined child: it may write its
  scratch dir, may not write a sibling directory, and may not open an outbound
  socket. Every assertion in that tier prints the child's exit code, stdout and
  stderr, because an AppContainer launch that dies at startup is otherwise
  undiagnosable from a CI log (see ``_diag``). These five tests run
  **everywhere** — developer machines, self-hosted runners, and GitHub-hosted
  ones, where they are covered by ci.yml's ``check`` matrix on every push. They
  were gated off on hosted runners for a long time on the belief that such a
  runner could not launch a confined child at all; the probe workflow measured it
  and they pass there in about four seconds. The ``sandbox_e2e`` marker they
  carry is for selection (``-m sandbox_e2e``) and skips nothing; the one test
  that really is gated on hosted runners is
  ``test_sandbox.py::test_windows_strict_worker_runs_and_confines``, which goes
  through ConsoleBridge and carries ``console_bridge_e2e`` as well.

The whole module is Windows-only; the argv/env/describe surface that *does* run
cross-platform is already covered by ``test_sandbox.py``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading

import pytest

from abax import sandbox as sb
from abax import sandbox_windows as sw

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows AppContainer only"
)

# CREATE_NO_WINDOW — what the bridge passes so a confined child never flashes a
# console window (abax.gui.console.console_bridge._spawn).
_CREATE_NO_WINDOW = 0x08000000


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _ace_lines(path: str) -> "set[str]":
    """The ACL of *path* as a set of ACE strings.

    Parsed out of ``icacls`` rather than a name lookup so the comparison is
    locale-independent: we only ever compare one snapshot against another.
    """
    # icacls writes in the console OEM codepage, not UTF-8 — and ci.yml sets
    # PYTHONUTF8=1 workflow-wide, which would make a bare text=True decode
    # strict UTF-8 and raise UnicodeDecodeError on the first non-ASCII byte in a
    # principal name. Decode as OEM, and never let an odd byte fail the run:
    # every comparison here is snapshot-against-snapshot, so a replaced
    # character is stable on both sides.
    r = subprocess.run(["icacls", path], capture_output=True, text=True,
                       encoding="oem", errors="replace", timeout=60)
    assert r.returncode == 0, f"icacls {path} failed: {r.stdout}{r.stderr}"
    aces = set()
    for raw in r.stdout.splitlines():
        line = raw.strip()
        if line.startswith(path):          # first line is "<path> <ACE>"
            line = line[len(path):].strip()
        if line.endswith(")") and ":" in line:   # drops the "N files" summary
            aces.add(line)
    return aces


def _explicit_aces(path: str) -> "set[str]":
    """The *explicit* ACEs of *path* — inherited ones (icacls flag ``(I)``) removed.

    Grant/revoke only ever add and remove explicit ACEs, so this is the set the
    sandbox actually owns, and the only one a before/after comparison may
    assume is stable.

    The full ACL is not stable: writing the first explicit ACE onto a directory
    that had none makes Windows materialise the inherited ACEs into the DACL, so
    ``_ace_lines`` legitimately grows by entries nobody added. That never shows
    up on a developer box whose temp directory already carries explicit ACEs,
    but it does on a hosted CI runner — where it read as "the grant added four
    ACEs, not one" and failed every Windows cell. Filtering to explicit ACEs
    tests the promise more precisely, not less: an inherited ACE appearing in
    the listing is a representation change, never a grant.
    """
    return {a for a in _ace_lines(path) if "(I)" not in a.split(":", 1)[-1]}


class _FakeProc:
    """A stand-in for the ``_ACProcess`` the real launcher returns."""


class _FakeCtypes:
    """Stands in for :mod:`abax._winsandbox_ctypes`.

    Lets the launcher's wiring (flags, SID, profile name, cleanup state) be
    asserted without creating a real AppContainer or a real process.
    """

    def __init__(self, *, sid="SID-SENTINEL", spawn_error=None,
                 profile_error=None, delete_error=None):
        self.sid = sid
        self.spawn_error = spawn_error
        self.profile_error = profile_error
        self.delete_error = delete_error
        self.created: list[str] = []
        self.deleted: list[str] = []
        self.spawns: list[tuple] = []
        self.proc = _FakeProc()

    def create_app_container_profile(self, name):
        self.created.append(name)
        if self.profile_error is not None:
            raise self.profile_error
        return self.sid

    def delete_app_container_profile(self, name):
        self.deleted.append(name)
        if self.delete_error is not None:
            raise self.delete_error

    def create_process_appcontainer(self, argv, env, sid, creationflags):
        self.spawns.append((list(argv), dict(env), sid, creationflags))
        if self.spawn_error is not None:
            raise self.spawn_error
        return self.proc


@pytest.fixture
def fake_ctypes(monkeypatch):
    """Install a :class:`_FakeCtypes` in place of the lazily-imported plumbing.

    ``custom_spawn`` does ``from . import _winsandbox_ctypes as C``; setting the
    attribute on the ``abax`` package short-circuits the submodule import, so no
    Win32 call is ever made.
    """
    import abax

    def _install(**kwargs):
        fake = _FakeCtypes(**kwargs)
        monkeypatch.setattr(abax, "_winsandbox_ctypes", fake, raising=False)
        return fake

    return _install


@pytest.fixture
def no_real_acls(monkeypatch):
    """Replace the icacls layer with recorders.

    ``custom_spawn`` otherwise grants ALL APPLICATION PACKAGES read+execute on
    the whole interpreter prefix, which is both slow and a real machine-wide
    side effect — unwanted in the tests that are only about launcher wiring.
    """
    calls = {"granted": [], "revoked": []}

    def _grant(scratch):
        paths = [scratch, "C:\\fake\\interpreter"]
        calls["granted"].append(scratch)
        return paths

    monkeypatch.setattr(sw, "_grant_container_access", _grant)
    monkeypatch.setattr(sw, "_revoke_container_access",
                        lambda granted: calls["revoked"].append(list(granted)))
    return calls


# --------------------------------------------------------------------------- #
# the strategy interface
# --------------------------------------------------------------------------- #


def test_confinement_is_an_available_appcontainer_strategy():
    strat = sw.confinement()
    assert strat is not None
    # Confinement is a runtime_checkable Protocol, so this only asserts that the
    # protocol's members (name, available, wrap_argv, child_env, apply_in_child,
    # describe) are all *present* — never their signatures or return types. It
    # catches a rename or a dropped method; the behaviour of each one is pinned
    # by the dedicated tests below.
    assert isinstance(strat, sb.Confinement)
    assert strat.name == "appcontainer"
    # Windows 8 / Server 2012 and later expose the primitives; anything abax
    # supports has them, so the probe must say yes here.
    assert strat.available() is True


def test_select_confinement_picks_the_appcontainer_on_windows():
    # The platform seam must resolve to this strategy (not the null sentinel),
    # otherwise strict mode silently refuses to run on the primary platform.
    strat = sb.select_confinement()
    assert isinstance(strat, sw.WindowsAppContainer)
    assert strat.available() is True


def test_describe_names_the_mechanism_and_the_guarantees():
    text = sw.confinement().describe()
    assert "AppContainer" in text
    lowered = text.lower()
    assert "no network" in lowered
    assert "scratch" in lowered
    assert "read-only" in lowered


def test_available_is_false_when_the_appcontainer_apis_are_absent(monkeypatch):
    """Fail closed on a Windows too old for AppContainers.

    ``available()`` is the gate the bridge uses to decide whether strict mode can
    be honored at all; if the userenv entry points are missing it must report
    False rather than blow up or optimistically say yes.
    """
    import ctypes

    class _NoAppContainer:
        # kernel32's attributes exist, userenv's do not.
        def __getattr__(self, name):
            if name in ("InitializeProcThreadAttributeList",
                        "UpdateProcThreadAttribute"):
                return object()
            raise AttributeError(name)

    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: _NoAppContainer())
    assert sw.WindowsAppContainer().available() is False


def test_available_is_false_when_a_dll_cannot_be_loaded(monkeypatch):
    import ctypes

    def _boom(*a, **k):
        raise OSError("cannot load")

    monkeypatch.setattr(ctypes, "WinDLL", _boom)
    assert sw.WindowsAppContainer().available() is False


def test_wrap_argv_is_the_identity():
    # AppContainer selection happens at CreateProcess time, not by prepending a
    # launcher: if wrap_argv ever grew a prefix the bridge would run the wrong
    # program (it calls custom_spawn instead).
    argv = [sys.executable, "-c", "from abax.console_worker import main; main()"]
    out = sw.confinement().wrap_argv(argv, "C:\\scratch")
    assert out == argv


def test_child_env_points_both_temp_vars_at_scratch():
    strat = sw.confinement()
    src = {"PATH": "C:\\Windows", "TEMP": "C:\\Users\\x\\Temp", "TMP": "C:\\old"}
    out = strat.child_env(src, "C:\\scratch")
    # Both spellings must move: stdlib tempfile consults TMP, TEMP and TMPDIR in
    # that order, and the scratch dir is the only writable place in the jail.
    assert out["TEMP"] == "C:\\scratch"
    assert out["TMP"] == "C:\\scratch"
    assert out["PATH"] == "C:\\Windows"    # everything else survives
    assert src["TEMP"] == "C:\\Users\\x\\Temp"   # caller's mapping not mutated


def test_apply_in_child_is_a_noop_even_for_a_bogus_scratch():
    # Confinement is established by the parent, so the in-child hook has nothing
    # to do and must never raise (a raise here would fail the worker closed for
    # no reason).
    assert sw.confinement().apply_in_child("Z:\\does\\not\\exist") is None


# --------------------------------------------------------------------------- #
# profile naming / the dirs the confined interpreter needs
# --------------------------------------------------------------------------- #


def test_profile_name_is_stable_per_process_and_legal():
    name = sw._profile_name()
    assert name == sw._profile_name()          # stable within a process
    assert name.endswith(str(os.getpid()))     # unique across live abax runs
    # CreateAppContainerProfile rejects names over 64 chars or containing path
    # separators / wildcards.
    assert 0 < len(name) <= 64
    assert not (set(name) & set("\\/:*?\"<>|"))


def test_needed_read_dirs_are_absolute_existing_directories():
    dirs = sw._needed_read_dirs()
    assert dirs, "the confined interpreter must be granted something to read"
    for d in dirs:
        assert os.path.isabs(d), d
        assert os.path.isdir(d), d
        assert d == os.path.abspath(d), d


def test_needed_read_dirs_covers_the_interpreter_prefix():
    # Without read+execute on the base prefix the confined Python cannot even
    # start, so some granted dir must be the prefix or an ancestor of it.
    dirs = sw._needed_read_dirs()
    # normcase both sides: Windows paths are case-insensitive, and sys.prefix
    # and dirname(sys.executable) need not agree on casing on every machine.
    prefix = os.path.normcase(os.path.abspath(sys.base_prefix))
    assert any(prefix == os.path.normcase(d)
               or prefix.startswith(os.path.normcase(d) + os.sep)
               for d in dirs), dirs


def test_needed_read_dirs_drops_nested_blank_and_missing_entries(tmp_path):
    """Only the minimal covering set is handed to icacls.

    A child of an already-granted directory is redundant (the ACE is
    inheritable), and blank / missing / non-directory sys.path entries are not
    grantable at all — each extra path is another icacls round trip on spawn.

    ``sys.path`` has to be restored before pytest formats anything, so the
    patches are applied through a private ``MonkeyPatch.context()`` that unwinds
    at the end of the ``with`` block. The ``monkeypatch`` *fixture* would be the
    wrong tool: it is shared with conftest's autouse fixtures, so undoing it
    early would also restore the real ``abax._runtime`` user dirs and un-silence
    TTS for the rest of this test.
    """
    parent = tmp_path / "parent"
    (parent / "nested" / "deeper").mkdir(parents=True)
    other = tmp_path / "other"
    other.mkdir()
    a_file = tmp_path / "a_file.zip"
    a_file.write_text("not a dir", encoding="utf-8")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sys, "base_prefix", str(parent))
        mp.setattr(sys, "prefix", str(parent))
        mp.setattr(sys, "executable", str(parent / "python.exe"))
        mp.setattr(sys, "path", [
            "",                                   # the "-c" entry
            str(parent / "nested"),               # covered by parent
            str(parent / "nested" / "deeper"),    # covered twice over
            str(other),                           # genuinely disjoint -> kept
            str(tmp_path / "missing"),            # never existed
            str(a_file),                          # a zip on sys.path, not a dir
        ])
        dirs = sw._needed_read_dirs()

    assert sorted(dirs) == sorted([str(parent), str(other)])


# --------------------------------------------------------------------------- #
# the icacls layer
# --------------------------------------------------------------------------- #


def test_icacls_reports_failure_for_a_missing_path(tmp_path):
    missing = str(tmp_path / "not-there")
    assert sw._icacls(missing, "/grant", f"{sw.ALL_APP_PACKAGES}:(OI)(CI)(M)") is False


def test_icacls_reports_failure_for_a_malformed_ace(tmp_path):
    # A bad SID/permission string must be reported, not silently treated as a
    # successful grant (that would mean spawning into a container with no access).
    assert sw._icacls(str(tmp_path), "/grant", "*S-1-15-2-1:(NOSUCHPERM)") is False


@pytest.mark.parametrize("exc", [
    FileNotFoundError("icacls not on PATH"),
    subprocess.TimeoutExpired("icacls", 60),
])
def test_icacls_never_raises_when_the_tool_misbehaves(monkeypatch, tmp_path, exc):
    def _boom(*a, **k):
        raise exc

    monkeypatch.setattr(sw.subprocess, "run", _boom)
    assert sw._icacls(str(tmp_path), "/grant", "whatever") is False


def test_grant_is_additive_and_revoke_reverts_it_exactly(monkeypatch, tmp_path):
    """The documented promise: the ACEs we add never weaken anyone's access and
    the machine is left byte-identical afterwards."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    readable = tmp_path / "importable"
    readable.mkdir()
    # Keep the real interpreter prefix out of it — this test is about the ACEs.
    monkeypatch.setattr(sw, "_needed_read_dirs", lambda: [str(readable)])

    before_scratch = _explicit_aces(str(scratch))
    before_read = _explicit_aces(str(readable))
    # The full ACL too: nothing that already granted access may disappear.
    all_before_scratch = _ace_lines(str(scratch))
    all_before_read = _ace_lines(str(readable))

    granted = sw._grant_container_access(str(scratch))
    try:
        assert granted == [str(scratch), str(readable)]

        added_scratch = _explicit_aces(str(scratch)) - before_scratch
        added_read = _explicit_aces(str(readable)) - before_read
        # Exactly one new ACE per path, and nothing pre-existing was disturbed.
        assert len(added_scratch) == 1, added_scratch
        assert len(added_read) == 1, added_read
        assert all_before_scratch <= _ace_lines(str(scratch))
        assert all_before_read <= _ace_lines(str(readable))
        # Scratch is the one writable place; imports are read+execute only.
        assert added_scratch.pop().endswith(":(OI)(CI)(M)")
        assert added_read.pop().endswith(":(OI)(CI)(RX)")
    finally:
        sw._revoke_container_access(granted)

    # Our ACEs are gone...
    assert _explicit_aces(str(scratch)) == before_scratch
    assert _explicit_aces(str(readable)) == before_read
    # ...and we destroyed nothing on the way out.
    assert all_before_scratch <= _ace_lines(str(scratch))
    assert all_before_read <= _ace_lines(str(readable))


def test_grant_omits_paths_icacls_refused(monkeypatch, tmp_path):
    """A path that could not be granted must not appear in the revoke list.

    Otherwise teardown would run ``icacls /remove`` against a path we never
    touched — and, worse, the caller would believe the container can reach it.
    """
    readable = tmp_path / "importable"
    readable.mkdir()
    monkeypatch.setattr(sw, "_needed_read_dirs",
                        lambda: [str(readable), str(tmp_path / "vanished")])

    granted = sw._grant_container_access(str(tmp_path / "no-such-scratch"))
    try:
        assert granted == [str(readable)]
    finally:
        sw._revoke_container_access(granted)


def test_revoke_tolerates_paths_that_disappeared(tmp_path):
    # A scratch dir deleted before teardown (or a grant that never landed) must
    # not turn cleanup into an exception — cleanup runs from a finally block.
    sw._revoke_container_access([str(tmp_path / "gone"), str(tmp_path)])


# --------------------------------------------------------------------------- #
# custom_spawn — the bespoke launcher's wiring
# --------------------------------------------------------------------------- #


def test_custom_spawn_passes_flags_sid_and_argv_through(fake_ctypes, no_real_acls):
    fake = fake_ctypes()
    argv = [sys.executable, "-c", "pass"]
    env = {"PATH": "C:\\Windows", "ABAX_SANDBOX_STRICT": "1"}

    proc = sw.confinement().custom_spawn(argv, env, "C:\\scratch", _CREATE_NO_WINDOW)

    assert proc is fake.proc
    assert fake.created == [sw._profile_name()]
    (got_argv, got_env, got_sid, flags), = fake.spawns
    assert got_argv == argv
    assert got_env == env
    assert got_sid == "SID-SENTINEL"          # the SID the profile call returned
    # The caller's flags survive, and the two the AppContainer launch requires
    # are added: an extended STARTUPINFO (carrying the security capabilities)
    # over a unicode environment block.
    assert flags & _CREATE_NO_WINDOW
    assert flags & 0x00080000                 # EXTENDED_STARTUPINFO_PRESENT
    assert flags & 0x00000400                 # CREATE_UNICODE_ENVIRONMENT
    assert no_real_acls["revoked"] == []      # nothing torn down on success


def test_custom_spawn_records_what_cleanup_must_undo(fake_ctypes, no_real_acls):
    # The bridge cleans up through cleanup_process(proc); the launcher is the
    # only place that can tell it which grants and which profile to revert.
    fake = fake_ctypes()
    proc = sw.confinement().custom_spawn(["x.exe"], {}, "C:\\scratch", 0)
    granted, profile = proc._sandbox_cleanup
    assert granted == ["C:\\scratch", "C:\\fake\\interpreter"]
    assert profile == sw._profile_name()
    assert proc._sandbox_ctypes is fake


def test_custom_spawn_fails_closed_when_createprocess_fails(fake_ctypes, no_real_acls):
    """A launch failure must leave nothing behind.

    The grants and the container profile are machine-wide state; leaking them on
    every failed spawn would slowly widen ALL APPLICATION PACKAGES' access.
    """
    fake = fake_ctypes(spawn_error=OSError("CreateProcessW failed: 5"))

    with pytest.raises(OSError, match="CreateProcessW"):
        sw.confinement().custom_spawn(["x.exe"], {}, "C:\\scratch", 0)

    assert no_real_acls["revoked"] == [["C:\\scratch", "C:\\fake\\interpreter"]]
    assert fake.deleted == [sw._profile_name()]


def test_custom_spawn_grants_nothing_when_the_profile_cannot_be_created(
        fake_ctypes, no_real_acls):
    # Ordering matters: the profile is created first, so a failure there must not
    # have opened up any ACLs at all.
    fake = fake_ctypes(profile_error=OSError("AppContainer profile failed"))

    with pytest.raises(OSError, match="AppContainer profile"):
        sw.confinement().custom_spawn(["x.exe"], {}, "C:\\scratch", 0)

    assert no_real_acls["granted"] == []
    assert no_real_acls["revoked"] == []
    assert fake.deleted == []
    assert fake.spawns == []


# --------------------------------------------------------------------------- #
# cleanup_process
# --------------------------------------------------------------------------- #


def test_cleanup_process_ignores_a_process_it_never_confined():
    # The bridge calls cleanup_process on whatever worker just died, including
    # an ordinary non-strict Popen. That must be a no-op, not an AttributeError.
    plain = _FakeProc()
    assert sw.cleanup_process(plain) is None
    assert not hasattr(plain, "_sandbox_cleanup")


def test_cleanup_process_really_removes_the_acl_grant(monkeypatch, tmp_path):
    """End-to-end for the teardown half: a real grant, reverted through the same
    entry point the bridge uses."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(sw, "_needed_read_dirs", lambda: [])

    before = _explicit_aces(str(scratch))
    all_before = _ace_lines(str(scratch))
    granted = sw._grant_container_access(str(scratch))
    assert granted == [str(scratch)]
    assert _explicit_aces(str(scratch)) != before

    fake = _FakeCtypes()
    proc = _FakeProc()
    proc._sandbox_cleanup = (granted, "abax-sandbox-test")
    proc._sandbox_ctypes = fake

    sw.cleanup_process(proc)

    assert _explicit_aces(str(scratch)) == before
    assert all_before <= _ace_lines(str(scratch))
    assert fake.deleted == ["abax-sandbox-test"]
    assert proc._sandbox_cleanup is None


def test_cleanup_process_is_idempotent(tmp_path):
    # close() and the crashed-worker path can both reach cleanup for the same
    # process; the second pass must not re-delete the (possibly recycled) profile.
    fake = _FakeCtypes()
    proc = _FakeProc()
    proc._sandbox_cleanup = ([str(tmp_path)], "abax-sandbox-test")
    proc._sandbox_ctypes = fake

    sw.cleanup_process(proc)
    sw.cleanup_process(proc)

    assert fake.deleted == ["abax-sandbox-test"]


def test_cleanup_process_reverts_acls_even_without_the_ctypes_module(monkeypatch, tmp_path):
    # If the lazy plumbing import never happened there is no profile to delete,
    # but the ACL grants still exist and must still come back off.
    revoked = []
    monkeypatch.setattr(sw, "_revoke_container_access", revoked.append)
    proc = _FakeProc()
    proc._sandbox_cleanup = (["C:\\scratch"], "abax-sandbox-test")

    sw.cleanup_process(proc)

    assert revoked == [["C:\\scratch"]]
    assert proc._sandbox_cleanup is None


def test_cleanup_process_survives_a_failing_profile_delete(monkeypatch):
    # Deleting a profile can fail (still in use by a zombie child). The ACLs are
    # the security-relevant half, so cleanup must complete regardless.
    revoked = []
    monkeypatch.setattr(sw, "_revoke_container_access", revoked.append)
    fake = _FakeCtypes(delete_error=OSError("profile in use"))
    proc = _FakeProc()
    proc._sandbox_cleanup = (["C:\\scratch"], "abax-sandbox-test")
    proc._sandbox_ctypes = fake

    sw.cleanup_process(proc)

    assert revoked == [["C:\\scratch"]]
    assert proc._sandbox_cleanup is None


# --------------------------------------------------------------------------- #
# lazy import
# --------------------------------------------------------------------------- #


def test_the_ctypes_plumbing_is_not_imported_until_a_worker_spawns(tmp_path):
    """``_winsandbox_ctypes`` stays unloaded until a strict worker is launched.

    The settings UI and ``select_confinement`` touch this strategy on every
    launch; dragging in the ctypes/_winapi layer (and its DLL loads) there would
    make an unrelated abax start pay for a sandbox it never uses.
    """
    prog = (
        "import sys\n"
        "from abax import sandbox_windows as sw\n"
        "s = sw.confinement()\n"
        "s.available(); s.describe(); s.wrap_argv(['x'], 'c'); s.child_env({}, 'c')\n"
        "s.apply_in_child('c')\n"
        "print('LOADED' if 'abax._winsandbox_ctypes' in sys.modules else 'LAZY')\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([p for p in sys.path if p])
    # conftest's abax_user_dirs redirect patches abax._runtime in *this*
    # process; a child gets a fresh interpreter and would create the real
    # %APPDATA%/%LOCALAPPDATA% abax dirs on import. Point them at tmp_path so
    # the suite keeps its promise to stay out of the user's profile.
    env["APPDATA"] = str(tmp_path / "roaming")
    env["LOCALAPPDATA"] = str(tmp_path / "local")
    r = subprocess.run([sys.executable, "-c", prog], capture_output=True,
                       text=True, timeout=120, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "LAZY" in r.stdout, r.stdout + r.stderr


# --------------------------------------------------------------------------- #
# end-to-end: a real AppContainer-confined child
# --------------------------------------------------------------------------- #

# What the confined child reports back. Each probe prints a stable token so a
# partial run is still readable in the failure diagnostics, and every probe runs
# even if an earlier one reports an escape.
_PROBE = r"""
import errno, os, socket, sys

scratch = os.environ["ABAX_PROBE_SCRATCH"]
outside = os.environ["ABAX_PROBE_OUTSIDE"]
try:
    with open(os.path.join(scratch, "inside.txt"), "w") as fh:
        fh.write("ok")
    print("SCRATCH_WRITE_OK")
except OSError as exc:
    print("SCRATCH_WRITE_DENIED", type(exc).__name__)
try:
    with open(outside, "w") as fh:
        fh.write("escape")
    print("OUTSIDE_WRITE_OK")
except OSError as exc:
    print("OUTSIDE_WRITE_DENIED", type(exc).__name__)
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
except OSError as exc:
    print("NET_SOCKET_DENIED", type(exc).__name__)
else:
    s.settimeout(0.5)
    try:
        s.connect(("192.0.2.1", 80))   # RFC 5737 TEST-NET, never answers
        print("NET_REACHED")
    except OSError as exc:
        name = errno.errorcode.get(exc.errno, exc.errno)
        print("NET_DENIED" if exc.errno in (errno.EPERM, errno.EACCES)
              else "NET_REACHED", name)
    finally:
        s.close()
# The production fail-closed gate, run exactly as the worker runs it. It probes
# the home dir / TMP / cwd, which the checks above deliberately do not.
try:
    from abax import sandbox
    sandbox.selftest(scratch)
    print("SELFTEST_OK")
except Exception as exc:
    print("SELFTEST_FAILED", type(exc).__name__, exc)
print("PROBE_DONE")
sys.stdout.flush()
"""


def _diag(rc, out, err) -> str:
    """Everything needed to debug an AppContainer launch from a CI log alone.

    The failure mode worth naming is a confined child that exits at startup: then
    ``out`` is empty and ``err``/``rc`` are the only evidence, so they go into
    every assertion message rather than being swallowed. That is what the
    ConsoleBridge path does on a hosted runner; these five, launching through
    ``custom_spawn``, do not — which is only knowable because of this function.
    """
    return (f"\n  exit code : {rc!r}"
            f"\n  stdout    : {out!r}"
            f"\n  stderr    : {err!r}"
            f"\n  (an empty stdout with a non-zero exit code means the confined "
            f"child died before running the probe)")


def _spawn_confined(strat, code, scratch, extra_env, timeout=120):
    """Run *code* in an AppContainer via the real launcher; return (rc, out, err).

    Reads both pipes on threads so a chatty child cannot deadlock the test, and
    always tears the confinement down (profile + ACL grants) on the way out.
    """
    env = strat.child_env(dict(os.environ), scratch)
    env.update(extra_env)
    proc = strat.custom_spawn([sys.executable, "-c", code], env, scratch,
                              _CREATE_NO_WINDOW)
    chunks: dict[str, bytes] = {}

    def _drain(name, fh):
        try:
            chunks[name] = fh.read()
        except OSError as exc:                     # pipe torn down under us
            chunks[name] = repr(exc).encode()

    readers = [threading.Thread(target=_drain, args=(n, f), daemon=True)
               for n, f in (("out", proc.stdout), ("err", proc.stderr))]
    for t in readers:
        t.start()
    try:
        try:
            proc.stdin.close()                     # the probe reads no input
        except OSError:
            pass
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            rc = "timed out"
        for t in readers:
            t.join(15)
    finally:
        sw.cleanup_process(proc)
        proc.close_handle()
    return (rc,
            chunks.get("out", b"").decode("utf-8", "replace"),
            chunks.get("err", b"").decode("utf-8", "replace"))


# The five tests below carry ``@pytest.mark.sandbox_e2e`` spelled out rather than
# hidden behind a module-level alias: tests/test_sandbox_gate.py parses this file
# to pin the invariant that they are marked for *selection* and never for the
# skip, and a reader scanning for what runs on CI should not have to resolve an
# alias to find out.


@pytest.fixture(scope="module")
def confined_run(tmp_path_factory):
    """One real AppContainer child, shared by the end-to-end assertions below.

    Launching is expensive — ``custom_spawn`` grants ALL APPLICATION PACKAGES
    read+execute across the whole interpreter prefix and ``cleanup_process``
    revokes it again — so the probes run once and each test reads the result.
    """
    base = tmp_path_factory.mktemp("appcontainer-e2e")
    scratch = base / "scratch"
    scratch.mkdir()
    outside = base / "outside.txt"          # a sibling dir entry, never granted

    baseline = _explicit_aces(str(scratch))
    rc, out, err = _spawn_confined(sw.confinement(), _PROBE, str(scratch), {
        "ABAX_PROBE_SCRATCH": str(scratch),
        "ABAX_PROBE_OUTSIDE": str(outside),
        # So `from abax import sandbox` resolves inside the container, the same
        # way ConsoleBridge._spawn hands the worker its import path.
        "PYTHONPATH": os.pathsep.join([p for p in sys.path if p]),
    })
    return {"rc": rc, "out": out, "err": err, "diag": _diag(rc, out, err),
            "scratch": scratch, "outside": outside, "baseline": baseline}


@pytest.mark.sandbox_e2e
def test_e2e_confined_child_runs_to_completion(confined_run):
    """A container the interpreter cannot boot in is not confinement, it is a
    launch failure wearing confinement's clothes — fail loudly, with the
    evidence, rather than letting the four assertions below pass vacuously."""
    assert "PROBE_DONE" in confined_run["out"], \
        "the confined child never finished its probes" + confined_run["diag"]
    assert confined_run["rc"] == 0, \
        "the confined child exited non-zero" + confined_run["diag"]


@pytest.mark.sandbox_e2e
def test_e2e_scratch_is_writable_and_its_parent_is_not(confined_run):
    out, diag = confined_run["out"], confined_run["diag"]
    # The worker has to be able to work: the scratch dir is the one writable spot.
    assert "SCRATCH_WRITE_OK" in out, "scratch dir was not writable" + diag
    assert (confined_run["scratch"] / "inside.txt").read_text(encoding="utf-8") == "ok"
    # And nothing beside it is, even though it is only one directory up.
    assert "OUTSIDE_WRITE_DENIED" in out, "wrote outside the scratch dir" + diag
    assert not confined_run["outside"].exists(), \
        "escape file materialised outside scratch" + diag


@pytest.mark.sandbox_e2e
def test_e2e_no_capabilities_means_no_network(confined_run):
    out, diag = confined_run["out"], confined_run["diag"]
    assert "NET_REACHED" not in out, "outbound socket reached the stack" + diag
    assert ("NET_DENIED" in out or "NET_SOCKET_DENIED" in out), \
        "the network probe reported neither denial nor escape" + diag


@pytest.mark.sandbox_e2e
def test_e2e_worker_selftest_passes_inside_the_container(confined_run):
    """The production fail-closed gate must pass under a real AppContainer.

    If :func:`abax.sandbox.selftest` raised here every strict-mode execution
    would refuse to run — this is what keeps strict mode *usable* on Windows
    rather than merely safe.
    """
    assert "SELFTEST_OK" in confined_run["out"], \
        "selftest reported an escape inside the container" + confined_run["diag"]


@pytest.mark.sandbox_e2e
def test_e2e_cleanup_reverts_the_scratch_grant(confined_run):
    # cleanup_process ran in _spawn_confined's finally; the machine must be back
    # exactly where it started.
    assert _explicit_aces(str(confined_run["scratch"])) == confined_run["baseline"], \
        "the AppContainer ACL grant leaked past cleanup"
