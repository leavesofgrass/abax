"""Windows OS-confinement for the code-execution worker (sandbox Phase 3).

Implements the :class:`abax.sandbox.Confinement` contract on Windows using an
**AppContainer**: the worker process runs inside an isolated security context
with *no capabilities*, which by default denies **network** access and denies
**filesystem** access to everything except locations explicitly granted to the
container. We grant the container:

* **read + execute** on the interpreter prefix and the ``sys.path`` entries the
  worker must import from (otherwise Python can't even start) — including the
  ones that are *files* rather than directories, which is how the shipped
  ``abax.pyz`` provides the package, and
* **modify** on a private **scratch** directory (the one place the worker may
  write).

Everything else — the user's profile, the rest of the disk, the network — is
denied by the AppContainer. Verified on this platform: a confined worker writes
to the scratch dir, is denied writing to the home directory, and gets
``EACCES`` opening an outbound socket.

Why a bespoke launcher (``custom_spawn``) instead of ``wrap_argv``: an
AppContainer is selected at process-creation time via a *security-capabilities*
process-thread attribute, which ``subprocess.Popen`` does not expose. So this
module calls ``CreateProcessW`` directly (via ``ctypes``) with an
``EXTENDED_STARTUPINFO`` attribute list, wiring up inheritable pipes with the
stdlib ``_winapi`` primitives (the same ones ``subprocess`` uses) and returning
a small Popen-compatible handle the bridge drives exactly like a normal worker.

The ALL-APPLICATION-PACKAGES ACEs we add are **additive** (read/execute only;
they never weaken anyone's access) and are **reverted** — but on two different
clocks, because they have two different owners. The scratch dir's ``(M)`` grant
belongs to one worker and comes off at that worker's teardown. The *shared*
read grants (interpreter prefix, ``sys.path``) belong to every confinement in
the process, are taken once per session, and come off once, at process exit;
see the note above :func:`_hold_session_grant` for the three measurements that
forced that split. Both halves
of that bookkeeping are load-bearing and neither is allowed to fail quietly: a
grant the container genuinely needs and did not get refuses the launch
(:class:`SandboxGrantError`, naming the path) rather than spawning a child that
cannot read its own stdlib, and a revoke that fails is logged and *returned* to
the caller. The AppContainer profile is bookkeeping of the same kind and is held
to the same rule: :func:`abax._winsandbox_ctypes.delete_app_container_profile`
checks its HRESULT, and a delete that fails is reported through the same list
(:func:`cleanup_process`) rather than survived in silence. Even so,
Phase 3's fail-closed :func:`abax.sandbox.selftest` runs inside the worker after
launch: if for any reason the container did not actually confine, the worker
refuses to execute user code. Nothing here can silently ship a fake sandbox.

**How little the ``_log`` calls below are actually worth.** abax configures no
logging anywhere — no ``basicConfig``, ``dictConfig``, ``fileConfig``,
``addHandler`` or handler class in the whole package — so this module's logger
inherits the root's default WARNING and has no handler at all. Measured: an
effective level of 30 and :data:`logging.lastResort` as the only sink. Two
consequences, and both are properties of abax rather than of this module (the
same ``getLogger``-with-no-configuration pattern is in ``abax/core/fonts.py``,
``abax/core/pandoc.py``, ``abax/core/faceplate_assets.py`` and
``abax/macros.py``):

* ``_log.warning`` reaches stderr only by ``lastResort``'s accident — unformatted,
  with no logger name or level — and this module runs only inside the GUI parent
  (``abax/gui/console/console_bridge.py`` is its one caller), whose shipped
  Windows build is the windowed ``abaxw.exe`` (``console=False``,
  ``packaging/windows/abax.spec:151``). There is usually no console there to
  receive it.
* ``_log.info`` is discarded at the call site, before formatting. That includes
  the "already has an ACE, continuing" line in
  :func:`_unreachable_requirements` — the one record that explains why a
  required grant failed and the launch went ahead anyway.

So treat the log lines here as a best-effort trace for someone running from a
console, not as the report. What actually surfaces is the raised
:class:`SandboxGrantError`, the list :func:`cleanup_process` hands back to the
bridge (unrevoked grant paths *and* an undeleted profile name), and the worker's
own selftest. Installing a handler is an abax-wide
change and deliberately not made here; see ``dev/lessons-learned.md``.

Pure stdlib (atexit, ctypes, _winapi, msvcrt, os, sys, threading, subprocess for
icacls). No deps. Imports cleanly on any OS — all Windows-only work is inside
method bodies.
"""

from __future__ import annotations

import atexit
import logging
import os
import subprocess
import sys
import threading

from ._runtime import console_encoding

_log = logging.getLogger(__name__)

# The well-known SID for "ALL APPLICATION PACKAGES" — the group every
# AppContainer process belongs to. Granting it read/execute on a path makes that
# path reachable from inside any AppContainer.
ALL_APP_PACKAGES = "*S-1-15-2-1"

# CreateProcess / proc-thread-attribute constants (winbase.h).
_EXTENDED_STARTUPINFO_PRESENT = 0x00080000
_CREATE_UNICODE_ENVIRONMENT = 0x00000400
_PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009
_HANDLE_FLAG_INHERIT = 0x00000001
_STARTF_USESTDHANDLES = 0x00000100
_HRESULT_ALREADY_EXISTS = 0x800700B7

# How long to wait for the `/findsid` probe in `_container_ace_present`, in
# seconds. Deliberately far below the 60 the grant/revoke calls use: the probe is
# a single non-recursive lookup (~30 ms measured) that runs *only* on the refusal
# path — which is synchronous on the GUI thread, once per required target. At 60
# each, three stalled probes freeze the window for three minutes before the user
# is told anything. A timeout can only ever answer False, and False never
# upgrades a refusal, so cutting the wait short can lose nothing but the wait.
_FINDSID_TIMEOUT = 5


class SandboxGrantError(OSError):
    """A path the confined worker genuinely needs could not be made reachable.

    Raised by :meth:`WindowsAppContainer.custom_spawn` *instead of* launching.
    Deriving from :class:`OSError` is not decoration: ``custom_spawn`` tears the
    confinement down in a ``finally`` (revoke the grants, delete the profile,
    let it propagate), which is exactly the teardown a refused launch needs, and
    the one caller — ``ConsoleBridge._spawn`` — already lets an ``OSError`` from
    ``CreateProcessW`` reach the GUI. "I will not launch this" and "I could not
    launch this" want the same handling.

    The message always names the offending path: a confinement that fails
    anonymously is how issue #6 stayed unread for months. That naming is the
    *whole* point of the class, so nothing on the refusal path may be allowed to
    replace it with an incidental error — see ``custom_spawn``'s teardown, where
    the profile delete is guarded for exactly that reason.

    ``ConsoleBridge._roundtrip`` catches it and turns it into the ordinary
    ``{"output": "", "error": …}`` response rather than letting it unwind:
    ``_run_macro`` and the Run-script path call the bridge *synchronously on the
    GUI thread*, so an exception leaving there escapes a Qt slot.
    """


