"""abax Jupyter kernel: the testable brain (AbaxShell) and the kernelspec."""

from __future__ import annotations

import json

import pytest

from abax import kernel


def test_shell_expression_returns_mime_bundle():
    sh = kernel.AbaxShell()
    r = sh.run_cell("1 + 1")
    assert r["data"] == {"text/plain": "2"}
    assert r["execution_count"] == 1
    assert r["error"] is None


def test_shell_statement_has_no_display():
    sh = kernel.AbaxShell()
    assert sh.run_cell("x = 5")["data"] is None
    # state persists across cells
    assert sh.run_cell("x + 1")["data"] == {"text/plain": "6"}
    assert sh.execution_count == 2


def test_shell_captures_stdout():
    sh = kernel.AbaxShell()
    r = sh.run_cell("print('hello')")
    assert r["stdout"] == "hello\n"
    assert r["data"] is None


def test_shell_renders_sheet_richly():
    sh = kernel.AbaxShell()
    sh.workbook.sheet.set_cell(0, 0, "hdr")
    data = sh.run_cell("sheet()")["data"]
    assert "text/html" in data and "text/markdown" in data   # rich in Jupyter


def test_shell_survives_errors():
    sh = kernel.AbaxShell()
    r = sh.run_cell("1 / 0")
    blob = (r["stdout"] or "") + (r["error"] or "")
    assert "ZeroDivisionError" in blob
    # the shell keeps working afterwards
    assert sh.run_cell("2 + 2")["data"] == {"text/plain": "4"}


def test_install_kernelspec_writes_valid_json(tmp_path):
    target = kernel.install_kernelspec(prefix=str(tmp_path))
    spec_file = target / "kernel.json"
    assert spec_file.exists()
    spec = json.loads(spec_file.read_text(encoding="utf-8"))
    assert spec["language"] == "python"
    assert spec["display_name"] == "abax"
    assert spec["argv"][1:3] == ["-m", "abax.kernel"]
    assert "{connection_file}" in spec["argv"]


def test_main_without_ipykernel_errors_clearly():
    try:
        import ipykernel  # noqa: F401
    except ImportError:
        with pytest.raises(SystemExit) as exc:
            kernel.main()
        assert "ipykernel" in str(exc.value)
    else:
        pytest.skip("ipykernel is installed; cannot test the missing-dep path")
