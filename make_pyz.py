"""Build pipeline for abax.pyz — optimize=2, compressed, stripped.

Stages the `abax` package, byte-compiles with optimize=2 (drops docstrings +
asserts), strips dev artifacts, verifies the bootstrapper is stdlib-only, then
zips it. Run via `just pyz`.
"""

from __future__ import annotations

import ast
import py_compile
import shutil
import zipapp
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "abax"
STAGE = ROOT / "_stage"
OUT = ROOT / "abax.pyz"

_STDLIB_OK = {"hashlib", "os", "sys", "zipfile", "pathlib", "importlib"}


def verify_bootstrap_stdlib_only() -> None:
    """Fail the build if pyz_main.py imports anything outside stdlib."""
    tree = ast.parse((ROOT / "pyz_main.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            for name in names:
                root = name.split(".")[0]
                # `from abax.app import main` lives inside bootstrap() and runs
                # only after the archive is on sys.path; the top-level imports
                # are what must stay stdlib-only. Allow abax here since it is
                # the archive's own package, imported lazily inside a function.
                if root and root not in _STDLIB_OK and root != "abax":
                    raise SystemExit(f"pyz_main.py imports non-stdlib: {root}")


def strip_and_stage() -> None:
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)

    # Byte-compile the package with optimize=2. Emit .pyc files (zipimport
    # imports them directly) named to match each module so the archive needs
    # no source. optimize=2 strips docstrings and asserts.
    for src in SRC.rglob("*.py"):
        rel = src.relative_to(SRC.parent).with_suffix(".pyc")
        dst = STAGE / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        py_compile.compile(str(src), str(dst), optimize=2, quiet=1)

    # Copy non-Python package data (QSS themes).
    for data in SRC.rglob("*.qss"):
        rel = data.relative_to(SRC.parent)
        dst = STAGE / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(data, dst)

    # The bootstrapper itself (uncompiled, so zipapp can find main).
    shutil.copy2(ROOT / "pyz_main.py", STAGE / "pyz_main.py")

    # Strip dev artifacts that may have crept in.
    for drop in ("tests", "docs", "__pycache__", "*.egg-info"):
        for p in STAGE.rglob(drop):
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink(missing_ok=True)


def recompress_max(path: Path) -> None:
    """Rewrite the archive's entries at DEFLATE level 9 (zipapp uses the default
    level 6). Preserves the shebang prefix and every member verbatim — only the
    compression ratio changes — so the entry point and zipimport stay intact."""
    import io
    import zipfile

    raw = path.read_bytes()
    shebang = b""
    if raw.startswith(b"#!"):
        shebang = raw[: raw.index(b"\n") + 1]
    buf = io.BytesIO()
    with zipfile.ZipFile(path) as src, \
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as dst:
        for name in src.namelist():
            dst.writestr(name, src.read(name))
    path.write_bytes(shebang + buf.getvalue())


def build() -> None:
    verify_bootstrap_stdlib_only()
    strip_and_stage()
    zipapp.create_archive(
        STAGE,
        target=OUT,
        interpreter="/usr/bin/env python3",
        compressed=True,  # DEFLATE — recompressed to level 9 below
        main="pyz_main:bootstrap",
    )
    before = OUT.stat().st_size
    recompress_max(OUT)
    after = OUT.stat().st_size
    print(f"Built {OUT.name} ({after // 1024} KB; "
          f"level-9 saved {(before - after) // 1024} KB)")


if __name__ == "__main__":
    build()
