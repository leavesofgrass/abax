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
  socket; plus a sixth that runs 24 real confinements from four threads at once
  and checks they are 24 separate containers (issue #10), and a seventh that
  holds one confined worker open across a second worker's teardown, because the
  read grants the two share are held for the *session* and an unconditional
  per-worker ``/remove`` used to take the survivor's stdlib with it (issue #11).
  Every assertion in
  that tier prints the child's exit code, stdout and
  stderr, because an AppContainer launch that dies at startup is otherwise
  undiagnosable from a CI log (see ``_diag``). These seven tests run
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
import queue
import string
import subprocess
import sys
import threading
import time

import pytest

from abax import sandbox as sb
from abax import sandbox_windows as sw

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows AppContainer only"
)

# CREATE_NO_WINDOW — what the bridge passes so a confined child never flashes a
# console window (abax.gui.console.console_bridge._spawn).
_CREATE_NO_WINDOW = 0x08000000

#: The production ``_icacls``, captured before any test can replace it. The
#: session-grant cleanup fixture needs the real tool to undo a real ACE even in
#: a test whose whole point was to monkeypatch the fake one in.
_REAL_ICACLS = sw._icacls


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
        self.procs: list[_FakeProc] = []

    @property
    def proc(self):
        """The handle from the most recent spawn."""
        return self.procs[-1]

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
        # A *fresh* handle per spawn, because the real launcher returns one and
        # because `custom_spawn` hangs each confinement's teardown state off it
        # (``proc._sandbox_cleanup``). A fake that handed both spawns the same
        # object would silently let the second overwrite the first's profile
        # name — precisely the class of shared-state bug this file now covers.
        self.procs.append(_FakeProc())
        return self.procs[-1]


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

    ``calls["unreachable"]`` is the seam for the fail-closed half: assign a list
    of paths to it *before* calling ``custom_spawn`` and the stub grant reports
    them as required-but-unreachable, exactly as the real one would when icacls
    refused the interpreter prefix.

    The stub honours the real signature's out-list: ``custom_spawn`` owns the
    ``granted`` list so it can revoke what landed even if the grant call raises
    partway, and a stub that only *returned* the paths would quietly stop
    exercising that.
    """
    calls = {"granted": [], "revoked": [], "unreachable": []}

    def _grant(scratch, granted=None):
        if granted is None:
            granted = []
        granted.extend([scratch, "C:\\fake\\interpreter"])
        calls["granted"].append(scratch)
        return granted, list(calls["unreachable"])

    def _revoke(granted):
        calls["revoked"].append(list(granted))
        return []                      # nothing left standing, as on success

    monkeypatch.setattr(sw, "_grant_container_access", _grant)
    monkeypatch.setattr(sw, "_revoke_container_access", _revoke)
    return calls


@pytest.fixture(autouse=True)
def session_grants_isolated():
    """Undo, per test, what ``sandbox_windows`` deliberately holds per session.

    The shared read grants are taken once per *process* and revoked once, at
    interpreter exit (issue #11) — which is right for abax and exactly wrong for
    a test suite. Without this fixture the first test to grant the real
    interpreter prefix would hold it for the remaining thousands of tests, and
    the next test that meant to observe a grant would instead observe a reuse and
    silently assert nothing.

    So every entry a test adds is removed *for real* afterwards, with the icacls
    captured at import — the test may well have replaced ``sw._icacls`` with a
    fake, and a fake cannot take an ACE off a directory. The table is then put
    back exactly as it was found: an entry that was already there belongs to
    whoever put it there (the module-scoped ``confined_run``, for instance).

    ``_SESSION_SWEEP_PID`` is deliberately *not* restored. Arming the exit sweep
    is a one-way, once-per-process act and ``atexit`` has already been told; a
    reset would let the next test arm a second hook. The armed hook is harmless
    here precisely because this fixture leaves it nothing to do — which is worth
    something as a check in itself. The tests that are *about* arming manage
    their own registration (see ``_no_real_atexit``).
    """
    before = dict(sw._SESSION_GRANTS)
    try:
        yield
    finally:
        added = [v for k, v in sw._SESSION_GRANTS.items() if k not in before]
        sw._SESSION_GRANTS.clear()
        sw._SESSION_GRANTS.update(before)
        for path, _ace in added:
            if os.path.exists(path):
                _REAL_ICACLS(path, "/remove", sw.ALL_APP_PACKAGES)


@pytest.fixture
def own_session_table(monkeypatch):
    """Give this test a private, empty copy of the session grant table.

    Two reasons, and both are consequences of the table being process-wide by
    design rather than of anything wrong with it:

    * ``_revoke_session_grants`` is the *whole-table* exit sweep. A test that
      calls it against the shared table would revoke grants the rest of the run
      is holding — ``test_sandbox.py``'s strict-worker test runs earlier and
      leaves the real interpreter prefix held, deliberately — and each of those
      costs ~17 s of DACL walking to take off and put back.
    * a test that asserts the table's *contents* would otherwise have to spell
      out whatever the wider suite happens to be holding, which is a different
      list depending on which files were selected.

    Swapping the module attribute is enough: every function here reads the
    global by name at call time. Whatever the test leaves in the private table
    is revoked on the way out, with the real icacls, in case the test's own
    sweep did not run.
    """
    private: "dict[str, tuple[str, str]]" = {}
    monkeypatch.setattr(sw, "_SESSION_GRANTS", private)
    yield private
    for path, _ace in list(private.values()):
        if os.path.exists(path):
            _REAL_ICACLS(path, "/remove", sw.ALL_APP_PACKAGES)


@pytest.fixture(scope="module", autouse=True)
def session_grants_swept_at_module_exit():
    """Run the production exit sweep when this module is finished, not at exit.

    The end-to-end tier grants ALL APPLICATION PACKAGES read+execute across the
    *real* interpreter prefix and ``sys.path``, and by design nothing during the
    session takes those off — the module-scoped ``confined_run`` in particular
    outlives the per-test fixture above, so its grants are not "added by a test"
    and are not cleaned up by it.

    Left alone, the real ``atexit`` hook would collect them, which is correct but
    lands ~20 s of DACL walking *after* pytest has printed its summary and
    settled its exit code — where it reads as a hang rather than as work. Sweeping
    here makes it deterministic and visible, and leaves the armed hook with
    nothing to do, which is itself the check that this fixture and the production
    one agree about what is outstanding.
    """
    yield
    sw._revoke_session_grants()


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


def test_profile_name_is_fresh_for_every_confinement():
    """Unique per *confinement*, not per process (issue #10).

    The old name was ``f"abax-sandbox-{os.getpid()}"`` and this test asserted it
    was *stable within a process*, which is exactly the property that was wrong:
    abax runs two confined workers in the GUI process — ``pyconsole.py`` and
    ``mixin_macros.py`` each build their own strict ``ConsoleBridge`` — and one
    name puts both in one container, because
    ``create_app_container_profile`` answers ``ALREADY_EXISTS`` by deriving the
    existing SID rather than failing. The first teardown then deletes the
    container the other worker is still living in.

    Stability was never a requirement of anything: ``custom_spawn`` mints the
    name once and carries it to teardown through ``proc._sandbox_cleanup``, so
    nothing recomputes it and nothing compares two computations.
    """
    names = [sw._profile_name() for _ in range(500)]
    assert len(set(names)) == len(names), "profile names repeated within a process"
    for name in names:
        # Still identifiable as abax's on a machine carrying ~150 other
        # AppContainers, and still traceable to a run: a leaked profile is a
        # registry mapping plus a %LOCALAPPDATA%\\Packages directory, and the
        # only clue to its origin is this name.
        assert name.startswith("abax-sandbox-"), name
        assert name.split("-")[2] == str(os.getpid()), name


def test_profile_name_fits_the_measured_appcontainer_name_limits(monkeypatch):
    """The length and charset limits, measured against the real API — not read
    off the documentation and not assumed.

    ``CreateAppContainerProfile`` on this platform accepts a 64-character name
    and rejects 65 with ``hr=0x80070057`` (``E_INVALIDARG``); it rejects ``\\``
    and ``/`` with ``0x80070003``, ``*`` and ``?`` with ``0x8007007b``, and
    ``:`` with ``0x8007010b``. Hyphens, digits and ASCII letters are accepted.

    The PID is the only unbounded-looking part, so the check is run against a
    full-width one: a Windows PID is a DWORD, so ``4294967295`` is the widest
    that can ever be formatted here. 13 + 10 + 1 + 12 = 36, leaving 28 spare —
    a random suffix could double and still fit.
    """
    legal = set(string.ascii_lowercase + string.digits + "-")
    for pid in (1, os.getpid(), 4294967295):
        monkeypatch.setattr(os, "getpid", lambda pid=pid: pid)
        name = sw._profile_name()
        assert 0 < len(name) <= 64, (len(name), name)
        assert set(name) <= legal, sorted(set(name) - legal)
        # Spelled out as well as bounded by the allowlist above, so the failure
        # names the actual rejection rather than an anonymous set difference.
        assert not (set(name) & set("\\/:*?\"<>|")), name


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
# the zipapp: a sys.path entry that is a *file* (issue #8 follow-up)
# --------------------------------------------------------------------------- #


def _zipapp_shaped_package(tmp_path):
    """A real zip holding the real ``sandbox_windows`` inside an ``abax`` package.

    Not a stand-in for ``make_pyz.py``'s output — the same *shape*, which is the
    only thing :func:`_abax_package_dir` reads: a module imported out of an
    archive *file*. The two siblings it imports are stubbed so the archive stays
    a few KB and the child never drags in the rest of abax, but
    ``sandbox_windows`` itself is the shipping file, so the assertion below is
    about the real function and cannot drift from it.
    """
    import zipfile

    source = os.path.abspath(sw.__file__)
    archive = tmp_path / "abax.pyz"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("abax/__init__.py", "")
        z.writestr("abax/_runtime.py",
                   "def console_encoding():\n    return 'oem'\n")
        z.write(source, "abax/sandbox_windows.py")
    return archive


def test_a_zipapp_puts_the_abax_package_path_on_a_file_not_a_directory(tmp_path):
    """Constructed, not argued: import the real module out of a real archive.

    ``python abax.pyz`` makes ``sandbox_windows.__file__``
    ``…\\abax.pyz\\abax\\sandbox_windows.pyc``, so ``_abax_package_dir()`` — two
    ``dirname``s up — is the **archive itself**, a file. Measured against a
    ``make_pyz.py`` build and reproduced here in a child interpreter.

    Both halves matter. ``_needed_read_dirs`` filters on ``os.path.isdir`` and so
    can *never* carry the archive: that is the mechanism by which a required
    target became permanently unreachable and every strict launch in the shipped
    portable build refused unconditionally. ``_needed_read_files`` is what fixes
    it, and a fix that stopped covering this shape would restore the bug in the
    one build a developer is least likely to run the suite against.
    """
    archive = _zipapp_shaped_package(tmp_path)
    prog = (
        "import os, sys\n"
        f"sys.path.insert(0, r'{archive}')\n"
        "from abax import sandbox_windows as sw\n"
        "p = sw._abax_package_dir()\n"
        "nc = os.path.normcase\n"
        "print('PKGDIR', p)\n"
        "print('ISDIR', os.path.isdir(p))\n"
        "print('ISFILE', os.path.isfile(p))\n"
        "print('IN_DIRS', any(nc(d) == nc(p) for d in sw._needed_read_dirs()))\n"
        "print('IN_FILES', any(nc(f) == nc(p) for f in sw._needed_read_files()))\n"
        "print('REQUIRED', any(nc(t) == nc(p) for t in sw._required_read_targets()))\n"
    )
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    r = subprocess.run([sys.executable, "-c", prog], capture_output=True,
                       text=True, timeout=120, env=env, cwd=str(tmp_path))
    assert r.returncode == 0, r.stdout + r.stderr
    reported = dict(line.split(" ", 1) for line in r.stdout.splitlines() if line)

    assert reported["PKGDIR"] == str(archive), r.stdout
    assert reported["ISDIR"] == "False"        # the archive is a file...
    assert reported["ISFILE"] == "True"
    assert reported["REQUIRED"] == "True"      # ...that the child cannot boot without
    # The mechanism of the bug, pinned so the fix cannot be "quietly" moved back
    # into the dirs list, where isdir would drop it again.
    assert reported["IN_DIRS"] == "False", r.stdout
    assert reported["IN_FILES"] == "True", r.stdout


def _as_a_zipapp(mp, archive, prefix):
    """Point interpreter introspection at a zipapp launch of *archive*.

    The shape the test above measured on a real archive, applied in-process so
    the grant path can be exercised against it with real icacls on throwaway
    paths. *prefix* stands in for the interpreter so no ACE ever lands on this
    machine's real Python.
    """
    mp.setattr(sys, "path", [str(archive), ""])
    mp.setattr(sys, "base_prefix", str(prefix))
    mp.setattr(sys, "prefix", str(prefix))
    mp.setattr(sys, "executable", str(prefix / "python.exe"))
    mp.setattr(sw, "_abax_package_dir", lambda: str(archive))


def test_a_file_shaped_syspath_entry_is_granted_rather_than_refused(
        tmp_path, own_session_table):
    """The shipped zipapp must be able to confine at all.

    With the archive on ``sys.path`` and providing ``abax``, it is a required
    target that no *directory* grant can cover: ``D:\\abax`` is on ``sys.path``
    only by accident of the CWD. Before the file grant existed this returned
    ``unreachable == [archive]`` on every call, so ``custom_spawn`` raised
    ``SandboxGrantError`` unconditionally and strict mode could not be switched
    on in the portable build at all.

    Real icacls, throwaway paths: the ACE has to actually land, which is the
    whole point — see the flags test above.

    The archive is a *shared* import root, so like the read dirs it is held for
    the session and removed by the exit sweep rather than by the worker's
    teardown (issue #11); both owners run below, and the machine ends where it
    started either way. ``own_session_table`` keeps that sweep from reaching
    grants the rest of the run is holding.
    """
    archive = tmp_path / "abax.pyz"
    archive.write_bytes(b"PK\x05\x06" + b"\x00" * 18)   # a valid empty zip
    prefix = tmp_path / "prefix"
    scratch = tmp_path / "scratch"
    for d in (prefix, scratch):
        d.mkdir()
    before = _explicit_aces(str(archive))

    with pytest.MonkeyPatch.context() as mp:
        _as_a_zipapp(mp, archive, prefix)
        granted, unreachable = sw._grant_container_access(str(scratch))
        try:
            # Nothing about a file-shaped entry is fatal any more...
            assert unreachable == []
            # ...because the archive itself was granted, by identity.
            assert str(archive) in granted
            assert granted == [str(scratch), str(prefix), str(archive)]
            # A file takes the flags a file can hold — the directory ACE would
            # have exited 0 and added nothing (see the test below).
            added = _explicit_aces(str(archive)) - before
            assert len(added) == 1, added
            assert added.pop().endswith(":(RX)")
        finally:
            sw._revoke_container_access(granted)
            # The worker's teardown is not this ACE's owner: the archive is on
            # every confinement's import path, so it is the session's.
            held = _explicit_aces(str(archive)) - before
            sw._revoke_session_grants()

    assert len(held) == 1, "a shared import root came off with one worker"
    assert _explicit_aces(str(archive)) == before


def test_a_zipapp_already_inside_a_granted_directory_is_not_granted_twice(
        tmp_path, own_session_table):
    """The inheritable directory ACE already reaches it.

    The ordinary developer case — ``abax.pyz`` sitting in a checkout that is
    itself on ``sys.path``. A second, explicit ACE on the file would be one more
    icacls round trip on every spawn and one more thing the exit sweep has to
    remove — and the sweep runs below, against ``own_session_table``'s private
    copy, because the read dir is now the session's and not the worker's.
    """
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    archive = prefix / "abax.pyz"
    archive.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    # Ask by SID, not by comparing ACLs.
    #
    # NOT `_explicit_aces(archive) == before`: granting an *inheritable*
    # (OI)(CI) ACE on a directory triggers a propagation pass over its children,
    # and that pass can rewrite a child's DACL — converting previously-explicit
    # entries into inherited ones. So the child's explicit set legitimately
    # changes across a parent grant/revoke on a runner whose temp files carry
    # explicit ACEs, though not on a dev box whose temp files do not. Comparing
    # whole ACLs across an operation is not an invariant Windows offers.
    #
    # NOT a name match either: "ALL APPLICATION PACKAGES" is localised, so a
    # substring test would quietly match nothing on a non-English Windows and
    # this test would pass by finding no ACE rather than by there being none.
    # `_container_ace_present` matches the well-known SID.
    assert sw._container_ace_present(str(archive)) is False   # none to begin with

    with pytest.MonkeyPatch.context() as mp:
        _as_a_zipapp(mp, archive, prefix)
        granted, unreachable = sw._grant_container_access(str(scratch))
        try:
            assert unreachable == []
            assert granted == [str(scratch), str(prefix)]   # no separate file ACE
        finally:
            sw._revoke_container_access(granted)
            sw._revoke_session_grants()      # the read dir's owner, not the worker

    # The archive never got an ACE of its own — the parent's inheritable one
    # reached it — and the revokes left none behind.
    assert sw._container_ace_present(str(archive)) is False


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


def test_inheritance_flags_are_silently_dropped_from_a_grant_on_a_file(tmp_path):
    """Why a file-shaped import root gets a plain ``(RX)``: measured, not assumed.

    ``icacls <file> /grant "<sid>:(OI)(CI)(RX)"`` **exits 0 and adds nothing**.
    The object/container inheritance flags have nothing to inherit on a leaf, and
    icacls discards the whole ACE rather than reporting it — a grant that reports
    success and did nothing, which is the exact class of failure this module
    exists to make impossible. Reusing the directory ACE for the zipapp archive
    would therefore have looked like a fix and been none.

    If this ever starts failing, icacls has changed its mind about leaf ACEs and
    ``_needed_read_files``' rationale wants re-reading; the ``(RX)`` grant abax
    actually issues is unaffected either way.
    """
    target = tmp_path / "abax.pyz"
    target.write_bytes(b"PK\x05\x06" + b"\x00" * 18)
    before = _explicit_aces(str(target))

    assert sw._icacls(str(target), "/grant",
                      f"{sw.ALL_APP_PACKAGES}:(OI)(CI)(RX)") is True
    assert _explicit_aces(str(target)) == before, \
        "icacls reported success on a directory-shaped ACE for a file"

    assert sw._icacls(str(target), "/grant", f"{sw.ALL_APP_PACKAGES}:(RX)") is True
    try:
        added = _explicit_aces(str(target)) - before
        assert len(added) == 1, added
        assert added.pop().endswith(":(RX)")
    finally:
        sw._revoke_container_access([str(target)])
    assert _explicit_aces(str(target)) == before


def test_grant_is_additive_and_revoke_reverts_it_exactly(
        monkeypatch, tmp_path, own_session_table):
    """The documented promise: the ACEs we add never weaken anyone's access and
    the machine is left byte-identical afterwards.

    Two owners now revert it, not one, and the test says so rather than papering
    over it (issue #11): the scratch dir's ``(M)`` grant comes off at the
    worker's teardown, the shared read grant at the process's exit sweep. The
    intermediate assertion — that the read dir's ACE is *still there* after the
    worker teardown — is the design, not a leak, and pinning it here is what
    stops a future "tidy-up" quietly restoring the per-worker ``/remove`` that
    stripped a live sibling's stdlib. ``own_session_table`` scopes the sweep to
    this test's own grants.
    """
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    readable = tmp_path / "importable"
    readable.mkdir()
    # Keep the real interpreter prefix out of it — this test is about the ACEs.
    monkeypatch.setattr(sw, "_needed_read_dirs", lambda: [str(readable)])
    # ...and with the prefix out, the real requirements are by construction
    # ungranted here, so they are patched out too rather than asserted around.
    # The requirement policy has its own tests below; this one owns the promise
    # that the ACEs are additive and exactly reverted.
    monkeypatch.setattr(sw, "_required_read_targets", lambda: [])

    before_scratch = _explicit_aces(str(scratch))
    before_read = _explicit_aces(str(readable))
    # The full ACL too: nothing that already granted access may disappear.
    all_before_scratch = _ace_lines(str(scratch))
    all_before_read = _ace_lines(str(readable))

    granted, unreachable = sw._grant_container_access(str(scratch))
    try:
        assert granted == [str(scratch), str(readable)]
        assert unreachable == []          # everything asked for was granted

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
        worker_leaks = sw._revoke_container_access(granted)
        mid_read = _explicit_aces(str(readable))
        mid_scratch = _explicit_aces(str(scratch))
        sweep_leaks = sw._revoke_session_grants()

    # The worker's teardown took its own writable grant and nothing else, and
    # reported nothing: the read dir it left standing has an owner and a
    # scheduled removal, so it is live state rather than a leak.
    assert worker_leaks == []
    assert mid_scratch == before_scratch
    assert len(mid_read - before_read) == 1, \
        "the worker's teardown removed a read grant the whole session shares"

    # Our ACEs are gone...
    assert sweep_leaks == []
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
    monkeypatch.setattr(sw, "_required_read_targets", lambda: [])
    missing_scratch = str(tmp_path / "no-such-scratch")

    granted, unreachable = sw._grant_container_access(missing_scratch)
    try:
        assert granted == [str(readable)]
        # The scratch dir is the one place the worker may write; a grant that
        # did not land there is fatal even though the read dirs were fine.
        assert unreachable == [missing_scratch]
    finally:
        sw._revoke_container_access(granted)


def test_revoke_tolerates_paths_that_disappeared(tmp_path):
    # A scratch dir deleted before teardown (or a grant that never landed) must
    # not turn cleanup into an exception — cleanup runs from a finally block.
    # A path that is gone is also not *reported*: its ACL went with it, so there
    # is no grant left standing to warn anyone about.
    assert sw._revoke_container_access([str(tmp_path / "gone"), str(tmp_path)]) == []


# --------------------------------------------------------------------------- #
# the grant policy: which failures are fatal (issue #8, grant side)
# --------------------------------------------------------------------------- #


def _grant_failing_on(*doomed):
    """An ``_icacls`` stand-in that refuses exactly *doomed* and grants the rest."""
    doomed = {os.path.normcase(os.path.abspath(p)) for p in doomed}

    def _fake(path, *args):
        return os.path.normcase(os.path.abspath(path)) not in doomed

    return _fake


def test_required_read_targets_name_the_interpreter_and_the_abax_package():
    """The two things the child cannot boot without, named explicitly.

    ``_needed_read_dirs`` is a superset (every ``sys.path`` entry); this is the
    subset whose absence is not a degraded worker but a dead one — and the abax
    package's directory belongs in it precisely because the child's whole job is
    ``from abax.console_worker import main``.
    """
    targets = [os.path.normcase(t) for t in sw._required_read_targets()]
    assert os.path.normcase(os.path.abspath(sys.base_prefix)) in targets
    assert os.path.normcase(os.path.dirname(os.path.abspath(sys.executable))) in targets
    provider = os.path.dirname(os.path.dirname(os.path.abspath(sw.__file__)))
    assert os.path.normcase(provider) in targets
    for t in sw._required_read_targets():
        assert os.path.isabs(t), t


def test_the_real_required_targets_are_all_covered_by_the_real_read_dirs():
    """The two halves must agree on this machine, or strict mode never launches.

    ``_needed_read_dirs`` is what actually gets handed to icacls; if a required
    target stopped being covered by it — a `sys.path` shape nobody anticipated,
    a minimisation bug — every strict spawn would refuse with the fail-closed
    error instead of running. That is a safe failure but a total one, so it is
    worth an assertion rather than a discovery.
    """
    dirs = sw._needed_read_dirs()
    for target in sw._required_read_targets():
        assert sw._covered_by(target, dirs), (
            f"{target} is required but no directory in {dirs} covers it")


def test_covered_by_accepts_a_parent_and_rejects_a_sibling(tmp_path):
    parent = tmp_path / "parent"
    (parent / "child").mkdir(parents=True)
    sibling = tmp_path / "parentele"          # shares a prefix, is not inside
    sibling.mkdir()

    assert sw._covered_by(str(parent), [str(parent)])
    assert sw._covered_by(str(parent / "child"), [str(parent)])
    # Case-insensitive, like the filesystem: an ancestor spelled differently
    # still covers, or a grant would be silently judged not to have landed.
    assert sw._covered_by(str(parent / "child"), [str(parent).upper()])
    assert not sw._covered_by(str(sibling), [str(parent)])
    assert not sw._covered_by(str(parent), [str(parent / "child")])


def test_grant_reports_a_required_path_it_could_not_reach(monkeypatch, tmp_path):
    """The fail-closed signal: a refused grant on the interpreter prefix.

    Without this the launcher spawns a child that cannot read its own stdlib and
    dies during interpreter startup with no output at all — indistinguishable
    from issue #6, which is why that class took months to see.
    """
    scratch = tmp_path / "scratch"
    prefix = tmp_path / "prefix"
    for d in (scratch, prefix):
        d.mkdir()
    monkeypatch.setattr(sw, "_needed_read_dirs", lambda: [str(prefix)])
    monkeypatch.setattr(sw, "_required_read_targets", lambda: [str(prefix)])
    monkeypatch.setattr(sw, "_icacls", _grant_failing_on(str(prefix)))
    # No pre-existing ACE to fall back on.
    monkeypatch.setattr(sw, "_container_ace_present", lambda path: False)

    granted, unreachable = sw._grant_container_access(str(scratch))

    assert granted == [str(scratch)]      # the failed path is not revocable
    assert unreachable == [str(prefix)]


def test_grant_survives_a_syspath_entry_that_is_not_required(monkeypatch, tmp_path, caplog):
    """A redundant ``sys.path`` directory is a warning, not a refusal.

    It may hold nothing the worker imports, and if it does the failure surfaces
    as an ordinary ModuleNotFoundError on the child's stderr — which the bridge
    already reports. Refusing here would trade a silent failure for a spurious
    one on any machine with an exotic PYTHONPATH.
    """
    scratch = tmp_path / "scratch"
    prefix = tmp_path / "prefix"
    extra = tmp_path / "some-syspath-entry"
    for d in (scratch, prefix, extra):
        d.mkdir()
    monkeypatch.setattr(sw, "_needed_read_dirs", lambda: [str(prefix), str(extra)])
    monkeypatch.setattr(sw, "_required_read_targets", lambda: [str(prefix)])
    monkeypatch.setattr(sw, "_icacls", _grant_failing_on(str(extra)))
    monkeypatch.setattr(sw, "_container_ace_present", lambda path: False)

    with caplog.at_level("WARNING", logger=sw.__name__):
        granted, unreachable = sw._grant_container_access(str(scratch))

    assert granted == [str(scratch), str(prefix)]
    assert unreachable == []              # survivable: the spawn goes ahead
    assert str(extra) in caplog.text      # but it is not silent


def test_grant_accepts_a_required_path_that_is_already_container_readable(
        monkeypatch, tmp_path):
    """The Program Files case: the grant fails and the child reads it anyway.

    A non-elevated abax cannot rewrite the DACL of a machine-wide Python
    install, but Windows already grants ALL APPLICATION PACKAGES read+execute
    under ``C:\\Program Files``. Refusing there would break strict mode on every
    all-users installation, so a pre-existing ACE downgrades the refusal.
    """
    scratch = tmp_path / "scratch"
    prefix = tmp_path / "prefix"
    for d in (scratch, prefix):
        d.mkdir()
    asked = []
    monkeypatch.setattr(sw, "_needed_read_dirs", lambda: [str(prefix)])
    monkeypatch.setattr(sw, "_required_read_targets", lambda: [str(prefix)])
    monkeypatch.setattr(sw, "_icacls", _grant_failing_on(str(prefix)))
    monkeypatch.setattr(sw, "_container_ace_present",
                        lambda path: asked.append(path) or True)

    granted, unreachable = sw._grant_container_access(str(scratch))

    assert unreachable == []
    assert asked == [str(prefix)], "the pre-existing-ACE probe was never consulted"
    # Still not in the revoke list: we added no ACE there, so we remove none.
    assert granted == [str(scratch)]


def test_the_ace_probe_is_not_consulted_when_every_grant_landed(monkeypatch, tmp_path):
    """The ordinary path pays nothing for the fallback.

    ``/findsid`` is a second icacls round trip per required path; running it on
    every successful spawn would be pure latency on the hot path.
    """
    scratch = tmp_path / "scratch"
    prefix = tmp_path / "prefix"
    for d in (scratch, prefix):
        d.mkdir()
    monkeypatch.setattr(sw, "_needed_read_dirs", lambda: [str(prefix)])
    monkeypatch.setattr(sw, "_required_read_targets", lambda: [str(prefix)])
    monkeypatch.setattr(sw, "_icacls", lambda *a: True)

    def _never(path):
        raise AssertionError(f"the /findsid probe ran for {path} on a clean grant")

    monkeypatch.setattr(sw, "_container_ace_present", _never)
    granted, unreachable = sw._grant_container_access(str(scratch))
    assert unreachable == []
    assert granted == [str(scratch), str(prefix)]


def test_scratch_is_required_even_when_a_parent_grant_covers_it(monkeypatch, tmp_path):
    """Read access to an ancestor is not write access to the scratch dir.

    The scratch dir is granted ``(M)`` and everything else ``(RX)``, so treating
    "inside something we granted" as good enough would wave through a worker
    that cannot write a single byte — which fails later, at the first temp file,
    pointing nowhere near the ACL that caused it.
    """
    scratch = tmp_path / "outer" / "scratch"
    scratch.mkdir(parents=True)
    outer = tmp_path / "outer"
    monkeypatch.setattr(sw, "_needed_read_dirs", lambda: [str(outer)])
    monkeypatch.setattr(sw, "_required_read_targets", lambda: [])
    monkeypatch.setattr(sw, "_icacls", _grant_failing_on(str(scratch)))

    granted, unreachable = sw._grant_container_access(str(scratch))

    assert granted == [str(outer)]
    assert unreachable == [str(scratch)]


# --- the pre-existing-ACE probe ---------------------------------------------


def test_container_ace_probe_agrees_with_the_real_icacls():
    """Against the real tool: a system dir every AppContainer can read, and a
    path that cannot be listed at all."""
    system_root = os.environ.get("SystemRoot") or "C:\\Windows"
    # ALL APPLICATION PACKAGES has RX on %SystemRoot% on every supported
    # Windows — an AppContainer that could not read it could not run anything.
    assert sw._container_ace_present(system_root) is True
    assert sw._container_ace_present("C:\\no-such-dir-abax-8\\nope") is False


@pytest.mark.parametrize("rc,stdout,expected", [
    (0, "SID Found: C:\\probe.\r\nSuccessfully processed 1 files\r\n", True),
    (0, "No files with a matching SID was found\r\n"
        "Successfully processed 1 files; Failed processing 0 files\r\n", False),
    # A localised "found" line still names the path; a localised "not found"
    # line still cannot. The path is the discriminator, never the wording.
    (0, "SID gefunden: C:\\probe.\r\n", True),
    (0, "Kein Objekt mit einer entsprechenden SID gefunden\r\n", False),
    # An error echoes the path too — but exits non-zero, which is what keeps
    # "The system cannot find the path specified" from reading as a hit.
    (3, "C:\\probe: The system cannot find the path specified.\r\n", False),
])
def test_container_ace_probe_reads_findsid_by_path_not_by_wording(
        monkeypatch, rc, stdout, expected):
    seen = {}

    def _fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, rc, stdout, "")

    monkeypatch.setattr(sw.subprocess, "run", _fake_run)
    assert sw._container_ace_present("C:\\probe") is expected
    assert seen["argv"] == ["icacls", "C:\\probe", "/findsid", sw.ALL_APP_PACKAGES]
    # No /T: this asks about the one path, not about every file beneath it.
    assert "/T" not in seen["argv"]
    # Same encoding policy as _icacls (issue #5): the console codepage, never
    # strict — a replaced byte must not turn the probe into an exception.
    assert seen["kwargs"].get("encoding") == sw.console_encoding()
    assert seen["kwargs"].get("errors") == "replace"


def test_the_ace_probe_waits_far_less_than_the_grant_calls_do(monkeypatch):
    """It runs on the refusal path, and the refusal path is the GUI thread.

    ``/findsid`` with no ``/T`` is one non-recursive lookup — ~30 ms measured —
    but it is consulted once per *required* target, and only when a required
    grant already failed. That path is synchronous inside a Qt slot
    (``_run_macro``, Run script), so inheriting ``_icacls``' 60-second timeout
    means three stalled probes can freeze the window for three minutes before
    the user is told anything. A timeout can only ever answer False, and False
    never upgrades a refusal, so a short wait cannot cost an answer — only the
    waiting.
    """
    seen = {}

    def _fake_run(argv, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(sw.subprocess, "run", _fake_run)
    sw._container_ace_present("C:\\probe")

    assert 0 < seen["timeout"] <= 10, seen["timeout"]


@pytest.mark.parametrize("exc", [
    FileNotFoundError("icacls not on PATH"),
    subprocess.TimeoutExpired("icacls", 60),
])
def test_container_ace_probe_answers_false_when_the_tool_misbehaves(monkeypatch, exc):
    """False is the conservative answer: the probe may only ever downgrade a
    refusal, so a broken tool must not be able to wave a launch through."""
    def _boom(*a, **k):
        raise exc

    monkeypatch.setattr(sw.subprocess, "run", _boom)
    assert sw._container_ace_present("C:\\probe") is False


# --------------------------------------------------------------------------- #
# the revoke side reports what it could not undo (issue #8, revoke side)
# --------------------------------------------------------------------------- #


def test_revoke_reports_and_logs_grants_it_could_not_remove(monkeypatch, tmp_path, caplog):
    """A failed revoke leaves a machine-wide ACE standing; it must not do so
    silently. It still must not raise — teardown continues past a failure."""
    left = tmp_path / "prefix"
    also = tmp_path / "site-packages"
    for d in (left, also):
        d.mkdir()
    monkeypatch.setattr(sw, "_icacls", lambda *a: False)

    with caplog.at_level("WARNING", logger=sw.__name__):
        still_standing = sw._revoke_container_access([str(left), str(also)])

    assert still_standing == [str(left), str(also)]
    assert str(left) in caplog.text and str(also) in caplog.text
    assert any(r.levelname == "WARNING" for r in caplog.records), caplog.records


def test_revoke_reports_nothing_when_every_removal_succeeds(tmp_path):
    # The real tool, on a real path: removing an ACE that isn't there succeeds,
    # so the ordinary teardown reports an empty list.
    assert sw._revoke_container_access([str(tmp_path)]) == []


# --------------------------------------------------------------------------- #
# the shared read grants are held for the session (issue #11)
# --------------------------------------------------------------------------- #
#
# The read grants land on paths every confinement in the process needs — the
# interpreter prefix, the `sys.path` directories — while teardown belongs to one
# worker, and abax runs two long-lived strict-capable bridges in the GUI process
# (`pyconsole.py`'s worker persists between commands, `mixin_macros.py`'s does
# not). Three measurements, all against the real icacls on this platform, set
# the shape of the fix and are restated in `sandbox_windows` beside the code:
#
#   1. `icacls /grant` is idempotent for a principal, so one `/remove` strips an
#      ACE two workers are sharing.
#   2. The AppContainer access check is not cached, so a live worker loses its
#      stdlib on its *next* import — while staying up and answering.
#   3. Grant and revoke are not atomic. Each is a DACL propagation walk timed at
#      19.4-21.6 s, and every child spawned into a revoke walk dies:
#      `Fatal Python error: init_fs_encoding`, then `0xC0000022` with no output
#      at all — issue #9's text, from this mechanism.
#
# (3) is why refcounting is not enough and was discarded: even a perfect count
# leaves a ~20 s window at the last teardown. Holding the grants for the session
# removes the 1->0 transition entirely, and with it the window.
#
# The scratch dir is emphatically *not* session-held: it is per-worker, carries
# `(M)` write access, and is revoked unconditionally at that worker's teardown.
#
# Every test here goes through the autouse `session_grants_isolated` fixture,
# because the table it exercises is process-wide by design.


def _icacls_spy(monkeypatch, calls):
    """Record every icacls operation *and still perform it for real*.

    The promise is about how many times the tool is invoked — one grant for two
    spawns, and none at all on the second — and no amount of ACL snapshotting
    can see that: a path granted once and a path granted twice have identical
    ACLs, which is exactly why the old bookkeeping bug was invisible. So the
    calls are counted. The ACL is still asserted separately, because a test that
    only counted calls would pass just as happily if the grant never landed.
    """
    real = sw._icacls

    def _spy(path, *args):
        ok = real(path, *args)
        calls.append((args[0], os.path.normcase(os.path.abspath(path))))
        return ok

    monkeypatch.setattr(sw, "_icacls", _spy)
    return calls


def _ops(calls, verb, path):
    """The recorded *verb* operations against *path*."""
    key = os.path.normcase(os.path.abspath(str(path)))
    return [c for c in calls if c == (verb, key)]


@pytest.fixture
def shared_paths(monkeypatch, tmp_path, own_session_table):
    """A throwaway stand-in for the interpreter prefix, plus two scratch dirs.

    Real directories and the real ``icacls``, so the ACL assertions mean
    something, but nowhere near the real ``sys.path`` — a test that granted the
    actual interpreter prefix would pay ~17 s each way for it. The private
    session table comes with it, so every table assertion below can name exactly
    what this test put there.
    """
    shared = tmp_path / "interpreter"
    console = tmp_path / "scratch-console"
    macro = tmp_path / "scratch-macros"
    for d in (shared, console, macro):
        d.mkdir()
    monkeypatch.setattr(sw, "_needed_read_dirs", lambda: [str(shared)])
    monkeypatch.setattr(sw, "_needed_read_files", lambda: [])
    monkeypatch.setattr(sw, "_required_read_targets", lambda: [str(shared)])
    return shared, console, macro


@pytest.fixture
def no_real_atexit(monkeypatch):
    """Capture ``atexit.register`` calls instead of really arming the sweep.

    Arming for real inside a test would leave a hook that fires at the end of the
    whole pytest run, against a table other tests own. The tests that care about
    arming want to count registrations anyway, which is what this returns.
    """
    registered: list = []
    monkeypatch.setattr(sw.atexit, "register", registered.append)
    monkeypatch.setattr(sw, "_SESSION_SWEEP_PID", None)
    return registered


def test_a_second_confinement_does_no_icacls_work_for_a_held_shared_path(
        monkeypatch, shared_paths):
    """The core of the design, with the real tool on throwaway paths.

    Console spawns, then the macro runner spawns. The shared path is granted
    once; the second confinement neither re-grants it (a redundant ``/grant`` is
    a full DACL walk — measured at the same 16.5 s as a cold one, so it is not a
    cheap no-op) nor treats it as unreachable.
    """
    shared, console_scratch, macro_scratch = shared_paths
    baseline = _explicit_aces(str(shared))
    calls = _icacls_spy(monkeypatch, [])

    console, unreachable = sw._grant_container_access(str(console_scratch))
    assert unreachable == []
    assert len(_ops(calls, "/grant", shared)) == 1
    assert sw._container_ace_present(str(shared)) is True
    assert sw._session_grant_paths() == [str(shared)]

    macro, unreachable = sw._grant_container_access(str(macro_scratch))

    assert unreachable == [], "the second confinement thought the path unreachable"
    assert str(shared) in macro, "the reused path was not reported as reachable"
    assert len(_ops(calls, "/grant", shared)) == 1, \
        "the second spawn paid a second ~20 s grant walk for a path already held"
    # One ACE, not two, and the table holds one entry however many spawns saw it.
    assert len(_explicit_aces(str(shared)) - baseline) == 1
    assert sw._session_grant_paths() == [str(shared)]


def test_a_workers_teardown_leaves_the_shared_grant_standing(
        monkeypatch, shared_paths):
    """The reproduction shape, at unit level: macro tears down, console lives.

    An unconditional ``/remove`` here is what stripped the surviving worker's
    stdlib. It must not happen at *any* teardown, not merely at the non-final
    ones — that is the difference between this design and the refcount, and the
    reason there is no window for a starting worker to fall into.
    """
    shared, console_scratch, macro_scratch = shared_paths
    calls = _icacls_spy(monkeypatch, [])

    console, _ = sw._grant_container_access(str(console_scratch))
    macro, _ = sw._grant_container_access(str(macro_scratch))

    assert sw._revoke_container_access(macro) == []
    assert _ops(calls, "/remove", shared) == [], \
        "one worker's teardown removed a grant its live sibling was still using"
    assert sw._container_ace_present(str(shared)) is True

    # ...and the *last* teardown does not remove it either. Nothing during the
    # session does; only the exit sweep.
    assert sw._revoke_container_access(console) == []
    assert _ops(calls, "/remove", shared) == []
    assert sw._container_ace_present(str(shared)) is True
    assert sw._session_grant_paths() == [str(shared)]


def test_each_worker_revokes_its_own_scratch_dir_regardless(
        monkeypatch, shared_paths):
    """Scratch is per-worker, so it is never session-held and never kept back.

    ``mkdtemp`` per bridge, ``(M)`` rather than ``(RX)``, shared with nobody: if
    the session table swept it up with the read dirs, the first worker to finish
    would leave its own *writable* directory reachable from every AppContainer on
    the machine until abax exited — the one grant with real write access.
    """
    shared, console_scratch, macro_scratch = shared_paths
    calls = _icacls_spy(monkeypatch, [])

    console, _ = sw._grant_container_access(str(console_scratch))
    macro, _ = sw._grant_container_access(str(macro_scratch))
    assert sw._container_ace_present(str(macro_scratch)) is True

    assert sw._revoke_container_access(macro) == []

    # The macro's own scratch went, unconditionally and immediately...
    assert len(_ops(calls, "/remove", macro_scratch)) == 1
    assert sw._container_ace_present(str(macro_scratch)) is False
    # ...while the shared path and the sibling's scratch are untouched.
    assert sw._container_ace_present(str(shared)) is True
    assert sw._container_ace_present(str(console_scratch)) is True
    # Neither scratch dir is in the session table; only the shared read dir is.
    held = {os.path.normcase(p) for p in sw._session_grant_paths()}
    assert held == {os.path.normcase(str(shared))}

    assert sw._revoke_container_access(console) == []
    assert sw._container_ace_present(str(console_scratch)) is False


def test_a_path_held_for_the_session_is_not_reported_as_a_leak(
        monkeypatch, shared_paths):
    """Through ``cleanup_process``, the entry point the bridge actually calls.

    Its return value means "these are still on the machine and nothing will ever
    take them off". A shared path deliberately left standing, with an owner and a
    scheduled removal, is not that — and reporting it would train whoever reads
    the list (a future ``abax doctor``) to ignore it.

    The contrast at the end is the point, and it is what makes this more than a
    tautology: the *same* teardown, with a revoke that genuinely fails, must put
    the worker's own scratch dir in the list. One list, two paths, one reported.
    """
    shared, console_scratch, macro_scratch = shared_paths
    procs = []
    for scratch in (console_scratch, macro_scratch):
        granted, unreachable = sw._grant_container_access(str(scratch))
        assert unreachable == []
        proc = _FakeProc()
        proc._sandbox_cleanup = (granted, f"abax-sandbox-test-{scratch.name}")
        proc._sandbox_ctypes = _FakeCtypes()
        procs.append(proc)
    console, macro = procs

    assert sw.cleanup_process(macro) == [], \
        "a path held for the session was reported as a leak"
    assert sw._container_ace_present(str(shared)) is True
    assert sw._container_ace_present(str(macro_scratch)) is False

    # Now the same teardown with a tool that refuses everything. The scratch dir
    # is a real leak and must be named; the shared path is still not one, and is
    # not even attempted — the skip happens before any icacls call.
    monkeypatch.setattr(sw, "_icacls", lambda *a: False)
    assert sw.cleanup_process(console) == [str(console_scratch)]


def test_an_externally_removed_ace_is_repaired_by_the_next_spawn(
        monkeypatch, shared_paths):
    """The table is a record of intent, never of fact.

    This is the failure the discarded refcount shipped: it trusted its own count
    absolutely, so a transient strip by anything outside abax became a permanent
    one — the table said "held", the grant was skipped, and every later worker
    launched into a stripped tree. The current code must ask the machine, and it
    asks with ``/findsid`` (~10 ms) rather than by re-granting blind, because a
    redundant ``/grant`` costs the same full DACL walk as a cold one.
    """
    shared, console_scratch, macro_scratch = shared_paths

    console, _ = sw._grant_container_access(str(console_scratch))
    assert sw._container_ace_present(str(shared)) is True

    # Something outside abax takes the ACE off — an admin, another tool, an
    # `icacls /reset`, a restored backup.
    assert _REAL_ICACLS(str(shared), "/remove", sw.ALL_APP_PACKAGES) is True
    assert sw._container_ace_present(str(shared)) is False
    assert sw._session_grant_paths() == [str(shared)], \
        "the table forgot the path, so this would be a first grant, not a repair"

    calls = _icacls_spy(monkeypatch, [])
    macro, unreachable = sw._grant_container_access(str(macro_scratch))

    assert len(_ops(calls, "/grant", shared)) == 1, \
        "the next spawn trusted the table and skipped a grant that had gone"
    assert sw._container_ace_present(str(shared)) is True
    assert unreachable == []
    assert str(shared) in macro


def test_the_exit_sweep_removes_the_session_grants(shared_paths):
    """The one place the shared ACEs come off, and it is at process exit."""
    shared, console_scratch, _macro = shared_paths
    baseline = _explicit_aces(str(shared))

    granted, unreachable = sw._grant_container_access(str(console_scratch))
    assert unreachable == []
    assert sw._container_ace_present(str(shared)) is True
    # The worker's teardown runs first and leaves it alone, exactly as it does
    # in production; the sweep is what is being measured.
    assert sw._revoke_container_access(granted) == []
    assert sw._container_ace_present(str(shared)) is True

    assert sw._revoke_session_grants() == []

    assert sw._container_ace_present(str(shared)) is False
    assert _explicit_aces(str(shared)) == baseline, \
        "the exit sweep did not leave the machine as it found it"
    assert sw._session_grant_paths() == []


def test_the_exit_sweep_reports_and_logs_what_it_could_not_remove(
        monkeypatch, shared_paths, caplog):
    """A crash is not the only way to leak: a failing ``/remove`` leaks too.

    ``atexit`` discards the return value, which is why the log line is there as
    well — and why the function returns one at all, for a direct caller and for
    a future ``abax doctor``.
    """
    shared, console_scratch, _macro = shared_paths
    sw._grant_container_access(str(console_scratch))
    monkeypatch.setattr(sw, "_icacls", lambda *a: False)

    with caplog.at_level("WARNING", logger=sw.__name__):
        failed = sw._revoke_session_grants()

    assert failed == [str(shared)]
    assert str(shared) in caplog.text
    assert any(r.levelname == "WARNING" for r in caplog.records), caplog.records
    # The table is emptied either way: the process is going, and an entry that
    # outlived the sweep is a lie about what is still owned.
    assert sw._session_grant_paths() == []


def test_the_exit_sweep_does_not_report_a_path_that_no_longer_exists(
        monkeypatch, tmp_path, own_session_table):
    """A tmp tree deleted before exit took its ACL with it; nothing leaked."""
    gone = tmp_path / "went-away"
    gone.mkdir()
    monkeypatch.setattr(sw, "_icacls", lambda *a: True)
    monkeypatch.setattr(sw, "_container_ace_present", lambda p: False)
    assert sw._hold_session_grant(str(gone), "irrelevant", []) is True
    gone.rmdir()
    monkeypatch.setattr(sw, "_icacls", lambda *a: False)

    assert sw._revoke_session_grants() == []


@pytest.mark.parametrize("exc", [
    KeyboardInterrupt(),
    RuntimeError("dictionary changed size during iteration"),
    SystemExit(1),
])
def test_the_exit_sweep_never_raises(monkeypatch, shared_paths, exc):
    """It runs from ``atexit``, during interpreter shutdown.

    A traceback there goes to a stderr the windowed ``abaxw.exe`` does not have,
    and it abandons every path after the one that raised. The guard catches
    ``BaseException`` rather than ``Exception`` on purpose: shutdown can deliver
    things that are neither, and the contract is that the process exits — not
    that the sweep succeeds.
    """
    _shared, console_scratch, _macro = shared_paths
    sw._grant_container_access(str(console_scratch))

    def _boom(*a, **k):
        raise exc

    monkeypatch.setattr(sw, "_icacls", _boom)
    assert sw._revoke_session_grants() == []


def test_a_shared_grant_icacls_refused_is_not_recorded_as_held(
        monkeypatch, tmp_path, own_session_table):
    """Only a grant that landed may register, or fail-closed stops working.

    A path whose grant failed is not reachable, is not in ``granted``, and — the
    half this test exists for — is not in the session table either. Recording it
    would make the next confinement probe, find nothing, and... re-grant, which
    is survivable; but it would also make *this* spawn's ``unreachable`` come
    back empty and wave the launch through.
    """
    shared = tmp_path / "prefix"
    scratch = tmp_path / "scratch"
    for d in (shared, scratch):
        d.mkdir()
    monkeypatch.setattr(sw, "_needed_read_dirs", lambda: [str(shared)])
    monkeypatch.setattr(sw, "_needed_read_files", lambda: [])
    monkeypatch.setattr(sw, "_required_read_targets", lambda: [str(shared)])
    monkeypatch.setattr(sw, "_container_ace_present", lambda path: False)
    monkeypatch.setattr(sw, "_icacls", _grant_failing_on(str(shared)))

    granted, unreachable = sw._grant_container_access(str(scratch))

    assert granted == [str(scratch)]
    assert unreachable == [str(shared)], "the fail-closed refusal stopped working"
    assert sw._session_grant_paths() == [], \
        "a grant that failed registered a hold on an ACE that does not exist"


def test_a_refused_launch_keeps_the_session_grant_and_drops_the_scratch_one(
        fake_ctypes, monkeypatch, tmp_path, own_session_table):
    """``custom_spawn``'s fail-closed teardown, split the way the design splits.

    The refusal revokes ``granted`` from a ``finally``. The worker's own scratch
    dir must come off — it is writable and its worker will never exist. The
    shared path must *not*: a refused launch is not the end of the session, the
    next spawn will want it, and revoking it here would reopen the ~20 s window
    for that next spawn — on behalf of a launch that is failing anyway.
    """
    fake_ctypes()
    shared = tmp_path / "syspath-entry"
    doomed = tmp_path / "prefix"
    scratch = tmp_path / "scratch"
    for d in (shared, doomed, scratch):
        d.mkdir()
    monkeypatch.setattr(sw, "_needed_read_dirs", lambda: [str(shared), str(doomed)])
    monkeypatch.setattr(sw, "_needed_read_files", lambda: [])
    monkeypatch.setattr(sw, "_required_read_targets", lambda: [str(doomed)])
    monkeypatch.setattr(sw, "_container_ace_present", lambda path: False)
    calls = []

    def _icacls(path, *args):
        calls.append((args[0], path))
        return path != str(doomed)

    monkeypatch.setattr(sw, "_icacls", _icacls)

    with pytest.raises(sw.SandboxGrantError) as caught:
        sw.confinement().custom_spawn(["x.exe"], {}, str(scratch), 0)

    assert str(doomed) in str(caught.value), "the refusal stopped naming the path"
    # The worker's own writable grant is gone...
    assert ("/remove", str(scratch)) in calls
    # ...the shared one is kept, and kept honestly: it is in the table, so the
    # next spawn will find it and verify it rather than assume it.
    assert ("/remove", str(shared)) not in calls
    assert sw._session_grant_paths() == [str(shared)]
    # The path that never got an ACE was neither recorded nor removed.
    assert ("/remove", str(doomed)) not in calls


def test_the_exit_sweep_is_armed_by_the_first_grant_and_only_once(
        monkeypatch, shared_paths, no_real_atexit):
    """Armed lazily, from the grant — which is what keeps it out of the child.

    Registering at import would arm it inside the confined worker too, since
    ``console_worker.py`` imports this module to call ``apply_in_child`` (the
    test below measures that half in a real child interpreter). A *second*
    registration would mean a second sweep at exit, walking DACLs the first
    already stripped.

    The second grant here is deliberately a **repair** — the ACE is stripped from
    under the session first — because a plain second spawn takes the reuse fast
    path and never reaches the arming code at all. Only the repair path calls it
    twice, so only the repair path can tell a guarded registration from an
    unguarded one.
    """
    shared, console_scratch, macro_scratch = shared_paths

    sw._grant_container_access(str(console_scratch))
    assert no_real_atexit == [sw._revoke_session_grants]
    assert sw._SESSION_SWEEP_PID == os.getpid()

    assert _REAL_ICACLS(str(shared), "/remove", sw.ALL_APP_PACKAGES) is True
    granted, _unreachable = sw._grant_container_access(str(macro_scratch))

    assert str(shared) in granted, "the repair did not happen; nothing was re-armed"
    assert no_real_atexit == [sw._revoke_session_grants], \
        "a second grant armed a second exit sweep"


def test_nothing_a_confined_child_does_arms_the_exit_sweep(tmp_path):
    """``sandbox_windows`` is imported inside the worker; the sweep must not be.

    ``abax/console_worker.py`` calls ``select_confinement().apply_in_child``, so
    everything below runs *inside the confined child*. A hook armed there would,
    at that child's exit, revoke the **parent's** grants — machine-wide, silently,
    while the parent's other worker was still running on them. That is the exact
    shape of the bug this whole change exists to remove, delivered from the one
    process that has no idea it is doing it.

    Measured in a fresh interpreter rather than in-process, because the property
    is about *import* and this module has long since been imported here: an
    in-process check can only ever assert about calls, and would sail straight
    past an ``atexit.register`` at module level. The child does the full
    child-side surface — the strategy is selected and ``apply_in_child`` is
    called, exactly as ``console_worker`` does it — and then reports whether
    anything armed.
    """
    prog = (
        "import atexit, sys\n"
        f"sys.path.insert(0, {os.path.dirname(os.path.dirname(os.path.abspath(sw.__file__)))!r})\n"
        "from abax import sandbox as sb, sandbox_windows as sw\n"
        "after_import = atexit._ncallbacks()\n"
        f"scratch = {str(tmp_path)!r}\n"
        "strat = sb.select_confinement()\n"
        "strat.available(); strat.describe()\n"
        "strat.wrap_argv([sys.executable, '-c', 'pass'], scratch)\n"
        "strat.child_env({'PATH': 'C:\\\\Windows'}, scratch)\n"
        "strat.apply_in_child(scratch)\n"
        "sw._profile_name(); sw._needed_read_dirs(); sw._needed_read_files()\n"
        "print('SWEEP_PID', sw._SESSION_SWEEP_PID)\n"
        "print('HELD', sw._session_grant_paths())\n"
        "print('ADDED_BY_CHILD_WORK', atexit._ncallbacks() - after_import)\n"
    )
    r = subprocess.run([sys.executable, "-c", prog], capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    reported = dict(line.split(" ", 1) for line in r.stdout.splitlines() if line)

    # The direct signal: nothing in the child armed the sweep, so nothing at the
    # child's exit will revoke what the parent granted.
    assert reported["SWEEP_PID"] == "None", r.stdout
    assert reported["HELD"] == "[]", r.stdout
    assert reported["ADDED_BY_CHILD_WORK"] == "0", r.stdout


def test_the_exit_sweep_refuses_to_run_in_a_process_that_did_not_arm_it(
        monkeypatch, shared_paths):
    """Belt and braces for the same hazard, from the other end.

    Windows has no ``fork`` and ``multiprocessing`` re-imports this module fresh,
    so nothing here can inherit the registration today. The check costs one
    comparison and the failure it guards against — a child revoking its parent's
    machine-wide grants — is silent and total.
    """
    shared, console_scratch, _macro = shared_paths
    sw._grant_container_access(str(console_scratch))
    held = sw._session_grant_paths()
    calls = []
    monkeypatch.setattr(sw, "_icacls",
                        lambda path, *a: calls.append((a[0], path)) is None)
    monkeypatch.setattr(sw, "_SESSION_SWEEP_PID", os.getpid() + 1)

    assert sw._revoke_session_grants() == []

    assert calls == [], "a child process revoked its parent's grants"
    assert sw._session_grant_paths() == held
    assert sw._container_ace_present(str(shared)) is True


def test_concurrent_first_use_grants_the_shared_path_exactly_once(
        monkeypatch, tmp_path, own_session_table):
    """The lock must be held *across* the icacls call, not just the dict access.

    Both bridges spawn from worker threads (``abax/workers.py``'s FuncWorker), so
    two first-use grants genuinely race. What makes the race dangerous is the
    shape of a real ``icacls /grant``: it is a DACL propagation walk that writes
    the root first and the leaves last, so ``/findsid`` — which asks about the
    root — answers "present" long before the container can actually read the
    tree. A second spawn that probes mid-walk sees the ACE, skips the grant, and
    launches a child into a half-propagated tree, which is precisely how measured
    (3) kills children: ``Fatal Python error: init_fs_encoding``.

    The fake models that ordering, and the ordering is the whole point: the
    effect lands at the *end* of the walk, not at the start. An earlier fake in
    this file's history set the flag and then slept, which is backwards — it
    modelled an instantaneous write followed by an irrelevant pause, and no
    amount of threading against it could reproduce the window.

    Seeded as a *repair* (the table already knows the path, the ACE has gone) so
    every thread reaches the probe. icacls is faked because 60 real DACL walks
    would take twenty minutes; the ACL behaviour is pinned against the real tool
    by the tests above.
    """
    shared = str(tmp_path / "interpreter")
    key = sw._shared_key(shared)
    monkeypatch.setattr(sw, "_needed_read_dirs", lambda: [shared])
    monkeypatch.setattr(sw, "_needed_read_files", lambda: [])
    monkeypatch.setattr(sw, "_required_read_targets", lambda: [])

    walk = 0.4
    state = {"visible": False, "complete": False}
    state_lock = threading.Lock()
    ops: list[str] = []

    def _fake_icacls(path, *args):
        if sw._shared_key(path) != key:
            return True                       # a scratch dir; instant and local
        with state_lock:
            ops.append(args[0])
        if args[0] == "/grant":
            time.sleep(walk / 4)              # the root's DACL is written early
            with state_lock:
                state["visible"] = True       # ...so /findsid can already see it
            time.sleep(walk * 3 / 4)          # the leaves take the rest
            with state_lock:
                state["complete"] = True      # only now can a child read the tree
        else:
            time.sleep(walk)
            with state_lock:
                state["visible"] = state["complete"] = False
        return True

    monkeypatch.setattr(sw, "_icacls", _fake_icacls)
    monkeypatch.setattr(sw, "_container_ace_present",
                        lambda path: state["visible"])
    # The repair shape: this session holds the path, and the ACE has been
    # stripped from under it.
    sw._SESSION_GRANTS[key] = (shared, f"{sw.ALL_APP_PACKAGES}:(OI)(CI)(RX)")

    threads = 6
    early: list[str] = []
    reported: list[str] = []
    barrier = threading.Barrier(threads)

    def _spawn(worker: int) -> None:
        barrier.wait(30)
        time.sleep(worker * walk / (threads + 1))   # arrive across the window
        granted, _unreachable = sw._grant_container_access(
            os.path.join(str(tmp_path), f"scratch-{worker}"))
        with state_lock:
            if not state["complete"]:
                early.append(f"w{worker}")
        failed = sw._revoke_container_access(granted)
        if failed:
            reported.append(f"w{worker}: {failed}")

    runners = [threading.Thread(target=_spawn, args=(i,)) for i in range(threads)]
    for t in runners:
        t.start()
    for t in runners:
        t.join(120)
    assert not any(t.is_alive() for t in runners), "a grant cycle hung"

    assert early == [], (
        f"{len(early)} spawn(s) of {threads} were told the shared path was ready "
        f"while the grant walk was still propagating: {early}")
    assert ops == ["/grant"], (
        "the shared path's icacls sequence was not a single grant — either two "
        f"spawns granted at once or a teardown removed it: {ops}")
    assert sw._session_grant_paths() == [shared]


# --------------------------------------------------------------------------- #
# the two CROSS-process windows (issue #9)
# --------------------------------------------------------------------------- #
#
# Holding the shared grants for the session makes them safe from *this* process's
# teardowns. The ACE is machine-wide, so a second abax reopens the problem twice
# over, and both were measured with two real processes (P1 holding the grants and
# a live worker, P2 granting and then exiting so its atexit sweep walks the same
# DACLs, P1 spawning a fresh confined worker every 3 s through that walk):
#
#   W1  P2's sweep strips paths P1's LIVE worker is running on. Measured:
#       `FAIL IMPORT wave ModuleNotFoundError: No module named 'wave'` from a
#       worker that was up and answering. Closed by the holder record.
#   W2  P1 probes DURING P2's walk. icacls writes the root's DACL first and the
#       leaves last, so `/findsid` answers True about a half-stripped tree, the
#       grant is skipped, and the child dies in interpreter startup. Measured:
#       1 spawn of 7. Closed by the machine-wide mutex.
#
# The acceptance measurement for the pair is the reproduction itself (0 of 7 and
# 0 of 8 after, against 1 of 7 and 1 of 8 before); what these tests pin is the
# mechanism, so a later change cannot quietly move a call out from under the
# mutex or teach the sweep to ignore a live holder.


def _winsandbox():
    """The lazily-imported ctypes layer, as an object tests can patch."""
    from abax import _winsandbox_ctypes as C

    return C


@pytest.fixture
def private_acl_mutex(monkeypatch):
    """Give this test its own named mutex instead of the production one.

    The mutex is machine-wide by design, so a test that deliberately abandons it
    — or holds it from a child process — would otherwise be reaching into every
    other test in the run, and into any abax the developer happens to have open.
    The production *name* is asserted separately, in
    ``test_the_acl_mutex_is_scoped_to_the_logon_session``.
    """
    name = f"Local\\abax-test-acl-{os.getpid()}-{os.urandom(4).hex()}"
    monkeypatch.setattr(sw, "_ACL_MUTEX_NAME", name)
    monkeypatch.setattr(sw, "_ACL_MUTEX_HANDLE", None)
    yield name
    handle = sw._ACL_MUTEX_HANDLE          # created during the test, if at all
    if handle is not None:
        _winsandbox().close_handle(handle)


@pytest.fixture
def acl_trace(monkeypatch):
    """One interleaved record of the mutex, the icacls calls and the probes.

    The property under test is an *ordering* — every DACL read and every DACL
    write happens between one acquire and one release — and no snapshot of an ACL
    can see an ordering. Everything still runs for real underneath, so a test
    that asserts the order also still asserts the effect.
    """
    C = _winsandbox()
    trace: list[str] = []
    real_wait, real_release = C.wait_for_mutex, C.release_mutex
    real_icacls, real_probe = sw._icacls, sw._container_ace_present

    def _wait(handle, timeout_ms):
        code = real_wait(handle, timeout_ms)
        trace.append("acquire" if code in (C.WAIT_OBJECT_0, C.WAIT_ABANDONED)
                     else "acquire-FAILED")
        return code

    def _release(handle):
        trace.append("release")
        return real_release(handle)

    def _icacls(path, *args):
        trace.append("icacls " + args[0])
        return real_icacls(path, *args)

    def _probe(path):
        trace.append("probe")
        return real_probe(path)

    monkeypatch.setattr(C, "wait_for_mutex", _wait)
    monkeypatch.setattr(C, "release_mutex", _release)
    monkeypatch.setattr(sw, "_icacls", _icacls)
    monkeypatch.setattr(sw, "_container_ace_present", _probe)
    return trace


def _assert_all_inside_the_mutex(trace: "list[str]") -> None:
    """Every ACL operation in *trace* sits between one acquire and one release."""
    assert trace, "nothing was recorded at all"
    assert trace[0] == "acquire", f"an ACL operation preceded the mutex: {trace}"
    assert trace[-1] == "release", f"the mutex was released early: {trace}"
    assert "acquire" not in trace[1:], f"the mutex was taken twice: {trace}"
    assert "release" not in trace[:-1], f"the mutex was released twice: {trace}"
    assert any(t.startswith("icacls") for t in trace[1:-1]), \
        f"no real ACL work happened, so the ordering proves nothing: {trace}"


def test_the_grant_holds_the_acl_mutex_across_every_probe_and_every_walk(
        monkeypatch, shared_paths, private_acl_mutex, acl_trace):
    """W2's fix, and the reason it has to cover the *reads* as well as the writes.

    A grant that serialised only its `/grant` calls would still let a second
    process's ``/findsid`` land mid-walk, see the root's freshly-written ACE, skip
    its own grant and launch a child into a tree whose leaves are not done yet.
    That is the measured death — so the probe, the reuse fast path, the grant and
    `_unreachable_requirements`' pre-existing-ACE check must all be inside.
    """
    _shared, console_scratch, _macro = shared_paths

    granted, unreachable = sw._grant_container_access(str(console_scratch))

    assert unreachable == []
    _assert_all_inside_the_mutex(acl_trace)
    assert len(granted) == 2


def test_the_exit_sweep_holds_the_acl_mutex_across_its_walk(
        shared_paths, private_acl_mutex, acl_trace):
    """The other side of W2: nobody may observe a tree this sweep is stripping."""
    _shared, console_scratch, _macro = shared_paths
    sw._grant_container_access(str(console_scratch))
    del acl_trace[:]                       # the grant's own cycle is tested above

    assert sw._revoke_session_grants() == []

    _assert_all_inside_the_mutex(acl_trace)
    assert "icacls /remove" in acl_trace


def test_a_workers_teardown_does_not_take_the_acl_mutex(
        shared_paths, private_acl_mutex, acl_trace):
    """And it must not: teardown runs on the GUI thread.

    ``ConsoleBridge`` closes a worker synchronously from the GUI thread, so
    waiting there for another process's ~19 s DACL walk would freeze the window
    for that long — to revoke a `mkdtemp` scratch dir that is this worker's alone
    and that no other process has ever heard of. The mutex guards the *shared*
    paths; the scratch dir is not one.
    """
    _shared, console_scratch, _macro = shared_paths
    granted, _ = sw._grant_container_access(str(console_scratch))
    del acl_trace[:]

    assert sw._revoke_container_access(granted) == []

    assert "acquire" not in acl_trace, \
        f"a worker teardown waited on the machine-wide mutex: {acl_trace}"
    assert "icacls /remove" in acl_trace, "the scratch grant was not removed"


def test_the_probe_is_not_trusted_when_the_acl_mutex_could_not_be_taken(
        monkeypatch, shared_paths, private_acl_mutex):
    """The degradation, and why it is a re-grant rather than a shrug.

    `_container_ace_present` is only *trustworthy* because the mutex guarantees
    nobody is walking the tree while it answers. Without the mutex a True is
    exactly the answer that killed the child in the measurement, so the fast path
    is skipped and the grant is re-issued — a redundant ~20 s walk instead of a
    worker that cannot read its own stdlib.
    """
    shared, console_scratch, macro_scratch = shared_paths
    sw._grant_container_access(str(console_scratch))
    assert sw._container_ace_present(str(shared)) is True
    assert sw._session_grant_paths() == [str(shared)], "not the reuse shape"

    C = _winsandbox()
    monkeypatch.setattr(C, "wait_for_mutex", lambda h, ms: C.WAIT_TIMEOUT)
    calls = _icacls_spy(monkeypatch, [])

    granted, unreachable = sw._grant_container_access(str(macro_scratch))

    assert unreachable == []
    assert str(shared) in granted
    assert len(_ops(calls, "/grant", shared)) == 1, (
        "the reuse fast path trusted a /findsid probe taken while another "
        "process may have been mid-walk")


def test_an_abandoned_acl_mutex_is_taken_and_still_released(
        monkeypatch, shared_paths, private_acl_mutex, caplog):
    """A process killed mid-walk must not wedge every later abax.

    Windows hands the next waiter ownership plus a ``WAIT_ABANDONED`` status
    rather than leaving the mutex owned forever, so the recovery is simply to
    treat 0x80 as success — and, critically, to still release it afterwards.
    Reading 0x80 as a failure would be the wedge: every abax on the box would
    then run unserialised, for the life of the boot, and quietly.
    """
    _shared, console_scratch, _macro = shared_paths
    C = _winsandbox()
    released: list = []
    real_release = C.release_mutex
    monkeypatch.setattr(C, "wait_for_mutex", lambda h, ms: C.WAIT_ABANDONED)
    monkeypatch.setattr(
        C, "release_mutex",
        lambda h: (released.append(h), real_release(h))[1])

    with caplog.at_level("WARNING", logger=sw.__name__):
        with sw._acl_mutex(5, "a test") as held:
            assert held is True, "an abandoned mutex is owned, not lost"

    assert len(released) == 1, "an abandoned mutex was never released"
    assert "abandoned" in caplog.text.lower()


def test_a_mutex_that_cannot_be_had_at_all_does_not_stop_the_grant(
        monkeypatch, shared_paths, caplog):
    """Fail *open*, deliberately, and say so.

    Refusing to grant means refusing to launch, and the mutex is not the security
    boundary — the AppContainer and the worker's own selftest are. A squatted
    name or a handle exhaustion costs cross-process serialisation, which is what
    abax had before this existed; it must not cost the sandbox.
    """
    shared, console_scratch, _macro = shared_paths
    monkeypatch.setattr(sw, "_acl_mutex_handle", lambda: None)

    with caplog.at_level("WARNING", logger=sw.__name__):
        granted, unreachable = sw._grant_container_access(str(console_scratch))

    assert unreachable == []
    assert str(shared) in granted
    assert sw._container_ace_present(str(shared)) is True


def test_the_acl_mutex_is_scoped_to_the_logon_session():
    """``Local\\``, and the reasoning is measured rather than inherited.

    The usual reason to avoid ``Global\\`` is that it needs
    SeCreateGlobalPrivilege — which is **false** on this platform: a
    non-elevated token with no such privilege in ``whoami /priv`` created a
    ``Global\\`` mutex successfully. The real reasons are that a ``Global\\``
    object carries its creator's DACL (so a second *user* could not open it
    anyway, without publishing a machine-wide-writable synchronisation object and
    the denial-of-service surface that comes with it) and that elevation does not
    change logon session, so the pair that actually collides — an elevated abax
    and a plain one on the same desktop — share the ``Local\\`` namespace.
    """
    assert sw._ACL_MUTEX_NAME.startswith("Local\\")
    assert "abax" in sw._ACL_MUTEX_NAME


def test_the_acl_mutex_really_excludes_another_process(private_acl_mutex):
    """The primitive itself, against a second real process.

    Deliberately *not* in the ``sandbox_e2e`` tier even though it drives a second
    process: that tier is the eight tests that launch a real AppContainer and
    verify the confinement promise (``test_sandbox_gate.py`` pins its membership
    by count). This one launches an ordinary process to hold a mutex. Adding it
    there would dilute what selecting the tier means. It still runs in every
    ordinary suite run; the marker skips nothing.

    Everything above fakes ``wait_for_mutex`` to get a deterministic ordering;
    this one does not fake anything, because the claim that closes W2 is a claim
    about two *processes* and a mock cannot make it.
    """
    prog = (
        "import ctypes, sys, time\n"
        "from ctypes import wintypes\n"
        "k32 = ctypes.WinDLL('kernel32', use_last_error=True)\n"
        "k32.CreateMutexW.restype = wintypes.HANDLE\n"
        "k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]\n"
        f"h = k32.CreateMutexW(None, False, {private_acl_mutex!r})\n"
        "k32.WaitForSingleObject(h, 0)\n"
        "print('HELD', flush=True)\n"
        "time.sleep(2.0)\n"
        "k32.ReleaseMutex(h)\n"
    )
    child = subprocess.Popen([sys.executable, "-u", "-c", prog],
                             stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "HELD"
        t0 = time.perf_counter()
        with sw._acl_mutex(30, "a test") as held:
            waited = time.perf_counter() - t0
            assert held is True, "never got the mutex the child gave up"
        assert waited > 1.0, (
            f"took the mutex after {waited:.2f}s while another process held it — "
            "two DACL walks can overlap")
    finally:
        child.wait(timeout=30)


def test_a_process_that_died_holding_the_acl_mutex_does_not_wedge_the_next(
        monkeypatch, private_acl_mutex):
    """WAIT_ABANDONED, end to end, with a child that really is killed.

    The unit test above proves the *code* recovers from 0x80; this proves Windows
    really delivers 0x80 rather than blocking forever, which is the half that
    cannot be asserted against a fake and the half that decides whether one
    crashed abax bricks the feature until reboot. So the wait code is recorded
    and asserted, not merely the outcome: without that, the test passes just as
    happily when the mutex object died with the child and this process created a
    brand new one — which is not the situation being claimed, and is what happens
    if the handle below is opened after the kill instead of before it.
    """
    prog = (
        "import ctypes, sys, time\n"
        "from ctypes import wintypes\n"
        "k32 = ctypes.WinDLL('kernel32', use_last_error=True)\n"
        "k32.CreateMutexW.restype = wintypes.HANDLE\n"
        "k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]\n"
        f"h = k32.CreateMutexW(None, False, {private_acl_mutex!r})\n"
        "k32.WaitForSingleObject(h, 0)\n"
        "print('HELD', flush=True)\n"
        "time.sleep(30)\n"
    )
    C = _winsandbox()
    codes: list = []
    real_wait = C.wait_for_mutex
    monkeypatch.setattr(
        C, "wait_for_mutex",
        lambda h, ms: (codes.append(real_wait(h, ms)), codes[-1])[1])

    child = subprocess.Popen([sys.executable, "-u", "-c", prog],
                             stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "HELD"
        # Open our handle FIRST, so the kernel object outlives the child and the
        # abandonment is really delivered rather than the name being recycled.
        assert sw._acl_mutex_handle() is not None
        child.kill()                       # dies still owning the mutex
        child.wait(timeout=30)
        t0 = time.perf_counter()
        with sw._acl_mutex(20, "a test") as held:
            assert held is True, "a crashed holder wedged the mutex"
        assert time.perf_counter() - t0 < 10
        assert codes == [C.WAIT_ABANDONED], (
            f"expected Windows to hand over an abandoned mutex, got {codes}")
        # ...and it is still usable afterwards, which is what "released it
        # anyway" buys: an abandoned mutex left unreleased wedges the next one.
        with sw._acl_mutex(5, "a test") as held_again:
            assert held_again is True
        assert codes[-1] == C.WAIT_OBJECT_0, codes
    finally:
        if child.poll() is None:
            child.kill()


# --- the cross-process holder record (W1) ------------------------------------


def _plant_holder(pid: int, created: int, paths=(), *, retiring=False) -> str:
    """A holder record for *pid*, as another process would have left it.

    ``retiring=True`` writes the mark a holder puts down when it enters its own
    exit sweep — the statement that it is still running but is not relying on
    these grants any more (see ``sandbox_windows._HOLDER_RETIRING_MARK``).
    """
    os.makedirs(sw._holder_dir(), exist_ok=True)
    record = os.path.join(sw._holder_dir(),
                          f"{pid}-{created}{sw._HOLDER_SUFFIX}")
    body = "".join(str(p) + "\n" for p in paths)
    if retiring:
        body = sw._HOLDER_RETIRING_MARK + "\n" + body
    with open(record, "w", encoding="utf-8") as fh:
        fh.write(body)
    return record


@pytest.fixture
def a_live_process():
    """A real process that stays up for the duration of the test."""
    child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"],
                             stdin=subprocess.PIPE)
    yield child
    child.kill()
    child.wait(timeout=30)


def test_a_live_holder_stops_the_exit_sweep_from_removing_anything(
        shared_paths, a_live_process):
    """W1: the sweep is correct *for this process* and wrong for the machine.

    P2's sweep removes exactly what P2 granted — which is the same interpreter
    prefix P1 is running on, so P1's live worker loses its standard library on
    its very next import. Measured with two real processes. The ACEs come off
    only when the last holder goes.
    """
    shared, console_scratch, _macro = shared_paths
    sw._grant_container_access(str(console_scratch))
    assert sw._container_ace_present(str(shared)) is True
    created = _winsandbox().process_create_time(a_live_process.pid)
    assert created is not None
    _plant_holder(a_live_process.pid, created)

    assert sw._revoke_session_grants() == [], "a deferral is not a leak report"

    assert sw._container_ace_present(str(shared)) is True, \
        "the sweep stripped an ACE another live process was relying on"
    # The table is still emptied: this process is on its way out either way, and
    # an entry that outlived the sweep would be a lie about what it still owns.
    assert sw._session_grant_paths() == []


def test_a_deferred_sweep_hands_its_paths_to_whoever_goes_last(
        shared_paths, a_live_process):
    """Deferring is not forgetting, and the handoff falls out of the mechanism.

    Two abax processes need not hold the *same* paths — different working
    directories put different entries on ``sys.path`` — so a process that defers
    must leave a record of what it was holding, or its unique paths keep their
    ACEs forever. It leaves its own record in place; it is exiting, so that
    record goes stale by definition, and the last holder out unions it in.
    """
    shared, console_scratch, _macro = shared_paths
    sw._grant_container_access(str(console_scratch))
    created = _winsandbox().process_create_time(a_live_process.pid)
    _plant_holder(a_live_process.pid, created)
    mine = sw._holder_record_path()

    sw._revoke_session_grants()

    assert mine and os.path.exists(mine), \
        "the deferring process deleted its own record; its paths are now orphaned"
    assert sw._holder_record_paths(mine) == [str(shared)]


def test_a_stale_holder_does_not_block_the_sweep(shared_paths):
    """A crashed abax must not make the ACEs permanent.

    This is the failure mode a naive holder count ships: one hard kill and the
    machine-wide grant on the developer's interpreter prefix has nothing left
    that will ever remove it. Liveness is asked of the operating system, not of
    the record.
    """
    shared, console_scratch, _macro = shared_paths
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait(timeout=30)
    sw._grant_container_access(str(console_scratch))
    record = _plant_holder(dead.pid, 1)
    mine = sw._holder_record_path()

    assert sw._revoke_session_grants() == []

    assert sw._container_ace_present(str(shared)) is False, \
        "a dead process's record blocked the sweep"
    assert not os.path.exists(record), "the stale record was left to block again"
    assert mine and not os.path.exists(mine), \
        "a sweep that really ran must drop its own record"


def test_a_reused_pid_is_not_mistaken_for_the_process_that_wrote_the_record(
        shared_paths, a_live_process):
    """Why the record is PID *plus* creation time and not a bare PID.

    PIDs are reused. A record naming a PID that some unrelated process now
    occupies would look live for as long as the box stays up, and the sweep would
    never run again — the same permanent ACE as the stale case, arrived at from
    the opposite direction. The creation time (100 ns) pins the record to one
    process rather than to one slot.
    """
    shared, console_scratch, _macro = shared_paths
    sw._grant_container_access(str(console_scratch))
    created = _winsandbox().process_create_time(a_live_process.pid)
    # The PID is genuinely running; it is simply not the process that wrote this.
    _plant_holder(a_live_process.pid, created + 1)

    assert sw._revoke_session_grants() == []

    assert sw._container_ace_present(str(shared)) is False, \
        "a recycled PID kept the machine-wide grants alive"


def test_the_last_sweep_removes_what_a_dead_holder_recorded_and_never_did(
        tmp_path, shared_paths):
    """The union, which is what makes the handoff — and crash recovery — real.

    A record left by a process that deferred, or by one that was killed between
    granting and sweeping, names paths nobody else is going to remove. Whoever
    sweeps last takes them off too, so the leak the design otherwise trades W1
    for does not exist, and a previous run's crash leftovers are collected as a
    side effect.
    """
    shared, console_scratch, _macro = shared_paths
    orphaned = tmp_path / "someone-elses-syspath-entry"
    orphaned.mkdir()
    assert _REAL_ICACLS(str(orphaned), "/grant",
                        f"{sw.ALL_APP_PACKAGES}:(OI)(CI)(RX)") is True
    assert sw._container_ace_present(str(orphaned)) is True
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait(timeout=30)
    record = _plant_holder(dead.pid, 1, [str(orphaned)])

    sw._grant_container_access(str(console_scratch))
    assert sw._revoke_session_grants() == []

    assert sw._container_ace_present(str(shared)) is False
    assert sw._container_ace_present(str(orphaned)) is False, \
        "the dead holder's paths kept their ACEs with nothing left to remove them"
    assert not os.path.exists(record)


@pytest.mark.parametrize("line,ok", [
    ("C:\\Python313", True),
    ("c:/python313", True),
    ("D:\\a checkout\\with spaces", True),
    # UNC: `os.path.isabs` says True and `icacls` on one is a network operation.
    ("\\\\attacker\\share\\x", False),
    ("//attacker/share/x", False),
    # The device namespace, likewise absolute and likewise never granted here.
    ("\\\\?\\C:\\x", False),
    ("\\\\.\\pipe\\x", False),
    # Already rejected by `isabs` on 3.13; pinned so a future change is noticed.
    ("\\rooted-but-driveless", False),
    ("C:relative", False),
    ("relative\\path", False),
    ("", False),
    (sw._HOLDER_RETIRING_MARK, False),
])
def test_only_local_drive_letter_paths_are_read_out_of_a_holder_record(line, ok):
    """``_HOLDER_MAX_PATHS`` bounds how many; this bounds *what*.

    The sweep runs ``icacls <path> /remove`` for every line that survives this
    filter, on a file written by another process. A UNC path is the one that
    matters: ``icacls`` on ``\\\\host\\share`` is a network operation that
    authenticates as this user and blocks for the SMB timeout when nothing
    answers — and the sweep holds the machine-wide ACL mutex while it waits, so
    every other abax on the box stalls behind it. 64 such lines is minutes of
    that, during interpreter shutdown.

    Deliberately NOT narrowed to paths this process would itself grant: the union
    exists to collect the paths another run held and this one would not (see
    ``test_the_last_sweep_removes_what_a_dead_holder_recorded_and_never_did``),
    and narrowing it there would turn every divergent ``sys.path`` entry into a
    permanent machine-wide ACE.
    """
    assert sw._sweepable_record_path(line) is ok


def test_a_holder_record_cannot_send_the_exit_sweep_to_a_network_path(
        monkeypatch, tmp_path, shared_paths):
    """The filter, end to end, against the real sweep.

    A record naming a UNC path, a device path and a local one: the local path is
    collected and stripped exactly as the handoff requires, and no ``icacls``
    invocation is ever made against the other two.
    """
    _shared, console_scratch, _macro = shared_paths
    orphaned = tmp_path / "someone-elses-syspath-entry"
    orphaned.mkdir()
    assert _REAL_ICACLS(str(orphaned), "/grant",
                        f"{sw.ALL_APP_PACKAGES}:(OI)(CI)(RX)") is True
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait(timeout=30)
    record = _plant_holder(dead.pid, 1,
                           ["\\\\10.255.255.1\\share\\x", "\\\\?\\C:\\dev",
                            str(orphaned)])
    assert sw._holder_record_paths(record) == [str(orphaned)]

    sw._grant_container_access(str(console_scratch))
    calls = _icacls_spy(monkeypatch, [])

    assert sw._revoke_session_grants() == []

    assert sw._container_ace_present(str(orphaned)) is False, \
        "the filter ate a legitimate handoff path"
    assert [c for c in calls if c[1].startswith("\\\\")] == [], \
        "the sweep ran icacls against a UNC or device path from a record"


def test_a_truncated_holder_record_is_still_identified_and_swept(shared_paths):
    """Why the identity lives in the file NAME and not in the contents.

    A process killed between ``open`` and ``write`` leaves a zero-length file. If
    that file were the identity, it would be unreadable and would have to be
    either ignored (an ACE nobody removes) or trusted (a sweep nobody runs). In
    the name, it survives the kill intact: the record still says who it belonged
    to, that process is still checkable, and the sweep proceeds.
    """
    shared, console_scratch, _macro = shared_paths
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait(timeout=30)
    record = _plant_holder(dead.pid, 1)
    assert os.path.getsize(record) == 0

    sw._grant_container_access(str(console_scratch))
    assert sw._revoke_session_grants() == []

    assert sw._container_ace_present(str(shared)) is False
    assert not os.path.exists(record)


def test_the_holder_record_is_on_disk_before_the_mutex_is_released(
        shared_paths, private_acl_mutex, monkeypatch):
    """The ordering that lets ``custom_spawn`` launch outside the mutex.

    ``CreateProcessW`` runs after the grant returns, with the mutex already
    given up. What keeps another process from stripping the tree in that gap is
    not the mutex but the holder record — so the record has to be published
    while the mutex is still held, or the gap is exactly W1 again, one spawn
    wide.
    """
    _shared, console_scratch, _macro = shared_paths
    C = _winsandbox()
    seen: list = []
    real_release = C.release_mutex

    def _release(handle):
        record = sw._holder_record_path()
        seen.append(bool(record) and os.path.exists(record))
        return real_release(handle)

    monkeypatch.setattr(C, "release_mutex", _release)

    sw._grant_container_access(str(console_scratch))

    assert seen == [True], \
        "the mutex was released before this process announced it was a holder"


def test_publishing_a_holder_record_leaves_no_partial_file(shared_paths):
    """Written to a sibling and ``os.replace``d, so a reader sees one version.

    The contents are the paths another process will remove on this one's behalf.
    A half-written list is a half-removed leak, so the write is atomic and the
    temporary never survives.
    """
    _shared, console_scratch, _macro = shared_paths
    sw._grant_container_access(str(console_scratch))

    names = sorted(os.listdir(sw._holder_dir()))
    assert names == [os.path.basename(sw._holder_record_path())], names
    assert not any(n.endswith(".new") for n in names)


def test_holder_records_live_under_the_user_data_dir(shared_paths):
    """Not a world-writable location, and the reason is the sweep.

    A record someone else could plant makes abax skip its own cleanup — the ACEs
    stay on the interpreter prefix and the process that granted them exits
    believing someone else will tidy up. ``DATA_DIR`` on Windows is
    ``%LOCALAPPDATA%\\abax``; this used to add "whose DACL is this user, SYSTEM
    and Administrators (measured with icacls; no world-writable ACE)", which was
    two ACEs short of what icacls prints — see the note above the holder record
    in ``abax/sandbox_windows.py`` for the measured five and for what a principal
    who *can* write here would actually gain (less than dropping an ``init.py``
    in the same directory, which is executed as arbitrary Python by design). What
    this test pins is the placement itself: a shared temp directory would not do.
    """
    import abax._runtime as rt

    sw._grant_container_access(str(shared_paths[1]))
    holder = os.path.normcase(os.path.abspath(sw._holder_dir()))

    assert holder.startswith(os.path.normcase(os.path.abspath(str(rt.DATA_DIR))))
    assert os.path.normcase(os.path.abspath(sw._holder_record_path())) \
        .startswith(holder)


def test_nothing_a_confined_child_does_publishes_a_holder_record(tmp_path):
    """The child imports this module too; a record from there is a machine-wide
    veto on everyone else's cleanup.

    ``console_worker.py`` calls ``select_confinement().apply_in_child``, so the
    whole child-side surface runs inside the confined worker. A holder record
    written there would outlive nothing and block everything: every other abax's
    exit sweep would defer to a process that never held a grant in its life.
    Measured in a fresh interpreter, for the same reason the ``atexit`` sibling
    of this test is — the property is about what merely *importing* does.
    """
    prog = (
        "import os, sys\n"
        f"sys.path.insert(0, {os.path.dirname(os.path.dirname(os.path.abspath(sw.__file__)))!r})\n"
        "from abax import sandbox as sb, sandbox_windows as sw\n"
        f"scratch = {str(tmp_path / 'scratch')!r}\n"
        "os.makedirs(scratch, exist_ok=True)\n"
        "strat = sb.select_confinement()\n"
        "strat.available(); strat.describe()\n"
        "strat.wrap_argv([sys.executable, '-c', 'pass'], scratch)\n"
        "strat.child_env({'PATH': 'C:\\\\Windows'}, scratch)\n"
        "strat.apply_in_child(scratch)\n"
        "sw._profile_name(); sw._needed_read_dirs(); sw._needed_read_files()\n"
        "d = sw._holder_dir()\n"
        "print('RECORDS', sorted(os.listdir(d)) if os.path.isdir(d) else [])\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([p for p in sys.path if p])
    env["APPDATA"] = str(tmp_path / "roaming")
    env["LOCALAPPDATA"] = str(tmp_path / "local")
    r = subprocess.run([sys.executable, "-c", prog], capture_output=True,
                       text=True, timeout=120, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "RECORDS []" in r.stdout, r.stdout + r.stderr


# --- "is anyone still relying on these ACEs?" is not "is that PID running?" ---
#
# The sweep asks the operating system one question about each foreign record and
# acts on the answer, so the two ways that question can be got wrong are the two
# ways the machine-wide ACEs go wrong:
#
#   * answering "gone" for a process that is running strips the standard library
#     out from under a live worker — issue #9 again, and the ACCESS_DENIED case
#     below is a new door onto it;
#   * answering "still relying" for every process that happens to be running
#     lets two abaxes exiting together each defer to the other, leaving the ACEs
#     with no owner at all.
#
# Everything from here to the launcher section pins one or the other.


def _open_process_error(pid: int) -> int:
    """``GetLastError`` from ``OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)``.

    0 means the handle came back (and is closed again here). The two failures
    that matter are 5 (``ERROR_ACCESS_DENIED`` — that PID is running and this
    token may not interrogate it) and 87 (``ERROR_INVALID_PARAMETER`` — there is
    no such process).
    """
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    op = k32.OpenProcess
    op.restype = wintypes.HANDLE
    op.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    ctypes.set_last_error(0)
    handle = op(0x1000, False, pid)
    if handle:
        k32.CloseHandle(wintypes.HANDLE(handle))
        return 0
    return ctypes.get_last_error()


def _a_pid_we_may_not_open() -> "int | None":
    """A PID that is **running** and that this token cannot ``OpenProcess``.

    Scanned rather than hardcoded: pid 4 (System) answers ERROR_ACCESS_DENIED
    from a plain non-elevated Python on this box — as do 7 more under 40000 —
    but an elevated run opens some of them and a CI runner's process table is not
    this desktop's. None when every PID on the box is open to us, which is the
    one case the caller has to handle rather than assert.
    """
    for pid in range(4, 40000, 4):
        if _open_process_error(pid) == 5:          # ERROR_ACCESS_DENIED
            return pid
    return None


def _a_pid_that_does_not_exist() -> "int | None":
    """A PID no process holds — ``OpenProcess`` answers ERROR_INVALID_PARAMETER."""
    for pid in (999_999, 999_995, 999_991, 888_887, 777_775):
        if _open_process_error(pid) == 87:         # ERROR_INVALID_PARAMETER
            return pid
    return None


def test_process_create_time_tells_gone_from_could_not_ask():
    """The three answers, because two of them used to be one.

    ``OpenProcess`` failing was read as "that process is gone" whatever the
    reason, and ERROR_ACCESS_DENIED is the *opposite* fact: the PID belongs to an
    elevated, another-user or protected process, i.e. one that is running. Both
    came back ``None``, both compared unequal to the recorded creation time, and
    the caller filed a live holder as stale.
    """
    C = _winsandbox()

    assert isinstance(C.process_create_time(os.getpid()), int), \
        "this process cannot read its own creation time"

    # Exited, but its handle is still held by Popen, so the PID still resolves.
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait(timeout=30)
    assert C.process_create_time(dead.pid) is None

    absent = _a_pid_that_does_not_exist()
    assert absent is not None, "found no free PID to ask about"
    assert C.process_create_time(absent) is None

    denied = _a_pid_we_may_not_open()
    if denied is not None:
        answer = C.process_create_time(denied)
        assert answer is C.PROCESS_LIVENESS_UNKNOWN, (
            f"pid {denied} cannot be opened by this token, so its liveness is "
            f"unknown — answering {answer!r} claims to know")
        # And the sentinel must not be mistakable for either real answer.
        assert answer is not None
        assert answer != 0 and answer != C.process_create_time(os.getpid())


def test_a_holder_we_may_not_open_is_treated_as_live(shared_paths):
    """Issue #9's mechanism through a new door, with a real un-openable PID.

    ``_scan_holder_records`` documents a fail-safe — "a liveness query that
    cannot run at all keeps the ACEs" — and honoured it only for a raised
    exception. A denial is not an exception; it was a ``None``, and ``None ==
    created`` is False, so the record was swept and the ACEs came off under a
    process that is very much alive.
    """
    denied = _a_pid_we_may_not_open()
    if denied is None:
        pytest.skip("every PID on this box is open to this token; the "
                    "monkeypatched sibling test covers the same property")
    shared, console_scratch, _macro = shared_paths
    # Deliberately not the real creation time: the whole point is that we cannot
    # read it, so no record naming this PID can ever match on equality.
    record = _plant_holder(denied, 1)
    sw._grant_container_access(str(console_scratch))

    assert sw._revoke_session_grants() == []

    assert sw._container_ace_present(str(shared)) is True, (
        f"the sweep stripped the shared ACEs because it could not open pid "
        f"{denied} — a process that is running")
    assert os.path.exists(record), "a live holder's record was collected"


def test_a_liveness_query_that_could_not_run_keeps_the_aces(
        shared_paths, monkeypatch):
    """The same fail-safe, forced rather than found.

    ``_a_pid_we_may_not_open`` depends on what the box happens to be running and
    on whether the suite is elevated, so the property is also pinned by making
    the ctypes layer report the denial for a PID of this test's choosing. This is
    the test that must pass on every machine.
    """
    shared, console_scratch, _macro = shared_paths
    C = _winsandbox()
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait(timeout=30)
    record = _plant_holder(dead.pid, 1)
    real = C.process_create_time

    def _denied(pid):
        if pid == dead.pid:
            return C.PROCESS_LIVENESS_UNKNOWN   # as ERROR_ACCESS_DENIED reports
        return real(pid)

    monkeypatch.setattr(C, "process_create_time", _denied)
    sw._grant_container_access(str(console_scratch))

    assert sw._revoke_session_grants() == []

    assert sw._container_ace_present(str(shared)) is True, \
        "an unanswerable liveness query was read as 'that holder is gone'"
    assert os.path.exists(record)


def test_a_deferring_sweep_marks_its_own_record_retiring(
        shared_paths, a_live_process):
    """Half a tie-break is no tie-break: a deferral has to be announced.

    Leaving the record behind carries the *paths*, which is what the handoff
    needs. It does not carry the fact that this process is on its way out — and
    without that, the holder we deferred to reads us as an ordinary live abax and
    defers right back.
    """
    shared, console_scratch, _macro = shared_paths
    sw._grant_container_access(str(console_scratch))
    created = _winsandbox().process_create_time(a_live_process.pid)
    _plant_holder(a_live_process.pid, created)
    mine = sw._holder_record_path()

    sw._revoke_session_grants()

    assert mine and os.path.exists(mine)
    assert sw._holder_record_retiring(mine) is True, \
        "the deferring process left a record indistinguishable from a live one"
    # The mark shares the file with the paths and must not eat one of them.
    assert sw._holder_record_paths(mine) == [str(shared)]


def test_a_process_that_grants_again_stops_advertising_its_exit(
        shared_paths, a_live_process):
    """The mark has to come off as reliably as it goes on.

    A deferred sweep is not always the end of a process — this module's own
    module-scoped sweep runs mid-run and pytest carries on for thousands of
    tests. A record left marked retiring while its writer is holding grants again
    is an invitation to every other abax to strip them, which is W1 with the
    veto disabled from the inside.
    """
    shared, console_scratch, macro_scratch = shared_paths
    sw._grant_container_access(str(console_scratch))
    created = _winsandbox().process_create_time(a_live_process.pid)
    _plant_holder(a_live_process.pid, created)
    mine = sw._holder_record_path()
    sw._revoke_session_grants()
    assert sw._holder_record_retiring(mine) is True

    sw._grant_container_access(str(macro_scratch))

    assert sw._holder_record_retiring(mine) is False, \
        "this process holds the grants again and is still advertising its exit"
    assert sw._holder_record_paths(mine) == [str(shared)]


def test_a_retiring_holder_is_not_a_reason_to_defer(shared_paths, a_live_process):
    """The other side of the tie-break: a marked record is collectable.

    The process is genuinely running — it is the ``a_live_process`` fixture — and
    liveness alone would make this sweep defer. What the record says is that its
    writer has entered its own exit sweep and will not grant again, and that is a
    stronger statement than liveness, made by the only process that can know it.
    """
    shared, console_scratch, _macro = shared_paths
    created = _winsandbox().process_create_time(a_live_process.pid)
    record = _plant_holder(a_live_process.pid, created, [str(shared)],
                           retiring=True)
    sw._grant_container_access(str(console_scratch))

    assert sw._revoke_session_grants() == []

    assert sw._container_ace_present(str(shared)) is False, \
        "a holder that had published its own exit still blocked the sweep"
    assert not os.path.exists(record), "the retiring holder's record was left"


def test_an_unreadable_record_is_never_read_as_retiring(shared_paths,
                                                        a_live_process):
    """The mark only ever *removes* protection, so absence must be the default.

    A truncated record — the zero-length file a process killed between ``open``
    and ``write`` leaves — carries no mark, and the sweep must therefore treat
    its writer as still relying on the grants. Failing the other way would turn
    every crash into a stripped ACE.
    """
    shared, console_scratch, _macro = shared_paths
    created = _winsandbox().process_create_time(a_live_process.pid)
    record = _plant_holder(a_live_process.pid, created)
    assert os.path.getsize(record) == 0
    assert sw._holder_record_retiring(record) is False
    sw._grant_container_access(str(console_scratch))

    assert sw._revoke_session_grants() == []

    assert sw._container_ace_present(str(shared)) is True
    assert os.path.exists(record)


def test_a_deferred_sweep_finishes_the_job_when_it_runs_again(
        shared_paths, a_live_process):
    """The sweep is idempotent, deferral included — the design's own claim.

    A deferral empties the session table but keeps the record, so a second sweep
    that reads only the table finds nothing to remove, revokes nothing, and then
    deletes the record at the bottom anyway. Measured before the fix: the ACEs
    stayed on disk and the last thing that named them was gone.
    """
    shared, console_scratch, _macro = shared_paths
    created = _winsandbox().process_create_time(a_live_process.pid)
    _plant_holder(a_live_process.pid, created)
    sw._grant_container_access(str(console_scratch))
    mine = sw._holder_record_path()

    assert sw._revoke_session_grants() == []          # sweep #1: defers
    assert sw._container_ace_present(str(shared)) is True
    assert sw._session_grant_paths() == [], "the table must still be emptied"
    assert os.path.exists(mine)

    a_live_process.kill()
    a_live_process.wait(timeout=30)

    assert sw._revoke_session_grants() == []          # sweep #2: last one out

    assert sw._container_ace_present(str(shared)) is False, (
        "the second sweep forgot the paths the first one handed to disk — they "
        "are still granted and nothing names them any more")
    assert not os.path.exists(mine)
    # ...and a third call has nothing left to do and must still not raise.
    assert sw._revoke_session_grants() == []


#: One abax-shaped holder process, driven over stdin. Grants, announces, waits;
#: sweeps, announces, waits; exits. Two of these are what a pair of abaxes
#: quitting at the same instant reduces to — and the waits are what make that
#: instant reproducible instead of a race the test has to win.
_HOLDER_CHILD = """\
import os, sys
sys.path.insert(0, {root!r})
import abax._runtime as rt
from abax import sandbox_windows as sw
data, shared, scratch, mutex = sys.argv[1:5]
rt.DATA_DIR = data
sw._needed_read_dirs = lambda: [shared]
sw._needed_read_files = lambda: []
sw._required_read_targets = lambda: [shared]
sw._ACL_MUTEX_NAME = mutex
os.makedirs(scratch, exist_ok=True)
granted, unreachable = sw._grant_container_access(scratch)
print("GRANTED" if not unreachable else "UNREACHABLE", flush=True)
sys.stdin.readline()
sw._revoke_session_grants()
print("SWEPT", flush=True)
sys.stdin.readline()
"""


def _holder_says(proc, expected: str) -> None:
    """Read one protocol line from a holder child, or fail loudly.

    An AppContainer-adjacent child that dies during startup is undiagnosable
    from a bare ``assert line == "GRANTED"``, so the child's exit code and stderr
    go into the message — the same reason ``_diag`` exists for the e2e tier.
    """
    line = proc.stdout.readline().strip()
    if line == expected:
        return
    if proc.poll() is None:
        proc.kill()
    err = proc.communicate(timeout=30)[1]
    raise AssertionError(
        f"holder child said {line!r}, expected {expected!r} "
        f"(rc={proc.returncode})\n{err}")


def test_no_ace_outlives_two_holders_exiting_together(tmp_path):
    """The invariant, with two real processes: after all holders exit, no ACE.

    Both used to defer. P1's sweep ran while P2 was up, so P1 left the grants for
    P2; P2's sweep ran while P1 was still up — it had not *finished* exiting —
    so P2 left them for P1. Both then exited. Measured, 2 of 2 attempts before
    the fix and reproduced deterministically here by making "at the same instant"
    an explicit interleaving rather than a timing race::

        P1 SWEPT [] record=kept
        P2 SWEPT [] record=kept
        both exited, rc: 0 0
        ACE after ALL holders exited: True
        holder records left: ['35232-....hold', '42164-....hold']

    Four machine-wide ACEs standing on a developer's interpreter prefix with
    nothing scheduled to collect them, and two orphaned records that no later
    abax has any reason to consult, because both name processes that are gone and
    neither is anybody's own.

    The children share one holder directory (that is the point) but get their own
    ACL mutex and their own throwaway "interpreter" — the production mutex is
    machine-wide, and a test that took it would serialise against any abax the
    developer has open.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(sw.__file__)))
    shared = tmp_path / "interpreter"
    data = tmp_path / "data"
    for d in (shared, data):
        d.mkdir()
    mutex = f"Local\\abax-test-acl-{os.getpid()}-{os.urandom(4).hex()}"
    prog = _HOLDER_CHILD.format(root=root)

    def _start(tag):
        return subprocess.Popen(
            [sys.executable, "-c", prog, str(data), str(shared),
             str(tmp_path / ("scratch-" + tag)), mutex],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)

    holders = [_start("p1"), _start("p2")]
    try:
        for proc in holders:
            _holder_says(proc, "GRANTED")
        assert sw._container_ace_present(str(shared)) is True, \
            "neither child granted anything, so the test proves nothing"
        # Each sweeps while the other is still up: nobody has exited yet.
        for proc in holders:
            proc.stdin.write("sweep\n")
            proc.stdin.flush()
            _holder_says(proc, "SWEPT")
        for proc in holders:
            proc.stdin.write("exit\n")
            proc.stdin.flush()
            proc.stdin.close()
        for proc in holders:
            assert proc.wait(timeout=120) == 0, proc.stderr.read()

        assert sw._container_ace_present(str(shared)) is False, (
            "both holders deferred to the other and exited; the machine-wide "
            "ALL APPLICATION PACKAGES grant is standing with nothing left that "
            "will ever remove it")
        assert os.listdir(str(data / sw._HOLDER_DIR_NAME)) == [], \
            "records were orphaned, so a later abax cannot finish the job either"
    finally:
        for proc in holders:
            if proc.poll() is None:
                proc.kill()
            proc.stdout.close()
            proc.stderr.close()
        _REAL_ICACLS(str(shared), "/remove", sw.ALL_APP_PACKAGES)


# --------------------------------------------------------------------------- #
# custom_spawn — the bespoke launcher's wiring
# --------------------------------------------------------------------------- #


def test_custom_spawn_passes_flags_sid_and_argv_through(fake_ctypes, no_real_acls):
    fake = fake_ctypes()
    argv = [sys.executable, "-c", "pass"]
    env = {"PATH": "C:\\Windows", "ABAX_SANDBOX_STRICT": "1"}

    proc = sw.confinement().custom_spawn(argv, env, "C:\\scratch", _CREATE_NO_WINDOW)

    assert proc is fake.proc
    # One profile, minted by the launcher — not recomputed here. `_profile_name`
    # is fresh on every call now (issue #10), so a test that called it again to
    # compare would be asserting the bug back into existence.
    created, = fake.created
    assert created.startswith("abax-sandbox-")
    assert created == proc._sandbox_cleanup[1]
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
    # The name the launcher actually created, carried through verbatim: it is
    # per-spawn now, so this handle is the *only* record of which profile this
    # worker's teardown must delete.
    assert fake.created == [profile]
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
    assert fake.deleted == fake.created    # exactly its own profile, not "a" profile


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


def test_custom_spawn_refuses_to_launch_when_a_required_grant_failed(
        fake_ctypes, no_real_acls):
    """Issue #8, the grant side: do not spawn a child that cannot work.

    ``_needed_read_dirs`` hands back the interpreter's base prefix, so a failed
    grant there means the confined child cannot read its own stdlib: it dies
    inside interpreter startup with an empty stdout and a bare exit code, which
    is exactly what issue #6 looked like for months. Refusing is the only
    outcome that can be read from a log.
    """
    fake = fake_ctypes()
    no_real_acls["unreachable"] = ["C:\\fake\\interpreter"]

    with pytest.raises(OSError) as excinfo:
        sw.confinement().custom_spawn(["x.exe"], {}, "C:\\scratch", 0)

    assert isinstance(excinfo.value, sw.SandboxGrantError)
    # The message has to name the path — an anonymous refusal is the same
    # undiagnosable failure wearing a different hat.
    assert "C:\\fake\\interpreter" in str(excinfo.value)
    # Nothing was launched...
    assert fake.spawns == []
    # ...and the machine is back where it started: the grants that did land are
    # revoked and the container profile is deleted.
    assert no_real_acls["revoked"] == [["C:\\scratch", "C:\\fake\\interpreter"]]
    assert fake.deleted == fake.created    # exactly its own profile, not "a" profile


def test_a_refusal_is_not_replaced_by_a_failing_profile_delete(fake_ctypes, no_real_acls):
    """The refusal has to survive its own teardown.

    Deleting the container profile can fail — a zombie child still holds it,
    which is what ``test_cleanup_process_survives_a_failing_profile_delete``
    exists for. Unguarded, that ``OSError`` is raised *while* the
    ``SandboxGrantError`` is being handled and **replaces** it: the launch fails
    with "profile in use", ``isinstance(exc, SandboxGrantError)`` is False, and
    the path that could not be granted survives only in ``__context__`` — which
    is nowhere any caller looks. Naming the path is the entire contract of the
    refusal, so the delete is guarded exactly as ``cleanup_process`` guards it.
    """
    fake = fake_ctypes(delete_error=OSError("profile in use"))
    no_real_acls["unreachable"] = ["C:\\fake\\interpreter"]

    with pytest.raises(OSError) as excinfo:
        sw.confinement().custom_spawn(["x.exe"], {}, "C:\\scratch", 0)

    assert isinstance(excinfo.value, sw.SandboxGrantError), excinfo.value
    assert "C:\\fake\\interpreter" in str(excinfo.value)
    assert "profile in use" not in str(excinfo.value)
    # ...and the teardown still ran all the way through, both halves of it.
    assert no_real_acls["revoked"] == [["C:\\scratch", "C:\\fake\\interpreter"]]
    assert fake.deleted == fake.created    # exactly its own profile, not "a" profile
    assert fake.spawns == []


def test_custom_spawn_undoes_grants_applied_before_an_unexpected_failure(
        fake_ctypes, monkeypatch):
    """The grant runs inside the teardown's reach, and reports as it goes.

    ``_grant_container_access`` opens machine-wide ACLs one icacls call at a
    time, and the fail-closed change widened it further with a ``/findsid``
    subprocess and several log calls. If anything in there raises, a caller
    holding only its *return value* has nothing to revoke with: every ACE that
    already landed is unrevokable and the container profile leaks beside them.
    Hence the out-list, and hence a ``finally`` rather than ``except OSError`` —
    the exception that gets you here need not be an ``OSError`` at all.
    """
    fake = fake_ctypes()
    revoked = []

    def _grant_then_die(scratch, granted=None):
        # Tolerates a caller that passes no out-list, so what this test pins is
        # the leak itself and not a TypeError from the seam.
        if granted is None:
            granted = []
        granted.append(scratch)
        granted.append("C:\\fake\\interpreter")
        raise RuntimeError("the icacls layer blew up")

    monkeypatch.setattr(sw, "_grant_container_access", _grant_then_die)
    monkeypatch.setattr(sw, "_revoke_container_access", _recording_revoke(revoked))

    with pytest.raises(RuntimeError, match="blew up"):
        sw.confinement().custom_spawn(["x.exe"], {}, "C:\\scratch", 0)

    assert revoked == [["C:\\scratch", "C:\\fake\\interpreter"]]
    assert fake.deleted == fake.created    # exactly its own profile, not "a" profile
    assert fake.spawns == []


def test_custom_spawn_launches_when_nothing_is_unreachable(fake_ctypes, no_real_acls):
    # The discriminator for the test above: with the same wiring and an empty
    # unreachable list the spawn goes ahead untouched, so a refusal cannot be
    # mistaken for "the launcher always refuses now".
    fake = fake_ctypes()
    assert no_real_acls["unreachable"] == []

    proc = sw.confinement().custom_spawn(["x.exe"], {}, "C:\\scratch", 0)

    assert proc is fake.proc
    assert len(fake.spawns) == 1
    assert no_real_acls["revoked"] == []
    assert fake.deleted == []


# --------------------------------------------------------------------------- #
# two confined workers in one process (issue #10)
# --------------------------------------------------------------------------- #


def test_two_confinements_in_one_process_get_distinct_profile_names(
        fake_ctypes, no_real_acls):
    """The GUI process really does confine twice.

    ``pyconsole.py`` and ``mixin_macros.py`` each build their own
    ``ConsoleBridge``, and both are strict when ``code_isolation == "strict"``.
    With a per-*process* name the second ``CreateAppContainerProfile`` returns
    ``ALREADY_EXISTS``, which ``create_app_container_profile`` handles by
    *deriving* the existing SID — so the second spawn does not fail, it just
    quietly joins the first worker's container. Two "isolated" workers sharing
    one jail is not an isolation boundary, and the shared name outlives both of
    them: the first teardown deletes the profile, and a later spawn that derives
    that same name gets a SID with no profile behind it.
    """
    fake = fake_ctypes()
    strat = sw.confinement()

    console = strat.custom_spawn(["x.exe"], {}, "C:\\scratch-console", 0)
    macros = strat.custom_spawn(["x.exe"], {}, "C:\\scratch-macros", 0)

    first, second = fake.created
    assert first != second, "both confined workers landed in the same container"
    # Each handle carries its own name to teardown; neither overwrote the other.
    assert console._sandbox_cleanup[1] == first
    assert macros._sandbox_cleanup[1] == second
    assert console is not macros


def test_each_teardown_deletes_only_the_profile_it_created(fake_ctypes, no_real_acls):
    """The half of the collision that outlives the two workers colliding.

    Deleting a profile does not kill a child already confined by it — measured
    on this platform with ``DeleteAppContainerProfile`` fired 0, 5, 20, 50 and
    150 ms after launch: rc=0 every time, the child still printing and
    importing. What a shared name costs is the *next* launch: once
    ``cleanup_process`` deletes a profile another confinement is still using,
    any spawn deriving that name gets a SID with no profile behind it and fails
    at ``CreateProcessW``. So the invariant is not merely "the names differ" but
    "the console's teardown never names the macro runner's profile".
    """
    fake = fake_ctypes()
    strat = sw.confinement()
    console = strat.custom_spawn(["x.exe"], {}, "C:\\scratch-console", 0)
    macros = strat.custom_spawn(["x.exe"], {}, "C:\\scratch-macros", 0)
    console_profile, macros_profile = fake.created

    assert sw.cleanup_process(console) == []
    assert fake.deleted == [console_profile]
    assert macros_profile not in fake.deleted, \
        "one worker's teardown deleted the other's live container"
    # ...and the survivor still knows what to delete when its own turn comes.
    assert macros._sandbox_cleanup == (["C:\\scratch-macros",
                                        "C:\\fake\\interpreter"], macros_profile)

    assert sw.cleanup_process(macros) == []
    assert fake.deleted == [console_profile, macros_profile]


# --------------------------------------------------------------------------- #
# cleanup_process
# --------------------------------------------------------------------------- #


def test_cleanup_process_ignores_a_process_it_never_confined():
    # The bridge calls cleanup_process on whatever worker just died, including
    # an ordinary non-strict Popen. That must be a no-op, not an AttributeError
    # — and it reports no leftover grants, because it made none.
    plain = _FakeProc()
    assert sw.cleanup_process(plain) == []
    assert not hasattr(plain, "_sandbox_cleanup")


def test_cleanup_process_really_removes_the_acl_grant(monkeypatch, tmp_path):
    """End-to-end for the teardown half: a real grant, reverted through the same
    entry point the bridge uses."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(sw, "_needed_read_dirs", lambda: [])
    monkeypatch.setattr(sw, "_required_read_targets", lambda: [])

    before = _explicit_aces(str(scratch))
    all_before = _ace_lines(str(scratch))
    granted, unreachable = sw._grant_container_access(str(scratch))
    assert granted == [str(scratch)]
    assert unreachable == []
    assert _explicit_aces(str(scratch)) != before

    fake = _FakeCtypes()
    proc = _FakeProc()
    proc._sandbox_cleanup = (granted, "abax-sandbox-test")
    proc._sandbox_ctypes = fake

    assert sw.cleanup_process(proc) == []      # nothing left standing

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


def _recording_revoke(revoked, still_standing=()):
    """A ``_revoke_container_access`` stand-in: records, reports, never raises."""
    def _revoke(granted):
        revoked.append(list(granted))
        return list(still_standing)

    return _revoke


def test_cleanup_process_reverts_acls_even_without_the_ctypes_module(monkeypatch, tmp_path):
    # If the lazy plumbing import never happened there is no profile to delete,
    # but the ACL grants still exist and must still come back off.
    revoked = []
    monkeypatch.setattr(sw, "_revoke_container_access", _recording_revoke(revoked))
    proc = _FakeProc()
    proc._sandbox_cleanup = (["C:\\scratch"], "abax-sandbox-test")

    assert sw.cleanup_process(proc) == []

    assert revoked == [["C:\\scratch"]]
    assert proc._sandbox_cleanup is None


def test_cleanup_process_survives_a_failing_profile_delete(monkeypatch):
    # Deleting a profile can fail (still in use by a zombie child). The ACLs are
    # the security-relevant half, so cleanup must complete regardless.
    revoked = []
    monkeypatch.setattr(sw, "_revoke_container_access", _recording_revoke(revoked))
    fake = _FakeCtypes(delete_error=OSError("profile in use"))
    proc = _FakeProc()
    proc._sandbox_cleanup = (["C:\\scratch"], "abax-sandbox-test")
    proc._sandbox_ctypes = fake

    sw.cleanup_process(proc)

    assert revoked == [["C:\\scratch"]]
    assert proc._sandbox_cleanup is None


def test_cleanup_process_surfaces_a_profile_it_could_not_delete(monkeypatch):
    """The profile side of the same rule: continuing is not swallowing.

    ``test_cleanup_process_survives_a_failing_profile_delete`` above pins that
    teardown *continues* past a failed delete — deliberate, the ACLs are the
    security-relevant half. But for a long time continuing was all that
    happened, and the failure was invisible in every direction at once:
    ``delete_app_container_profile`` discarded ``DeleteAppContainerProfile``'s
    HRESULT, so the ``except OSError`` that was supposed to catch this could not
    fire at all, and the profile leaked reporting success.

    What leaks is not nothing: measured on this platform, a delete attempted
    while any handle is open under ``%LOCALAPPDATA%\\Packages\\<name>`` returns
    ``hr=0x80070020`` (``ERROR_SHARING_VIOLATION``) and leaves both the registry
    mapping and the profile tree in place — the same class of leftover as an
    unrevoked ACE, and reported the same way.
    """
    revoked = []
    monkeypatch.setattr(sw, "_revoke_container_access", _recording_revoke(revoked))
    fake = _FakeCtypes(delete_error=OSError(
        "AppContainer profile delete failed: hr=0x80070020"))
    proc = _FakeProc()
    proc._sandbox_cleanup = (["C:\\scratch"], "abax-sandbox-4242-0badc0ffee11")
    proc._sandbox_ctypes = fake

    leaked = sw.cleanup_process(proc)

    # The profile *name*: it identifies both halves of the leak (the
    # `HKCU\\...\\AppContainer\\Mappings` entry and the `Packages` tree), and its
    # `abax-sandbox-` prefix is what tells it apart from the ACL paths sharing
    # the list.
    assert leaked == ["abax-sandbox-4242-0badc0ffee11"]
    # ...and the rest of teardown still ran, exactly as the test above requires.
    assert revoked == [["C:\\scratch"]]
    assert fake.deleted == ["abax-sandbox-4242-0badc0ffee11"]
    assert proc._sandbox_cleanup is None


def test_cleanup_process_reports_both_kinds_of_leftover_together(monkeypatch):
    # A teardown can fail on both halves at once, and one report has to carry
    # both — a future `abax doctor` reading this list gets the whole picture or
    # it gets a misleading one. Paths first, then the profile: teardown order.
    revoked = []
    monkeypatch.setattr(
        sw, "_revoke_container_access",
        _recording_revoke(revoked, still_standing=["C:\\Python313"]))
    fake = _FakeCtypes(delete_error=OSError("profile in use"))
    proc = _FakeProc()
    proc._sandbox_cleanup = (["C:\\Python313"], "abax-sandbox-7-deadbeef")
    proc._sandbox_ctypes = fake

    assert sw.cleanup_process(proc) == ["C:\\Python313", "abax-sandbox-7-deadbeef"]


def test_cleanup_process_surfaces_the_grants_it_could_not_revoke(monkeypatch):
    """Issue #8, the revoke side: teardown must not swallow a leak.

    ``cleanup_process`` is the bridge's entry point; if a revoke fails there,
    an ALL APPLICATION PACKAGES ACE is left standing on a real interpreter
    prefix. Returning the paths is what lets the caller say so — and what a
    future ``abax doctor`` check would look for after an interrupted run.
    """
    revoked = []
    monkeypatch.setattr(
        sw, "_revoke_container_access",
        _recording_revoke(revoked, still_standing=["C:\\Python313"]))
    fake = _FakeCtypes()
    proc = _FakeProc()
    proc._sandbox_cleanup = (["C:\\scratch", "C:\\Python313"], "abax-sandbox-test")
    proc._sandbox_ctypes = fake

    left = sw.cleanup_process(proc)

    assert left == ["C:\\Python313"]
    # A reported failure must not abort the rest of teardown.
    assert revoked == [["C:\\scratch", "C:\\Python313"]]
    assert fake.deleted == ["abax-sandbox-test"]
    assert proc._sandbox_cleanup is None


# --------------------------------------------------------------------------- #
# the refusal must reach the GUI as a response, never as an exception
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name,call", [
    ("execute", lambda b: b.execute("1 + 1", {"sheets": []})),
    ("execute_script", lambda b: b.execute_script("x = 1", "C:\\s.py",
                                                  {"sheets": []})),
    ("execute_macro", lambda b: b.execute_macro("m", [], None, {"sheets": []})),
])
def test_a_refusal_surfaces_as_a_response_not_an_exception(monkeypatch, name, call):
    """``SandboxGrantError`` must reach the user as a message, not as a traceback.

    ``ConsoleBridge._roundtrip`` calls ``_spawn`` for every execution op. This
    used to say that two of the three callers run "synchronously on the GUI
    thread", which was true when it was written and is no longer: ``_run_macro``
    and the Run-script path now go through ``_run_io``/``FuncWorker`` like the
    console (see the module docstring of ``abax/gui/mixin_macros.py``). The
    conclusion is unchanged. Every caller is now behind ``FuncWorker.run``'s
    blanket ``except Exception``, which turns a raise into the generic ``error``
    signal — a failure dialog with no envelope handling and no operation-specific
    title, for a condition the user is *supposed* to be told about precisely.

    So it comes back as the response ``_STRICT_UNAVAILABLE`` already uses, which
    all three callers handle: ``_apply_exec_response`` shows ``error`` and leaves
    the workbook untouched. The path stays in the message, because that is the
    only part of a confinement failure anyone can act on.
    """
    from abax.gui.console import console_bridge as cb

    def _refuse():
        raise sw.SandboxGrantError(
            "AppContainer confinement was not established: the confined worker "
            "could not be granted access to C:\\Python313 — refusing to launch.")

    bridge = cb.ConsoleBridge()
    monkeypatch.setattr(bridge, "_spawn", _refuse)
    try:
        resp = call(bridge)          # must not raise
    finally:
        bridge.close()

    assert "C:\\Python313" in resp["error"], (name, resp)
    assert resp["output"] == ""
    assert resp["envelope"] == {"sheets": []}     # the workbook crosses back intact
    # Exactly the shape the strict-unavailable refusal returns — in particular
    # not "crashed", which would send _apply_exec_response down the "the worker
    # process exited" branch and describe a crash that never happened.
    assert set(resp) == {"output", "error", "envelope"}, resp


def test_an_ordinary_spawn_failure_still_propagates(monkeypatch):
    """The discriminator: only the *refusal* is converted.

    An ``OSError`` from ``CreateProcessW`` is not a policy decision the user can
    act on, and the bridge has always let it reach the caller. Swallowing every
    ``OSError`` here would hide a broken launcher behind a tidy message box.
    """
    from abax.gui.console import console_bridge as cb

    def _boom():
        raise OSError("CreateProcessW failed: 5")

    bridge = cb.ConsoleBridge()
    monkeypatch.setattr(bridge, "_spawn", _boom)
    try:
        with pytest.raises(OSError, match="CreateProcessW"):
            bridge.execute("1 + 1", {"sheets": []})
    finally:
        bridge.close()


# --------------------------------------------------------------------------- #
# ...and the GUI thread must not be the thread that pays for a grant walk
# --------------------------------------------------------------------------- #


class _StubWindow:
    """The smallest thing ``MacroMixin``'s two entry points need.

    Records what they hand to ``_run_io`` instead of starting a QThread, so the
    property under test — *the bridge is not called before this method returns* —
    is observable without a real window, a real thread or a real worker process.
    """

    def __init__(self, tmp_path):
        self.bridge_calls: list = []
        self.io: list = []
        self.applied: list = []
        self.status: list = []
        self._macro_registry = _StubRegistry()
        self._doc = _StubDoc()
        self._tmp = tmp_path

    def _exec_bridge(self):
        window = self

        class _Bridge:
            def execute_macro(self, *a):
                window.bridge_calls.append(("macro", a))
                return {"output": "ok", "envelope": {"sheets": []}}

            def execute_script(self, *a):
                window.bridge_calls.append(("script", a))
                return {"output": "ok", "envelope": {"sheets": []}}

        return _Bridge()

    def _current_cell(self):
        return (0, 0)

    def _run_io(self, worker, *, on_success, busy_msg):
        self.io.append((worker, on_success, busy_msg))

    def _apply_exec_response(self, resp, what):
        self.applied.append((resp, what))
        return True

    def _set_status(self, msg):
        self.status.append(msg)

    def _require_code_consent(self, what="?"):
        return True


class _StubRegistry:
    macros = {"m": object()}
    sources = ["C:\\macros.py"]


class _StubWorkbook:
    def to_envelope(self):
        return {"sheets": []}


class _StubDoc:
    workbook = _StubWorkbook()


def _stub_window(tmp_path):
    """A ``_StubWindow`` with the real ``MacroMixin`` behind it.

    The two entry points, and the two ``_..._finished`` callbacks they hand to
    ``_run_io``, come from the shipping mixin; everything they lean on comes from
    the stub, which is listed first so it wins the MRO.
    """
    from abax.gui.mixin_macros import MacroMixin

    return type("_StubMacroWindow", (_StubWindow, MacroMixin), {})(tmp_path)


def test_the_gui_thread_does_not_wait_for_a_confinement_to_be_established(
        tmp_path, monkeypatch):
    """The Windows grant path is not something a Qt slot may block on.

    ``custom_spawn`` establishes the AppContainer's ACL grants before it launches
    anything: up to ``_ACL_MUTEX_GRANT_WAIT`` (60 s) waiting for another abax's
    DACL walk, and then a walk of its own measured at 19-21 s over the real
    interpreter prefix and ``sys.path``. A single spawn was measured blocking
    36.7 s. ``_run_macro`` and Run-script used to call the bridge straight from a
    Qt slot, so all of that — plus the user's code, which these two pass no
    ``timeout`` for — was paid with the window frozen.

    Neither the wait nor the walk can be tuned away (see the note above
    ``_acl_mutex``: a shorter wait only converts itself into the redundant walk
    of ``trust_probe=False``, and the first strict spawn of a session has a full
    walk to pay regardless). So the thread changed instead. What this pins is
    exactly that: **the bridge has not been called by the time the entry point
    returns**, and the call it eventually makes is inside the worker handed to
    ``_run_io``.
    """
    pytest.importorskip("abax.gui._qtcompat")

    win = _stub_window(tmp_path)
    win._run_macro("m")

    assert win.bridge_calls == [], \
        "the macro entry point blocked on the bridge before returning"
    assert len(win.io) == 1, "the macro run never reached the worker-thread path"
    worker, on_success, busy = win.io[0]
    assert "m" in busy, busy

    # A real FuncWorker, so `_run_io` will really move it to a QThread — not a
    # stand-in that happens to satisfy the assertions below.
    from abax.workers import FuncWorker

    assert isinstance(worker, FuncWorker)
    # The blocking call lives in the worker's callable, and only there.
    resp = worker._fn()
    assert win.bridge_calls == [("macro", ("m", ["C:\\macros.py"], (0, 0),
                                           {"sheets": []}))]
    # ...and applying it is the GUI thread's job again, via on_success.
    on_success(resp)
    assert win.applied == [(resp, "Macro")]
    assert win.status and win.status[-1].startswith("ran macro m")


def test_the_gui_thread_does_not_wait_for_a_script_run_either(
        tmp_path, monkeypatch):
    """The same property for Run-script, which is the other synchronous caller."""
    pytest.importorskip("abax.gui._qtcompat")
    from abax.gui import _qtcompat

    script = tmp_path / "s.py"
    script.write_text("x = 1\n", encoding="utf-8")

    class _Dialog:
        @staticmethod
        def getOpenFileName(*a, **k):     # noqa: N802 - Qt's name
            return str(script), ""

    monkeypatch.setattr(_qtcompat, "QFileDialog", _Dialog)

    win = _stub_window(tmp_path)
    win.run_script()

    assert win.bridge_calls == [], \
        "the Run-script entry point blocked on the bridge before returning"
    assert len(win.io) == 1
    worker, on_success, busy = win.io[0]
    assert "s.py" in busy, busy

    resp = worker._fn()
    assert win.bridge_calls == [("script", ("x = 1\n", str(script),
                                            {"sheets": []}))]
    on_success(resp)
    assert win.applied == [(resp, "Run script")]


# --------------------------------------------------------------------------- #
# the ctypes plumbing: HRESULTs are checked, never discarded
# --------------------------------------------------------------------------- #


class _FakeWinFn:
    """A stand-in for a ``ctypes`` function pointer.

    Callable, and — the part a plain function or bound method cannot do —
    accepts the ``restype`` / ``argtypes`` assignments the code under test makes
    before calling it.
    """

    def __init__(self, hr: int) -> None:
        self._hr = hr
        self.calls: list[str] = []
        self.restype = None
        self.argtypes = None

    def __call__(self, name):
        self.calls.append(name)
        return self._hr


class _FakeUserenv:
    """``userenv.dll`` reduced to the one entry point under test."""

    def __init__(self, hr: int) -> None:
        self.DeleteAppContainerProfile = _FakeWinFn(hr)


def _fake_dlls(userenv):
    """A ``_dlls()`` replacement. Patching the *function* rather than its cache
    matters: ``_dlls`` memoises on its own ``__dict__``, so a real call anywhere
    earlier in the run would otherwise have pinned the genuine DLLs."""
    return lambda: (object(), userenv, object())


def test_delete_app_container_profile_raises_on_a_failed_hresult(monkeypatch):
    """Issue #10, the dead-error-handling half.

    ``DeleteAppContainerProfile`` answers with an HRESULT and this wrapper used
    to throw it away, which made a failed delete invisible in every direction at
    once — no exception, no log, no return value — and made the
    ``except OSError`` guards in :mod:`abax.sandbox_windows` dead code: nothing
    they wrapped could raise.

    The failure is real and reproducible: measured on this platform with a
    handle held open under ``%LOCALAPPDATA%\\Packages\\<name>``, the call
    returns ``hr=0x80070020`` (``ERROR_SHARING_VIOLATION``) and the profile —
    registry mapping and directory both — survives.

    The value arrives **signed**, because ``restype`` is ``ctypes.c_long``; a
    check spelled ``hr > 0`` would pass every real Windows error code straight
    through, so the sentinel here is the signed form of 0x80070020 rather than
    the number a reader would write down.
    """
    import abax._winsandbox_ctypes as C

    userenv = _FakeUserenv(-2147024864)        # 0x80070020 through a c_long
    monkeypatch.setattr(C, "_dlls", _fake_dlls(userenv))

    with pytest.raises(OSError) as excinfo:
        C.delete_app_container_profile("abax-sandbox-42-c0ffeebabe")

    # Reported the way `create_app_container_profile` reports its own failures:
    # the unsigned HRESULT, which is the only form anyone can look up.
    assert "0x80070020" in str(excinfo.value)
    assert userenv.DeleteAppContainerProfile.calls == ["abax-sandbox-42-c0ffeebabe"]


def test_delete_app_container_profile_is_quiet_when_the_profile_is_already_gone(
        monkeypatch):
    """S_OK, and therefore no exception, for a name that is not there.

    Measured: deleting a profile that exists, one already deleted, and one never
    created all return ``hr=0x00000000``. That is what makes the check above
    safe to add — ``cleanup_process`` and ``custom_spawn``'s refusal path can
    both reach a delete for the same name, and a redundant teardown must not
    start reporting a leak that does not exist.
    """
    import abax._winsandbox_ctypes as C

    userenv = _FakeUserenv(0)
    monkeypatch.setattr(C, "_dlls", _fake_dlls(userenv))

    assert C.delete_app_container_profile("abax-sandbox-42-c0ffeebabe") is None
    assert userenv.DeleteAppContainerProfile.calls == ["abax-sandbox-42-c0ffeebabe"]


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
            f"child died before running the probe; on such a failure ``err`` "
            f"also carries the live ACL snapshot ``_spawn_confined`` takes "
            f"before teardown — see #9)")


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
        # Snapshot the ACLs BEFORE the finally revokes them — after teardown
        # every probe answers "no ACE" and proves nothing. Only on a failed
        # launch, so the happy path pays nothing.
        #
        # This is for #9: a confined child that intermittently dies inside
        # interpreter startup ("Failed to import encodings module"). #8
        # established the grants all return 0 and /findsid confirms the ACE
        # present, so the gap is between "the ACE exists" and "the child can
        # read the file" — which no pre-launch check can see, and which is only
        # observable in the window between the child dying and teardown. The
        # failure has resisted reproduction (once, then 15+ clean runs), so the
        # goal is that the NEXT occurrence is conclusive rather than another
        # sighting.
        if rc != 0 and not chunks.get("out"):
            probe = []
            try:
                for path in sw._required_read_targets():
                    live = sw._container_ace_present(path)
                    probe.append(f"{'ACE' if live else 'NO ACE!'}  {path}")
            except Exception as exc:               # never mask the real failure
                probe.append(f"(ACL probe failed: {exc!r})")
            chunks["acl"] = ("\n    ".join(
                ["", "--- required-path ACEs, still granted at this point ---",
                 *probe,
                 "a 'NO ACE!' here means the grant was not in force when the "
                 "child ran (#9)"]).encode("utf-8"))
    finally:
        sw.cleanup_process(proc)
        proc.close_handle()
    return (rc,
            chunks.get("out", b"").decode("utf-8", "replace"),
            chunks.get("err", b"").decode("utf-8", "replace")
            + chunks.get("acl", b"").decode("utf-8", "replace"))


# The six tests below (five here, plus the concurrency reproduction at the end of
# the file) carry ``@pytest.mark.sandbox_e2e`` spelled out rather than hidden
# behind a module-level alias: tests/test_sandbox_gate.py parses this file to pin
# the invariant that they are marked for *selection* and never for the skip, and
# a reader scanning for what runs on CI should not have to resolve an alias to
# find out.


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
    # cleanup_process ran in _spawn_confined's finally; the worker's own writable
    # grant must be back exactly where it started. Only that one: the shared read
    # grants belong to the session and come off at the exit sweep (issue #11),
    # which `session_grants_swept_at_module_exit` runs for this module.
    assert _explicit_aces(str(confined_run["scratch"])) == confined_run["baseline"], \
        "the AppContainer ACL grant leaked past cleanup"


# --------------------------------------------------------------------------- #
# end-to-end: a live worker survives a sibling's teardown (issue #11)
# --------------------------------------------------------------------------- #

# A confined child that stays up and answers commands — the shape of the console
# bridge's worker, which persists between commands and is therefore *sitting* in
# the window a sibling's teardown used to close on it. The probes above all run
# to completion in milliseconds, which is precisely why an earlier attempt at
# this hypothesis measured 0 failures in 16 launches: the overlap was too short
# to be in. `-u` and an explicit flush because both ends are pipes.
_LIVE_PROBE = r"""
import importlib, sys

def _say(msg):
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()

_say("READY")
while True:
    line = sys.stdin.readline()
    if not line:
        break
    verb, _, arg = line.strip().partition(" ")
    if verb == "EXIT":
        break
    try:
        if verb == "IMPORT":
            importlib.import_module(arg)
        elif verb == "WRITE":
            with open(arg, "w", encoding="utf-8") as fh:
                fh.write("alive")
        _say("OK %s %s" % (verb, arg))
    except BaseException as exc:
        _say("FAIL %s %s %s: %s" % (verb, arg, type(exc).__name__, exc))
"""


class _LiveWorker:
    """One long-lived AppContainer-confined child, driven over its pipes.

    Deliberately not built on :func:`_spawn_confined`: that helper's whole shape
    is "run to completion, then tear down", and the defect this exercises needs
    a worker that is still alive *while* another confinement's teardown runs.

    Both pipes are pumped on threads — a child that fills its stderr buffer while
    the test is waiting on stdout would hang, and a hang here is indistinguishable
    from the failure being looked for.
    """

    def __init__(self, strat, scratch: str) -> None:
        env = strat.child_env(dict(os.environ), scratch)
        # The commands carry paths; keep both ends on one encoding rather than
        # on whatever console codepage the child inherits.
        env["PYTHONIOENCODING"] = "utf-8"
        self.proc = strat.custom_spawn([sys.executable, "-u", "-c", _LIVE_PROBE],
                                       env, scratch, _CREATE_NO_WINDOW)
        self.replies: "queue.Queue[str]" = queue.Queue()
        self.errors: "list[str]" = []
        for stream, sink in ((self.proc.stdout, self.replies.put),
                             (self.proc.stderr, self.errors.append)):
            threading.Thread(target=self._pump, args=(stream, sink),
                             daemon=True).start()

    @staticmethod
    def _pump(stream, sink) -> None:
        try:
            while True:
                line = stream.readline()
                if not line:
                    return
                sink(line.decode("utf-8", "replace").rstrip("\r\n"))
        except OSError as exc:                     # pipe torn down under us
            sink(repr(exc))

    def ask(self, command: str, timeout: float = 60) -> str:
        try:
            self.proc.stdin.write((command + "\n").encode("utf-8"))
        except OSError as exc:
            return f"<could not send {command!r}: {exc!r}>{self.diag()}"
        return self.reply(timeout)

    def reply(self, timeout: float = 60) -> str:
        try:
            return self.replies.get(timeout=timeout)
        except queue.Empty:
            return f"<no reply within {timeout}s>{self.diag()}"

    def diag(self) -> str:
        return _diag(self.proc.poll(), "", "\n".join(self.errors))

    def close(self) -> "list[str]":
        """Stop the child and tear its confinement down. Returns cleanup's list.

        Never raises: it runs from ``finally`` blocks, and a teardown that did
        not run would leave a real AppContainer profile on the machine.
        """
        try:
            self.proc.stdin.write(b"EXIT\n")
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        leaked = sw.cleanup_process(self.proc)
        self.proc.close_handle()
        return leaked


@pytest.mark.sandbox_e2e
def test_e2e_a_live_worker_survives_a_second_workers_teardown(tmp_path):
    """Issue #11 as the GUI process actually reaches it, with real ACLs.

    The console's worker is long-lived; the macro runner spawns its own, finishes
    and tears down. Both need the same interpreter prefix, ``icacls /remove`` is
    not refcounted by Windows, and the macro's teardown therefore used to strip
    the running console worker's read access to its own stdlib — while it was
    still running.

    Three assertions, because they fail differently and any one alone would be a
    trap:

    * the ACE is still *listed* after the sibling's teardown — the bookkeeping;
    * the surviving child can still *read* through it — the access, which no ACL
      query can speak for, since a listing says nothing about what a running
      process's cached handles will still be allowed to do;
    * the second confinement issued **no** ``/grant`` for the shared paths — the
      half that is only true of a session-scoped grant and not of a refcount, and
      the reason the second strict command of a session no longer costs ~20 s.

    The first two really do fail without the fix. Measured directly, by stripping
    the ACE under a live worker: its very next import failed immediately with
    ``ModuleNotFoundError``, while ``PING`` still answered ``PONG`` — a worker
    with no standard library and a healthy pulse. And a *fresh* launch during the
    ~20 s revoke walk dies with ``Fatal Python error: init_fs_encoding``, then
    ``0xC0000022`` with no output at all: issue #9's shape, which is why this is
    not fixed by counting holders.

    Nothing is stubbed. This grants ALL APPLICATION PACKAGES read+execute across
    the real interpreter prefix and ``sys.path`` — as ``confined_run`` above
    already does, at the same ~20 s — and the session-scoped hold is what makes
    the *second* confinement free rather than a second full walk.
    """
    strat = sw.confinement()
    dirs = sw._needed_read_dirs()
    base = os.path.abspath(sys.base_prefix)
    shared = next((d for d in dirs if sw._covered_by(base, [d])), None)
    assert shared, f"no directory in {dirs} covers the interpreter at {base}"

    console_scratch = tmp_path / "console"
    macro_scratch = tmp_path / "macros"
    for d in (console_scratch, macro_scratch):
        d.mkdir()

    console = _LiveWorker(strat, str(console_scratch))
    try:
        assert console.reply() == "READY", \
            "the long-lived confined worker never started" + console.diag()
        assert console.ask("IMPORT json").startswith("OK"), \
            "the confined worker could not import at all" + console.diag()
        assert sw._container_ace_present(shared) is True
        assert shared in sw._session_grant_paths()

        # The macro runner spawns while the console's worker is live. Spy on
        # icacls across just this spawn: the shared read paths must cost nothing.
        calls: list[tuple] = []
        with pytest.MonkeyPatch.context() as mp:
            _icacls_spy(mp, calls)
            macro = _LiveWorker(strat, str(macro_scratch))
        try:
            assert macro.reply() == "READY", \
                "the second confined worker never started" + macro.diag()
            own = os.path.normcase(os.path.abspath(str(macro_scratch)))
            shared_grants = [c for c in calls
                             if c[0] == "/grant" and c[1] != own]
            assert shared_grants == [], (
                "the second confinement re-walked the shared DACLs instead of "
                f"reusing the grant already in force: {shared_grants}")
            # ...and it did do its own per-worker work.
            assert _ops(calls, "/grant", macro_scratch), calls
            assert sw._container_ace_present(str(macro_scratch)) is True
        finally:
            macro_leaked = macro.close()

        # The macro runner is gone. Its own scratch grant went with it...
        assert macro_leaked == [], f"the macro teardown reported leaks: {macro_leaked}"
        assert sw._container_ace_present(str(macro_scratch)) is False, \
            "a per-worker scratch grant outlived its worker"
        # ...and the shared grant did not, because the process still needs it.
        # The machine first, the bookkeeping after: a mutation that breaks this
        # should be caught by what the OS says, not by what the table says.
        assert sw._container_ace_present(shared) is True, (
            f"the macro runner's teardown removed {shared} while the console's "
            "worker was still confined and still reading from it")

        # The measurement that matters: a module this child has not imported
        # yet, so it is a real open() through the container's access check
        # rather than something the loader already mapped.
        reply = console.ask("IMPORT xml.dom.minidom")
        assert reply.startswith("OK"), (
            "the surviving confined worker lost its stdlib when its sibling tore "
            f"down: {reply}" + console.diag())
        alive = console_scratch / "still-alive.txt"
        assert console.ask(f"WRITE {alive}").startswith("OK"), \
            "the surviving worker lost its scratch dir" + console.diag()
        assert alive.read_text(encoding="utf-8") == "alive"
    finally:
        console_leaked = console.close()

    assert console_leaked == [], f"the console teardown reported leaks: {console_leaked}"
    # Even the *last* teardown leaves the shared grant alone — that is the whole
    # difference from a refcount, and it is what closes issue #9's window.
    assert sw._container_ace_present(shared) is True
    assert shared in sw._session_grant_paths()


# --------------------------------------------------------------------------- #
# end-to-end: concurrent confinements in one process (issue #10)
# --------------------------------------------------------------------------- #

# Reports the container the child actually landed in, so "two workers, two
# jails" is read off the OS rather than inferred from the two names the parent
# chose. ``TokenAppContainerSid`` is TOKEN_INFORMATION_CLASS 31; a token that is
# not in a container has no such SID, so an unconfined child cannot reach the
# print at all.
_CONCURRENT_PROBE = r"""
import ctypes, os, sys
from ctypes import wintypes

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
adv = ctypes.WinDLL("advapi32", use_last_error=True)
k32.GetCurrentProcess.restype = wintypes.HANDLE
adv.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                 ctypes.POINTER(wintypes.HANDLE)]
adv.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                    wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
adv.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p,
                                       ctypes.POINTER(wintypes.LPWSTR)]