def confinement():
    """The Windows AppContainer strategy, or None off Windows."""
    if sys.platform != "win32":
        return None
    return WindowsAppContainer()


class WindowsAppContainer:
    name = "appcontainer"

    def available(self) -> bool:
        """True when the AppContainer + proc-thread-attribute APIs are present.

        The real proof that confinement *works* is the worker's startup
        self-test; here we only confirm the platform exposes the primitives
        (Windows 8 / Server 2012 and later)."""
        if sys.platform != "win32":
            return False
        try:
            import ctypes

            userenv = ctypes.WinDLL("userenv", use_last_error=True)
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            return (hasattr(userenv, "CreateAppContainerProfile")
                    and hasattr(userenv, "DeriveAppContainerSidFromAppContainerName")
                    and hasattr(k32, "InitializeProcThreadAttributeList")
                    and hasattr(k32, "UpdateProcThreadAttribute"))
        except OSError:
            return False

    def wrap_argv(self, argv: "list[str]", scratch: str) -> "list[str]":
        # AppContainer is applied by custom_spawn, not by wrapping argv.
        return argv

    def child_env(self, env: "dict[str, str]", scratch: str) -> "dict[str, str]":
        env = dict(env)
        # Point temp files at the one writable location.
        env["TEMP"] = scratch
        env["TMP"] = scratch
        return env

    def apply_in_child(self, scratch: str) -> None:
        # Confinement is established by the parent at CreateProcess time.
        return None

    def describe(self) -> str:
        return ("Windows AppContainer — no network, filesystem writes confined "
                "to a private scratch dir; interpreter granted read-only")

    # --- the bespoke launcher ------------------------------------------------

    def custom_spawn(self, argv, env, scratch, creationflags):
        """Launch ``argv`` inside an AppContainer, returning a Popen-like handle.

        Raises :class:`SandboxGrantError` — without spawning anything — when a
        path the confined child genuinely needs could not be made reachable; see
        the policy note above :func:`_required_read_targets` for which paths
        those are and why the rest are survivable.
        """
        from . import _winsandbox_ctypes as C  # lazy: Windows-only ctypes defs

        # Once per spawn, not once per process: two ConsoleBridges live in the
        # GUI process (console + macros) and a shared name silently puts both
        # workers in one container that the first teardown then deletes. See
        # `_profile_name`. The answer is carried to teardown through
        # `proc._sandbox_cleanup`, so this call is the only place it is minted.
        profile_name = _profile_name()
        sid = C.create_app_container_profile(profile_name)
        # `granted` is owned out here and filled in place, so the teardown below
        # can revoke whatever landed even when `_grant_container_access` itself
        # dies partway through — a return value would be lost in that case, and
        # every ACE it had already applied with it. The grant call is *inside*
        # the try for the same reason: it opens machine-wide ACLs and runs a
        # subprocess per path, so an exception anywhere in it would otherwise
        # leak both the profile and those ACEs.
        granted: list[str] = []
        launched = False
        try:
            _, unreachable = _grant_container_access(scratch, granted)
            if unreachable:
                # Fail closed, inside the try: the teardown below (revoke what
                # did land, delete the profile, propagate) is exactly what a
                # refused launch needs.
                #
                # The paths go in verbatim, not through repr(): a Windows path
                # repr'd is "C:\\\\Python313", which no reader recognises and no
                # grep of a support log finds.
                raise SandboxGrantError(
                    "AppContainer confinement was not established: the confined "
                    "worker could not be granted access to "
                    + ", ".join(unreachable)
                    + " — refusing to launch a worker that cannot reach it, "
                    "since it would die during interpreter startup with no "
                    "output.")
            proc = C.create_process_appcontainer(
                argv, env, sid,
                creationflags | _EXTENDED_STARTUPINFO_PRESENT
                | _CREATE_UNICODE_ENVIRONMENT)
            launched = True
        finally:
            if not launched:
                # Takes back this worker's scratch grant, and deliberately not
                # the shared read grants: those belong to the session (see
                # `_hold_session_grant`), a refused launch is not the end of the
                # session, and revoking them here would reopen the ~20 s window
                # for whatever spawns next — for a launch that is failing anyway.
                _revoke_container_access(granted)
                # Guarded for a sharper reason than in `cleanup_process`:
                # deleting a profile can fail (measured: `hr=0x80070020` while
                # anything holds a handle under it), and an OSError raised
                # *during* the teardown of a SandboxGrantError replaces it — the
                # launch then fails with "profile in use", `isinstance(exc,
                # SandboxGrantError)` is False, and the offending path survives
                # only in `__context__`, where no message a user sees will find
                # it. Naming the path is the entire contract of the refusal, so
                # the exception stays untouched.
                #
                # Which leaves the log as the only channel here — worth little
                # (module docstring), but the alternative is nothing at all.
                # `cleanup_process` can do better because it *returns* a list;
                # this path has no return value to put a leak in.
                try:
                    C.delete_app_container_profile(profile_name)
                except OSError as exc:
                    _log.warning(
                        "sandbox: refusing this launch left the AppContainer "
                        "profile %s behind — it could not be deleted (%s)",
                        profile_name, exc)
        # Remember what to clean up when the process is closed.
        proc._sandbox_cleanup = (granted, profile_name)  # noqa: SLF001
        proc._sandbox_ctypes = C  # noqa: SLF001
        return proc


