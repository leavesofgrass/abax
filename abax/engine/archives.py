"""Unified archive facade for the file manager — one API over every format.

Routes by archive type: ``.zip`` / ``.tar[.gz|.bz2|.xz]`` go to the pure-stdlib
:mod:`abax.core.archive`; ``.7z`` goes to the optional :mod:`abax.engine.archive7z`
(``py7zr``). The GUI calls only this module, so it never has to branch on format.

Beyond create/list/extract it adds :func:`read_member` and
:func:`extract_member_to_temp` — the primitives behind "open a supported file
from *inside* an archive" without unpacking the whole thing.
"""

from __future__ import annotations

import tarfile
import tempfile
import zipfile
from pathlib import Path

from . import archive7z
from ..core import archive as _core
from ..core.archive import ArchiveError


def sevenzip_available() -> bool:
    return archive7z.available()


def _is_7z_name(path) -> bool:
    return str(path).lower().endswith(".7z")


def is_archive(path) -> bool:
    """True if ``path`` is a readable archive of any supported type."""
    p = Path(path)
    try:
        if zipfile.is_zipfile(p) or tarfile.is_tarfile(p):
            return True
    except OSError:
        return False
    return _is_7z_name(p) and archive7z.is_7z(p)


def create_exts() -> "list[str]":
    """Destination suffixes the file manager can offer for *creating* an archive
    (``.7z`` only when ``py7zr`` is installed)."""
    exts = [".zip", ".tar.gz"]
    if sevenzip_available():
        exts.append(".7z")
    return exts


def create_archive(sources, dest) -> str:
    if _is_7z_name(dest):
        return archive7z.create_7z(sources, dest)
    return _core.create_archive(sources, dest)


def list_archive(path) -> "list[str]":
    if _is_7z_name(path) or archive7z.is_7z(path):
        return archive7z.list_7z(path)
    return _core.list_archive(path)


def extract_archive(path, dest_dir) -> "list[str]":
    if _is_7z_name(path) or archive7z.is_7z(path):
        return archive7z.extract_7z(path, dest_dir)
    return _core.extract_archive(path, dest_dir)


def read_member(path, member) -> bytes:
    """Raw bytes of a single member, dispatched by archive type."""
    p = Path(path)
    if _is_7z_name(p) or archive7z.is_7z(p):
        return archive7z.read_member(p, member)
    if zipfile.is_zipfile(p):
        with zipfile.ZipFile(p) as zf:
            return zf.read(member)
    if tarfile.is_tarfile(p):
        with tarfile.open(p) as tf:
            fh = tf.extractfile(member)
            if fh is None:
                raise ArchiveError(f"member is not a regular file: {member}")
            return fh.read()
    raise ArchiveError(f"not a readable archive: {p.name}")


def extract_member_to_temp(path, member) -> str:
    """Extract one member to a temp file (keeping its base name so the extension
    survives) and return that path — the seam for opening a file from inside an
    archive. The caller owns the temp copy; the OS reclaims the temp dir."""
    data = read_member(path, member)
    base = Path(member).name or "member"
    tmpdir = tempfile.mkdtemp(prefix="abax-archive-")
    out = Path(tmpdir) / base
    out.write_bytes(data)
    return str(out)