token = wintypes.HANDLE()
if not adv.OpenProcessToken(k32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
    raise SystemExit("OpenProcessToken failed")
size = wintypes.DWORD()
adv.GetTokenInformation(token, 31, None, 0, ctypes.byref(size))
buf = (ctypes.c_byte * max(size.value, 8))()
if not adv.GetTokenInformation(token, 31, buf, ctypes.sizeof(buf),
                               ctypes.byref(size)):
    raise SystemExit("TokenAppContainerSid unavailable — not in a container")
text = wintypes.LPWSTR()
adv.ConvertSidToStringSidW(ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0],
                           ctypes.byref(text))
print("APPCONTAINER_SID", text.value)

# The (M) grant: this container's own scratch dir, in a temp tree an
# AppContainer has no default access to at all.
with open(os.path.join(os.environ["ABAX_PROBE_SCRATCH"], "mine.txt"), "w") as fh:
    fh.write(os.environ["ABAX_PROBE_TAG"])
print("SCRATCH_WRITE_OK")
# The (RX) grant, exercised after startup so it is this container's access being
# measured and not a section the loader already mapped.
import xml.etree.ElementTree            # noqa: F401
print("STDLIB_READ_OK")
print("CHILD_DONE")
sys.stdout.flush()
"""


def _interpreter_read_paths() -> "list[str]":
    """The paths a confined child must read to reach its first bytecode.

    ``_required_read_targets()`` minus the abax package dir — the concurrency
    probe imports nothing but the stdlib, and the package dir is the abax
    checkout, whose ACLs that test has no business rewriting. Deduped through
    the production :func:`~abax.sandbox_windows._covered_by`, so a venv whose
    ``Scripts`` dir sits under its own base prefix yields one entry, not two.

    One function because two callers must agree on the answer: the test hoists
    a grant onto these paths and then verifies it took, and
    :func:`_one_confinement` probes these same paths when a child dies.
    """
    paths: list[str] = []
    for raw in (os.path.dirname(sys.executable), sys.base_prefix):
        path = os.path.abspath(raw)
        if not sw._covered_by(path, paths):
            paths.append(path)
    return paths


def _acl_snapshot(paths: "list[str]") -> str:
    """Which of *paths* ALL APPLICATION PACKAGES can reach, rendered for a
    failure message.

    Must be taken while the grants are still in force — after teardown every
    probe answers "no ACE" and proves nothing — which is why the callers run it
    before ``cleanup_process`` rather than after. ``_spawn_confined`` above
    carries the same block for the single-child probes, and for the same reason:
    a child that dies inside interpreter startup ("Failed to import encodings
    module") produces no stdout and a bare exit code, so whether the grant it
    needed was actually in place is the only fact worth having.
    """
    lines = []
    try:
        for path in paths:
            lines.append(f"{'ACE' if sw._container_ace_present(path) else 'NO ACE!'}"
                         f"  {path}")
    except Exception as exc:                   # never mask the real failure
        lines.append(f"(ACL probe failed: {exc!r})")
    return "\n    ".join(
        ["", "--- ACEs, still granted at this point ---", *lines,
         "a 'NO ACE!' here means the grant was not in force when the child ran"])


def _one_confinement(scratch: str, tag: str) -> dict:
    """One complete confinement — profile, launch, drain, teardown.

    Emphatically **not** "as ``ConsoleBridge`` performs it", which this
    docstring used to claim: the caller stubs ``_needed_read_dirs``,
    ``_needed_read_files`` and ``_required_read_targets`` to ``[]``, so every
    grant a real bridge makes on the interpreter and ``sys.path`` — and with
    them ``custom_spawn``'s fail-closed check, which has nothing left to
    check — is switched off here and replaced by one hoisted grant made once for
    all 24 cycles. What *is* the real thing is the per-confinement half this
    test is about: profile name, SID, launch, the scratch grant and revoke, and
    teardown.

    Split out from :func:`_spawn_confined` rather than reusing it because this
    one is called from several threads at once and must not share a scratch dir,
    a profile, or a result slot with its siblings.
    """
    strat = sw.confinement()
    env = strat.child_env(dict(os.environ), scratch)
    env["ABAX_PROBE_SCRATCH"] = scratch
    env["ABAX_PROBE_TAG"] = tag
    try:
        proc = strat.custom_spawn([sys.executable, "-c", _CONCURRENT_PROBE], env,
                                  scratch, _CREATE_NO_WINDOW)
    except Exception as exc:                  # the collision's loudest symptom
        return {"tag": tag, "spawn_error": f"{type(exc).__name__}: {exc}"}
    profile = proc._sandbox_cleanup[1]
    err: dict[str, bytes] = {}

    def _drain():
        try:
            err["b"] = proc.stderr.read()
        except OSError as exc:
            err["b"] = repr(exc).encode()

    reader = threading.Thread(target=_drain, daemon=True)
    reader.start()
    out: bytes = b""
    rc: "int | str | None" = None
    acl = ""
    try:
        try:
            proc.stdin.close()
        except OSError:
            pass
        out = proc.stdout.read()
        rc = proc.wait(timeout=120)
        reader.join(15)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, rc = b"", "timed out"
    finally:
        # Snapshot BEFORE the cleanup below revokes the scratch grant, and only
        # when this child failed, so the happy path pays nothing. The caller's
        # hoisted interpreter grant is machine-global and unrefcounted; if it
        # was stripped, every child here dies during interpreter startup with an
        # empty stdout, and this is what says so instead of leaving 24 silent
        # corpses to be read as 24 successful confinements.
        if rc != 0 or b"CHILD_DONE" not in out:
            acl = _acl_snapshot([scratch, *_interpreter_read_paths()])
        leaked = sw.cleanup_process(proc)
        proc.close_handle()
    return {"tag": tag, "spawn_error": None, "profile": profile, "rc": rc,
            "out": out.decode("utf-8", "replace"),
            "err": err.get("b", b"").decode("utf-8", "replace"),
            "acl": acl, "leaked": leaked}


def _profile_dirs() -> "set[str]":
    """abax's AppContainer profiles as they exist on disk right now.

    ``CreateAppContainerProfile`` writes a registry mapping under
    ``HKCU\\...\\AppContainer\\Mappings\\<SID>`` *and* a
    ``%LOCALAPPDATA%\\Packages\\<name>`` tree, and ``DeleteAppContainerProfile``
    removes both together (measured). The directory is the half that can be
    listed by *name*, so a leak is visible here without a SID lookup.
    """
    packages = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages")
    if not os.path.isdir(packages):
        return set()
    return {n for n in os.listdir(packages) if n.startswith("abax-sandbox-")}


@pytest.mark.sandbox_e2e
def test_e2e_concurrent_confinements_in_one_process_do_not_collide(tmp_path):
    """Real containers, real children, all at once — the issue #10 reproduction.

    abax confines twice in the GUI process (``pyconsole.py`` and
    ``mixin_macros.py``), and with the old per-*process* profile name the two
    collided: ``CreateAppContainerProfile`` answered ``ALREADY_EXISTS``,
    ``create_app_container_profile`` derived the existing SID instead of
    failing, both workers ended up in one container, and the first teardown
    deleted it. Measured on this platform at exactly this shape — 4 concurrent
    cycles, 6 rounds each — **7 of 24 launches failed** (``AppContainer profile
    failed: hr=0x8000ffff / 0x80070003 / 0x8007000a``, ``CreateProcessW failed:
    2``) against 0 with the per-spawn name.

    **Why the shared read grants are hoisted out of the loop.** Every
    ``custom_spawn`` grants ALL APPLICATION PACKAGES read+execute on the same
    interpreter prefix and ``sys.path`` directories, and every teardown revokes
    them — machine-global state that is *not* refcounted, so one cycle's revoke
    can pull the stdlib out from under a sibling's live child. That is a real
    second defect and it is not this one; leaving it in the loop would make the
    test measure a race it is not about. It is also 400x slower, because an
    inheritable ``(OI)(CI)`` ACE on the prefix rewrites the DACL of every file
    beneath it: the same 24 launches take 299s with per-cycle ACL work and 0.9s
    without (measured). Hoisting costs the reproduction nothing — 7/24 failed
    under the old name either way. The per-cycle *scratch* grant and revoke are
    untouched and still real, because scratch dirs are per-confinement and race
    nothing.

    Only the interpreter is hoisted, not all of ``_needed_read_dirs()``: the
    probe imports nothing but the stdlib, so ``sys.path`` entries buy it nothing
    — and one of them is the abax checkout, whose ACLs this test has no business
    rewriting. See :func:`_interpreter_read_paths` for the exact set. Measured
    on this platform, that also drops the setup from 38.7s to 33.5s.

    **What stops the hoist turning this into a vacuous pass.** Stubbing the
    shared grants away also stubs away ``custom_spawn``'s fail-closed check, so
    a hoist that silently did not take would produce 24 children that die in
    interpreter startup — and every assertion below would read that as a clean
    non-collision. Two things prevent it: the ``_container_ace_present`` check
    after the hoist, which fails with a message about the *grant*; and the ACL
    snapshot :func:`_one_confinement` attaches to any child that does not print
    ``CHILD_DONE``, which says whether the grant was in force when that child
    ran. Neither existed when this test was written.
    """
    threads, rounds = 4, 6
    hoisted: list[str] = []
    reachable = _interpreter_read_paths()
    results: list[dict] = []
    lock = threading.Lock()

    def _round(worker: int) -> None:
        for r in range(rounds):
            tag = f"w{worker}r{r}"
            scratch = tmp_path / tag
            scratch.mkdir()
            outcome = _one_confinement(str(scratch), tag)
            with lock:
                results.append(outcome)

    try:
        for path in reachable:
            # An all-users Python already grants ALL APPLICATION PACKAGES read
            # on its prefix, and adding a redundant ACE there is not free: an
            # inheritable ACE rewrites the DACL of every file underneath, ~17s
            # each way on this box's per-user install. If the container can
            # already read it, leave the machine alone.
            if sw._container_ace_present(path):
                continue
            if sw._icacls(path, "/grant", f"{sw.ALL_APP_PACKAGES}:(OI)(CI)(RX)"):
                hoisted.append(path)
        # **The hoist is this test's entire read-grant story, so verify it.**
        # The MonkeyPatch context below stubs `_needed_read_dirs`,
        # `_needed_read_files` and `_required_read_targets` to `[]`, which
        # switches off `custom_spawn`'s own fail-closed check — nothing else is
        # left to notice that the children cannot reach an interpreter. If the
        # grant above failed, or an unrelated run stripped the ACE, all 24
        # children die inside interpreter startup, every launch still
        # "succeeds", every profile name is still distinct, and the test reports
        # a clean 24/24 non-collision: a pass for entirely the wrong reason.
        #
        # The old guard here was `assert reachable`, which could never fire —
        # `reachable` is built from `dirname(sys.executable)` and
        # `sys.base_prefix`, both always non-empty. Ask the machine instead of
        # the list, and fail with a message about the grant rather than with 24
        # dead children.
        assert any(sw._container_ace_present(p) for p in reachable), (
            "ALL APPLICATION PACKAGES cannot reach any interpreter path "
            f"({', '.join(reachable)}) — the hoisted grant did not take, and "
            "without it every confined child below would die during interpreter "
            "startup while this test read that as 'no collision'")
        before = _profile_dirs()
        with pytest.MonkeyPatch.context() as mp:
            # Only the *shared* targets are stubbed out; the scratch dir is
            # still granted and revoked for real by every cycle.
            mp.setattr(sw, "_needed_read_dirs", lambda: [])
            mp.setattr(sw, "_needed_read_files", lambda: [])
            mp.setattr(sw, "_required_read_targets", lambda: [])
            runners = [threading.Thread(target=_round, args=(i,))
                       for i in range(threads)]
            for t in runners:
                t.start()
            for t in runners:
                t.join(300)
            assert not any(t.is_alive() for t in runners), "a confinement hung"
    finally:
        for path in hoisted:
            sw._icacls(path, "/remove", sw.ALL_APP_PACKAGES)

    assert len(results) == threads * rounds

    def _diagnose(rs):
        # `acl` is appended whole rather than truncated with `err`: it is the
        # one line that distinguishes "the container could not read the
        # interpreter" from "the container could, and something else broke",
        # and 200 characters would cut it off mid-path.
        return "\n".join(
            f"  {r['tag']}: spawn_error={r.get('spawn_error')!r} "
            f"rc={r.get('rc')!r} profile={r.get('profile')!r} "
            f"out={r.get('out', '')!r} err={r.get('err', '')[:200]!r}"
            + r.get("acl", "")
            for r in rs)

    # 1. Every launch succeeded. This is the assertion that was 7/24 red.
    broken = [r for r in results if r.get("spawn_error")]
    assert not broken, (
        f"{len(broken)}/{len(results)} confined launches failed:\n"
        + _diagnose(broken))
    unfinished = [r for r in results
                  if r["rc"] != 0 or "CHILD_DONE" not in r["out"]]
    assert not unfinished, (
        f"{len(unfinished)}/{len(results)} confined children did not finish:\n"
        + _diagnose(unfinished))

    # 2. Every confinement was its own container — read off the children's own
    #    tokens, not off the names the parent picked.
    names = [r["profile"] for r in results]
    assert len(set(names)) == len(names), f"profile names collided: {sorted(names)}"
    sids = [line.split(" ", 1)[1]
            for r in results for line in r["out"].splitlines()
            if line.startswith("APPCONTAINER_SID ")]
    assert len(sids) == len(results), _diagnose(results)
    assert len(set(sids)) == len(sids), \
        f"two children shared an AppContainer SID: {sorted(sids)}"

    # 3. Distinct SIDs still get the access: the grants name ALL APPLICATION
    #    PACKAGES, the group every container is in, so a per-spawn SID must not
    #    cost a child its scratch dir (an (M) ACE in a temp tree it otherwise
    #    cannot touch) or its stdlib (an (RX) ACE on the prefix).
    for r in results:
        assert "SCRATCH_WRITE_OK" in r["out"], _diagnose([r])
        assert "STDLIB_READ_OK" in r["out"], _diagnose([r])
        assert (tmp_path / r["tag"] / "mine.txt").read_text(
            encoding="utf-8") == r["tag"], "a child wrote into a sibling's scratch"

    # 4. Every teardown ran, and each deleted only its own. One profile per
    #    spawn instead of one per process is only safe if that holds: a leak is
    #    a registry mapping plus a ~147 KB %LOCALAPPDATA%\\Packages tree that
    #    nothing ever collects.
    #
    #    Two independent readings of that, kept because they fail differently:
    #    the directory listing catches a profile nobody even tried to delete,
    #    while `leaked` catches one whose `DeleteAppContainerProfile` came back
    #    non-zero — which used to be indistinguishable from success, since the
    #    HRESULT was discarded.
    assert _profile_dirs() == before, \
        f"AppContainer profiles leaked: {sorted(_profile_dirs() - before)}"
    for r in results:
        assert r["leaked"] == [], _diagnose([r])
