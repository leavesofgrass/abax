"""AbaxShell completion / introspection — the brains behind do_complete /
do_inspect / do_is_complete, plus the block executor notebooks run through."""

from __future__ import annotations

from abax import kernel
from abax.core import completion

# --- Python-namespace completion on non-'=' source --------------------------
#
# The gotcha this whole feature exists for: abax's formula completer gates on a
# leading '=' (require_formula=True), so it returns nothing for plain Python. The
# shell must fall back to the console namespace + builtins for Python source.


def test_formula_completer_is_gated_off_for_python_source():
    # Baseline: the raw formula completer offers nothing without a leading '='.
    assert completion.complete("sheet", require_formula=True) == []


def test_python_completion_returns_namespace_matches():
    sh = kernel.AbaxShell()
    matches = sh.complete("she")["matches"]
    assert "sheet" in matches          # a build_namespace binding
    assert "sheet_to_df" in matches


def test_python_completion_includes_workbook_bindings():
    sh = kernel.AbaxShell()
    assert "wb" in sh.complete("w")["matches"]
    assert "cell" in sh.complete("cel")["matches"]


def test_python_completion_includes_builtins():
    sh = kernel.AbaxShell()
    assert "print" in sh.complete("prin")["matches"]


def test_python_completion_offers_formula_names_too():
    # Per spec, function_names() are folded into the Python namespace, so even a
    # non-'=' line surfaces them (this is exactly the gap a naive pass leaves).
    sh = kernel.AbaxShell()
    assert "SUM" in sh.complete("SUM")["matches"]


def test_python_completion_cursor_range_marks_the_token():
    sh = kernel.AbaxShell()
    res = sh.complete("x = fft", 7)
    assert "fft" in res["matches"]
    # cursor_start..cursor_end must bracket exactly the "fft" token
    assert res["cursor_start"] == 4
    assert res["cursor_end"] == 7


def test_attribute_completion_resolves_the_object():
    sh = kernel.AbaxShell()
    sh.run_cell_block("import math")
    res = sh.complete("math.sq")
    assert "sqrt" in res["matches"]
    # only the trailing partial ("sq") is replaced, the "math." prefix stays
    assert res["cursor_start"] == len("math.")
    assert res["cursor_end"] == len("math.sq")


def test_attribute_completion_on_unknown_object_is_empty():
    sh = kernel.AbaxShell()
    assert sh.complete("nope_xyz.wha")["matches"] == []


def test_empty_token_yields_no_matches():
    sh = kernel.AbaxShell()
    assert sh.complete("1 + ")["matches"] == []


# --- formula completion still works when the line starts with '=' -----------


def test_formula_completion_on_equals_line():
    sh = kernel.AbaxShell()
    matches = sh.complete("=SU")["matches"]
    assert "SUM" in matches and "SUMIF" in matches


def test_formula_completion_offers_defined_names():
    sh = kernel.AbaxShell()
    sh.workbook.names.define("Tax_Rate", "Sheet1!A1")
    assert "Tax_Rate" in sh.complete("=Tax")["matches"]


# --- inspection (do_inspect) ------------------------------------------------


def test_inspect_python_object_reports_doc():
    sh = kernel.AbaxShell()
    info = sh.inspect("print")
    assert info["found"] is True
    assert "print(" in info["text"]        # signature line


def test_inspect_formula_returns_signature():
    sh = kernel.AbaxShell()
    info = sh.inspect("=SUM")
    assert info["found"] is True
    assert "SUM(" in info["text"]


def test_inspect_unknown_is_not_found():
    sh = kernel.AbaxShell()
    assert sh.inspect("definitely_not_a_name_xyz")["found"] is False


# --- is_complete (do_is_complete) -------------------------------------------


def test_is_complete_statuses():
    sh = kernel.AbaxShell()
    assert sh.is_complete("x = 1")["status"] == "complete"
    assert sh.is_complete("if x:")["status"] == "incomplete"
    assert sh.is_complete("def f(:")["status"] == "invalid"


# --- run_cell_block: whole-cell (multi-statement) execution -----------------
#
# run_cell (single-statement, console) can't run a block; run_cell_block can, and
# echoes a trailing expression the way Jupyter does.


def test_block_runs_multiple_statements_and_echoes_last_expr():
    sh = kernel.AbaxShell()
    r = sh.run_cell_block("a = 20\nb = 22\na + b")
    assert r["error"] is None
    assert r["data"] == {"text/plain": "42"}


def test_block_trailing_statement_has_no_result():
    sh = kernel.AbaxShell()
    r = sh.run_cell_block("a = 1\nb = 2")
    assert r["data"] is None
    assert r["error"] is None


def test_block_captures_stdout():
    sh = kernel.AbaxShell()
    r = sh.run_cell_block("for i in range(3):\n    print(i)")
    assert r["stdout"] == "0\n1\n2\n"


def test_block_reports_runtime_error_in_error_field():
    sh = kernel.AbaxShell()
    r = sh.run_cell_block("x = 1\n1 / 0")
    assert r["data"] is None
    assert "ZeroDivisionError" in (r["error"] or "")


def test_block_reports_syntax_error():
    sh = kernel.AbaxShell()
    r = sh.run_cell_block("def broken(:\n    pass")
    assert "SyntaxError" in (r["error"] or "")


def test_block_state_persists_across_cells():
    sh = kernel.AbaxShell()
    sh.run_cell_block("acc = 10")
    r = sh.run_cell_block("acc += 5\nacc")
    assert r["data"] == {"text/plain": "15"}
