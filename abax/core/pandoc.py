"""Pandoc detection and on-demand bootstrap — for LaTeX → MathML equations.

abax prefers a real pandoc for rich equation rendering (see
:mod:`abax.core.latexmath`). If none is installed it can fetch one on demand
via the ``pypandoc_binary`` wheel (which bundles the pandoc executable), then
expose it to :mod:`latexmath` through the ``PANDOC`` env var. Everything is
graceful: no network / no pip → returns False, never raises.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys

log = logging.getLogger("abax.pandoc")


def pandoc_path() -> str | None:
    """Resolve a pandoc executable: $PANDOC, PATH, or a pypandoc-managed binary."""
    env = os.environ.get("PANDOC")
    if env and shutil.which(env):
        return shutil.which(env)
    found = shutil.which("pandoc")
    if found:
        return found
    try:
        import pypandoc

        path = pypandoc.get_pandoc_path()
        if path:
            return path
    except Exception:
        pass
    return None


def available() -> bool:
    return pandoc_path() is not None


def ensure(install: bool = True, timeout: int = 300) -> bool:
    """Return True if pandoc is usable, installing ``pypandoc_binary`` if needed.

    On success the resolved path is written to ``os.environ['PANDOC']`` so
    :mod:`abax.core.latexmath` finds it. Never raises.
    """
    path = pandoc_path()
    if path:
        os.environ.setdefault("PANDOC", path)
        return True
    if not install:
        return False
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "pypandoc_binary"],
            timeout=timeout,
            capture_output=True,
        )
    except Exception as exc:  # pragma: no cover - environment dependent
        log.warning("pandoc install failed: %s", exc)
    path = pandoc_path()
    if path:
        os.environ["PANDOC"] = path
        return True
    return False
