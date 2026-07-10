"""Line-oriented system-shell passthrough — the testable core of an in-app terminal.

This is *not* a PTY: each command is run once through the system shell with its
output captured, then returned as a :class:`Result`. The system shell is
``cmd /c`` on Windows (``os.name == "nt"``) and ``/bin/sh -c`` elsewhere.

:class:`ShellSession` adds statefulness that a series of independent
``subprocess.run`` calls can't have on their own. ``cd`` is a shell builtin, so
it would not persist from one ``subprocess.run`` to the next; the session
therefore tracks the working directory itself and passes it via the ``cwd=``
argument of each run. Pure stdlib → core.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


@dataclass
class Result:
    """The captured outcome of one shell command."""

    stdout: str
    stderr: str
    returncode: int


def _shell_command(command: str) -> list[str] | str:
    """The system-shell invocation that runs `command` as one shell line.

    On POSIX this is the argv ``["/bin/sh", "-c", command]``. On Windows it must
    be a single pre-quoted string: passing a list there would route through
    ``subprocess.list2cmdline``, which re-quotes the embedded command and breaks
    ``cmd``'s own quote handling. ``cmd /s /c "<command>"`` keeps the inner
    quoting (e.g. ``python -c "..."``) intact.
    """
    if os.name == "nt":
        return 'cmd /s /c "' + command + '"'
    return ["/bin/sh", "-c", command]


def run(command: str, cwd: str | None = None, timeout: float = 30.0,
        env: "dict[str, str] | None" = None) -> Result:
    """Run `command` through the system shell and capture its output.

    `cwd` selects the working directory (the process cwd when ``None``).
    `env` replaces the child's environment when given (callers merge extra
    variables — e.g. abax's ``$ABAX_*`` selection context — into ``os.environ``
    themselves). On timeout, return a :class:`Result` with a nonzero
    ``returncode`` and a note in ``stderr`` rather than raising.
    """
    try:
        proc = subprocess.run(
            _shell_command(command),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or ""
        err = exc.stderr or ""
        if isinstance(out, bytes):
            out = out.decode(errors="replace")
        if isinstance(err, bytes):
            err = err.decode(errors="replace")
        note = f"abax: command timed out after {timeout:g}s"
        err = f"{err}\n{note}" if err else note
        return Result(stdout=out, stderr=err, returncode=124)
    return Result(stdout=proc.stdout, stderr=proc.stderr, returncode=proc.returncode)


class ShellSession:
    """A stateful shell: tracks cwd (and inherited environment) across commands."""

    def __init__(self, cwd: str | None = None,
                 env: "dict[str, str] | None" = None) -> None:
        self._cwd = os.path.abspath(cwd if cwd is not None else os.getcwd())
        # None -> the child inherits this process's environment. A dict replaces
        # it (callers merge extras, e.g. the $ABAX_* selection context).
        self._env = env

    @property
    def cwd(self) -> str:
        return self._cwd

    def prompt(self) -> str:
        """A display prompt, e.g. ``/home/me> ``."""
        return f"{self._cwd}> "

    def _cd(self, arg: str) -> Result:
        """Resolve and apply a ``cd`` target, updating ``self._cwd`` on success."""
        arg = arg.strip()
        if not arg or arg == "~":
            target = os.path.expanduser("~")
        else:
            target = os.path.expanduser(arg)
            if not os.path.isabs(target):
                target = os.path.join(self._cwd, target)
        target = os.path.abspath(target)
        if not os.path.isdir(target):
            return Result(
                stdout="",
                stderr=f"cd: no such directory: {arg}",
                returncode=1,
            )
        self._cwd = target
        return Result(stdout="", stderr="", returncode=0)

    def execute(self, command: str) -> Result:
        """Run `command`, handling ``cd`` and bare ``pwd`` in-process.

        ``cd`` changes :attr:`cwd` (relative to the current cwd; ``~`` and a
        bare ``cd`` go home). A bare ``pwd`` reports the tracked cwd directly so
        it stays consistent with :attr:`cwd`. Everything else is dispatched to
        :func:`run` with ``cwd=self.cwd``.
        """
        stripped = command.strip()
        if stripped == "cd" or stripped.startswith("cd ") or stripped.startswith("cd\t"):
            return self._cd(stripped[2:])
        if stripped == "pwd":
            return Result(stdout=self._cwd + "\n", stderr="", returncode=0)
        return run(command, cwd=self._cwd, env=self._env)
