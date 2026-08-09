"""Windows ctypes plumbing for AppContainer process launch (sandbox Phase 3).

Split out from :mod:`abax.sandbox_windows` to keep the intricate ``ctypes`` /
``_winapi`` code isolated. Imported lazily (only on Windows, only when a strict
worker is spawned), so nothing here loads on other platforms.

The one public entry point is :func:`create_process_appcontainer`, which calls
``CreateProcessW`` with an ``EXTENDED_STARTUPINFO`` carrying a
security-capabilities attribute (the AppContainer SID, no capabilities), wires
up three inheritable pipes with the stdlib ``_winapi`` primitives, and returns
an :class:`_ACProcess` exposing just enough of the ``subprocess.Popen`` surface
(``stdin`` / ``stdout`` / ``stderr`` / ``poll`` / ``wait`` / ``kill`` /
``terminate`` / ``_handle``) for :class:`abax.gui.console.console_bridge.ConsoleBridge`
to drive it like an ordinary worker.
"""

from __future__ import annotations

import ctypes
import msvcrt
import os
import subprocess
from ctypes import wintypes

_EXTENDED_STARTUPINFO_PRESENT = 0x00080000
_PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009
_STARTF_USESTDHANDLES = 0x00000100
_HRESULT_ALREADY_EXISTS = 0x800700B7
_STILL_ACTIVE = 259


def _dlls():
    """The three Win32 DLLs we need (cached on the function object)."""
    cache = _dlls.__dict__.get("_c")
    if cache is None:
        cache = (ctypes.WinDLL("kernel32", use_last_error=True),
                 ctypes.WinDLL("userenv", use_last_error=True),
                 ctypes.WinDLL("advapi32", use_last_error=True))
        _dlls.__dict__["_c"] = cache
    return cache


# --- structures --------------------------------------------------------------


class SECURITY_CAPABILITIES(ctypes.Structure):
    _fields_ = [("AppContainerSid", ctypes.c_void_p),
                ("Capabilities", ctypes.c_void_p),
                ("CapabilityCount", wintypes.DWORD),
                ("Reserved", wintypes.DWORD)]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.c_void_p),
                ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE),
                ("hStdError", wintypes.HANDLE)]


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]


# --- AppContainer profile ----------------------------------------------------


def create_app_container_profile(name: str) -> ctypes.c_void_p:
    """Create (or, if it already exists, derive) the AppContainer profile SID."""
    _k32, userenv, _adv = _dlls()
    fn = userenv.CreateAppContainerProfile
    fn.restype = ctypes.c_long
    fn.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                   ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    sid = ctypes.c_void_p()
    hr = fn(name, name, name, None, 0, ctypes.byref(sid))
    if (hr & 0xFFFFFFFF) == _HRESULT_ALREADY_EXISTS:
        d = userenv.DeriveAppContainerSidFromAppContainerName
        d.restype = ctypes.c_long
        d.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
        hr = d(name, ctypes.byref(sid))
    if hr != 0:
        raise OSError(f"AppContainer profile failed: hr=0x{hr & 0xFFFFFFFF:08x}")
    return sid


def delete_app_container_profile(name: str) -> None:
    """Delete the AppContainer profile *name*. Raises ``OSError`` on failure.

    The HRESULT is checked and reported in the same shape
    :func:`create_app_container_profile` reports its own. It used to be
    discarded, which made a failed delete completely invisible — no exception,
    no log, no return value — and made the ``except OSError`` guards in
    :func:`abax.sandbox_windows.cleanup_process` and
    :meth:`~abax.sandbox_windows.WindowsAppContainer.custom_spawn` dead code:
    nothing they wrapped could raise.

    Measured on this platform, with a handle held open under
    ``%LOCALAPPDATA%\\Packages\\<name>``: ``hr=0x80070020``
    (``ERROR_SHARING_VIOLATION``), and *both* halves of the profile survive the
    call — the ``HKCU\\...\\AppContainer\\Mappings`` registry entry and the
    ``Packages`` tree. That is a real leak that used to report success.

    Deleting a name that is not there is **not** a failure, so the guard cannot
    fire on a redundant teardown: measured ``hr=0x00000000`` both for a profile
    already deleted and for one never created.
    """
    _k32, userenv, _adv = _dlls()
    fn = userenv.DeleteAppContainerProfile
    fn.restype = ctypes.c_long
    fn.argtypes = [wintypes.LPCWSTR]
    hr = fn(name)
    if hr != 0:
        raise OSError(
            f"AppContainer profile delete failed: hr=0x{hr & 0xFFFFFFFF:08x}")


# --- confined process launch -------------------------------------------------


def _env_block(env: "dict[str, str]") -> ctypes.Array:
    parts = [f"{k}={v}" for k, v in env.items()]
    return ctypes.create_unicode_buffer("\0".join(parts) + "\0\0")


def _make_inheritable(handle: int) -> int:
    """A duplicate of *handle* that child processes inherit (the original stays
    non-inheritable and should be closed by the caller)."""
    import _winapi

    cur = _winapi.GetCurrentProcess()
    return _winapi.DuplicateHandle(cur, handle, cur, 0, True,
                                   _winapi.DUPLICATE_SAME_ACCESS)


