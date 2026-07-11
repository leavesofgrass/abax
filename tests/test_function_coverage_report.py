"""Tests for the read-only function-coverage dashboard (scripts/function_coverage.py).

These pin the *reporting* tool, not the registries: the report runs, produces a
sane coverage number, its curated target list is well-formed (plausible UPPERCASE
function tokens), and the implemented count stays at/above the registry's current
size floor. No behaviour of the engine is exercised or changed here.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

# Load scripts/function_coverage.py as a module (scripts/ is not a package).
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "function_coverage.py"
_spec = importlib.util.spec_from_file_location("function_coverage", _SCRIPT)
assert _spec and _spec.loader
function_coverage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(function_coverage)

# A plausible spreadsheet-function token: UPPERCASE letters/digits, optional dotted
# or underscored segments (e.g. NORM.S.DIST, ERROR.TYPE, R.DBINOM, SUMX2MY2).
_TOKEN = re.compile(r"^[A-Z][A-Z0-9]*(?:[._][A-Z0-9]+)*$")


def test_report_runs_and_returns_coverage_number():
    report = function_coverage.build_report()
    assert isinstance(report, dict)
    coverage = report["coverage"]
    assert isinstance(coverage, (int, float))
    assert 0.0 <= coverage <= 100.0
    # Covered targets are a subset of the (deduped) target total.
    assert 0 <= report["covered"] <= report["target_total"]
    assert report["target_total"] > 0


def test_curated_coverage_is_complete():
    # The whole curated Excel/Gnumeric target set is implemented — 100%, no
    # missing functions. This is a ratchet: it must never regress.
    report = function_coverage.build_report()
    assert report["coverage"] == 100.0, report.get("missing")
    assert report["covered"] == report["target_total"]


def test_every_target_is_a_plausible_uppercase_token():
    for category, names in function_coverage.TARGETS.items():
        assert names, f"empty target category: {category}"
        for name in names:
            assert name == name.upper(), f"{name} is not uppercase"
            assert _TOKEN.match(name), f"{name} is not a plausible function token"


def test_implemented_count_meets_registry_sanity_bound():
    report = function_coverage.build_report()
    # The live registries currently number in the many hundreds after the parity
    # waves; the report must reflect at least that floor (matches the >=560 bound
    # in test_function_coverage.py, with headroom for lazy/context registries).
    assert report["implemented"] >= 560


def test_text_and_markdown_render():
    report = function_coverage.build_report()
    text = function_coverage.format_text(report)
    assert "function-coverage dashboard" in text
    assert f"{report['coverage']}" in text

    md = function_coverage.format_markdown(report)
    assert md.startswith("# Function-coverage dashboard")
    assert "| Coverage % |" in md
    # Any missing functions must show up in the rendered markdown.
    for names in report["missing"].values():
        for name in names:
            assert name in md
