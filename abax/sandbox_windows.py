"""Windows OS-confinement for the code-execution worker (sandbox Phase 3).

Implements the :class:`abax.sandbox.Confinement` contract on Windows using an
**AppContainer**: the worker process runs inside an isolated security context
with *no capabilities*, which by default denies **network** access and denies
**filesystem** access to everything except locations explicitly granted to the
container. We grant the container:

* **read + execute** on the interpreter prefix and the ``sys.path`` entries the
  worker must import from (otherwise Python can't even start), and
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
they never weaken anyone's access) and are **reverted** on teardown. Even so,
Phase 3's fail-closed :func:`abax.sandbox.selftest` runs inside the worker after
launch: if for any reason the container did not actually confine, the worker
refuses to execute user code. Nothing here can silently ship a fake sandbox.

Pure stdlib (ctypes, _winapi, msvcrt, os, sys, subprocess for icacls). No deps.
Imports cleanly on any OS — all Windows-only work is inside method bodies.
"""

from __future__ import annotations

import os
import subprocess
import sys

from ._runtime import console_encoding

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
        """Launch ``argv`` inside an AppContainer, returning a Popen-like handle."""
        from . import _winsandbox_ctypes as C  # lazy: Windows-only ctypes defs

        profile_name = _profile_name()
        sid = C.create_app_container_profile(profile_name)
        granted = _grant_container_access(scratch)
        try:
            proc = C.create_process_appcontainer(
                argv, env, sid,
                creationflags | _EXTENDED_STARTUPINFO_PRESENT
                | _CREATE_UNICODE_ENVIRONMENT)
        except OSError:
            _revoke_container_access(granted)
            C.delete_app_container_profile(profile_name)
            raise
        # Remember what to clean up when the process is closed.
        proc._sandbox_cleanup = (granted, profile_name)  # noqa: SLF001
        proc._sandbox_ctypes = C  # noqa: SLF001
        return proc


def _profile_name() -> str:
    # A per-process container name (no Date/random available in this codebase's
    # constraints — the PID is unique enough for a live profile, and we delete
    # it on teardown).
    return f"abax-sandbox-{os.getpid()}"


def _needed_read_dirs() -> "list[str]":
    """Directories the confined interpreter must be able to read+execute: the
    base prefix (interpreter + stdlib) and the importable ``sys.path`` entries."""
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


def _grant_container_access(scratch: str) -> "list[str]":
    """Grant ALL APPLICATION PACKAGES the access the worker needs. Returns the
    list of paths granted, for later revocation."""
    granted = []
    # The scratch dir: full modify (the worker writes here).
    if _icacls(scratch, "/grant", f"{ALL_APP_PACKAGES}:(OI)(CI)(M)"):
        granted.append(scratch)
    # Read + execute on the interpreter and import dirs.
    for d in _needed_read_dirs():
        if _icacls(d, "/grant", f"{ALL_APP_PACKAGES}:(OI)(CI)(RX)"):
            granted.append(d)
    return granted


def _revoke_container_access(granted: "list[str]") -> None:
    for path in granted:
        _icacls(path, "/remove", ALL_APP_PACKAGES)


def cleanup_process(proc) -> None:
    """Revert the ACL grants and delete the container profile for a finished
    process. Called by the bridge when it closes a confined worker."""
    info = getattr(proc, "_sandbox_cleanup", None)
    C = getattr(proc, "_sandbox_ctypes", None)
    if info is None:
        return
    granted, profile_name = info
    _revoke_container_access(granted)
    if C is not None:
        try:
            C.delete_app_container_profile(profile_name)
        except OSError:
            pass
    proc._sandbox_cleanup = None  # noqa: SLF001
