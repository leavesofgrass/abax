"""Macro engine: loading, command macros, and UDFs callable from formulas."""

from __future__ import annotations

import pytest

from abax.core import Sheet
from abax.core.workbook import Workbook
from abax.engine.document import Document
from abax.macros import (
    MacroError,
    discover_macros,
    install_functions,
    load_macro_file,
    run_macro,
)

MACRO_SRC = '''
@macro("fill")
def fill(ctx):
    ctx.set("A1", "10")
    ctx.set("A2", "=A1*2")
    ctx.recalc()
    ctx.log("filled A1:A2")

@macro
def clear_a1(ctx):
    ctx.set("A1", "")

@register_function("DOUBLE")
def double(args):
    return numbers([args[0]])[0] * 2

@register_function("SHOUT")
def shout(args):
    return text(args[0]).upper() + "!"
'''


@pytest.fixture
def macro_file(tmp_path):
    p = tmp_path / "m.py"
    p.write_text(MACRO_SRC)
    return p


def test_load_registers_macros_and_functions(macro_file):
    reg = load_macro_file(macro_file)
    assert "fill" in reg.macros
    assert "clear_a1" in reg.macros  # bare @macro uses function name
    assert "DOUBLE" in reg.functions
    assert "SHOUT" in reg.functions


def test_run_command_macro_mutates_workbook(macro_file):
    reg = load_macro_file(macro_file)
    wb = Workbook()
    ctx = run_macro(reg, "fill", wb)
    assert wb.sheet.get("A1") == 10
    assert wb.sheet.get("A2") == 20
    assert ctx.messages == ["filled A1:A2"]


def test_run_unknown_macro_raises(macro_file):
    reg = load_macro_file(macro_file)
    with pytest.raises(MacroError):
        run_macro(reg, "nope", Workbook())


def test_udf_callable_in_formula(macro_file):
    reg = load_macro_file(macro_file)
    install_functions(reg)
    s = Sheet()
    s.set("A1", "21")
    s.set("B1", "=DOUBLE(A1)")
    s.set("B2", '=SHOUT("hi")')
    assert s.get("B1") == 42
    assert s.get("B2") == "HI!"


def test_discover_from_directory(tmp_path):
    (tmp_path / "a.py").write_text('@macro\ndef one(ctx):\n    ctx.set("A1","1")\n')
    (tmp_path / "b.py").write_text('@macro\ndef two(ctx):\n    ctx.set("A1","2")\n')
    reg = discover_macros([tmp_path])
    assert {"one", "two"} <= set(reg.macros)


def test_bad_macro_file_does_not_break_discovery(tmp_path):
    (tmp_path / "ok.py").write_text('@macro\ndef good(ctx):\n    pass\n')
    (tmp_path / "bad.py").write_text("this is ( not python")
    reg = discover_macros([tmp_path])  # must not raise
    assert "good" in reg.macros


def test_shipped_sample_macro_runs(tmp_path):
    # The repo's example macro should load and its 'totals' macro should work.
    from pathlib import Path

    sample = Path(__file__).resolve().parent.parent / "macros" / "sample.py"
    reg = load_macro_file(sample)
    install_functions(reg)

    doc = Document()
    doc.workbook.sheet.set("A1", "1")
    doc.workbook.sheet.set("A2", "2")
    doc.workbook.sheet.set("A3", "3")
    run_macro(reg, "totals", doc.workbook)
    assert doc.workbook.sheet.get("A4") == 6  # SUM(A1:A3)

    s = Sheet()
    s.set("A1", "100")
    s.set("B1", "=TAXED(A1, 0.1)")
    assert s.get("B1") == pytest.approx(110)