def create_process_appcontainer(argv, env, sid, creationflags):
    """Launch ``argv`` inside the AppContainer identified by ``sid``.

    Returns an :class:`_ACProcess`. Raises ``OSError`` on failure (the caller
    reverts its ACL grants and deletes the profile so we fail closed).
    """
    import _winapi

    k32, _userenv, _adv = _dlls()

    # Three anonymous pipes; the child inherits one end of each, the parent
    # keeps the other (non-inheritable) end wrapped as a Python file object.
    stdin_r, stdin_w = _winapi.CreatePipe(None, 0)     # parent writes stdin_w
    stdout_r, stdout_w = _winapi.CreatePipe(None, 0)   # parent reads stdout_r
    stderr_r, stderr_w = _winapi.CreatePipe(None, 0)   # parent reads stderr_r

    child_stdin = _make_inheritable(stdin_r)
    child_stdout = _make_inheritable(stdout_w)
    child_stderr = _make_inheritable(stderr_w)
    _winapi.CloseHandle(stdin_r)
    _winapi.CloseHandle(stdout_w)
    _winapi.CloseHandle(stderr_w)

    # The proc-thread attribute list carrying the AppContainer security caps.
    caps = SECURITY_CAPABILITIES()
    caps.AppContainerSid = sid
    caps.Capabilities = None
    caps.CapabilityCount = 0        # no capabilities -> no network, minimal FS
    caps.Reserved = 0

    size = ctypes.c_size_t(0)
    k32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
    attr_buf = (ctypes.c_char * size.value)()
    attr_list = ctypes.cast(attr_buf, ctypes.c_void_p)
    if not k32.InitializeProcThreadAttributeList(attr_list, 1, 0, ctypes.byref(size)):
        raise OSError(f"InitializeProcThreadAttributeList: {ctypes.get_last_error()}")
    if not k32.UpdateProcThreadAttribute(
            attr_list, 0, _PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
            ctypes.byref(caps), ctypes.sizeof(caps), None, None):
        err = ctypes.get_last_error()
        k32.DeleteProcThreadAttributeList(attr_list)
        raise OSError(f"UpdateProcThreadAttribute: {err}")

    si = STARTUPINFOEXW()
    si.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
    si.StartupInfo.dwFlags = _STARTF_USESTDHANDLES
    si.StartupInfo.hStdInput = child_stdin
    si.StartupInfo.hStdOutput = child_stdout
    si.StartupInfo.hStdError = child_stderr
    si.lpAttributeList = attr_list

    pi = PROCESS_INFORMATION()
    cmdline = subprocess.list2cmdline(argv)
    CreateProcessW = k32.CreateProcessW
    CreateProcessW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p, ctypes.c_void_p,
        wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
        ctypes.c_void_p, ctypes.c_void_p]
    ok = CreateProcessW(
        argv[0], ctypes.create_unicode_buffer(cmdline), None, None, True,
        creationflags, ctypes.cast(_env_block(env), ctypes.c_void_p), None,
        ctypes.byref(si), ctypes.byref(pi))
    err = ctypes.get_last_error()
    k32.DeleteProcThreadAttributeList(attr_list)
    # The child now owns its inherited ends; close our copies either way.
    for h in (child_stdin, child_stdout, child_stderr):
        _winapi.CloseHandle(h)
    if not ok:
        for h in (stdin_w, stdout_r, stderr_r):
            _winapi.CloseHandle(h)
        raise OSError(f"CreateProcessW failed: {err}")

    _winapi.CloseHandle(pi.hThread)
    stdin = os.fdopen(msvcrt.open_osfhandle(stdin_w, 0), "wb", buffering=0)
    stdout = os.fdopen(msvcrt.open_osfhandle(stdout_r, 0), "rb", buffering=0)
    stderr = os.fdopen(msvcrt.open_osfhandle(stderr_r, 0), "rb", buffering=0)
    return _ACProcess(int(pi.hProcess), pi.dwProcessId, stdin, stdout, stderr)


class _ACProcess:
    """A minimal ``subprocess.Popen`` look-alike over a raw process handle."""

    def __init__(self, handle: int, pid: int, stdin, stdout, stderr) -> None:
        self._handle = handle          # int process HANDLE (proclimits uses this)
        self.pid = pid
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = None

    def poll(self):
        import _winapi

        if self.returncode is not None:
            return self.returncode
        res = _winapi.WaitForSingleObject(self._handle, 0)
        if res == _winapi.WAIT_OBJECT_0:
            self.returncode = _winapi.GetExitCodeProcess(self._handle)
        return self.returncode

    def wait(self, timeout=None):
        import _winapi

        if self.returncode is not None:
            return self.returncode
        ms = _winapi.INFINITE if timeout is None else int(timeout * 1000)
        res = _winapi.WaitForSingleObject(self._handle, ms)
        if res == _winapi.WAIT_OBJECT_0:
            self.returncode = _winapi.GetExitCodeProcess(self._handle)
            return self.returncode
        raise subprocess.TimeoutExpired("appcontainer-worker", timeout)

    def kill(self):
        k32, _u, _a = _dlls()
        if self.returncode is None:
            k32.TerminateProcess(wintypes.HANDLE(self._handle), 1)

    terminate = kill

    def close_handle(self):
        import _winapi

        try:
            _winapi.CloseHandle(self._handle)
        except OSError:
            pass
