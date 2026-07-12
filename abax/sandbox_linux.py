"""Linux OS-confinement strategies for the code-execution worker (sandbox Phase 3).

This module supplies the Linux implementation of the :class:`abax.sandbox.Confinement`
contract. It is imported lazily by :func:`abax.sandbox.select_confinement`, but is
written to **import cleanly on any OS** — all Linux-only ctypes / syscall work is
done inside method bodies, never at import time, so test collection on Windows or
macOS (`import abax.sandbox_linux`) does not blow up.

Preference order returned by :func:`confinement`:

1. **bubblewrap** (``bwrap``) — a *wrapper* strategy. If the ``bwrap`` binary is on
   PATH and ``bwrap --version`` runs, we prefer it. bwrap is unprivileged (uses user
   namespaces), well audited (it's the engine under Flatpak), and gives us a complete
   mount/network namespace jail with a single argv rewrite. This is the strong path.

2. **Landlock (filesystem)** — an *in-child* strategy. If the running kernel supports
   Landlock (feature-detected by probing the ``landlock_create_ruleset`` syscall),
   we can make the whole filesystem read-only except the scratch dir, applied from
   inside the worker via ctypes. Landlock is unprivileged and stackable (Linux 5.13+).

   **Network denial caveat (why the Landlock path is gated OFF by default):** the
   fail-closed :func:`abax.sandbox.selftest` also requires that *outbound sockets be
   denied*. Landlock's network support (LANDLOCK_ACCESS_NET_CONNECT_TCP) only landed
   in ABI v4 (Linux 6.7) and only covers TCP connect by port, not raw socket()/UDP.
   The general tool for blocking ``socket``/``connect`` is a seccomp-BPF filter, which
   must be assembled as raw BPF bytecode by hand. A subtly wrong seccomp filter is a
   classic way to ship a confinement that *looks* applied but either (a) kills the
   worker on an unrelated syscall or (b) silently fails open. Per the design rule
   "a broken confinement that claims to work is the worst outcome", we do **not**
   ship a hand-rolled seccomp BPF filter blind. The Landlock-only strategy therefore
   reports ``available() == False`` (it cannot satisfy the network half of the
   selftest on its own), so on a box without bwrap we fail closed rather than pretend.
   The Landlock filesystem logic is still fully implemented and unit-shaped so it can
   be promoted the moment a verified seccomp filter is added; :meth:`_LandlockConfine.
   apply_fs_only` can be called directly by future tests on a Linux kernel.

3. If neither is usable, :func:`confinement` returns ``None`` and the caller falls back
   to its own null sentinel (which refuses to run user code under strict mode).

Everything here is pure stdlib (ctypes, os, shutil, subprocess). No new dependencies.

Syscall numbers and constants are cited inline at each use site.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys

# ---------------------------------------------------------------------------
# bubblewrap (wrapper strategy)
# ---------------------------------------------------------------------------


def _bwrap_path() -> "str | None":
    """Return the path to a usable ``bwrap`` binary, or None.

    Feature detection is *real*: we require the binary on PATH and that
    ``bwrap --version`` exits 0. A binary that exists but can't run (e.g. user
    namespaces disabled by sysctl, so bwrap errors immediately) must not be
    reported as usable — the whole point of Phase 3 is to never claim a
    confinement we can't actually apply.
    """
    path = shutil.which("bwrap")
    if not path:
        return None
    try:
        proc = subprocess.run(
            [path, "--version"],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return path


def build_bwrap_argv(bwrap: str, argv: "list[str]", scratch: str) -> "list[str]":
    """Construct the bubblewrap command that wraps ``argv``.

    This is a standalone helper (not a method) so it can be unit-tested without
    bwrap installed — it just assembles a list of strings.

    The jail we build:

    * ``--ro-bind / /`` — bind the entire host root read-only into the sandbox.
      This is what lets the worker still read the Python interpreter, the stdlib,
      and site-packages (so ``import abax`` works) while being unable to modify
      anything on the real filesystem. Read-only is the default posture; only the
      scratch dir below is writable.
    * ``--dev /dev`` and ``--proc /proc`` — fresh minimal ``devtmpfs`` / ``proc``
      instead of the host's, so the worker can't reach host device nodes or peek
      at other processes.
    * ``--tmpfs /tmp`` — a private, in-memory ``/tmp`` unconnected to the host, so
      temp writes go nowhere real. TMPDIR is redirected into scratch by child_env.
    * ``--bind <scratch> <scratch>`` — the ONE writable path: the scratch dir is
      bound read-write at the same path inside the jail, matching what the worker
      and the selftest expect.
    * ``--unshare-net`` — new, empty network namespace with no interfaces (not even
      loopback is configured), so outbound sockets have nowhere to go: this is what
      satisfies the network half of the fail-closed selftest.
    * ``--unshare-pid`` — new PID namespace: the worker can't see or signal host
      processes.
    * ``--die-with-parent`` — if the worker's parent dies, the sandbox is torn down
      (no orphaned confined process lingering).

    We deliberately do NOT ``--unshare-user`` explicitly; bwrap already creates the
    user namespace it needs to operate unprivileged, and forcing extra unsharing can
    fail on hardened kernels. We keep the wrapper minimal and robust.

    ``argv`` (the original spawn command — Python executable + args) is appended
    verbatim as the command bwrap execs inside the jail, so the interpreter and its
    arguments are preserved. PYTHONPATH and other env are carried by child_env /
    the inherited environment; ``--ro-bind / /`` keeps the interpreter on disk
    reachable at its real path.
    """
    scratch = os.path.abspath(scratch)
    cmd = [
        bwrap,
        # Whole host filesystem, read-only. Covers the Python install + site-packages.
        "--ro-bind", "/", "/",
        # Minimal fresh /dev and /proc rather than the host's.
        "--dev", "/dev",
        "--proc", "/proc",
        # Private in-memory /tmp with nothing from the host.
        "--tmpfs", "/tmp",
        # The single writable location: the scratch dir, at its real path.
        "--bind", scratch, scratch,
        # No network namespace with usable interfaces -> outbound sockets blocked.
        "--unshare-net",
        # Isolate the PID namespace.
        "--unshare-pid",
        # Tear the sandbox down if the launching worker parent dies.
        "--die-with-parent",
        # Everything after this is the command run *inside* the jail.
        "--",
    ]
    cmd.extend(argv)
    return cmd


class _BwrapConfine:
    """bubblewrap wrapper strategy. Pure-wrapper: no in-child syscall work."""

    name = "bwrap"

    def __init__(self, bwrap_path: str) -> None:
        self._bwrap = bwrap_path

    def available(self) -> bool:
        # Re-verify at call time rather than trusting construction: the binary
        # could have been removed, or namespaces disabled, since we probed.
        return _bwrap_path() is not None

    def wrap_argv(self, argv: "list[str]", scratch: str) -> "list[str]":
        return build_bwrap_argv(self._bwrap, argv, scratch)

    def child_env(self, env: "dict[str, str]", scratch: str) -> "dict[str, str]":
        # Point TMPDIR at the (writable) scratch dir so anything that writes to a
        # temp file lands in the one place the jail permits writes, not the private
        # tmpfs that vanishes or the host /tmp that's now read-only.
        env = dict(env)
        env["TMPDIR"] = os.path.abspath(scratch)
        return env

    def apply_in_child(self, scratch: str) -> None:
        # Pure-wrapper strategy: all confinement is done by bwrap in the parent's
        # spawn. Nothing to do (and nothing to fail) in the child.
        return None

    def describe(self) -> str:
        return f"bubblewrap namespace jail ({self._bwrap}): read-only root, no network"


# ---------------------------------------------------------------------------
# Landlock (in-child filesystem strategy)  -- see the module docstring for why
# this is currently gated to available() == False (network half unmet).
# ---------------------------------------------------------------------------

# Landlock syscall numbers. Landlock has three syscalls; we only need the first
# to feature-detect, and all three to apply a ruleset.
#   __NR_landlock_create_ruleset = 444
#   __NR_landlock_add_rule       = 445
#   __NR_landlock_restrict_self  = 446
# These numbers are identical across x86-64 and aarch64 (the generic syscall
# table assigned them together in Linux 5.13). Ref: linux/arch/*/syscall*.tbl
# and include/uapi/asm-generic/unistd.h.
_NR_landlock_create_ruleset = 444
_NR_landlock_add_rule = 445
_NR_landlock_restrict_self = 446

# Flag for landlock_create_ruleset() that asks the kernel for the supported ABI
# version instead of creating a ruleset. Ref: linux/landlock.h
#   LANDLOCK_CREATE_RULESET_VERSION = (1U << 0)
_LANDLOCK_CREATE_RULESET_VERSION = 1 << 0

# Landlock filesystem access-right bits (ABI v1 subset we use). Ref: uapi
# linux/landlock.h `enum landlock_rule_type` / LANDLOCK_ACCESS_FS_*.
_LANDLOCK_ACCESS_FS_EXECUTE = 1 << 0
_LANDLOCK_ACCESS_FS_WRITE_FILE = 1 << 1
_LANDLOCK_ACCESS_FS_READ_FILE = 1 << 2
_LANDLOCK_ACCESS_FS_READ_DIR = 1 << 3
_LANDLOCK_ACCESS_FS_REMOVE_DIR = 1 << 4
_LANDLOCK_ACCESS_FS_REMOVE_FILE = 1 << 5
_LANDLOCK_ACCESS_FS_MAKE_CHAR = 1 << 6
_LANDLOCK_ACCESS_FS_MAKE_DIR = 1 << 7
_LANDLOCK_ACCESS_FS_MAKE_REG = 1 << 8
_LANDLOCK_ACCESS_FS_MAKE_SOCK = 1 << 9
_LANDLOCK_ACCESS_FS_MAKE_FIFO = 1 << 10
_LANDLOCK_ACCESS_FS_MAKE_BLOCK = 1 << 11
_LANDLOCK_ACCESS_FS_MAKE_SYM = 1 << 12

# The full set of ABI-v1 filesystem rights. A ruleset is created listing every
# right it *handles*; any handled right not granted to a bound path is denied.
_LANDLOCK_ACCESS_FS_ALL_V1 = (
    _LANDLOCK_ACCESS_FS_EXECUTE
    | _LANDLOCK_ACCESS_FS_WRITE_FILE
    | _LANDLOCK_ACCESS_FS_READ_FILE
    | _LANDLOCK_ACCESS_FS_READ_DIR
    | _LANDLOCK_ACCESS_FS_REMOVE_DIR
    | _LANDLOCK_ACCESS_FS_REMOVE_FILE
    | _LANDLOCK_ACCESS_FS_MAKE_CHAR
    | _LANDLOCK_ACCESS_FS_MAKE_DIR
    | _LANDLOCK_ACCESS_FS_MAKE_REG
    | _LANDLOCK_ACCESS_FS_MAKE_SOCK
    | _LANDLOCK_ACCESS_FS_MAKE_FIFO
    | _LANDLOCK_ACCESS_FS_MAKE_BLOCK
    | _LANDLOCK_ACCESS_FS_MAKE_SYM
)

# Read-ish rights we grant to the whole filesystem (so the interpreter, stdlib,
# and site-packages remain importable), while withholding every write/create bit.
_LANDLOCK_ACCESS_FS_READ_ONLY = (
    _LANDLOCK_ACCESS_FS_EXECUTE
    | _LANDLOCK_ACCESS_FS_READ_FILE
    | _LANDLOCK_ACCESS_FS_READ_DIR
)

# prctl option to forbid gaining new privileges; a precondition for an unprivileged
# process to restrict itself with Landlock. Ref: linux/prctl.h PR_SET_NO_NEW_PRIVS=38.
_PR_SET_NO_NEW_PRIVS = 38


class _landlock_ruleset_attr(ctypes.Structure):
    """struct landlock_ruleset_attr { __u64 handled_access_fs; ... }.

    ABI v1 has a single field; later ABIs append fields, but a v1-sized struct is
    accepted by all kernels for the rights we declare. Ref: uapi linux/landlock.h.
    """

    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class _landlock_path_beneath_attr(ctypes.Structure):
    """struct landlock_path_beneath_attr { __u64 allowed_access; __s32 parent_fd; }.

    Note the kernel struct is ``__attribute__((packed))``; we mirror that so the
    8-byte access field is immediately followed by the 4-byte fd with no padding.
    Ref: uapi linux/landlock.h.
    """

    _pack_ = 1
    # Python 3.14 deprecates setting `_pack_` without an explicit `_layout_`
    # (slated to become an error). `_pack_` already implies the MSVC-compatible
    # layout, so state it — same memory layout, no more warning.
    _layout_ = "ms"
    _fields_ = [
        ("allowed_access", ctypes.c_uint64),
        ("parent_fd", ctypes.c_int32),
    ]


def _libc() -> "ctypes.CDLL":
    """Load libc for raw ``syscall()`` access. Linux-only; only called on Linux."""
    # use_errno so we can read errno after a failed syscall.
    return ctypes.CDLL("libc.so.6", use_errno=True)


def landlock_abi_version() -> int:
    """Return the kernel's Landlock ABI version, 0 if unsupported, -1 on error.

    Real feature detection: we invoke ``landlock_create_ruleset(NULL, 0,
    LANDLOCK_CREATE_RULESET_VERSION)``. On a kernel with Landlock this returns the
    ABI version (>=1). On a kernel without it, the syscall itself is absent and
    returns -ENOSYS. This is the canonical probe from the Landlock man page.
    """
    if not sys.platform.startswith("linux"):
        return 0
    try:
        libc = _libc()
    except OSError:
        return -1
    ctypes.set_errno(0)
    ret = libc.syscall(
        ctypes.c_long(_NR_landlock_create_ruleset),
        ctypes.c_void_p(None),
        ctypes.c_size_t(0),
        ctypes.c_uint32(_LANDLOCK_CREATE_RULESET_VERSION),
    )
    if ret < 0:
        # -ENOSYS (no such syscall) or -EOPNOTSUPP (Landlock disabled) -> unsupported.
        return 0
    return int(ret)


class _LandlockConfine:
    """Landlock in-child filesystem confinement.

    See the module docstring: this strategy's :meth:`available` is intentionally
    ``False`` because Landlock alone cannot deny outbound sockets (the network half
    of the fail-closed selftest) without a hand-rolled seccomp filter we decline to
    ship blind. The filesystem restriction below is complete and correct, exposed as
    :meth:`apply_fs_only` for future promotion / on-kernel testing.
    """

    name = "landlock"

    def __init__(self, abi: int) -> None:
        self._abi = abi

    def available(self) -> bool:
        # Deliberately unavailable: cannot satisfy the network denial the selftest
        # requires on its own. Fail closed rather than ship a half-sandbox.
        return False

    def wrap_argv(self, argv: "list[str]", scratch: str) -> "list[str]":
        return argv  # in-child strategy: parent does not rewrite argv

    def child_env(self, env: "dict[str, str]", scratch: str) -> "dict[str, str]":
        env = dict(env)
        env["TMPDIR"] = os.path.abspath(scratch)
        return env

    def apply_in_child(self, scratch: str) -> None:
        # If this strategy were ever selected, applying only the filesystem half
        # would leave the network open and the selftest would (correctly) reject
        # it. To keep the fail-closed contract explicit, we refuse rather than
        # apply a partial confinement.
        raise RuntimeError(
            "landlock strategy provides no network denial; not usable standalone"
        )

    def describe(self) -> str:
        return f"Landlock ABI v{self._abi} (filesystem only; not standalone-usable)"

    # -- the actual Landlock filesystem restriction (correct; for future use) ----

    def apply_fs_only(self, scratch: str) -> None:
        """Make the filesystem read-only everywhere except ``scratch``.

        Applies a Landlock ruleset that *handles* every ABI-v1 filesystem right,
        grants read/execute rights on ``/`` (so the interpreter stays importable),
        and grants full read+write+create rights only beneath ``scratch``. Any right
        handled-but-not-granted for a path is denied by the kernel.

        Fails closed: raises on any syscall error. Must be called before user code.
        Only meaningful on a Linux kernel with Landlock (ABI >= 1).
        """
        if not sys.platform.startswith("linux"):
            raise RuntimeError("Landlock is Linux-only")
        if self._abi < 1:
            raise RuntimeError("kernel does not support Landlock")

        scratch = os.path.abspath(scratch)
        libc = _libc()

        # 1) Create a ruleset that handles all v1 filesystem rights.
        attr = _landlock_ruleset_attr(handled_access_fs=_LANDLOCK_ACCESS_FS_ALL_V1)
        ctypes.set_errno(0)
        ruleset_fd = libc.syscall(
            ctypes.c_long(_NR_landlock_create_ruleset),
            ctypes.byref(attr),
            ctypes.c_size_t(ctypes.sizeof(attr)),
            ctypes.c_uint32(0),
        )
        if ruleset_fd < 0:
            err = ctypes.get_errno()
            raise OSError(err, f"landlock_create_ruleset failed: {os.strerror(err)}")

        try:
            # 2a) Grant read+execute on the whole tree so imports keep working.
            self._add_path_rule(libc, ruleset_fd, "/", _LANDLOCK_ACCESS_FS_READ_ONLY)
            # 2b) Grant the full set (incl. write/create/remove) beneath scratch.
            self._add_path_rule(libc, ruleset_fd, scratch, _LANDLOCK_ACCESS_FS_ALL_V1)

            # 3) No-new-privs is mandatory before restrict_self for unprivileged use.
            ctypes.set_errno(0)
            if libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
                err = ctypes.get_errno()
                raise OSError(err, f"prctl(PR_SET_NO_NEW_PRIVS) failed: {os.strerror(err)}")

            # 4) Enforce the ruleset on the current thread/process tree.
            ctypes.set_errno(0)
            if libc.syscall(
                ctypes.c_long(_NR_landlock_restrict_self),
                ctypes.c_int(int(ruleset_fd)),
                ctypes.c_uint32(0),
            ) != 0:
                err = ctypes.get_errno()
                raise OSError(err, f"landlock_restrict_self failed: {os.strerror(err)}")
        finally:
            os.close(int(ruleset_fd))

    @staticmethod
    def _add_path_rule(libc, ruleset_fd, path: str, access: int) -> None:
        """Add one LANDLOCK_RULE_PATH_BENEATH rule granting ``access`` under ``path``."""
        # LANDLOCK_RULE_PATH_BENEATH = 1. Ref: uapi linux/landlock.h enum
        # landlock_rule_type.
        _LANDLOCK_RULE_PATH_BENEATH = 1
        fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
        try:
            rule = _landlock_path_beneath_attr(allowed_access=access, parent_fd=fd)
            ctypes.set_errno(0)
            if libc.syscall(
                ctypes.c_long(_NR_landlock_add_rule),
                ctypes.c_int(int(ruleset_fd)),
                ctypes.c_int(_LANDLOCK_RULE_PATH_BENEATH),
                ctypes.byref(rule),
                ctypes.c_uint32(0),
            ) != 0:
                err = ctypes.get_errno()
                raise OSError(
                    err, f"landlock_add_rule({path!r}) failed: {os.strerror(err)}"
                )
        finally:
            os.close(fd)


# ---------------------------------------------------------------------------
# Public selection entry point
# ---------------------------------------------------------------------------


def confinement() -> "Confinement | None":  # noqa: F821 - Confinement is a Protocol in abax.sandbox
    """Return the best usable Linux confinement, or None.

    Preference: bubblewrap (if the binary works) > Landlock (currently reports
    unavailable, see module docstring) > None. The caller treats a returned
    strategy whose ``available()`` is False the same as None (fails closed under
    strict mode), so returning the Landlock instance vs. None is equivalent; we
    return None to keep the "nothing usable" case unambiguous.
    """
    bwrap = _bwrap_path()
    if bwrap is not None:
        return _BwrapConfine(bwrap)
    # No bwrap. Landlock alone can't deny the network, so there's nothing usable.
    # (We still probe so a future seccomp addition can flip this on.)
    _ = landlock_abi_version()
    return None
