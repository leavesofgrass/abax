"""The most important test file: the suite must pass with ZERO optional deps.

Everything imported here is stdlib + abax core. No msgspec, openpyxl, PyQt6,
textual, platformdirs required.
"""

from __future__ import annotations

from abax import diagnostics
from abax.core import Sheet
from abax.core.io.csv_io import dumps_csv, loads_csv


def test_core_imports_without_optional_deps():
    sheet = Sheet()
    sheet.set("A1", "1")
    sheet.set("A2", "=A1+1")
    assert sheet.get("A2") == 2.0


def test_diagnostics_registry_complete():
    for name, info in diagnostics.OPTIONAL_DEPENDENCIES.items():
        assert "available" in info
        assert "fallback" in info
        assert isinstance(info["available"], bool)


def test_format_deps_runs():
    text = diagnostics.format_deps()
    assert "abax optional dependencies" in text


def test_csv_roundtrip_pure_stdlib():
    sheet = loads_csv("a,b,c\n1,2,3\n")
    out = dumps_csv(sheet)
    assert out.splitlines()[0] == "a,b,c"
