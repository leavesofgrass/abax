"""Clipboard history manager plus a stdlib-only OS clipboard bridge.

Two pieces, both pure stdlib → core:

* :class:`ClipboardManager` — a "too many clips" history. It keeps the most
  recent text fragments newest-first, deduplicates by text, lets entries be
  pinned (kept across eviction and ``clear``), and evicts the oldest unpinned
  entries once a capacity is exceeded. Entries carry a short one-line preview
  label, auto-derived from the text when not supplied.

* OS bridge — module functions :func:`os_copy`, :func:`os_paste`,
  :func:`osc52` and :func:`copy` route through the OS clipboard tool when one
  is available (pbcopy/pbpaste, wl-copy/wl-paste, xclip, xsel, or Windows
  clip/Get-Clipboard), falling back to an **OSC 52** escape for copy which
  sets the terminal's clipboard and works over SSH on supporting terminals.
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

from .._runtime import console_encoding

LABEL_MAX = 40


def _derive_label(text: str) -> str:
    """First non-empty line of `text`, stripped and truncated to LABEL_MAX."""
    line = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped:
            line = stripped
            break
    if len(line) > LABEL_MAX:
        return line[:LABEL_MAX] + "…"
    return line


@dataclass
class ClipEntry:
    """A single clipboard fragment with a preview label and pin state."""

    text: str
    label: str = ""
    pinned: bool = False

    def __post_init__(self) -> None:
        if not self.label:
            self.label = _derive_label(self.text)

    def to_dict(self) -> dict:
        return {"text": self.text, "label": self.label, "pinned": self.pinned}

    @classmethod
    def from_dict(cls, d: dict) -> "ClipEntry":
        return cls(
            text=d.get("text", ""),
            label=d.get("label", ""),
            pinned=bool(d.get("pinned", False)),
        )


@dataclass
class ClipboardManager:
    """History of clipboard fragments, newest first, with pinning + eviction."""

    capacity: int = 50
    _items: list[ClipEntry] = field(default_factory=list)

    def __init__(self, capacity: int = 50) -> None:
        self.capacity = capacity
        self._items = []

    def add(self, text: str, label: str = "") -> "ClipEntry | None":
        """Add `text` newest-first; return the entry, or None if blank.

        Empty/whitespace-only text is ignored. If an entry with identical
        text already exists it is moved to the front (keeping its pin), and
        a non-empty `label` overrides the existing one. After adding, the
        oldest *unpinned* entries beyond `capacity` are evicted.
        """
        if not text or not text.strip():
            return None
        existing = None
        for entry in self._items:
            if entry.text == text:
                existing = entry
                break
        if existing is not None:
            self._items.remove(existing)
            if label:
                existing.label = label
            self._items.insert(0, existing)
            entry = existing
        else:
            entry = ClipEntry(text=text, label=label)
            self._items.insert(0, entry)
        self._evict()
        return entry

    def _evict(self) -> None:
        if self.capacity < 0:
            return
        unpinned = [e for e in self._items if not e.pinned]
        excess = len(unpinned) - self.capacity
        if excess <= 0:
            return
        # Drop the oldest unpinned entries (closest to the end of the list).
        to_drop = set(id(e) for e in unpinned[len(unpinned) - excess:])
        self._items = [e for e in self._items if id(e) not in to_drop]

    def entries(self) -> list[ClipEntry]:
        """Pinned entries first, then the rest, each in recency order."""
        pinned = [e for e in self._items if e.pinned]
        rest = [e for e in self._items if not e.pinned]
        return pinned + rest

    def get(self, index: int) -> "ClipEntry | None":
        items = self.entries()
        if 0 <= index < len(items):
            return items[index]
        return None

    def pin(self, index: int, pinned: bool = True) -> None:
        entry = self.get(index)
        if entry is not None:
            entry.pinned = pinned

    def remove(self, index: int) -> None:
        entry = self.get(index)
        if entry is not None:
            self._items.remove(entry)

    def clear(self, keep_pinned: bool = True) -> None:
        if keep_pinned:
            self._items = [e for e in self._items if e.pinned]
        else:
            self._items = []

    def to_dict(self) -> dict:
        return {
            "capacity": self.capacity,
            "items": [e.to_dict() for e in self._items],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ClipboardManager":
        mgr = cls(capacity=int(d.get("capacity", 50)))
        mgr._items = [ClipEntry.from_dict(x) for x in d.get("items", [])]
        return mgr


# --- OS clipboard bridge ---------------------------------------------------


# Helpers whose pipe encoding is fixed by the display protocol they speak,
# not by this process's locale: Wayland's clipboard offers text as the MIME
# type ``text/plain;charset=utf-8``, and the X11 tools exchange the
# ``UTF8_STRING`` selection target. Both are UTF-8 whatever ``LC_ALL`` says.
_UTF8_TOOLS = frozenset({"wl-copy", "wl-paste", "xclip", "xsel"})


def _tool_encoding(cmd: "list[str]") -> str:
    """The codec for *cmd*'s pipes — a property of the tool, not of our locale."""
    name = os.path.basename(cmd[0]).lower() if cmd else ""
    if name.endswith(".exe"):
        name = name[:-4]
    return "utf-8" if name in _UTF8_TOOLS else console_encoding()