def _profile_name() -> str:
    """A fresh AppContainer name for **one confinement**. Never reused.

    It used to be ``f"abax-sandbox-{os.getpid()}"``, on the reasoning that "the
    PID is unique enough for a live profile, and we delete it on teardown". That
    holds only while a process has at most one confined worker alive, and abax
    has two: ``abax/gui/console/pyconsole.py`` and ``abax/gui/mixin_macros.py``
    each build their own :class:`~abax.gui.console.console_bridge.ConsoleBridge`
    in the GUI process, and both are strict when ``code_isolation == "strict"``.

    Two workers, one name, and the collision is **silent** rather than loud:
    :func:`abax._winsandbox_ctypes.create_app_container_profile` treats
    ``ALREADY_EXISTS`` by *deriving* the existing SID instead of failing, so the
    second spawn does not error — it simply joins the first worker's container,
    and two "isolated" workers in one container is not an isolation boundary.

    The teardown half is narrower than it first looks, and is measured rather
    than assumed: a confined child **survives** deletion of its own profile.
    With ``DeleteAppContainerProfile`` fired 0, 5, 20, 50 and 150 ms after
    launch, the child went on printing and importing normally and exited rc=0
    every time. What the shared name breaks is *later* spawns: once the first
    teardown deletes the profile both workers were using, a spawn that derives
    that same name gets a SID with no profile behind it and fails at
    ``CreateProcessW``. Measured by driving four concurrent confined spawns from
    one process: **9 of 24 launches failed** (``hr=0x8000ffff /
    0x80070002 / 0x80070003 / 0x8007000a``, ``CreateProcessW failed: 2``) against
    **0 of 8** with no concurrency and **0 of 16** across separate processes;
    reproduced here at 6–7 of 24 across several runs, and pinned by
    ``test_e2e_concurrent_confinements_in_one_process_do_not_collide``.
    Uniqueness therefore has to be per *confinement*, not per process.

    The pieces, and what each is for:

    * ``abax-sandbox-`` — so a profile left behind by a killed abax is
      identifiable as ours on a machine that has ~150 other AppContainers
      (measured under ``HKCU\\...\\AppContainer\\Mappings`` on this box).
    * the PID — so such a leftover is still traceable to a run.
    * six random bytes from :func:`os.urandom` — the actual uniqueness. It is
      per *call*, which is the whole point: ``custom_spawn`` calls this once and
      carries the answer through ``proc._sandbox_cleanup``, so each spawn creates
      and deletes exactly its own profile.

    ``os.urandom`` rather than ``random`` or ``uuid`` because it needs no import
    at all — this module is on the confined worker's spawn path and every import
    here is paid on it. (The old comment's "no Date/random available in this
    codebase's constraints" was simply untrue: ``random`` is imported in
    ``abax/core/arrayfuncs.py`` and ``abax/core/functions/builtins.py``, and
    ``uuid`` is stdlib. It is gone rather than preserved.)

    Both limits below are measured against ``CreateAppContainerProfile`` on this
    platform, not taken from the documentation:

    * **length** — 64 characters is accepted, 65 is rejected with
      ``hr=0x80070057`` (``E_INVALIDARG``). Worst case here is 13 + 10 + 1 + 12 =
      36, with a full-width DWORD PID;
      ``test_profile_name_fits_the_measured_appcontainer_name_limits`` pins it
      against that widest PID rather than against whatever this run happens to
      have.
    * **charset** — ``\\`` and ``/`` are rejected (``0x80070003``), ``*`` and
      ``?`` are rejected (``0x8007007b``), ``:`` is rejected (``0x8007010b``).
      Hyphens, digits and ASCII letters — all this name contains — are accepted.
    """
    return f"abax-sandbox-{os.getpid()}-{os.urandom(6).hex()}"


def _needed_read_dirs() -> "list[str]":
    """*Directories* to grant the container read+execute: the base prefix
    (interpreter + stdlib) and the importable ``sys.path`` entries.

    Everything worth granting that is a directory, which is a *superset* of what
    the worker cannot live without — :func:`_required_read_targets` is the subset
    whose absence is fatal, and the note above it argues where the line falls.
    The ``sys.path`` entries that are *files* are :func:`_needed_read_files`'
    business, because they need a different ACE.
    """
    dirs = set()
    for base in (sys.base_prefix, sys.prefix, os.path.dirname(sys.executable)):
        if base and os.path.isdir(base):
            dirs.add(os.path.abspath(base))
    for entry in sys.path:
        if entry and os.path.isdir(entry):
            dirs.add(os.path.abspath(entry))
    # Drop entries already covered by a parent to keep the icacls work bounded.
    ordered = sorted(dirs, key=len)
    minimal = []
    for d in ordered:
        if not any(d != p and d.startswith(p + os.sep) for p in minimal):
            minimal.append(d)
    return minimal


def _needed_read_files() -> "list[str]":
    """*File*-shaped import roots to grant the container read+execute.

    A ``sys.path`` entry need not be a directory. A zipapp puts the archive
    itself on the path, and that is not a hypothetical here — it is how abax's
    own portable build runs. Measured under ``python abax.pyz``::

        sandbox_windows.__file__  D:\\abax\\abax.pyz\\abax\\sandbox_windows.pyc
        _abax_package_dir()       D:\\abax\\abax.pyz          (isfile, not isdir)

    so the archive is a *required* target that :func:`_needed_read_dirs` filters
    out with ``os.path.isdir``, never hands to icacls, and that
    :func:`_covered_by` then finds no ancestor grant for — because ``D:\\abax``
    is on ``sys.path`` only by accident of the CWD. Every strict launch in the
    shipped zipapp therefore refused *unconditionally*: strict mode was dead in
    the portable build. Granting the file fixes it.

    Kept separate from :func:`_needed_read_dirs` because the ACE differs, and not
    cosmetically. Measured on this platform::

        icacls <file> /grant "*S-1-15-2-1:(OI)(CI)(RX)"  -> exit 0, ACE ABSENT
        icacls <file> /grant "*S-1-15-2-1:(RX)"          -> exit 0, ACE present

    The inheritance flags have nothing to inherit on a leaf, and icacls drops the
    whole ACE rather than saying so: a grant that reports success and does
    nothing, which is precisely the failure mode this module exists to make
    impossible. Files get a plain ``(RX)``.

    The last entry is :func:`_abax_package_dir`'s answer when *it* is a file, so
    the archive is granted even if some future ``sys.path`` shape does not carry
    it: that path is required, and this is the only place that can grant it.
    """
    files: list[str] = []
    seen = set()
    for entry in [*sys.path, _abax_package_dir()]:
        if not entry or not os.path.isfile(entry):
            continue
        path = os.path.abspath(entry)
        key = os.path.normcase(path)
        if key not in seen:
            seen.add(key)
            files.append(path)
    return files


