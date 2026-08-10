"""No shipped file may point at a document that is not shipped.

`dev/` and `docs/roadmaps/` are gitignored working notes. On the maintainer's
machine they exist, so a reference to one reads fine while writing and reviewing
— and is a dead end for everyone who clones. Five had accumulated before anyone
looked, two of them in *published* mkdocs pages:

    docs/architecture.md        -> dev/sandbox-design.md
    docs/macros-and-scripting.md-> dev/sandbox-design.md
    CHANGELOG.md               -> dev/sandbox-design.md
    abax/sandbox_windows.py    -> dev/lessons-learned.md
    abax/core/depgraph.py      -> dev/roadmap.md

Nothing could have caught them: the files resolve locally, and `mkdocs build
--strict` does not check inline-code paths. So the check is here.

The private directories are read from `.gitignore` rather than hardcoded — if
one is ever un-ignored, this test relaxes on its own instead of lying.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

def _private_dirs() -> list[str]:
    """Directory prefixes `.gitignore` keeps out of the repo."""
    lines = (_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    return [ln.strip().rstrip("/") for ln in lines
            if ln.strip().endswith("/") and not ln.strip().startswith("#")]


def _scanned(private: list[str]) -> list[Path]:
    """Files that ship or are published.

    Anything *inside* a private directory is excluded: those notes reference
    each other freely and correctly, and scanning them would report every such
    link as a defect. `.gitignore` and `mkdocs.yml` are excluded for the
    mirror-image reason — naming these directories is their job.
    """
    candidates = (
        sorted(_ROOT.glob("abax/**/*.py"))
        + sorted(_ROOT.glob("docs/**/*.md"))
        + sorted(_ROOT.glob("scripts/*.py"))
        + [_ROOT / "README.md", _ROOT / "CHANGELOG.md",
           _ROOT / "CONTRIBUTING.md"]
    )
    return [p for p in candidates
            if not any(p.relative_to(_ROOT).as_posix().startswith(f"{d}/")
                       for d in private)]


def test_no_shipped_file_references_a_gitignored_document():
    private = _private_dirs()
    assert "dev" in private and "docs/roadmaps" in private, (
        f"expected dev/ and docs/roadmaps/ to be gitignored; got {private}")

    # A *document* reference — a path ending in .md. A bare directory mention
    # ("notes live under docs/roadmaps/") is prose, not a dead link.
    alternatives = "|".join(re.escape(d) for d in private)
    pattern = re.compile(rf"(?:{alternatives})/[A-Za-z0-9._/-]*\.md")

    dangling = []
    for path in _scanned(private):
        if not path.is_file():
            continue
        for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1):
            for hit in pattern.findall(line):
                rel = path.relative_to(_ROOT).as_posix()
                dangling.append(f"{rel}:{lineno} -> {hit}")

    assert not dangling, (
        "these shipped files reference documents no clone has:\n  "
        + "\n  ".join(dangling)
        + "\n\nEither point at published documentation, or inline the fact."
    )
