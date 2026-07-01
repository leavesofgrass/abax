"""Recursive file search for the file manager (pure stdlib).

Walks a directory tree and yields matches by name (glob), optional file contents
(regex), and size / type filters. Results are bounded (``limit``) and the walk is
robust to unreadable directories. Built on :mod:`os`, :mod:`fnmatch` and
:mod:`re` — no third-party code.
"""

from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Match:
    """One search hit. ``line_no``/``line`` are set only for content matches."""
    path: str
    size: int
    mtime: float
    is_dir: bool
    line_no: int = 0
    line: str = ""


def search(root, *, name_glob: str = "*", contains: str | None = None,
           regex: bool = False, ignore_case: bool = True,
           include_dirs: bool = True, min_size: int | None = None,
           max_size: int | None = None, max_depth: int | None = None,
           show_hidden: bool = False, limit: int = 5000) -> list[Match]:
    """Search ``root`` recursively.

    ``name_glob`` filters file/dir names (shell wildcards). ``contains`` searches
    text *file contents* (substring, or a regex when ``regex=True``); a content
    search implies files only. ``min_size``/``max_size`` (bytes) and ``max_depth``
    bound the search; ``limit`` caps the number of matches returned.
    """
    root = os.fspath(root)
    matches: list[Match] = []
    pat = None
    if contains is not None:
        flags = re.IGNORECASE if ignore_case else 0
        pat = re.compile(contains if regex else re.escape(contains), flags)
    glob = name_glob.lower() if ignore_case else name_glob
    root_depth = root.rstrip(os.sep).count(os.sep)

    for dirpath, dirnames, filenames in os.walk(root):
        if not show_hidden:
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            filenames = [f for f in filenames if not f.startswith(".")]
        # depth of entries in this dir is (relative dir depth + 1); stop descending
        # once that would exceed max_depth (max_depth=1 -> root level only).
        if max_depth is not None and dirpath.count(os.sep) - root_depth >= max_depth - 1:
            dirnames[:] = []

        names = filenames if contains is not None else (
            filenames + dirnames if include_dirs else filenames)
        for name in names:
            cmp_name = name.lower() if ignore_case else name
            if not fnmatch.fnmatch(cmp_name, glob):
                continue
            full = os.path.join(dirpath, name)
            is_dir = contains is None and name in dirnames
            try:
                st = os.stat(full)
            except OSError:
                continue
            size = 0 if is_dir else st.st_size
            if not is_dir:
                if min_size is not None and size < min_size:
                    continue
                if max_size is not None and size > max_size:
                    continue

            if pat is None:
                matches.append(Match(full, size, st.st_mtime, is_dir))
            else:
                hit = _content_hits(full, pat, remaining=limit - len(matches))
                matches.extend(Match(full, size, st.st_mtime, False, ln, text)
                               for ln, text in hit)
            if len(matches) >= limit:
                return matches[:limit]
    return matches


def _content_hits(path: str, pat: re.Pattern, *, remaining: int):
    """Yield ``(line_no, line)`` for content matches in a text file (binary or
    unreadable files yield nothing)."""
    out = []
    try:
        with open(path, encoding="utf-8", errors="strict") as fh:
            for i, line in enumerate(fh, start=1):
                if pat.search(line):
                    out.append((i, line.rstrip("\n")))
                    if len(out) >= remaining:
                        break
    except (OSError, UnicodeDecodeError):
        return []
    return out
