"""7-Zip (``.7z``) archive support — an optional engine adapter over ``py7zr``.

``.7z`` is not in the standard library (unlike ``.zip``/``.tar`` in
:mod:`abax.core.archive`), so it lives in the engine layer behind the optional
``py7zr`` dependency. Everything degrades gracefully: :func:`available` reports
whether ``py7zr`` is importable, and every operation raises
:class:`~abax.core.archive.ArchiveError` with an actionable message when it isn't
(``pip install abax[sevenzip]``).

Like the stdlib archive core, extraction is **path-traversal-safe**: a member
that would escape the destination directory raises rather than writing outside
it (the "zip-slip" guard).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ..core.archive import ArchiveError, _is_within


def available() -> bool:
    """True if ``py7zr`` is importable (so ``.7z`` operations can run)."""
    try:
        import py7zr  # noqa: F401
    except Exception:
        return False
    return True


def _require():
    try:
        import py7zr
    except Exception as exc:  # noqa: BLE001
        raise ArchiveError(
            "7-Zip support needs the 'py7zr' package — install it with "
            "'pip install abax[sevenzip]' (or 'pip install py7zr').") from exc
    return py7zr


def is_7z(path) -> bool:
    """True if ``path`` is a readable ``.7z`` archive (needs ``py7zr``)."""
    if not available():
        return False
    py7zr = _require()
    try:
        return bool(py7zr.is_7zfile(path))
    except OSError:
        return False


def create_7z(sources, dest) -> str:
    """Create a ``.7z`` archive at ``dest`` from ``sources`` (files and/or dirs).

    Each source is stored under its base name (directories recurse), matching the
    stdlib :func:`abax.core.archive.create_archive` behaviour.
    """
    py7zr = _require()
    srcs = [Path(s) for s in sources]
    if not srcs:
        raise ArchiveError("nothing to archive")
    dest = Path(dest)
    with py7zr.SevenZipFile(dest, "w") as zf:
        for src in srcs:
            zf.write(src, arcname=src.name)
    return str(dest)


def list_7z(path) -> "list[str]":
    """The member names inside a ``.7z`` archive."""
    py7zr = _require()
    with py7zr.SevenZipFile(path, "r") as zf:
        return list(zf.getnames())


def extract_7z(path, dest_dir, members=None) -> "list[str]":
    """Extract a ``.7z`` archive into ``dest_dir`` (optionally only ``members``).

    Rejects any member whose path escapes ``dest_dir`` (the zip-slip guard) and
    returns the member names that were extracted.
    """
    py7zr = _require()
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    with py7zr.SevenZipFile(path, "r") as zf:
        names = list(zf.getnames())
        wanted = names if members is None else [n for n in names if n in set(members)]
        for name in wanted:
            if not _is_within(dest, dest / name):
                raise ArchiveError(f"unsafe path in archive: {name}")
        zf.extract(path=str(dest), targets=wanted if members is not None else None)
    return wanted


def read_member(path, member) -> bytes:
    """Return the raw bytes of a single member of a ``.7z`` archive.

    ``py7zr`` extracts to the filesystem (its decompression is stream-based), so
    we unpack just the one target into a throwaway temp dir and read it back.
    """
    py7zr = _require()
    with tempfile.TemporaryDirectory(prefix="abax-7z-") as td:
        with py7zr.SevenZipFile(path, "r") as zf:
            if member not in set(zf.getnames()):
                raise ArchiveError(f"no such member: {member}")
            zf.extract(path=td, targets=[member])
        out = Path(td) / member
        if not out.is_file():
            raise ArchiveError(f"member is not a regular file: {member}")
        return out.read_bytes()
