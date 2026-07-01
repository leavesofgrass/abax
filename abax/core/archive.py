"""Archive support for the file manager: create / list / extract (pure stdlib).

Wraps :mod:`zipfile` and :mod:`tarfile` behind one small API so the file manager
can offer one-click "compress to .zip / .tar.gz" and safe extraction. Formats are
chosen from the destination suffix: ``.zip``; ``.tar``; ``.tar.gz`` / ``.tgz``;
``.tar.bz2`` / ``.tbz2``; ``.tar.xz`` / ``.txz``.

Extraction is path-traversal-safe — a member that would escape the destination
directory (``../`` or an absolute path) raises :class:`ArchiveError` rather than
writing outside it (the "zip-slip" / "tar-slip" guard).
"""

from __future__ import annotations

import os
import tarfile
import zipfile
from pathlib import Path

_TAR_MODES = {
    ".tar": "w", ".tgz": "w:gz", ".txz": "w:xz", ".tbz2": "w:bz2",
}
_TAR_COMPOUND = {
    ".tar.gz": "w:gz", ".tar.bz2": "w:bz2", ".tar.xz": "w:xz",
}


class ArchiveError(Exception):
    """Raised for an unsupported format or an unsafe archive member."""


def _kind(path: Path) -> tuple[str, str]:
    """Return ``("zip"|"tar", mode)`` for a destination path, by suffix."""
    name = path.name.lower()
    if name.endswith(".zip"):
        return "zip", ""
    for suffix, mode in _TAR_COMPOUND.items():
        if name.endswith(suffix):
            return "tar", mode
    ext = path.suffix.lower()
    if ext in _TAR_MODES:
        return "tar", _TAR_MODES[ext]
    raise ArchiveError(f"unsupported archive type: {path.name}")


def create_archive(sources, dest) -> str:
    """Create an archive at ``dest`` containing ``sources`` (files and/or dirs).

    Each source is stored under its base name (directories recurse). The format is
    inferred from ``dest``'s suffix. Returns the destination path.
    """
    dest = Path(dest)
    kind, mode = _kind(dest)
    srcs = [Path(s) for s in sources]
    if not srcs:
        raise ArchiveError("nothing to archive")

    if kind == "zip":
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for src in srcs:
                if src.is_dir():
                    for root, _dirs, files in os.walk(src):
                        for fname in files:
                            full = Path(root) / fname
                            arc = src.name / full.relative_to(src)
                            zf.write(full, arc.as_posix())
                    # keep empty directories
                    for root, dirs, files in os.walk(src):
                        if not dirs and not files:
                            arc = src.name / Path(root).relative_to(src)
                            zf.writestr(arc.as_posix() + "/", "")
                else:
                    zf.write(src, src.name)
    else:
        with tarfile.open(dest, mode) as tf:
            for src in srcs:
                tf.add(src, arcname=src.name)
    return str(dest)


def list_archive(path) -> list[str]:
    """The member names inside an archive."""
    path = Path(path)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            return zf.namelist()
    if tarfile.is_tarfile(path):
        with tarfile.open(path) as tf:
            return tf.getnames()
    raise ArchiveError(f"not a readable archive: {path.name}")


def _is_within(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def extract_archive(path, dest_dir) -> list[str]:
    """Extract an archive into ``dest_dir`` and return the extracted member names.

    Rejects any member whose path escapes ``dest_dir`` (raises :class:`ArchiveError`).
    """
    path = Path(path)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if not _is_within(dest, dest / name):
                    raise ArchiveError(f"unsafe path in archive: {name}")
            zf.extractall(dest)
            return zf.namelist()
    if tarfile.is_tarfile(path):
        with tarfile.open(path) as tf:
            members = tf.getmembers()
            for m in members:
                if m.islnk() or m.issym():
                    target = dest / m.name
                    link = Path(m.linkname)
                    if link.is_absolute() or not _is_within(dest, target.parent / link):
                        raise ArchiveError(f"unsafe link in archive: {m.name}")
                elif not _is_within(dest, dest / m.name):
                    raise ArchiveError(f"unsafe path in archive: {m.name}")
            try:
                tf.extractall(dest, filter="data")   # defense in depth (3.12+)
            except TypeError:
                tf.extractall(dest)                  # older Python: our checks guard
            return tf.getnames()
    raise ArchiveError(f"not a readable archive: {path.name}")