def _abax_package_dir() -> str:
    """The path that provides the ``abax`` package to the confined child.

    ``ConsoleBridge._spawn`` boots the worker as ``python -c "from
    abax.console_worker import main; main()"`` with the parent's ``sys.path``
    copied into ``PYTHONPATH``, so this is the entry that import resolves
    through: a checkout root, a ``site-packages`` directory, PyInstaller's
    ``_internal``, or — for the zipapp build — ``abax.pyz`` itself, which is a
    *file*, so it is granted by :func:`_needed_read_files` rather than by
    :func:`_needed_read_dirs`. Derived from this module's own location rather
    than guessed from ``sys.path``, because this module is *in* the package whose
    directory is wanted (inside the archive, ``__file__`` is
    ``…\\abax.pyz\\abax\\sandbox_windows.pyc`` and this still resolves).
    """
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Which failed grants are fatal — and why they are not all fatal
# --------------------------------------------------------------
# Refusing to launch whenever *any* path in `_needed_read_dirs()` could not be
# granted is the tempting rule, and it is wrong: that list is deliberately a
# superset. It carries every existing `sys.path` directory, which on a real
# machine means the CWD, whatever PYTHONPATH happened to be exported, and
# .pth-injected entries — directories the worker may never import a single
# module from. Refusing over one of those trades a silent failure for a spurious
# one, and a sandbox that refuses to start is a sandbox people switch off.
#
# Granting nothing fatal status is the bug this policy replaces (issue #8).
#
# The line between them is drawn by what each failure *looks like from outside*:
#
# * The interpreter — `python.exe`, its DLLs, the stdlib under `sys.base_prefix`
#   — and the path that provides `abax` are preconditions for the worker
#   existing at all. Lose the first and the child dies inside interpreter
#   startup: no traceback, no stderr, just an exit code. That is precisely the
#   signature of issue #6 (the worker could not open `nul`), which took months
#   to read *because* nothing distinguished it from a hang. Lose the second and
#   `-c "from abax.console_worker import main"` cannot resolve; the worker is
#   100% dead and no amount of retrying changes that.
# * Every other `sys.path` entry is a *maybe*. It may hold nothing the worker
#   imports; and if it does, the failure arrives as an ordinary
#   ModuleNotFoundError on the child's stderr, which the bridge already captures
#   and reports (`ConsoleBridge._dead_reason`). Diagnosable, therefore
#   survivable: carry on, and log it for whatever that is worth (the module
#   docstring measures exactly how little — the child's stderr, not the log
#   line, is what a reader will actually see).
# * The scratch dir is fatal for a different reason — it is the one *writable*
#   place in the jail and `child_env` points TEMP/TMP at it. A container that
#   cannot write there is not a degraded worker; it is one that fails at its
#   first temp file with an error pointing nowhere near the ACL that caused it.
#
# One distinction an `icacls` return code cannot make on its own: a failed
# `/grant` does not always mean the container cannot reach the path. The common
# case is an all-users Python under `C:\Program Files` — a non-elevated abax
# cannot rewrite that DACL, but Windows already grants ALL APPLICATION PACKAGES
# read+execute there, so the child reads it perfectly well today. Treating that
# as fatal would break strict mode on every machine-wide install. Hence
# `_container_ace_present`, consulted *only* when a required grant failed (so
# the ordinary path pays nothing) and used *only* to downgrade a refusal to a
# log line, never to upgrade one.
#
# Be clear-eyed about what "downgrade to a log line" buys today: that line is an
# `_log.info`, and with abax configuring no logging at all it is dropped before
# it is formatted (module docstring). The downgrade is still right — a refusal
# here would break strict mode on every machine-wide Python install — but the
# trace explaining why the launch proceeded does not currently exist anywhere a
# support report can reach. That is the argument for giving abax a handler, not
# for making this fatal.


def _required_read_targets() -> "list[str]":
    """The paths whose unreachability is fatal to the confined worker.

    The interpreter's own directory (which for a venv also holds
    ``pyvenv.cfg``), the base prefix that holds the stdlib, and whatever
    provides the ``abax`` package — a directory in a checkout or a wheel
    install, the ``abax.pyz`` archive (a *file*) in the portable build.
    Returned as *targets*, not as grantable paths: :func:`_needed_read_dirs`
    hands icacls a minimal covering set, so a target is satisfied by a grant on
    itself or on any ancestor.
    """
    targets: list[str] = []
    seen = set()
    for raw in (os.path.dirname(sys.executable), sys.base_prefix,
                _abax_package_dir()):
        if not raw:
            continue
        path = os.path.abspath(raw)
        key = os.path.normcase(path)
        if key not in seen:
            seen.add(key)
            targets.append(path)
    return targets


def _covered_by(target: str, granted: "list[str]") -> bool:
    """True when *target* is one of *granted* or lives under one of them.

    The ACEs we add to *directories* are inheritable — ``(OI)(CI)`` — so a grant
    on an ancestor reaches everything below it. That is what makes
    `_needed_read_dirs`' minimisation safe, and what lets an ``abax.pyz`` sitting
    inside an already granted directory count as reachable without a second
    grant. A file's own ``(RX)`` ACE inherits to nothing, but a file has nothing
    below it, so identity is the only case that matters there.
    """
    t = os.path.normcase(os.path.abspath(target))
    for entry in granted:
        g = os.path.normcase(os.path.abspath(entry))
        if t == g or t.startswith(g + os.sep):
            return True
    return False


def _container_ace_present(path: str) -> bool:
    """True when ALL APPLICATION PACKAGES already has an ACE on *path*.

    ``icacls <path> /findsid <sid>`` matches the well-known SID without a name
    lookup and, with no ``/T``, without recursing — one ~30 ms call. The
    discriminator is the *path echoed back* in icacls' "SID Found: <path>."
    line, never the wording of that line: every icacls message is localised (the
    lesson of issue #5), but the path it prints is the one we passed in. A path
    that cannot be listed at all exits non-zero, and any surprise answers False.

    Deliberately an approximation: an ACE's presence is not proof that it grants
    read+execute (it could be a DENY, or an unrelated right). It may only ever
    *downgrade* a refusal to a log line — an ``_log.info``, which a default
    install throws away (module docstring), so in practice the downgrade is
    silent. False, the conservative answer, is therefore also the safe one, and
    the worker's own fail-closed selftest still runs on the other side of the
    launch.

    **That is true of the refusal caller, and NOT of the other one.**
    :func:`_hold_session_grant` asks this to decide whether a grant can be
    *skipped*, so there ``True`` is the load-bearing answer: True means launch
    without walking the tree. A wrong True there launches a child into a tree it
    cannot read. That is not hypothetical — icacls writes the root's DACL first
    and the leaves last, so during another process's sweep this answers True
    while the tree is half-stripped (measured; see the note above
    ``_hold_session_grant`` and #9). Do not loosen this probe on the strength of
    the "False is the safe answer" argument above; it only holds for the caller
    it was written for.
    """
    try:
        r = subprocess.run(["icacls", path, "/findsid", ALL_APP_PACKAGES],
                           capture_output=True, text=True,
                           encoding=console_encoding(), errors="replace",
                           timeout=_FINDSID_TIMEOUT)
    except Exception:
        return False
    return r.returncode == 0 and path in (r.stdout or "")


