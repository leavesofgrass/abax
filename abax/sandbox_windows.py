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
the process, are taken once per session, and come off once, at process exit —
and then only when no *other* abax process is still relying on them, because the
ACE names ALL APPLICATION PACKAGES and is machine-wide however local the
bookkeeping feels. See the note above :func:`_hold_session_grant` for the three
measurements that forced the first split, and the note above :func:`_acl_mutex`
for the two cross-process windows (issue #9) that forced the second. Both halves
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

Pure stdlib (atexit, contextlib, ctypes, _winapi, msvcrt, os, sys, threading,
subprocess for icacls). No deps — ``contextlib`` is already loaded by
``subprocess``, which this module imports, so it costs nothing on the confined
worker's spawn path. Imports cleanly on any OS — all Windows-only work is inside
method bodies.
"""

from __future__ import annotations

import atexit
import contextlib
import logging
import os
import subprocess
import sys
import threading

from . import _runtime as _rt
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
# path, once per required target, and at 60 each three stalled probes would add
# three minutes to a launch that is already failing before the user is told
# anything. (That used to read "freeze the window for three minutes", which was
# literally true — all three execution entry points now reach this from a worker
# thread, so it costs the run rather than the window. It is still three minutes
# of nothing, which is why the short wait stays.) A timeout can only ever answer
# False, and False never upgrades a refusal, so cutting the wait short can lose
# nothing but the wait.
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
    ``{"output": "", "error": …}`` response rather than letting it unwind. That
    used to be because ``_run_macro`` and the Run-script path called the bridge
    *synchronously on the GUI thread*, where an escaping exception leaves a Qt
    slot; those two now run on a worker thread like the console, so the reason
    has changed but not the conclusion — a raise would be caught by
    ``FuncWorker.run`` and reported as a generic worker error, losing the
    envelope handling and the operation-specific dialog that a response gets.
    See ``ConsoleBridge._roundtrip`` for the current version of the argument.
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
# THAT CLAIM STOPS AT THE PROCESS BOUNDARY, and what lies past it was issue #9.
# The ACE names ALL APPLICATION PACKAGES, which is shared by every process on the
# box, so a *second* abax exiting walks the same DACLs this one is relying on.
# Measured, with P1 holding the grants and a live worker, P2's exit sweep
# running, and P1 spawning every 3 s through it: 1 spawn of 7 died — at t=4.0 s
# the /findsid probe answered True (icacls writes the ROOT's DACL first and the
# leaves last, so the root reads "present" while the tree is still being
# stripped), the grant was skipped, and the child died with
#   Fatal Python error: init_fs_encoding: failed to get the Python codec ...
# i.e. #9 exactly — and P1's *live* worker lost its stdlib in the same run. Both
# of those are closed by the machine-wide mutex and the cross-process holder
# record; see the note above `_acl_mutex`, which is where the design for that
# lives and where the before/after numbers are.
#
# The session-scoped grant also removes
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


# Closing the two CROSS-process windows (issue #9)
# ------------------------------------------------
# Everything above is right and insufficient: it makes one process's grants safe
# from that process's own teardowns. The ACE is machine-wide, so a *second* abax
# walking the same DACLs reopens the problem in two distinct shapes, and a fix
# has to close both. Measured with P1 holding the grants and a live worker, P2
# granting and then exiting so its atexit sweep walks the same paths, and P1
# spawning a fresh confined worker every 3 s straight through that walk:
#
#   W1  A SWEEP STRIPS PATHS ANOTHER LIVE PROCESS IS USING. P2's sweep is a
#       correct sweep *of P2's grants* — which are the same four paths P1 is
#       running on. P1's already-live worker lost its standard library mid-
#       session, exactly as measurement (2) above describes, while staying up
#       and answering PING.
#
#   W2  A GRANTOR PROBES DURING SOMEONE ELSE'S WALK. icacls writes the root's
#       DACL first and the leaves last, so `/findsid` — which asks about the
#       root — answers True while the tree is still half-stripped. At t=4.0 s
#       the probe said True, `_hold_session_grant` took the fast path in ~1.5 s,
#       and the child died with
#           Fatal Python error: init_fs_encoding: failed to get the Python
#           codec of the filesystem encoding
#       1 spawn of 7 died that way.
#
# W2 is the reason a holder count on its own is not a fix. Even if only the last
# holder ever sweeps, a process *starting* during that sweep still reads a
# misleading probe. The two windows need two mechanisms:
#
# THE MUTEX closes W2 by making the observation trustworthy: nobody may walk
# these DACLs while another process is walking them, and nobody may probe-and-
# skip while a walk is in flight. `_acl_mutex` is held across the whole of
# `_grant_container_access` — the probe, the fast path, the grant walk and the
# `_unreachable_requirements` check — and across the whole of the exit sweep.
# It is deliberately *not* held across `CreateProcessW`, and does not need to be:
# by the time it is released this process has published a holder record, and a
# holder record is what stops anyone else from stripping the tree underneath the
# launch.
#
# THE HOLDER RECORD closes W1 by making the sweep conditional: the ACEs come off
# only when no other live process is relying on them. Last one out turns off the
# lights.
#
# Why `Local\` and not `Global\`, measured rather than assumed. The received
# reason to avoid `Global\` is that it needs SeCreateGlobalPrivilege — and on
# this box that is simply **false**: a non-elevated token with no such privilege
# in `whoami /priv` created `Global\...` successfully. The real reasons are
# different and still point the same way. A `Global\` mutex created by one user
# carries that user's default DACL, so a second *user's* abax cannot open it and
# gets ERROR_ACCESS_DENIED — it would not be serialised with us either way,
# unless we published a machine-wide-writable synchronisation object, which is a
# denial-of-service surface (hold it and every abax on the box stalls for the
# full timeout) bought for a case that does not arise on a desktop. `Local\` is
# per *session*, and elevation does not change session, so an elevated abax and a
# non-elevated one in the same desktop session — the pair that actually collides
# — share it. What is deliberately NOT covered: two logon sessions (fast user
# switching, a concurrent RDP session) still race, and that residual window is
# stated here rather than papered over.
#
# Cost, measured on this machine. Uncontended, create+wait+release+close is
# 0.010 ms — nothing next to the 8.5 ms probe it guards. Contended, a spawn waits
# out whoever is walking: worst case one full sweep, 19-21 s. That is a real cost
# and it is the right trade — the alternative is the dead worker above — but it
# is a cost, so it is bounded (`_ACL_MUTEX_GRANT_WAIT`) and it degrades openly
# rather than into a lie: a wait that times out proceeds *without* trusting the
# probe (`trust_probe=False`), because the probe is exactly the thing the mutex
# was making trustworthy. That pays a redundant ~20 s grant walk instead of
# risking a child that cannot read its own stdlib.
#
# WHERE THAT COST LANDS, because it decided a change outside this module. The
# wait and the walk are paid by whoever called `custom_spawn`, and until this
# was looked at, two of abax's three execution entry points called it
# *synchronously from a Qt slot*: `_run_macro` and Run-script in
# `abax/gui/mixin_macros.py`. So the numbers above were window-freeze numbers. A
# single spawn was measured blocking 36.7 s, and the ceiling is worse than that
# — 60 s of mutex wait, then a ~20 s walk the timeout has just guaranteed will
# not be skipped. None of it is new in kind: before the mutex existed the same
# slot could block on the ~20 s walk alone. What the serialisation added is the
# 60 s wait in front of it, and the `trust_probe=False` fallback that turns a
# spawn which would have cost 0.05 s into a full walk.
#
# Tuning these constants cannot fix that, and it is worth being explicit about
# why, because "make the GUI-thread wait shorter" is the obvious move. A shorter
# wait does not remove the block — it converts a wait into a walk of the same
# order (that is exactly what the `trust_probe=False` fallback is), and the very
# first strict spawn of a session has a ~19 s walk to pay whatever the mutex
# does. There is no value of `_ACL_MUTEX_GRANT_WAIT` at which "grant an
# AppContainer read access to the interpreter prefix" becomes an operation you
# can do on a UI thread. So the entry points moved instead: all three now drive
# the bridge from a `FuncWorker` on a QThread, and the window stays live with a
# busy cursor and a progress bar for however long the walk takes. These waits
# are therefore left alone — on a worker thread, waiting out someone else's
# 19-21 s sweep really is better than paying a redundant 20 s walk, which is the
# trade this constant was chosen for in the first place.
#
#: The one name, deliberately not keyed by interpreter prefix. Two abax
#: processes on different Pythons still share `sys.path` entries (a checkout, a
#: shared site-packages), so keying by prefix would let exactly the overlapping
#: case race. Over-serialising costs a wait; under-serialising costs a worker.
_ACL_MUTEX_NAME = r"Local\abax-sandbox-acl-grants"

#: How long a grant will wait for another process's walk. One sweep is 19-21 s
#: and a grant is 17-20 s, so 60 covers a sweep followed by a grant with room to
#: spare; it is also `_icacls`' own timeout, which is this module's existing
#: answer to "how long may one ACL operation take".
_ACL_MUTEX_GRANT_WAIT = 60

#: The same wait for the exit sweep, shorter because it runs during interpreter
#: shutdown: sweeping beside someone is bad, and hanging the process on the way
#: out is worse. Long enough for a full grant walk to finish first.
_ACL_MUTEX_SWEEP_WAIT = 30

#: The process-wide handle, opened once. A Win32 mutex is owned by a *thread*
#: and is recursive for its owner (measured: a second wait on the same thread
#: returns WAIT_OBJECT_0 immediately, even through a different handle to the same
#: name), so nesting `_acl_mutex` is safe as long as every acquire is released —
#: which is what the context manager is for.
_ACL_MUTEX_HANDLE: "int | None" = None
_ACL_MUTEX_HANDLE_LOCK = threading.Lock()


def _acl_mutex_handle() -> "int | None":
    """The named-mutex handle for this process, or None if it cannot be had.

    None is a real answer, not an error: a squatted name with a hostile DACL, a
    handle exhaustion, a future platform without the API. Every caller degrades
    rather than refusing, because refusing to grant means refusing to launch, and
    an unserialised launch is what abax did before this existed.
    """
    global _ACL_MUTEX_HANDLE
    with _ACL_MUTEX_HANDLE_LOCK:
        if _ACL_MUTEX_HANDLE is None:
            try:
                from . import _winsandbox_ctypes as C

                _ACL_MUTEX_HANDLE = C.create_named_mutex(_ACL_MUTEX_NAME)
            except Exception as exc:           # noqa: BLE001 - degrade, see above
                _log.warning(
                    "sandbox: the ACL serialisation mutex %s could not be opened "
                    "(%s) — grants and sweeps in this process are not serialised "
                    "against other abax processes", _ACL_MUTEX_NAME, exc)
                return None
        return _ACL_MUTEX_HANDLE


@contextlib.contextmanager
def _acl_mutex(timeout: float, what: str):
    """Hold the machine-wide ACL mutex for the duration of the block.

    Yields True when we own it and False when we are proceeding without it — the
    caller must look, because the second case is where the probe stops being
    trustworthy (see the note above).

    ``WAIT_ABANDONED`` is treated as success, which is the whole recovery story
    for a process killed mid-walk: Windows hands the next waiter ownership and a
    0x80 status instead of leaving the mutex owned forever. Measured here — the
    release then succeeds and a re-acquire returns 0x0. Not handling it would
    mean one hard-killed abax wedges every later one at this exact line, for the
    life of the boot, which is a far worse failure than the one being fixed.
    It is logged, because it means somebody died holding the ACLs half-walked.
    """
    handle = _acl_mutex_handle()
    C = None
    held = False
    if handle is not None:
        try:
            from . import _winsandbox_ctypes as C

            code = C.wait_for_mutex(handle, int(timeout * 1000))
        except Exception as exc:                   # noqa: BLE001 - degrade
            _log.warning("sandbox: waiting for the ACL mutex before %s failed "
                         "(%s) — continuing unserialised", what, exc)
        else:
            if code == C.WAIT_ABANDONED:
                held = True
                _log.warning(
                    "sandbox: the ACL mutex was abandoned by a process that died "
                    "holding it; recovering ownership before %s — the shared "
                    "grants may be half-applied or half-removed", what)
            elif code == C.WAIT_OBJECT_0:
                held = True
            else:
                _log.warning(
                    "sandbox: could not take the ACL mutex within %ss before %s "
                    "(wait=0x%x) — another process is walking these DACLs; "
                    "continuing without it", timeout, what, code)
    try:
        yield held
    finally:
        if held:
            try:
                C.release_mutex(handle)
            except Exception:                      # noqa: BLE001 - teardown only
                _log.warning("sandbox: releasing the ACL mutex after %s failed; "
                             "it will be reclaimed as abandoned", what)


# The holder record — who else is relying on these ACEs right now
# ---------------------------------------------------------------
# One file per holding process, in a directory under `_runtime.DATA_DIR`. Three
# properties decided the shape:
#
# * **It must survive a hard kill without corrupting.** So the *identity* lives
#   in the file NAME (`<pid>-<creation-time>.hold`) rather than in its contents:
#   a process killed between `open` and `write` leaves a zero-length file whose
#   name is still completely readable. The contents are the paths that process
#   holds, written to a sibling and `os.replace`d into position, so a reader sees
#   either the whole previous version or the whole new one.
#
# * **A crashed holder must not block the sweep forever.** Hence PID *plus*
#   process creation time, not a bare PID: PIDs are reused, and a reused PID
#   would make a dead abax look live for as long as the box stays up — which
#   means the machine-wide ACEs would never come off again. `process_create_time`
#   pins the record to one process (100 ns resolution) and answers None for a
#   PID that is gone or has exited.
#
# * **Who can make abax skip its own cleanup, stated as measured.** The claim
#   here used to be that `DATA_DIR`'s DACL "is this user + SYSTEM +
#   Administrators (measured with icacls; no world-writable ACE)". Re-measured,
#   `icacls "%LOCALAPPDATA%\abax"` prints FIVE ACEs, every one of them inherited
#   (`(I)`) from `%LOCALAPPDATA%` itself, which prints exactly the same five:
#
#       S-1-15-3-<capability>:(I)(F)
#       S-1-15-3-<capability>:(I)(OI)(CI)(IO)(F)
#       <this user>:(I)(OI)(CI)(F)
#       NT AUTHORITY\SYSTEM:(I)(OI)(CI)(F)
#       BUILTIN\Administrators:(I)(OI)(CI)(F)
#
#   The two the old list omitted are a capability SID (the `S-1-15-3-` domain;
#   this one does not resolve to a name on this box, so icacls prints it raw)
#   carrying FULL control — object-inherit/container-inherit/inherit-only on the
#   second ACE, so it reaches this directory and everything created under it. A
#   capability SID is in a token only when the process was granted that
#   capability, which in practice means packaged/AppContainer apps of this user;
#   it is not another *user*. So the old sentence's conclusion survives — no
#   world-writable ACE, no second user — while its premise did not.
#
#   THE QUESTION THIS EXISTS TO ANSWER is narrower than the ACE list, and it
#   deserves an answer rather than a list: can another principal plant a holder
#   record that makes abax skip its own cleanup? **Yes, and the DACL is not what
#   stops it.** Anything that can write into this directory can plant a
#   live-looking record — `<pid>-<creation time>.hold` naming any running
#   process, and a process's creation time is readable by any process on the box
#   — after which every abax exit sweep defers forever and the shared ACEs stay
#   on the interpreter prefix until something removes them by hand. What bounds
#   that is not the ACL, it is the *ceiling on the damage*: the ACEs in question
#   are additive read+execute for ALL APPLICATION PACKAGES, so the worst outcome
#   is that AppContainer'd code on this machine keeps being able to read a tree
#   this user can already read. Nothing is granted that was not already granted;
#   the cleanup is what is lost.
#
#   And the principal set is exactly the set that already has strictly more than
#   this. `_runtime.CONFIG_DIR` and `_runtime.DATA_DIR` are the SAME directory on
#   Windows (both `%LOCALAPPDATA%\abax`, measured), and `CONFIG_DIR/init.py` is
#   executed as arbitrary Python with the user's privileges by design
#   (`abax/userconfig.py::load_user_config`). Anyone who can plant a holder
#   record here can instead drop an `init.py` beside it and run code inside abax.
#   That is the reason this directory is the right place for the record — not
#   that it is impregnable, but that a record forged there is the *weakest* thing
#   an attacker with write access to it would bother doing.
#
# A deferral is also a HANDOFF. When a sweep finds another live holder it leaves
# its own record in place instead of deleting it, and whoever sweeps last unions
# its paths into the removal — which matters because two abax processes need not
# hold the *same* paths (different CWDs put different entries on `sys.path`). The
# same code path also collects what a crashed abax left behind, so the leak that
# used to be permanent (a run killed between grant and sweep) is now cleared by
# the next abax that exits cleanly.
#
# THE HANDOFF DOES NOT FALL OUT OF LIVENESS ALONE, which is what this originally
# claimed ("the process then exits, so the record becomes stale by definition").
# It does not become stale by definition; it becomes stale when the *operating
# system* says that PID is gone, and a process that has begun its exit sweep is
# still very much running. Two abax processes exiting close together therefore
# each saw the other as live, each deferred, and the ACEs were left with nothing
# scheduled to collect them. Reproduced deterministically with two real holders,
# P1 sweeping while P2 was up and P2 sweeping while P1 was still up:
#
#     P1 SWEPT [] record=kept
#     P2 SWEPT [] record=kept
#     both exited, rc: 0 0
#     ACE after ALL holders exited: True
#     holder records left: ['35232-...hold', '42164-...hold']
#
# Four machine-wide ACEs standing, two orphaned records, and no third process
# with any reason to look. The tie is broken by making the record say something
# liveness cannot: a holder that has entered its exit sweep marks itself
# RETIRING before it gives the mutex back. Retiring is not a weaker "live" — it
# is a stronger statement than either, made by the only process that can know it:
# "I am not relying on these grants any more, and I am not going to grant again."
# So a retiring record is never a reason to defer, and its paths are collected
# exactly like a dead holder's. Symmetric by construction: whichever of the two
# sweeps second sees the first's mark and finishes the job, and if both mark
# before either scans, both sweep and the second `/remove` is a no-op.
#
# The mark is in the file CONTENTS, not the name: `_holder_record_paths` already
# ignores any line that is not an absolute path, so an older abax reading a newer
# abax's record still reads exactly the paths and simply declines to collect them
# early — which is the safe direction. Keeping the name stable also keeps the
# identity rule above intact.
_HOLDER_DIR_NAME = "sandbox-acl-holders"
_HOLDER_SUFFIX = ".hold"

#: First line of a record whose writer has entered its exit sweep. Not an
#: absolute path, so :func:`_holder_record_paths` skips it like any other noise.
_HOLDER_RETIRING_MARK = "#retiring"

#: Ceiling on the paths read back out of another process's record. Bounded
#: because it is a file, and a file is a thing that can be wrong. How many is
#: only half of that; :func:`_sweepable_record_path` bounds *what* they are.
_HOLDER_MAX_PATHS = 64

_SELF_CREATE_TIME: "int | None" = None

#: ``(retiring, paths)`` as last written to this process's record, so the reuse
#: path can skip a rewrite it does not need. `None` means "nothing written yet".
#: The flag is part of the key rather than a separate global because dropping the
#: mark is exactly as important as setting it: a process that swept and then
#: granted again — which is not hypothetical, ``test_sandbox_windows``'s
#: module-scoped sweep does it mid-run — must stop advertising that it is on its
#: way out, and a cache keyed on the paths alone would happily skip that rewrite.
_HOLDER_RECORD_WRITTEN: "tuple[bool, tuple[str, ...]] | None" = None


def _holder_dir() -> str:
    """Where holder records live. Resolved per call, not captured at import.

    ``_runtime.DATA_DIR`` is redirected per test by ``conftest``'s
    ``abax_user_dirs``, and a module-level capture would write the developer's
    real profile from the test suite.
    """
    return os.path.join(str(_rt.DATA_DIR), _HOLDER_DIR_NAME)


def _self_create_time() -> "int | None":
    """This process's creation-time FILETIME, cached. None if it cannot be read.

    ``process_create_time`` is three-valued and this is two-valued on purpose:
    both of its non-answers mean the same thing *here*. A process that cannot
    read its own creation time has no identity to publish, and there is nothing
    to fail safe towards — the fail-safe belongs to the reader
    (:func:`_scan_holder_records`), which is the only place the difference
    between "gone" and "could not look" can do any work.
    """
    global _SELF_CREATE_TIME
    if _SELF_CREATE_TIME is None:
        try:
            from . import _winsandbox_ctypes as C

            answer = C.process_create_time(os.getpid())
        except Exception:                          # noqa: BLE001 - degrade
            return None
        if not isinstance(answer, int):
            return None                            # gone, or unreadable: no id
        _SELF_CREATE_TIME = answer
    return _SELF_CREATE_TIME


def _holder_record_path() -> "str | None":
    """This process's holder record path, or None if it cannot identify itself.

    Without an identity there is nothing another process could liveness-check, so
    publishing a record would be worse than not publishing one: it would be
    indistinguishable from a stale entry and would either block sweeps forever or
    be swept immediately.
    """
    created = _self_create_time()
    if created is None:
        return None
    return os.path.join(_holder_dir(),
                        f"{os.getpid()}-{created}{_HOLDER_SUFFIX}")


def _write_holder_record(paths: "tuple[str, ...]", *, retiring: bool) -> bool:
    """Write this process's record atomically. True when it landed.

    Never raises: a record that cannot be written costs cross-process protection,
    and refusing the launch over it would cost the launch.
    """
    global _HOLDER_RECORD_WRITTEN
    path = _holder_record_path()
    if path is None:
        _log.warning("sandbox: this process could not read its own creation time, "
                     "so it cannot publish a holder record — another abax exiting "
                     "may revoke the shared grants while this one is using them")
        return False
    body = "".join(p + "\n" for p in paths)
    if retiring:
        body = _HOLDER_RETIRING_MARK + "\n" + body
    tmp = path + ".new"
    try:
        os.makedirs(_holder_dir(), exist_ok=True)
        _rt.write_text_utf8(tmp, body)
        os.replace(tmp, path)                  # atomic; readers see one version
    except OSError as exc:
        _log.warning("sandbox: could not publish the holder record %s (%s)",
                     path, exc)
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        return False
    _HOLDER_RECORD_WRITTEN = (retiring, paths)
    return True


def _publish_holder_record() -> None:
    """Tell other processes this one is relying on the shared grants.

    Called from :func:`_hold_session_grant` under both the ACL mutex and
    ``_SESSION_GRANTS_LOCK``, so the record is on disk *before* the mutex is
    released — which is what makes it safe for `custom_spawn` to launch outside
    the mutex. Also called on the reuse fast path, cheaply, so a record another
    process wrongly collected is put back rather than missing for the rest of the
    session — and so a record left marked *retiring* by an earlier sweep is
    un-marked the moment this process holds a grant again.
    """
    path = _holder_record_path()
    paths = tuple(p for p, _ace in _SESSION_GRANTS.values())
    if (_HOLDER_RECORD_WRITTEN == (False, paths)
            and path is not None and os.path.exists(path)):
        return
    _write_holder_record(paths, retiring=False)


def _retire_holder_record(paths: "list[str]") -> None:
    """Publish that this process is no longer relying on the shared grants.

    The other half of a deferral: the sweep leaves the ACEs standing because
    somebody else is using them, and this is what stops that somebody — who may
    be exiting in the same instant — from deferring straight back (see the note
    above :data:`_HOLDER_RETIRING_MARK`). *paths* is written in full, so the
    record still carries everything the last holder out has to remove.

    Called with the ACL mutex still held, for the same reason
    :func:`_publish_holder_record` is: the next sweeper must not be able to scan
    between the decision and the announcement.
    """
    _write_holder_record(tuple(paths), retiring=True)


def _holder_record_identity(name: str) -> "tuple[int, int] | None":
    """``(pid, creation time)`` from a record's *file name*, or None if unreadable.

    An unparseable name is neither live nor stale: it is ignored entirely, and
    deliberately not deleted. Only this module writes here, so a name we cannot
    read is either a newer abax's format or something a human put there, and
    deleting either would be worse than leaving it.
    """
    if not name.endswith(_HOLDER_SUFFIX):
        return None
    pid, sep, created = name[:-len(_HOLDER_SUFFIX)].partition("-")
    if not sep or not pid.isdigit() or not created.isdigit():
        return None
    return int(pid), int(created)


def _sweepable_record_path(line: str) -> bool:
    """True when *line* is a path the exit sweep may hand to ``icacls /remove``.

    :data:`_HOLDER_MAX_PATHS` bounds how *many* paths another process's record is
    believed about; this bounds *what* they are, which was the missing half. The
    sweep runs ``icacls <path> /remove`` for every line that gets past here, on
    strings read out of a file this process did not write — so the filter is the
    only thing standing between a wrong file and a subprocess.

    The rule is lexical and does nothing but look at the string: an absolute path
    on a **local drive letter**. Measured on this platform (3.13), that admits
    ``C:\\x`` and ``c:/x`` and rejects, in order of how much they matter:

    * ``\\\\server\\share\\x`` — a UNC path. ``os.path.isabs`` says True, and
      ``icacls`` on one is a *network* operation: it connects to whatever host the
      file names, authenticating as this user, and blocks for the SMB timeout if
      nothing answers. With 64 such lines the exit sweep can sit there for
      minutes during interpreter shutdown, holding the machine-wide ACL mutex the
      whole time, so every other abax on the box waits out
      :data:`_ACL_MUTEX_GRANT_WAIT` before it can spawn. This is the one the
      filter is really for.
    * ``\\\\?\\C:\\x`` and ``\\\\.\\pipe\\x`` — the device namespace, likewise
      absolute by ``isabs`` and nothing this module would ever grant.
    * ``\\foo`` and ``C:x`` — rooted-but-driveless and drive-relative.
      ``ntpath.isabs`` already answers False for both on 3.13, so this is
      belt-and-braces rather than a change.

    **What it deliberately does NOT do is narrow the paths to ones this process
    would itself grant**, which is the tighter rule and the wrong one. The union
    that reads these records exists precisely to collect paths this process would
    *not* grant — two abax runs with different working directories put different
    entries on ``sys.path``, and the whole point of the handoff is that the last
    one out removes the other's (``test_the_last_sweep_removes_what_a_dead_holder
    _recorded_and_never_did`` pins it). Restricting to
    ``_needed_read_dirs()``/``_needed_read_files()`` would quietly turn every
    divergent path into a permanent machine-wide ACE, which is the leak this
    mechanism was built to close.

    And the tighter rule would buy less than it looks. What it would prevent is a
    forged record aiming ``icacls /remove`` at a path of the attacker's choosing
    — but ``/remove`` for one well-known SID grants nothing, cannot touch
    inherited ACEs, and only ever strips an ALL APPLICATION PACKAGES ACE that was
    explicitly set; and whoever can write into the holder directory can write
    ``init.py`` into the same directory (they are the same directory on Windows —
    see the note above) and simply run code inside abax instead. Constraining the
    *shape* removes a hang and a needless network connection, which are real and
    are not covered by anything else. Constraining the *set* would trade a
    working mechanism for no additional security.
    """
    if not os.path.isabs(line):
        return False
    drive = os.path.splitdrive(line)[0]
    return len(drive) == 2 and drive[1] == ":" and drive[0].isalpha()


def _holder_record_paths(record: str) -> "list[str]":
    """The paths a holder record claims, filtered to plausible ones.

    Anything :func:`_sweepable_record_path` rejects is skipped rather than
    treated as an error, which is what lets :data:`_HOLDER_RETIRING_MARK` share
    the file with the paths — and what lets an older abax read a newer one's
    record without knowing about the mark at all.

    This is the one place a string out of another process's file becomes
    something the sweep will act on, so it is the one place the filter belongs.
    """
    try:
        text = _rt.read_text_utf8(record, errors="replace")
    except OSError:
        return []
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line and _sweepable_record_path(line):
            out.append(line)
        if len(out) >= _HOLDER_MAX_PATHS:
            break
    return out


def _holder_record_retiring(record: str) -> bool:
    """True when *record*'s writer has published that it is on its way out.

    False for anything unreadable, truncated or unrecognised, which is the
    fail-safe direction: a record that cannot be read stays a reason to defer,
    and the ACEs stay up. Only the explicit mark converts a live holder into a
    collectable one.
    """
    try:
        text = _rt.read_text_utf8(record, errors="replace")
    except OSError:
        return False
    return any(line.strip() == _HOLDER_RETIRING_MARK
               for line in text.splitlines())


def _scan_holder_records() -> "tuple[list[str], list[str]]":
    """``(live, stale)`` records belonging to **other** processes.

    The question is not really "is that PID running" — it is **"is anyone still
    relying on these ACEs"**, and liveness is only a proxy for it. *Live* means
    the answer is yes and the sweep must defer. *Stale* means the answer is no:
    the record's paths are collected into the sweep and the record is deleted
    with them. Two different facts put a record in ``stale``:

    * the writer is **gone** — the OS says that PID is not the process that
      wrote this any more; or
    * the writer is **retiring** — it is still running, and has published that it
      has entered its own exit sweep and will not grant again
      (:data:`_HOLDER_RETIRING_MARK`). Without this, two abax processes exiting
      in the same instant each read the other as live, each deferred, and the
      ACEs stayed up forever with both records orphaned — measured, see the note
      above :data:`_HOLDER_RETIRING_MARK`.

    This process's own record is in neither list — it is the caller's to drop or
    to leave behind as a handoff.

    Every way of **not knowing** resolves to live, because the two errors are not
    symmetrical. Guessing "live" leaves an additive read ACE standing that some
    later abax will collect; guessing "stale" strips the standard library out
    from under a worker that is running right now. So an unreadable directory
    yields nothing to sweep, a record whose contents cannot be read is not
    retiring, and a liveness query that cannot run keeps the ACEs.

    That last clause is a promise this code once broke.
    :func:`~abax._winsandbox_ctypes.process_create_time` answered ``None`` both
    for "there is no such process" and for "``OpenProcess`` was denied" — and a
    denial means the PID belongs to an *elevated, another-user or protected*
    process, i.e. one that is running. ``None == created`` is False, so the
    record was filed stale and the sweep stripped the ACEs out from under a live
    holder: issue #9's mechanism through a new door. The query is now
    three-valued and only a definite *gone* counts as gone; the sentinel is
    checked first, before the equality, precisely because the sentinel compares
    equal to nothing.
    """
    live: list[str] = []
    stale: list[str] = []
    mine = _holder_record_path()
    mine_name = os.path.basename(mine) if mine else None
    try:
        names = os.listdir(_holder_dir())
    except OSError:
        return live, stale                # no directory, so nobody is recorded
    try:
        from . import _winsandbox_ctypes as C
    except Exception:                              # noqa: BLE001 - degrade
        C = None
    for name in names:
        if name == mine_name:
            continue
        identity = _holder_record_identity(name)
        if identity is None:
            continue
        pid, created = identity
        record = os.path.join(_holder_dir(), name)
        try:
            if C is None:
                alive = True
            else:
                answer = C.process_create_time(pid)
                alive = (answer is C.PROCESS_LIVENESS_UNKNOWN
                         or answer == created)
        except Exception:                          # noqa: BLE001 - degrade
            alive = True                # cannot tell: assume live, keep the ACEs
        if alive and _holder_record_retiring(record):
            alive = False               # running, but done with these grants
        (live if alive else stale).append(record)
    return live, stale


def _drop_holder_records(records: "list[str]") -> None:
    """Delete holder records. Never raises; a leftover is re-checked next time."""
    for record in records:
        with contextlib.suppress(OSError):
            os.unlink(record)


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

    "Every grant this process is holding" is the *upper* bound, not the job. Two
    things narrow it, and both are cross-process (see the note above
    :func:`_acl_mutex`):

    * The whole sweep runs under the machine-wide ACL mutex, so nobody probes or
      grants while this walk is half-done — closing W2 from the sweeping side.
    * Nothing is removed at all while another process is still *relying* on a
      record (W1). That process's worker would lose its standard library on its
      very next import, measured. This one is exiting; it leaves its own record
      behind carrying its paths and marked retiring, and the last holder out
      unions them in. The same union collects what a *crashed* abax recorded and
      never removed, so the leak the docstrings below call permanent is now
      cleared by the next clean exit.

    "Relying" rather than "live" is the whole of the tie-break: two processes
    exiting in the same instant are both live, both used to defer, and the ACEs
    then had no owner at all. See :data:`_HOLDER_RETIRING_MARK`.

    **Idempotent, including after a deferral.** The paths this sweep is
    answerable for are the union of the in-memory table and this process's own
    record on disk, so a sweep that deferred — emptying the table but keeping the
    record — can be run again and still finish the job. Every removal is an
    ``icacls /remove`` for a principal, which succeeds whether or not the ACE is
    there, so a third and fourth call cost a walk and change nothing.

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
        with _acl_mutex(_ACL_MUTEX_SWEEP_WAIT, "the exit sweep"):
            got = _SESSION_GRANTS_LOCK.acquire(timeout=_SESSION_SWEEP_LOCK_WAIT)
            try:
                held = list(_SESSION_GRANTS.values())
                _SESSION_GRANTS.clear()
            finally:
                if got:
                    _SESSION_GRANTS_LOCK.release()
            # Everything this process is answerable for. The in-memory table is
            # only half of it: a sweep that DEFERRED already emptied that table
            # and left the paths on disk in our own record, so a second sweep
            # reading the table alone finds nothing to remove — and then deletes
            # the record anyway at the bottom of this function, taking the last
            # thing that knew about those ACEs with it. Measured, before this
            # line existed, with one deferral followed by the other holder dying:
            #
            #     sweep #1 (other live)  : []      ACE True   my record kept
            #     sweep #2 (other dead)  : []      ACE True   my record gone
            #
            # The record is the durable half of the handoff and it is read back
            # here for exactly that reason. Union rather than replace: the table
            # is authoritative for this session, the record for the last one.
            mine = _holder_record_path()
            ours: "list[str]" = [path for path, _ace in held]
            keys = {_shared_key(p) for p in ours}
            if mine:
                for path in _holder_record_paths(mine):
                    if _shared_key(path) not in keys:
                        keys.add(_shared_key(path))
                        ours.append(path)
            live, stale = _scan_holder_records()
            if live:
                # W1: another abax is running on these ACEs right now. Leave them
                # standing and leave OUR record behind carrying our paths, marked
                # retiring — this process will not grant again, so the mark is
                # true, and it is what stops a holder that is exiting in the same
                # instant from deferring straight back to us and leaving the ACEs
                # with nobody to collect them (see `_HOLDER_RETIRING_MARK`). The
                # mark goes down before the mutex is released, so the next
                # sweeper cannot scan between our decision and our announcement.
                # Nothing is leaked and nothing is reported: the grants have an
                # owner and a scheduled removal, which is the same distinction
                # `_revoke_container_access` draws for a path held mid-session.
                if ours or (mine and os.path.exists(mine)):
                    _retire_holder_record(ours)
                _log.info("sandbox: %d other process(es) are still holding the "
                          "shared grants; leaving them for the last one out",
                          len(live))
                return []
            # Nobody else is relying on them. Take off what this process granted
            # or recorded, plus what any holder that is gone — or retiring —
            # recorded and never got to remove: a crashed run, or a run that
            # deferred on the branch above.
            removing: "list[str]" = list(ours)
            for record in stale:
                for path in _holder_record_paths(record):
                    if _shared_key(path) not in keys:
                        keys.add(_shared_key(path))
                        removing.append(path)
            failed = []
            for path in removing:
                if _icacls(path, "/remove", ALL_APP_PACKAGES):
                    continue
                if not os.path.exists(path):
                    continue               # its ACL went with it; nothing leaked
                failed.append(path)
            # Our own record last, and only once the walk is done: killed
            # partway, the record survives and the next abax finishes the job.
            _drop_holder_records(stale + ([mine] if mine else []))
            if failed:
                _log.warning(
                    "sandbox: %d shared ALL APPLICATION PACKAGES grant(s) could "
                    "not be revoked at exit and are still standing on: %s",
                    len(failed), ", ".join(failed))
            return failed
    except BaseException:                  # noqa: BLE001 - see the docstring
        return []


def _hold_session_grant(path: str, ace: str, granted: "list[str]",
                        *, trust_probe: bool = True) -> bool:
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

    ``trust_probe=False`` says the caller could not take the machine-wide ACL
    mutex, so no answer `_container_ace_present` gives can be believed — another
    process may be halfway through a walk, and the root's DACL is written first
    (W2, see the note above :func:`_acl_mutex`). The reuse fast path is then
    skipped and the grant is re-issued: a redundant ~20 s DACL walk, which is the
    right price for not launching a child into a tree it cannot read.
    """
    key = _shared_key(path)
    with _SESSION_GRANTS_LOCK:
        if trust_probe and key in _SESSION_GRANTS and _container_ace_present(path):
            _publish_holder_record()       # cheap; restores a record swept as stale
            granted.append(path)           # already in force; no walk, no window
            return True
        if not _icacls(path, "/grant", ace):
            return False
        _SESSION_GRANTS[key] = (path, ace)
        _register_session_sweep()
        # Before the mutex is released, so no other process's sweep can decide we
        # are not here while this spawn is still on its way to CreateProcessW.
        _publish_holder_record()
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

    **The whole body runs under the machine-wide ACL mutex**, and that boundary is
    the fix for W2 (see the note above :func:`_acl_mutex`). It has to cover every
    probe as well as every walk: the reuse fast path, the grant itself, and
    `_unreachable_requirements`' pre-existing-ACE check all ask `/findsid` about a
    tree another process may be halfway through rewriting, and icacls writes the
    root first — so mid-walk the probe answers True about a tree the child cannot
    read. Serialising only the writes would leave exactly the observation that
    killed the child in the measurement.
    """
    if granted is None:
        granted = []
    with _acl_mutex(_ACL_MUTEX_GRANT_WAIT, "granting the shared read paths") as m:
        # The scratch dir: full modify (the worker writes here). Deliberately
        # *not* session-held — it is this worker's own `mkdtemp`, it carries
        # write access, and it is granted and revoked unconditionally with the
        # worker. Inside the mutex only because it is on the way past; it is a
        # fresh empty directory, measured at ~0.01 s, and shared with nobody.
        if _icacls(scratch, "/grant", f"{ALL_APP_PACKAGES}:(OI)(CI)(M)"):
            granted.append(scratch)
        else:
            _log.warning("sandbox: could not grant the confined worker write "
                         "access to its scratch dir %s", scratch)
        # Read + execute on the interpreter and import dirs, inheritable so one
        # ACE covers the whole tree. Shared with every other confinement in this
        # process, hence held for the session rather than granted per worker.
        for d in _needed_read_dirs():
            if not _hold_session_grant(d, f"{ALL_APP_PACKAGES}:(OI)(CI)(RX)",
                                       granted, trust_probe=m):
                _log.warning("sandbox: could not grant the confined worker read "
                             "access to %s", d)
        # ...and on the file-shaped import roots (a zipapp archive), which take a
        # plain (RX): the inheritance flags above are silently discarded on a
        # leaf, see `_needed_read_files`. Anything already under a granted
        # directory is skipped — the inheritable ACE reaches it, and a redundant
        # explicit ACE is one more thing the exit sweep has to remove. Shared for
        # the same reason the directories are: two bridges import the package
        # from one archive.
        for f in _needed_read_files():
            if _covered_by(f, granted):
                continue
            if not _hold_session_grant(f, f"{ALL_APP_PACKAGES}:(RX)", granted,
                                       trust_probe=m):
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
