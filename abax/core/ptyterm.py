"""Real pseudo-terminal (PTY) backend — the engine behind a true terminal.

Unlike :mod:`abax.core.shell`, which runs each command once and captures its
output, this module spawns a child process inside a *pseudo-terminal* so that
interactive, full-screen programs (editors, REPLs, anything that expects a tty)
run normally. Raw bytes from the PTY are fed into a :mod:`pyte` terminal-emulator
screen, giving a renderable ``rows`` x ``cols`` grid of text.

The backend is optional and platform-dependent:

* On Windows it uses ``pywinpty`` (``import winpty``) for a ConPTY-backed child.
* On POSIX it uses the stdlib :func:`pty.openpty` plus :class:`subprocess.Popen`.

In both cases :mod:`pyte` is required to model the screen. When a needed library
is missing, :func:`pty_available` returns ``False`` and :meth:`PtyTerminal.start`
raises :class:`PtyError`, letting a caller (the GUI) fall back gracefully to a
line-oriented terminal.
"""

from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pyte


class PtyError(Exception):
    """Raised when a PTY backend is unavailable or a child fails to spawn."""


def _have_pyte() -> bool:
    """True if the :mod:`pyte` screen model is importable."""
    try:
        import pyte  # noqa: F401
    except Exception:
        return False
    return True


def _have_backend() -> bool:
    """True if a platform PTY backend is usable on this host."""
    if os.name == "nt":
        try:
            import winpty  # noqa: F401
        except Exception:
            return False
        return True
    return hasattr(os, "openpty")


def pty_available() -> bool:
    """True only if :mod:`pyte` *and* a platform PTY backend are usable.

    On Windows the backend is ``pywinpty`` (``import winpty``); on POSIX it is
    the stdlib :func:`os.openpty`. This never raises.
    """
    return _have_pyte() and _have_backend()


def _default_command() -> str:
    """The system shell, used when no command is supplied."""
    if os.name == "nt":
        return os.environ.get("COMSPEC", "cmd.exe")
    return os.environ.get("SHELL", "/bin/sh")