def _icacls(path: str, *args: str) -> bool:
    """Run one ``icacls`` operation. True on success; **never** raises.

    ``icacls`` writes the console **OEM** codepage, not UTF-8, and ci.yml sets
    ``PYTHONUTF8=1`` for every job — so a bare ``text=True`` decodes strictly as
    UTF-8 and dies on the first non-ASCII byte in a principal name. Localised
    Windows installs have those as a matter of course (*Administratoren*,
    *Utilisateurs*, *Администраторы*). Hence ``encoding=console_encoding()``,
    which is ``"oem"`` here, matching ``tests/test_sandbox_windows.py::
    _ace_lines``; the shipping code and the test must read the same command the
    same way.

    We never look at the output — only ``returncode`` — so ``errors="replace"``
    costs nothing and means the decode cannot fail at all. The ``except`` is
    broad on purpose, as a second line of defence: the caller that matters is
    :func:`_revoke_container_access`, and it has no second chance. Every other
    failure mode here already degrades to ``False``; one that escapes as an
    unexpected type aborts the teardown partway and leaves the machine-wide
    ALL-APPLICATION-PACKAGES grant standing on the interpreter prefix and every
    ``sys.path`` directory, with nothing left to revert it. Returning ``False``
    loses an ACL operation; raising leaks the grant the sandbox exists to undo.
    """
    try:
        r = subprocess.run(["icacls", path, *args], capture_output=True,
                           text=True, encoding=console_encoding(),
                           errors="replace", timeout=60)
        return r.returncode == 0
    except Exception:
        return False


# The shared read grants are held for the SESSION, not for one worker (issue #11)
# ------------------------------------------------------------------------------
# `_grant_container_access` puts an ALL-APPLICATION-PACKAGES ACE on the
# interpreter prefix and on every `sys.path` directory. Those paths are
# **shared** — every confinement in this process needs exactly the same ones,
# only the scratch dir differs — while teardown is **per worker**:
# `cleanup_process(proc)` runs when one bridge's worker closes. abax has two
# long-lived strict-capable bridges in the GUI process
# (`abax/gui/console/pyconsole.py` and `abax/gui/mixin_macros.py`), so one
# worker's teardown really does fire while another's child is live.
#
# Three things were measured against the real icacls on this platform, and the
# third is the one that chose the design:
#
# 1. **The grants are not refcounted by Windows.** `icacls /grant` is idempotent
#    for a principal — granting twice adds one ACE — so a single `/remove`
#    deletes it. Grant twice, `/remove` once, and `_container_ace_present`
#    answers False. Two workers' granted lists share 4 of 5 paths.
#
# 2. **The AppContainer access check is not cached.** Stripping the ACE from
#    under a *live* confined worker breaks its very next import, immediately:
#
#        A <- 'IMPORT statistics'   =>  ModuleNotFoundError: No module named ...
#        A <- 'PING'                =>  PONG      (still up; it did not die)
#
#    A worker that has silently lost its standard library and a healthy pulse.
#
# 3. **Grant and revoke are not atomic.** Each is a DACL propagation walk — an
#    inheritable `(OI)(CI)` ACE rewrites the DACL of every file underneath — and
#    across the ~5 paths involved that walk was timed at 19.4-21.6 SECONDS.
#    During a revoke walk the tree is half-stripped, and every child spawned
#    into that window dies:
#
#        t= 0.8s             exit=0x00000000  'READY / IMPORTS-OK'
#        t= 3.3s .. 20.0s    exit=0x00000001  Fatal Python error: init_fs_encoding
#        t=20.8s             exit=0xC0000022  no output at all
#
#    That is issue #9's fatal text, reproduced from this mechanism.
#
# (3) is why this is a session-scoped grant and **not a refcount**. A refcount
# fixes (1) and (2) — the last holder revokes, so no live sibling is stripped —
# and leaves (3) entirely untouched: the 1->0 transition still opens a ~20 s
# window, and a worker that starts inside it still dies with no output. Even a
# perfect count is not sufficient. A refcounted implementation was written,
# reviewed and deliberately discarded on exactly this reasoning.
#
# So the shared paths are granted **once per process** and revoked **once, at
# process exit**. There is no 1->0 transition during the session at all, so
# there is no window for a starting worker to fall into.
#
# SCOPE THAT CLAIM TO ONE PROCESS — it is not machine-wide, and the difference
# is issue #9. The ACE names ALL APPLICATION PACKAGES, which is shared by every
# process on the box, so a *second* abax exiting walks the same DACLs this one
# is relying on. Measured: with P1 holding the grants and a live worker, P2's
# exit sweep running, and P1 spawning every 3 s through it, 1 spawn of 7 died —
# at t=4.0 s the /findsid probe answered True (icacls writes the ROOT's DACL
# first and the leaves last, so the root reads "present" while the tree is still
# being stripped), the grant was skipped, and the child died with
#   Fatal Python error: init_fs_encoding: failed to get the Python codec ...
# i.e. #9 exactly. Closing that needs a machine-scoped holder record, not a
# per-process one; it is tracked on #9 rather than pretended away here.
#
# The same change removes
# a second, purely-UX defect that was hiding inside this bug: every strict spawn
# used to pay a full grant walk *and* a full revoke walk, so the first strict
# console command of a session took twenty seconds to start and so did every one
# after it. Measured end to end on this machine, over the real interpreter
# prefix and `sys.path`:
#
#        spawn 1   grant 18.67 s    worker teardown 0.01 s
#        spawn 2   grant  0.05 s    worker teardown 0.01 s
#        spawn 3   grant  0.05 s    worker teardown 0.01 s
#        exit sweep      18.57 s    (once, and the machine is left as found)
#
# The teardown figure is the scratch dir alone, which is what a worker's teardown
# now owns; the 0.05 s is four `/findsid` probes.
#
# **Not the scratch dir.** It is `mkdtemp`'d per bridge, granted `(M)` rather
# than `(RX)`, and shared with nobody. It carries real WRITE access, and a temp
# dir reachable from every AppContainer on the machine after its worker is gone
# is a genuine exposure, so its revoke stays per-worker and unconditional. It is
# not in this table, and `_revoke_container_access` treats "not in the table" as
# "remove it" precisely so that stays true by construction.
#
# **Self-healing, not self-trusting.** The table is a record of intent, never of
# fact: if something outside abax strips an ACE, a later spawn must repair it.
# The discarded refcount trusted its own count absolutely — with `held > 0` it
# returned success without ever checking the ACE was there — which turns a
# transient strip into a permanent one. So every reuse is checked against the
# machine, and the check is a `/findsid` probe rather than an unconditional
# re-grant because a redundant `/grant` is not cheap. Measured here, interpreter
# prefix (~69k files):
#
#        cold grant, ACE absent        16.79 s
#        redundant grant #2 / #3 / #4  16.71 / 16.40 / 16.52 s
#        /findsid probe                 8.5 - 15.3 ms
#
# icacls walks the whole tree whether or not the ACE is already present, so
# "just re-grant every time" hands straight back the 20-s-per-spawn defect this
# design exists to remove. The probe is ~1800x cheaper than the work it decides
# about, and it runs once per shared path per spawn — four of them, 0.05 s in
# total, which is the whole cost of the second and every later strict spawn.
#
# **The lock.** Both bridges spawn and tear down from worker threads
# (`abax/workers.py` FuncWorker), so two first-use grants genuinely race. It is
# held *across* the icacls call, not merely across the dict access: dropping it
# in between would let a second spawn read "held" and launch while the first
# spawn's ~20 s walk had not landed — a child with no access and a table
# asserting it has some. The waiter's cost is bounded by `_icacls`' own 60 s
# timeout, and it is the wait it would otherwise have spent re-granting anyway.
# `threading` is free at import: `subprocess`, which this module already
# imports, has loaded it (measured). `atexit` is a builtin module, so importing
# it touches no file — which matters, because this module is on the confined
# worker's spawn path.
#
# **What a crash costs, stated plainly.** This table is in memory. If the
# process dies between a grant and the exit sweep — killed, hard crash, power
# loss — the shared ACEs are left standing on the interpreter prefix and every
# `sys.path` directory with nothing left to revert them. That exposure is not
# new; an unrevoked grant always leaked exactly this way. What changed is the
# window: it used to be one worker's lifetime and it is now the whole session.
# Nothing here sweeps a *previous* run's leftovers, deliberately: a sweeper has
# to tell an ACE abax left behind from one the machine legitimately carries — an
# all-users Python under `C:\Program Files` has these ACEs by default, which is
# the entire reason `_container_ace_present` exists — and that is separate work
# with its own failure modes. `abax doctor` is where it would belong, not
# teardown.
_SESSION_GRANTS_LOCK = threading.Lock()

