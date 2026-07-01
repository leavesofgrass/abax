"""File-manager core: directory listing and file operations (pure stdlib).

The non-GUI heart of qcell's dual-pane file manager. Everything here works on
plain paths with :mod:`os`, :mod:`shutil` and :mod:`pathlib`, so it is testable
without any GUI. Batch operations never raise on a single failure: they return an
:class:`OpResult` listing what succeeded and what failed (with the error text), so
the file manager can report partial results instead of aborting a whole copy.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def human_size(num: float) -> str:
    """A compact human-readable byte size (``1536`` -> ``"1.5 KB"``)."""
    size = float(num)
    for unit in _UNITS:
        if size < 1024.0 or unit == _UNITS[-1]:
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


@dataclass(frozen=True)
class Entry:
    """One directory entry."""
    name: str
    path: str
    is_dir: bool
    size: int
    mtime: float
    is_symlink: bool

    @property
    def suffix(self) -> str:
        return "" if self.is_dir else Path(self.name).suffix.lower()


_SORT_KEYS = {
    "name": lambda e: e.name.lower(),
    "size": lambda e: e.size,
    "mtime": lambda e: e.mtime,
    "type": lambda e: (e.suffix, e.name.lower()),
}


def list_dir(path, *, show_hidden: bool = False, sort_key: str = "name",
             reverse: bool = False, dirs_first: bool = True) -> list[Entry]:
    """List a directory as :class:`Entry` objects (directories first by default).

    Unreadable entries are skipped. ``sort_key`` is one of ``name``/``size``/
    ``mtime``/``type``. Raises :class:`NotADirectoryError` / :class:`FileNotFoundError`
    if ``path`` is not a readable directory.
    """
    base = Path(path)
    if not base.is_dir():
        raise NotADirectoryError(f"not a directory: {path}")
    entries: list[Entry] = []
    with os.scandir(base) as it:
        for de in it:
            if not show_hidden and de.name.startswith("."):
                continue
            try:
                st = de.stat(follow_symlinks=False)
                is_dir = de.is_dir(follow_symlinks=True)
            except OSError:
                continue
            entries.append(Entry(
                name=de.name, path=de.path, is_dir=is_dir,
                size=0 if is_dir else st.st_size, mtime=st.st_mtime,
                is_symlink=de.is_symlink()))
    keyfn = _SORT_KEYS.get(sort_key, _SORT_KEYS["name"])
    entries.sort(key=keyfn, reverse=reverse)
    if dirs_first:
        entries.sort(key=lambda e: not e.is_dir)
    return entries


@dataclass
class OpResult:
    """Outcome of a batch operation."""
    done: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed

    def summary(self) -> str:
        msg = f"{len(self.done)} succeeded"
        if self.failed:
            msg += f", {len(self.failed)} failed"
        return msg


def unique_path(dest: Path) -> Path:
    """A non-colliding sibling of ``dest`` (``file.txt`` -> ``file (1).txt``)."""
    if not dest.exists():
        return dest
    stem, suffix, parent = dest.stem, dest.suffix, dest.parent
    n = 1
    while True:
        cand = parent / f"{stem} ({n}){suffix}"
        if not cand.exists():
            return cand
        n += 1


def _resolve_dest(src: Path, dest_dir: Path, on_conflict: str) -> Path | None:
    dest = dest_dir / src.name
    if dest.exists():
        if on_conflict == "skip":
            return None
        if on_conflict == "rename":
            return unique_path(dest)
    return dest


def copy_paths(srcs, dest_dir, *, on_conflict: str = "rename") -> OpResult:
    """Copy files/dirs into ``dest_dir``. ``on_conflict``: ``rename`` (default),
    ``overwrite`` or ``skip``."""
    dest_dir = Path(dest_dir)
    res = OpResult()
    for s in srcs:
        src = Path(s)
        try:
            dest = _resolve_dest(src, dest_dir, on_conflict)
            if dest is None:
                continue
            if src.resolve() == dest.resolve():
                dest = unique_path(dest)
            if src.is_dir():
                shutil.copytree(src, dest, dirs_exist_ok=(on_conflict == "overwrite"))
            else:
                shutil.copy2(src, dest)
            res.done.append(str(dest))
        except OSError as exc:
            res.failed.append((str(src), str(exc)))
    return res


def move_paths(srcs, dest_dir, *, on_conflict: str = "rename") -> OpResult:
    """Move files/dirs into ``dest_dir``."""
    dest_dir = Path(dest_dir)
    res = OpResult()
    for s in srcs:
        src = Path(s)
        try:
            dest = _resolve_dest(src, dest_dir, on_conflict)
            if dest is None:
                continue
            if on_conflict == "overwrite" and dest.exists():
                delete_paths([dest])
            shutil.move(str(src), str(dest))
            res.done.append(str(dest))
        except OSError as exc:
            res.failed.append((str(src), str(exc)))
    return res


def delete_paths(paths) -> OpResult:
    """Delete files and directories (recursively)."""
    res = OpResult()
    for p in paths:
        path = Path(p)
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
            res.done.append(str(path))
        except OSError as exc:
            res.failed.append((str(path), str(exc)))
    return res


def make_dir(parent, name: str) -> str:
    """Create a new subdirectory and return its path."""
    target = Path(parent) / name
    target.mkdir(parents=False, exist_ok=False)
    return str(target)


def tree_size(path) -> int:
    """Total size in bytes of ``path`` — the file's own size, or the recursive sum
    of every file under it for a directory. Unreadable entries are skipped (a
    directory size should never abort on one permission error)."""
    p = Path(path)
    if p.is_file():
        try:
            return p.stat().st_size
        except OSError:
            return 0
    total = 0
    for root, _dirs, files in os.walk(p, onerror=lambda _e: None):
        for name in files:
            try:
                total += os.stat(os.path.join(root, name)).st_size
            except OSError:
                continue
    return total


def rename_path(path, new_name: str) -> str:
    """Rename ``path`` to ``new_name`` within the same directory."""
    src = Path(path)
    if "/" in new_name or "\\" in new_name:
        raise ValueError("new name must not contain a path separator")
    dest = src.with_name(new_name)
    if dest.exists():
        raise FileExistsError(f"already exists: {new_name}")
    src.rename(dest)
    return str(dest)