class PtyTerminal:
    """A child process running inside a PTY, rendered through a pyte screen.

    The constructor only records configuration; nothing is spawned until
    :meth:`start`. A daemon reader thread pumps raw PTY bytes into a
    :class:`pyte.ByteStream` feeding a :class:`pyte.Screen`, all guarded by a
    lock so that :meth:`read_screen`, :meth:`cursor` and :meth:`resize` see a
    consistent grid.
    """

    def __init__(
        self, cols: int = 100, rows: int = 30, command: str | None = None
    ) -> None:
        self.cols = cols
        self.rows = rows
        self.command = command if command is not None else _default_command()

        self._lock = threading.RLock()
        self._screen: pyte.Screen | None = None
        self._stream: pyte.ByteStream | None = None
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()

        # Exactly one of these is set after a successful start, per platform.
        self._proc: object | None = None  # winpty.PtyProcess (Windows)
        self._popen: object | None = None  # subprocess.Popen (POSIX)
        self._master_fd: int | None = None  # POSIX master fd

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Spawn ``command`` in a PTY and begin pumping output into the screen.

        Raises :class:`PtyError` if :func:`pty_available` is ``False`` or the
        child cannot be spawned.
        """
        if not pty_available():
            raise PtyError("PTY backend unavailable (need pyte and a PTY library)")

        import pyte

        self._screen = pyte.Screen(self.cols, self.rows)
        self._stream = pyte.ByteStream(self._screen)
        self._stop.clear()

        try:
            if os.name == "nt":
                self._start_windows()
            else:
                self._start_posix()
        except PtyError:
            raise
        except Exception as exc:  # spawn failure of any kind
            raise PtyError(f"failed to spawn PTY child: {exc}") from exc

        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _start_windows(self) -> None:
        import winpty

        self._proc = winpty.PtyProcess.spawn(self.command)
        self._proc.setwinsize(self.rows, self.cols)

    def _start_posix(self) -> None:
        import pty
        import subprocess

        master, slave = pty.openpty()
        self._master_fd = master
        try:
            self._popen = subprocess.Popen(
                self.command,
                shell=True,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                close_fds=True,
                preexec_fn=os.setsid,  # detach so it owns the tty
            )
        finally:
            os.close(slave)
        self._set_posix_winsize(self.cols, self.rows)

    # -- reader thread -----------------------------------------------------

    def _read_loop(self) -> None:
        """Read PTY bytes until the child exits, feeding the pyte stream."""
        if os.name == "nt":
            self._read_loop_windows()
        else:
            self._read_loop_posix()

    def _read_loop_windows(self) -> None:
        proc = self._proc
        while not self._stop.is_set():
            try:
                data = proc.read(4096)  # type: ignore[union-attr]
            except EOFError:
                break
            except Exception:
                break
            if data:
                chunk = data.encode("utf-8", "replace") if isinstance(data, str) else data
                with self._lock:
                    if self._stream is not None:
                        self._stream.feed(chunk)
            elif not self._isalive_unlocked():
                break

    def _read_loop_posix(self) -> None:
        import select

        fd = self._master_fd
        assert fd is not None
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([fd], [], [], 0.1)
            except (OSError, ValueError):
                break
            if not ready:
                if not self._isalive_unlocked():
                    break
                continue
            try:
                data = os.read(fd, 4096)
            except OSError:
                break
            if not data:
                break
            with self._lock:
                if self._stream is not None:
                    self._stream.feed(data)

    # -- I/O ---------------------------------------------------------------

    def write(self, data: str) -> None:
        """Send keystrokes to the PTY (encoded as UTF-8)."""
        if os.name == "nt":
            if self._proc is not None:
                self._proc.write(data)  # type: ignore[union-attr]
        else:
            if self._master_fd is not None:
                os.write(self._master_fd, data.encode("utf-8"))

    def read_screen(self) -> list[str]:
        """The current screen as a list of ``rows`` text lines."""
        with self._lock:
            if self._screen is None:
                return [""] * self.rows
            return list(self._screen.display)

    def read_cells(self) -> list[list[tuple]]:
        """A structured screen snapshot for an attribute-aware (colour) renderer.

        Returns ``rows`` lists of ``cols`` tuples
        ``(data, fg, bg, bold, italics, underscore, reverse)`` where ``fg``/``bg``
        are pyte colour strings (``"default"``, a named colour, or 6 hex digits).
        Decouples the GUI from pyte's ``Char`` type and is taken under the lock.
        """
        with self._lock:
            if self._screen is None:
                blank = ("", "default", "default", False, False, False, False)
                return [[blank] * self.cols for _ in range(self.rows)]
            buf = self._screen.buffer
            grid: list[list[tuple]] = []
            for y in range(self.rows):
                line = buf[y]
                row: list[tuple] = []
                for x in range(self.cols):
                    c = line[x]
                    row.append((c.data, c.fg, c.bg, c.bold, c.italics,
                                c.underscore, c.reverse))
                grid.append(row)
            return grid

    def cursor(self) -> tuple[int, int]:
        """The ``(row, col)`` position of the pyte cursor."""
        with self._lock:
            if self._screen is None:
                return (0, 0)
            cur = self._screen.cursor
            return (cur.y, cur.x)

    def resize(self, cols: int, rows: int) -> None:
        """Resize both the underlying PTY and the pyte screen."""
        self.cols = cols
        self.rows = rows
        if os.name == "nt":
            if self._proc is not None:
                try:
                    self._proc.setwinsize(rows, cols)  # type: ignore[union-attr]
                except Exception:
                    pass
        else:
            self._set_posix_winsize(cols, rows)
        with self._lock:
            if self._screen is not None:
                self._screen.resize(rows, cols)

    def _set_posix_winsize(self, cols: int, rows: int) -> None:
        if self._master_fd is None:
            return
        try:
            import fcntl
            import struct
            import termios

            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)
        except Exception:
            pass

    # -- status / teardown -------------------------------------------------

    def _isalive_unlocked(self) -> bool:
        if os.name == "nt":
            if self._proc is None:
                return False
            try:
                return bool(self._proc.isalive())  # type: ignore[union-attr]
            except Exception:
                return False
        if self._popen is None:
            return False
        return self._popen.poll() is None

    @property
    def alive(self) -> bool:
        """True while the child process is still running."""
        return self._isalive_unlocked()

    def close(self) -> None:
        """Terminate the child and stop the reader thread."""
        self._stop.set()
        if os.name == "nt":
            if self._proc is not None:
                try:
                    self._proc.terminate(force=True)
                except Exception:
                    pass
        else:
            if self._popen is not None:
                try:
                    self._popen.terminate()
                except Exception:
                    pass
            if self._master_fd is not None:
                try:
                    os.close(self._master_fd)
                except OSError:
                    pass
                self._master_fd = None
        if self._reader is not None:
            self._reader.join(timeout=2.0)
            self._reader = None