#: ``{normcased path: (path as granted, the ACE string used)}`` — the shared
#: read grants this process is holding until it exits. The ACE is kept so a
#: repair can re-issue the *same* grant rather than guess at one.
_SESSION_GRANTS: "dict[str, tuple[str, str]]" = {}

#: The PID the exit sweep was registered in, or None. See
#: :func:`_register_session_sweep` for why the answer is a PID and not a bool.
_SESSION_SWEEP_PID: "int | None" = None

#: How long the exit sweep will wait for a spawn in flight to finish before
#: sweeping anyway. Bounded because this runs during interpreter shutdown and a
#: hung `icacls` must not wedge the process on the way out; generous enough to
#: cover a grant that is already most of the way through its DACL walk.
_SESSION_SWEEP_LOCK_WAIT = 5


def _shared_key(path: str) -> str:
    """The session-table key for *path* — one entry per path, however spelled.

    The same normalisation :func:`_covered_by` uses, and for the same reason:
    two bridges can arrive at one directory through differently-cased
    ``sys.path`` entries, and two entries for one ACE would let the exit sweep
    issue two ``/remove`` calls for it while a reuse check missed the first.
    """
    return os.path.normcase(os.path.abspath(path))


def _session_grant_paths() -> "list[str]":
    """The shared paths this process is currently holding for the session.

    Nothing in this module calls it. It exists so a test — and any future
    diagnostic — can read the table without duplicating :func:`_shared_key`'s
    convention or touching it without the lock.
    """
    with _SESSION_GRANTS_LOCK:
        return [path for path, _ace in _SESSION_GRANTS.values()]


def _is_session_grant(path: str) -> bool:
    """True when *path* is held for the session, so no teardown may revoke it.

    Deliberately **without** the lock, which is a latency decision and a safety
    argument rather than an oversight. The latency: this runs once per path in
    every teardown, and ``ConsoleBridge`` closes a worker from the GUI thread, so
    taking a lock another thread may be holding for a 20 s DACL walk would freeze
    the window for that long — to answer a question that walk cannot change.

    The safety: a single ``in`` on a dict is atomic, and the only answer that
    could do harm is a False for a path that really is held, which cannot happen.
    A key is inserted *before* :func:`_hold_session_grant` returns True, and
    returning True is the only thing that puts the path into a caller's
    ``granted`` list — so by the time any teardown can be looking at a path, its
    key is already in the table. The one removal is :func:`_revoke_session_grants`
    clearing the lot at exit, after which a stray ``/remove`` finds no ACE and
    succeeds anyway.
    """
    return _shared_key(path) in _SESSION_GRANTS


def _register_session_sweep() -> None:
    """Arm :func:`_revoke_session_grants` for process exit. Called under the lock.

    Registered **lazily, from the first successful shared grant**, rather than at
    import — and that is the whole answer to "must not fire in a child".
    :mod:`abax.sandbox_windows` is imported inside the confined worker too
    (``abax/console_worker.py`` calls ``select_confinement().apply_in_child``),
    and a hook armed at import time would be armed there as well. A child never
    grants anything — ``apply_in_child`` returns immediately, confinement having
    been established by the parent at ``CreateProcess`` time — so it never
    reaches this function and never registers. The registration follows the
    grant because the grant is the thing that needs undoing.

    The PID is recorded rather than a bare "done" flag so the hook can refuse to
    run in a process that did not do the granting. Windows has no ``fork`` and
    ``multiprocessing`` re-imports this module fresh in the child, so nothing
    on this platform can inherit the registration today; the guard is there
    because "revoked the parent's grants from a child" is a silent, machine-wide
    failure, and one comparison is cheap insurance against a future platform or
    a future launcher that does inherit it.
    """
    global _SESSION_SWEEP_PID
    if _SESSION_SWEEP_PID is not None:
        return
    # Register FIRST, record second. The other order means a register that
    # raises or no-ops still marks the module "armed", every later call
    # short-circuits above, and nothing ever revokes the machine-wide grants —
    # silently, which is the worst failure this module has. This way a failed
    # register simply leaves it unarmed and the next grant tries again.
    atexit.register(_revoke_session_grants)
    _SESSION_SWEEP_PID = os.getpid()


