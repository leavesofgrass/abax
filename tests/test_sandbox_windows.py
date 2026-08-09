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
  and checks they are 24 separate containers (issue #10). Every assertion in
  that tier prints the child's exit code, stdout and
  stderr, because an AppContainer launch that dies at startup is otherwise
  undiagnosable from a CI log (see ``_diag``). These six tests run
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
import string
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


def test_a_file_shaped_syspath_entry_is_granted_rather_than_refused(tmp_path):
    """The shipped zipapp must be able to confine at all.

    With the archive on ``sys.path`` and providing ``abax``, it is a required
    target that no *directory* grant can cover: ``D:\\abax`` is on ``sys.path``
    only by accident of the CWD. Before the file grant existed this returned
    ``unreachable == [archive]`` on every call, so ``custom_spawn`` raised
    ``SandboxGrantError`` unconditionally and strict mode could not be switched
    on in the portable build at all.

    Real icacls, throwaway paths: the ACE has to actually land, which is the
    whole point — see the flags test above.
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

    assert _explicit_aces(str(archive)) == before


def test_a_zipapp_already_inside_a_granted_directory_is_not_granted_twice(tmp_path):
    """The inheritable directory ACE already reaches it.

    The ordinary developer case — ``abax.pyz`` sitting in a checkout that is
    itself on ``sys.path``. A second, explicit ACE on the file would be one more
    icacls round trip on every spawn and one more thing teardown has to remove.
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

    # The archive never got an ACE of its own — the parent's inheritable one
    # reached it — and the revoke left none behind.
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


def test_grant_is_additive_and_revoke_reverts_it_exactly(monkeypatch, tmp_path):
    """The documented promise: the ACEs we add never weaken anyone's access and
    the machine is left byte-identical afterwards."""
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
    """``SandboxGrantError`` must not unwind out of a Qt slot.

    ``ConsoleBridge._roundtrip`` calls ``_spawn`` for every execution op, and two
    of the three callers run *synchronously on the GUI thread*: ``_run_macro``
    (``abax/gui/mixin_macros.py``) and the Run-script path both call the bridge
    from inside a Qt slot with nothing catching around them. Only the console is
    protected, and only by ``FuncWorker.run``'s blanket ``except Exception``. A
    refusal escaping there is an exception unwinding through Qt — for a
    condition the user is *supposed* to be told about in a message box.

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
    # cleanup_process ran in _spawn_confined's finally; the machine must be back
    # exactly where it started.
    assert _explicit_aces(str(confined_run["scratch"])) == confined_run["baseline"], \
        "the AppContainer ACL grant leaked past cleanup"


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
