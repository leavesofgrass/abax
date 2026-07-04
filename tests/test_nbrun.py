"""Headless notebook execution (engine/nbrun): run an .ipynb without nbclient.

Round-trips a tiny in-memory notebook through :func:`abax.engine.nbrun.run_notebook`
and checks the outputs it writes back. Every test runs twice — once on the
nbformat path and once with the stdlib json cold path forced — so both branches
are covered even though nbformat happens to be installed here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from abax.engine import nbrun


@pytest.fixture(params=["nbformat", "stdlib"])
def path_backend(request, monkeypatch):
    """Exercise both the nbformat path and the forced-stdlib cold path."""
    if request.param == "stdlib":
        monkeypatch.setattr(nbrun, "HAS_NBFORMAT", False)
    return request.param


def _notebook(cells: list[dict]) -> dict:
    for i, cell in enumerate(cells):
        cell.setdefault("id", f"c{i}")
        cell.setdefault("metadata", {})
        if cell["cell_type"] == "code":
            cell.setdefault("outputs", [])
            cell.setdefault("execution_count", None)
    return {"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}


def _code(source: str) -> dict:
    return {"cell_type": "code", "source": source}


def _md(source: str) -> dict:
    return {"cell_type": "markdown", "source": source}


def _write_in(tmp_path: Path, nb: dict) -> Path:
    p = tmp_path / "in.ipynb"
    p.write_text(json.dumps(nb), encoding="utf-8")
    return p


def _code_cells(nb: dict) -> list[dict]:
    return [c for c in nb["cells"] if c["cell_type"] == "code"]


def _text(value) -> str:
    """A mime value read back from disk may be split into a list of lines by
    nbformat's writer; join it so assertions don't care which form it took."""
    return "".join(value) if isinstance(value, list) else value


def test_expression_becomes_execute_result(path_backend, tmp_path):
    nb = _notebook([_code("21 * 2")])
    p_in = _write_in(tmp_path, nb)
    summary = nbrun.run_notebook(p_in, tmp_path / "out.ipynb")
    out = _code_cells(summary["notebook"])[0]["outputs"]
    assert len(out) == 1
    assert out[0]["output_type"] == "execute_result"
    assert out[0]["data"] == {"text/plain": "42"}
    assert out[0]["execution_count"] == 1


def test_print_becomes_stream(path_backend, tmp_path):
    nb = _notebook([_code("print('hello')")])
    p_in = _write_in(tmp_path, nb)
    summary = nbrun.run_notebook(p_in, tmp_path / "out.ipynb")
    out = _code_cells(summary["notebook"])[0]["outputs"]
    assert out[0]["output_type"] == "stream"
    assert out[0]["name"] == "stdout"
    assert out[0]["text"] == "hello\n"


def test_error_becomes_error_output(path_backend, tmp_path):
    nb = _notebook([_code("1 / 0")])
    p_in = _write_in(tmp_path, nb)
    summary = nbrun.run_notebook(p_in, tmp_path / "out.ipynb")
    out = _code_cells(summary["notebook"])[0]["outputs"]
    assert out[0]["output_type"] == "error"
    assert out[0]["ename"] == "ZeroDivisionError"
    assert "division by zero" in out[0]["evalue"]
    assert isinstance(out[0]["traceback"], list) and out[0]["traceback"]
    assert summary["errors"] == 1
    assert summary["error_cells"] == [0]


def test_state_persists_across_cells(path_backend, tmp_path):
    nb = _notebook([_code("total = 40"), _code("total + 2")])
    p_in = _write_in(tmp_path, nb)
    summary = nbrun.run_notebook(p_in, tmp_path / "out.ipynb")
    cells = _code_cells(summary["notebook"])
    assert cells[0]["outputs"] == []              # a bare assignment shows nothing
    assert cells[1]["outputs"][0]["data"] == {"text/plain": "42"}
    assert summary["cells"] == 2 and summary["errors"] == 0


def test_abax_bindings_are_available(path_backend, tmp_path):
    # The shared shell binds wb/sheet/etc.; writing a cell must be observable in
    # a later cell's rich output.
    nb = _notebook([_code("wb.sheet.set_cell(0, 0, 'hdr')"), _code("sheet()")])
    p_in = _write_in(tmp_path, nb)
    summary = nbrun.run_notebook(p_in, tmp_path / "out.ipynb")
    data = _code_cells(summary["notebook"])[1]["outputs"][0]["data"]
    assert "text/html" in data and "text/markdown" in data      # rich Sheet repr
    assert "hdr" in data["text/markdown"]                        # the written cell


def test_markdown_cells_are_left_untouched(path_backend, tmp_path):
    nb = _notebook([_md("# Heading"), _code("1 + 1")])
    p_in = _write_in(tmp_path, nb)
    summary = nbrun.run_notebook(p_in, tmp_path / "out.ipynb")
    md = summary["notebook"]["cells"][0]
    assert md["cell_type"] == "markdown"
    assert "outputs" not in md                    # markdown cells gain no outputs
    assert summary["cells"] == 1                   # only the code cell ran


def test_source_as_list_of_lines(path_backend, tmp_path):
    # nbformat stores source as a list of lines; run_notebook must join them.
    nb = _notebook([{"cell_type": "code", "source": ["a = 20\n", "a + 22"]}])
    p_in = _write_in(tmp_path, nb)
    summary = nbrun.run_notebook(p_in, tmp_path / "out.ipynb")
    out = _code_cells(summary["notebook"])[0]["outputs"]
    assert out[0]["data"] == {"text/plain": "42"}


def test_output_file_is_written_and_valid(path_backend, tmp_path):
    nb = _notebook([_code("6 * 7")])
    p_in = _write_in(tmp_path, nb)
    p_out = tmp_path / "out.ipynb"
    nbrun.run_notebook(p_in, p_out)
    assert p_out.exists()
    written = json.loads(p_out.read_text(encoding="utf-8"))
    # The re-read notebook carries the executed result. (nbformat's writer may
    # store a mime string as a list of lines, hence _text.)
    code = [c for c in written["cells"] if c["cell_type"] == "code"][0]
    assert _text(code["outputs"][0]["data"]["text/plain"]) == "42"
    # And it validates (structural checks; nbformat schema when present).
    from abax.engine.nbvalidate import validate_notebook
    assert validate_notebook(written) == []


def test_path_out_none_writes_nothing(path_backend, tmp_path):
    nb = _notebook([_code("1 + 1")])
    p_in = _write_in(tmp_path, nb)
    summary = nbrun.run_notebook(p_in, None)
    assert summary["path_out"] is None
    assert list(tmp_path.iterdir()) == [p_in]      # no output file created
    # The executed notebook still rides back in the summary.
    assert _code_cells(summary["notebook"])[0]["outputs"][0]["data"] == {"text/plain": "2"}


def test_run_in_place(path_backend, tmp_path):
    nb = _notebook([_code("2 ** 5")])
    p_in = _write_in(tmp_path, nb)
    nbrun.run_notebook(p_in, p_in)                 # same path in and out
    written = json.loads(p_in.read_text(encoding="utf-8"))
    code = [c for c in written["cells"] if c["cell_type"] == "code"][0]
    assert _text(code["outputs"][0]["data"]["text/plain"]) == "32"


def test_summary_reports_backend(path_backend, tmp_path):
    nb = _notebook([_code("1")])
    p_in = _write_in(tmp_path, nb)
    summary = nbrun.run_notebook(p_in, None)
    assert summary["nbformat"] is (path_backend == "nbformat")
    assert summary["path_in"] == str(p_in)


def test_empty_notebook_is_a_noop(path_backend, tmp_path):
    nb = _notebook([])
    p_in = _write_in(tmp_path, nb)
    summary = nbrun.run_notebook(p_in, tmp_path / "out.ipynb")
    assert summary["cells"] == 0 and summary["errors"] == 0