def _revoke_session_grants() -> "list[str]":
    """Remove every shared grant this process is holding. The exit sweep.

    **Never raises, under any circumstances.** It runs from ``atexit``, where a
    traceback is printed to a stderr the windowed ``abaxw.exe`` does not have and
    where module globals are already being torn down; an exception here would
    also abandon the remaining paths. Everything is inside one guard for that
    reason, and the guard catches :class:`BaseException` rather than
    :class:`Exception` because interpreter shutdown can deliver things that are
    neither — the point is that the process exits, not that this succeeds.

    Returns the paths whose ``/remove`` failed, for the direct caller (a test, or
    a future ``abax doctor``); ``atexit`` discards it, which is exactly why the
    failure is logged as well.

    The lock is taken with a timeout rather than unconditionally: a spawn in
    flight holds it for the length of a DACL walk, and waiting out a full 60 s
    ``icacls`` timeout on the way out of the process is worse than sweeping
    beside it. The table is emptied under whatever lock we got, so a concurrent
    ``_hold_session_grant`` either ran before us (its path is in our snapshot) or
    runs after — and that second case is not free, so do not read it as
    harmless: a grant landing after the table is cleared and this loop has
    finished is never revoked by anything, which is the same permanent
    machine-wide ACE the crash case above describes. It needs the timeout to
    expire *and* a spawn to complete during shutdown, so it is narrow, but it is
    a leak rather than a wasted walk.

    Also worth knowing before changing this: the sweep is a full DACL walk,
    measured at 19.0-19.4 s over the four real paths here. abax's entry point
    returns normally, so this does run — after the last window is gone. On the
    shipped windowed ``abaxw.exe`` that means the UI vanishes while the process
    sits in the task list for ~19 s doing I/O with nothing on screen to explain
    it. That is a deliberate trade: it replaced a ~19 s walk on *every* worker
    teardown during the session.
    """
    try:
        if _SESSION_SWEEP_PID is not None and _SESSION_SWEEP_PID != os.getpid():
            # Armed in another process and inherited into this one. Those ACEs
            # are the parent's and the parent is still using them; removing them
            # here would strip a live confinement from inside its own child. See
            # `_register_session_sweep` for why this cannot happen on Windows
            # today and why it is checked anyway.
            return []
        got = _SESSION_GRANTS_LOCK.acquire(timeout=_SESSION_SWEEP_LOCK_WAIT)
        try:
            held = list(_SESSION_GRANTS.values())
            _SESSION_GRANTS.clear()
        finally:
            if got:
                _SESSION_GRANTS_LOCK.release()
        failed = []
        for path, _ace in held:
            if _icacls(path, "/remove", ALL_APP_PACKAGES):
                continue
            if not os.path.exists(path):
                continue                   # its ACL went with it; nothing leaked
            failed.append(path)
        if failed:
            _log.warning(
                "sandbox: %d shared ALL APPLICATION PACKAGES grant(s) could not "
                "be revoked at exit and are still standing on: %s",
                len(failed), ", ".join(failed))
        return failed
    except BaseException:                  # noqa: BLE001 - see the docstring
        return []


def _hold_session_grant(path: str, ace: str, granted: "list[str]") -> bool:
    """Make sure the shared ALL APPLICATION PACKAGES grant on *path* is in force.

    Applies *ace* with icacls on first use in this process, and thereafter only
    when the machine says the ACE has gone — checked with
    :func:`_container_ace_present` (~10 ms) rather than assumed from the table,
    so an ACE removed by something outside abax is repaired by the next spawn
    instead of skipped forever. On success *path* is appended to *granted*,
    which is what makes it count as reachable for
    :func:`_unreachable_requirements`; it is **not** thereby made revocable —
    :func:`_revoke_container_access` refuses to remove anything in the table.

    Returns False when the grant genuinely did not land, and then the caller is
    told the honest thing: the path is not in *granted*, so it is not covered,
    so ``custom_spawn`` refuses the launch if it was required. The table entry is
    left as it was — it records what this session intends to hold, and the next
    spawn will probe and try the repair again.

    Everything is inside the lock, including the icacls call: see the note above.
    """
    key = _shared_key(path)
    with _SESSION_GRANTS_LOCK:
        if key in _SESSION_GRANTS and _container_ace_present(path):
            granted.append(path)           # already in force; no walk, no window
            return True
        if not _icacls(path, "/grant", ace):
            return False
        _SESSION_GRANTS[key] = (path, ace)
        _register_session_sweep()
        granted.append(path)
        return True


def _grant_container_access(
        scratch: str,
        granted: "list[str] | None" = None) -> "tuple[list[str], list[str]]":
    """Grant ALL APPLICATION PACKAGES the access the worker needs.

    Returns ``(granted, unreachable)``:

    * ``granted`` — the paths this confinement can **reach**. An ACE is in force
      on every one of them, though not necessarily applied by this call: the
      shared read paths are held for the session (see the note above
      :func:`_hold_session_grant`), so a path an earlier spawn already granted
      is verified here rather than re-granted. It is also the list teardown is
      handed, and teardown removes the subset it owns — the scratch dir, not the
      session's. A path icacls refused is in neither sense present: the caller
      must not believe the container can reach it.
    * ``unreachable`` — the *required* paths (see the policy note above) the
      container still cannot reach. Non-empty means the caller must not spawn.

    A caller may pass its own list as *granted*; it is appended to in place, so
    the ACEs applied before an unexpected failure anywhere in here are still
    reachable by that caller's teardown. :meth:`custom_spawn` does exactly that —
    the return value is no use to a teardown for a call that never returned.
    """
    if granted is None:
        granted = []
    # The scratch dir: full modify (the worker writes here). Deliberately *not*
    # session-held — it is this worker's own `mkdtemp`, it carries write access,
    # and it is granted and revoked unconditionally with the worker.
    if _icacls(scratch, "/grant", f"{ALL_APP_PACKAGES}:(OI)(CI)(M)"):
        granted.append(scratch)
    else:
        _log.warning("sandbox: could not grant the confined worker write access "
                     "to its scratch dir %s", scratch)
    # Read + execute on the interpreter and import dirs, inheritable so one ACE
    # covers the whole tree. Shared with every other confinement in this process,
    # hence held for the session rather than granted per worker.
    for d in _needed_read_dirs():
        if not _hold_session_grant(d, f"{ALL_APP_PACKAGES}:(OI)(CI)(RX)", granted):
            _log.warning("sandbox: could not grant the confined worker read "
                         "access to %s", d)
    # ...and on the file-shaped import roots (a zipapp archive), which take a
    # plain (RX): the inheritance flags above are silently discarded on a leaf,
    # see `_needed_read_files`. Anything already under a granted directory is
    # skipped — the inheritable ACE reaches it, and a redundant explicit ACE is
    # one more thing the exit sweep has to remove. Shared for the same reason the
    # directories are: two bridges import the package from one archive.
    for f in _needed_read_files():
        if _covered_by(f, granted):
            continue
        if not _hold_session_grant(f, f"{ALL_APP_PACKAGES}:(RX)", granted):
            _log.warning("sandbox: could not grant the confined worker read "
                         "access to %s", f)
    return granted, _unreachable_requirements(scratch, granted)