def _run(cmd: "list[str]", text_in: "str | None" = None):
    """Drive one OS clipboard tool. None if it could not be run.

    This runs in **both** directions and round-trips the user's own clipboard
    text, the most likely thing in abax to be non-ASCII, so leaving the codec to
    the platform default is how a paste turns into mojibake or a
    ``UnicodeDecodeError``. But there is no single right codec for "the
    clipboard tool" either — it differs per tool, so :func:`_tool_encoding`
    picks from the argv:

    * ``wl-copy``/``wl-paste``, ``xclip``/``xsel`` — **UTF-8, by protocol.**
      Wayland's clipboard offers ``text/plain;charset=utf-8`` and the X11 tools
      use the ``UTF8_STRING`` selection target, so the bytes on the pipe are
      UTF-8 even under a latin-1 ``LC_ALL``, where our own locale would be the
      wrong answer in both directions. This is the ``pandoc`` case from
      :func:`abax._runtime.console_encoding`: a child *defined* to speak UTF-8
      names it literally.

    * ``clip`` and ``powershell -Command Get-Clipboard`` on Windows —
      :func:`~abax._runtime.console_encoding`. These really are console
      programs, and a redirected console pipe gets the OEM codepage; there is
      no protocol guarantee to lean on. (``subprocess`` applies one
      ``encoding=`` to stdin and stdout alike, and Windows' console input and
      output are strictly ANSI and OEM — the two cannot both be named, and OEM
      is the right single answer for a captured pipe.)

    * ``pbcopy``/``pbpaste`` on macOS — ``console_encoding()`` as well, which
      off Windows is the locale's codec. Unlike the Wayland/X11 tools these
      follow the user's ``LANG``/``LC_CTYPE`` rather than a wire format, so the
      locale *is* their contract and forcing UTF-8 would be the same mistake in
      the other direction. In practice the two agree: a macOS locale is UTF-8
      in every configuration a user is likely to have.

    ``errors="replace"`` throughout: a clipboard tool is a convenience, and a
    character we cannot map should cost that character, not the whole paste.
    """
    try:
        return subprocess.run(cmd, input=text_in, capture_output=True,
                              text=True, encoding=_tool_encoding(cmd),
                              errors="replace", timeout=2)
    except (OSError, subprocess.SubprocessError):
        return None


def os_copy(text: str) -> bool:
    """Copy via an OS clipboard tool. Returns True on success."""
    if sys.platform == "darwin" and shutil.which("pbcopy"):
        return _run(["pbcopy"], text) is not None
    if shutil.which("wl-copy"):
        return _run(["wl-copy"], text) is not None
    if shutil.which("xclip"):
        return _run(["xclip", "-selection", "clipboard"], text) is not None
    if shutil.which("xsel"):
        return _run(["xsel", "-b", "-i"], text) is not None
    if os.name == "nt" and shutil.which("clip"):
        return _run(["clip"], text) is not None
    return False


def os_paste() -> "str | None":
    """Read the OS clipboard, or None if no tool is available."""
    if sys.platform == "darwin" and shutil.which("pbpaste"):
        r = _run(["pbpaste"])
        return r.stdout if r is not None else None
    if shutil.which("wl-paste"):
        r = _run(["wl-paste", "-n"])
        return r.stdout if r is not None else None
    if shutil.which("xclip"):
        r = _run(["xclip", "-selection", "clipboard", "-o"])
        return r.stdout if r is not None else None
    if shutil.which("xsel"):
        r = _run(["xsel", "-b", "-o"])
        return r.stdout if r is not None else None
    if os.name == "nt" and shutil.which("powershell"):
        r = _run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"])
        return r.stdout.rstrip("\r\n") if r is not None else None
    return None


def osc52(text: str) -> None:
    """Emit an OSC 52 sequence to set the terminal clipboard (SSH-friendly)."""
    b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
    seq = f"\033]52;c;{b64}\a"
    if os.environ.get("TMUX"):                      # tmux passthrough wrapper
        seq = "\033Ptmux;\033" + seq + "\033\\"
    try:
        sys.stdout.write(seq)
        sys.stdout.flush()
    except (OSError, ValueError):
        pass


def copy(text: str) -> str:
    """Copy `text`; return a short status describing how it was copied."""
    if os_copy(text):
        return "copied"
    osc52(text)
    return "copied (OSC 52)"
