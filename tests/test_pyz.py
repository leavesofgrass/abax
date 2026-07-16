"""pyz_main.py must import only stdlib (AST walk) + a --help smoke test."""

from __future__ import annotations

import ast
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Roots allowed at module top level in the bootstrapper. `abax` is allowed
# only because it is imported lazily *inside* bootstrap(), after the archive is
# on sys.path; this test checks top-level imports.
_STDLIB_OK = {"os", "sys", "zipfile", "pathlib", "hashlib", "importlib"}


def test_pyz_main_top_level_imports_are_stdlib():
    tree = ast.parse((ROOT / "pyz_main.py").read_text())
    for node in tree.body:  # top level only
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            for name in names:
                root = name.split(".")[0]
                assert root in _STDLIB_OK, f"non-stdlib top-level import: {root}"


def test_cli_help_smoke():
    result = subprocess.run(
        [sys.executable, "-m", "abax", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "abax" in result.stdout.lower()


def test_cli_version_smoke():
    result = subprocess.run(
        [sys.executable, "-m", "abax", "--version"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "abax" in result.stdout.lower()


def test_bundled_theme_loads_from_zipapp(tmp_path):
    """Regression: bundled .qss stylesheets must load when abax runs from a zip.

    The GUI previously read themes via ``Path(__file__).parent / 'themes'`` +
    ``read_text()``, which works from source but raises on a zip-internal path —
    so the GUI crashed on startup from ``abax.pyz``. ``apply_theme`` now uses
    ``importlib.resources``; this packs abax into a zip (as the .pyz is) and
    loads a theme through that import path to prove it works.
    """
    pkg = ROOT / "abax"
    archive = tmp_path / "abax_pkg.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for f in pkg.rglob("*"):
            if f.suffix in (".py", ".qss") and "__pycache__" not in f.parts:
                z.write(f, f.relative_to(ROOT).as_posix())
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]);"
        "from abax.gui import theming;"
        "s = theming._read_qss('galaxy');"
        "assert len(s) > 100, 'qss came back empty';"
        "assert len(theming._read_qss('does_not_exist')) > 0, 'fallback failed';"
        "print('ZIPQSS_OK')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(archive)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "ZIPQSS_OK" in result.stdout