def _unreachable_requirements(scratch: str, granted: "list[str]") -> "list[str]":
    """The required paths the container still cannot reach after granting."""
    unreachable = []
    keys = {os.path.normcase(os.path.abspath(p)) for p in granted}
    if os.path.normcase(os.path.abspath(scratch)) not in keys:
        # Identity, not coverage: the scratch dir needs (M), and merely sitting
        # inside some directory we granted (RX) would satisfy a coverage test
        # while leaving the worker unable to write a single byte.
        unreachable.append(scratch)
    for target in _required_read_targets():
        if _covered_by(target, granted):
            continue
        if _container_ace_present(target):
            _log.info("sandbox: %s could not be granted, but ALL APPLICATION "
                      "PACKAGES already has an ACE there — continuing", target)
            continue
        unreachable.append(target)
    return unreachable


def _revoke_container_access(granted: "list[str]") -> "list[str]":
    """Remove the per-worker ACEs. **Never raises**; returns what would not go.

    Per-worker: a path held for the session (see the note above
    :func:`_hold_session_grant`) is skipped here — the whole design is that
    there is no 1->0 transition mid-session for a starting worker to fall into,
    and a teardown that removed one would put the window straight back. The
    scratch dir is not in that table and so comes off unconditionally, which is
    the half that matters most: it carries ``(M)``, and a writable temp dir left
    reachable from every AppContainer on the machine is a real exposure. Any
    path a caller hands in without having taken it through
    :func:`_grant_container_access` is likewise removed unconditionally, so the
    "remove it" branch is the default and only an explicit session entry buys an
    exemption.

    **A path deliberately kept is not a path that leaked**, and the two must not
    reach :func:`cleanup_process` looking alike: one says "an ALL APPLICATION
    PACKAGES ACE is standing on your interpreter prefix and nothing will ever
    take it off", the other says "this process is still using it and will drop
    it on the way out". Only the first is in the returned list. The skip happens
    before any icacls call, so a held path is never even attempted.

    Teardown has to continue past a failure — that was fixed deliberately in
    issue #5, and it runs from ``finally`` blocks and from the crashed-worker
    path. But a failure that is only *survived* leaves a machine-wide
    ALL-APPLICATION-PACKAGES grant standing on a developer's interpreter prefix
    and every ``sys.path`` directory of their real Python installation, with
    nothing anywhere to say so. So it is logged *and* handed back:
    :func:`cleanup_process` returns it to the bridge, and a future ``abax
    doctor`` can look for exactly these paths after an interrupted run.

    Of that pair, only the second is load-bearing. The ``_log.warning`` below
    clears the level bar but reaches nothing except :data:`logging.lastResort`'s
    stderr — which the windowed ``abaxw.exe`` does not have (module docstring).
    The returned list is the report; the log line is a courtesy to whoever ran
    abax from a console.

    A path that no longer exists is not counted: its ACL went with it, so there
    is nothing left to leak. The bridge deletes the scratch dir on close, and a
    revoke racing that deletion is bookkeeping noise, not a leak.
    """
    failed = []
    for path in granted:
        if _is_session_grant(path):
            continue                   # this process holds it until it exits
        if _icacls(path, "/remove", ALL_APP_PACKAGES):
            continue
        if not os.path.exists(path):
            continue
        failed.append(path)
    if failed:
        _log.warning(
            "sandbox: %d ALL APPLICATION PACKAGES grant(s) could not be revoked "
            "and are still standing on: %s", len(failed), ", ".join(failed))
    return failed


def cleanup_process(proc) -> "list[str]":
    """Revert the ACL grants and delete the container profile for a finished
    process. Called by the bridge when it closes a confined worker.

    Returns **what teardown could not clear** — empty for the ordinary case, and
    empty for a process this module never confined. Never raises. A shared read
    path this teardown left standing *on purpose*, because the process holds it
    for the session and revokes it at exit, is not in the list either: it is not
    a leftover, it is live state with an owner (see
    :func:`_revoke_container_access`). Two kinds of
    leftover go in the one list, and they are told apart by shape:

    * an absolute **path** — an ALL APPLICATION PACKAGES ACE still standing on
      it, from :func:`_revoke_container_access`;
    * an **AppContainer profile name** (``abax-sandbox-<pid>-<hex>``, see
      :func:`_profile_name`) — its ``DeleteAppContainerProfile`` failed, so a
      ``HKCU\\...\\AppContainer\\Mappings`` entry and a ``%LOCALAPPDATA%\\
      Packages\\<name>`` tree are still on the machine with nothing left to
      collect them.

    The profile half is reported for exactly the reason the ACL half is: it is
    the same class of leak, and the ``except OSError`` below only lets teardown
    *continue* past it — deliberately, since the ACLs are the security-relevant
    half and must come off regardless (``test_cleanup_process_survives_a_failing
    _profile_delete``). Continuing is not the same as swallowing. It used to be
    both, because :func:`abax._winsandbox_ctypes.delete_app_container_profile`
    discarded its HRESULT and this ``except`` could never fire at all.

    The name rather than a path because the name is the identity of *both*
    halves of the leak, and because the surviving artefact is the registry
    mapping — measured — while the ``Packages`` directory may or may not still
    be there. ``abax-sandbox-`` is already this codebase's marker for the thing
    (:func:`_profile_name`, and ``_profile_dirs`` in the tests), so a future
    ``abax doctor`` reading this list can tell a profile from a path without
    being told which is which.
    """
    info = getattr(proc, "_sandbox_cleanup", None)
    C = getattr(proc, "_sandbox_ctypes", None)
    if info is None:
        return []
    granted, profile_name = info
    leaked = _revoke_container_access(granted)
    if C is not None:
        try:
            C.delete_app_container_profile(profile_name)
        except OSError as exc:
            _log.warning(
                "sandbox: AppContainer profile %s could not be deleted (%s) and "
                "is still registered on this machine", profile_name, exc)
            leaked.append(profile_name)
    proc._sandbox_cleanup = None  # noqa: SLF001
    return leaked
