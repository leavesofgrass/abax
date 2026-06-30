"""Configurable command buttons for the file manager (Worker / Directory Opus style).

A :class:`Button` carries a label and a **command template** with placeholders that
expand against the current file-manager context — the active pane's directory, the
current selection, and the other pane's directory:

==========  ===================================================================
``{dir}``   active pane's directory
``{dest}``  other pane's directory (the usual copy/move target)
``{path}``  first selected path (full)
``{name}``  base name of ``{path}``
``{stem}``  ``{name}`` without its extension
``{ext}``   extension of ``{path}`` (with the dot)
``{sel}``   every selected path, space-joined and quoted
==========  ===================================================================

:func:`expand` does the substitution (pure, testable); :func:`run_button` runs the
expanded command through the system shell from the active directory. Buttons
round-trip to/from plain dicts so the GUI can persist a user's custom set. Worker
scripts buttons in Lua; qcell keeps everything in Python — a command can be a shell
one-liner or, naturally, ``python -c ...``.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field


def _quote(path: str) -> str:
    """Quote a path for a shell command if it needs it (empty stays empty)."""
    if not path:
        return ""
    if not any(ch in path for ch in ' \t"\'&|<>()'):
        return path
    return '"' + path.replace('"', '\\"') + '"'


@dataclass
class Context:
    """The file-manager state a button command expands against."""
    directory: str
    selection: list[str] = field(default_factory=list)
    dest_dir: str = ""

    @property
    def active(self) -> str:
        return self.selection[0] if self.selection else ""


def expand(template: str, ctx: Context) -> str:
    """Substitute the ``{...}`` placeholders in ``template`` from ``ctx``."""
    active = ctx.active
    name = os.path.basename(active)
    stem, ext = os.path.splitext(name)
    values = {
        "dir": _quote(ctx.directory),
        "dest": _quote(ctx.dest_dir),
        "path": _quote(active),
        "name": name,
        "stem": stem,
        "ext": ext,
        "sel": " ".join(_quote(p) for p in ctx.selection),
    }
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", value)
    return out


@dataclass
class RunResult:
    command: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass
class Button:
    """A labelled command button. ``command`` is a template for :func:`expand`."""
    label: str
    command: str
    confirm: bool = False        # ask before running (the GUI honors this)
    capture: bool = True         # capture stdout/stderr vs. fire-and-forget

    def to_dict(self) -> dict:
        return {"label": self.label, "command": self.command,
                "confirm": self.confirm, "capture": self.capture}

    @classmethod
    def from_dict(cls, data: dict) -> "Button":
        return cls(label=str(data["label"]), command=str(data["command"]),
                   confirm=bool(data.get("confirm", False)),
                   capture=bool(data.get("capture", True)))


def run_button(button: Button, ctx: Context, *, timeout: float | None = None) -> RunResult:
    """Expand and run ``button``'s command in ``ctx.directory`` via the shell.

    Returns a :class:`RunResult`. A command that cannot start (or times out) comes
    back with a non-zero return code and the reason in ``stderr`` rather than
    raising, so the file manager can show it.
    """
    command = expand(button.command, ctx)
    cwd = ctx.directory if os.path.isdir(ctx.directory) else None
    try:
        proc = subprocess.run(
            command, shell=True, cwd=cwd, timeout=timeout,
            capture_output=button.capture, text=True)
    except subprocess.TimeoutExpired:
        return RunResult(command, 124, "", f"timed out after {timeout}s")
    except OSError as exc:
        return RunResult(command, 127, "", str(exc))
    return RunResult(command, proc.returncode,
                     proc.stdout or "" if button.capture else "",
                     proc.stderr or "" if button.capture else "")


def default_buttons() -> list[Button]:
    """A starter set of buttons. Cross-platform where it's easy; the user edits
    the rest. (Archive/search/copy live as builtins in the GUI toolbar.)"""
    return [
        Button("Show path", "echo {path}"),          # echo works in cmd and sh
        Button("Git status", "git status -s"),        # runs in the active {dir}
        Button("Git log", "git log --oneline -10"),
        Button("Disk free", "df -h ." if os.name != "nt" else "wmic logicaldisk get size,freespace,caption"),
    ]
