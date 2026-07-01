"""Markdown, Jupyter notebook, R, and generic-JSON exchange I/O."""

from __future__ import annotations

import json

from abax.core import Sheet
from abax.core.io.exchange_io import workbook_from_json
from abax.core.io.markdown_io import from_markdown, to_markdown
from abax.core.io.notebook_io import from_notebook, to_notebook
from abax.core.io.r_io import from_r, to_r
from abax.core.workbook import Workbook


def _grid(rows, name="Sheet1"):
    s = Sheet(name)
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            if v != "":
                s.set(f"{chr(ord('A') + c)}{r + 1}", str(v))
    return s


# --- markdown --------------------------------------------------------------


def test_markdown_export_is_gfm():
    s = _grid([["name", "qty"], ["apple", 3], ["pear", 5]])
    md = to_markdown(s)
    lines = md.strip().splitlines()
    assert lines[0].startswith("| name")
    assert set(lines[1]) <= set("| -:")  # separator row
    assert "apple" in lines[2]


def test_markdown_roundtrip():
    s = _grid([["a", "b"], ["1", "2"], ["3", "4"]])
    md = to_markdown(s)
    s2 = from_markdown(md)
    assert s2.get("A1") == "a"
    assert s2.get("B3") == 4


def test_markdown_escapes_pipes():
    s = _grid([["a|b"], ["c"]])
    md = to_markdown(s)
    assert "\\|" in md
    s2 = from_markdown(md)
    assert s2.get("A1") == "a|b"


def test_markdown_computes_formula_values():
    s = Sheet()
    s.set("A1", "x")
    s.set("A2", "=1+2")
    md = to_markdown(s)
    assert "| 3 " in md or "| 3 |" in md or "3" in md.splitlines()[2]


# --- notebook --------------------------------------------------------------


def test_notebook_export_structure():
    wb = Workbook()
    wb.sheet.set("A1", "n")
    wb.sheet.set("A2", "5")
    nb = to_notebook(wb)
    assert nb["nbformat"] == 4
    kinds = [c["cell_type"] for c in nb["cells"]]
    assert "markdown" in kinds and "code" in kinds
    code = "".join(c2 for c in nb["cells"] if c["cell_type"] == "code" for c2 in c["source"])
    assert "pd.DataFrame" in code
    # nbformat 4.5 requires a unique id per cell (else nbformat.validate rejects it)
    ids = [c["id"] for c in nb["cells"]]
    assert all(ids) and len(set(ids)) == len(ids)


def test_notebook_roundtrip_via_tables():
    wb = Workbook()
    wb.sheet.set("A1", "name")
    wb.sheet.set("B1", "qty")
    wb.sheet.set("A2", "apple")
    wb.sheet.set("B2", "3")
    nb = to_notebook(wb)
    wb2 = from_notebook(nb)
    assert wb2.sheet.get("A1") == "name"
    assert wb2.sheet.get("B2") == 3
    assert wb2.sheets[0].name == wb.sheets[0].name  # named from heading


def test_notebook_lossless_roundtrip_preserves_formulas_and_sheets():
    wb = Workbook()
    wb.sheet.name = "Data"
    wb.sheet.set("A2", "10")
    wb.sheet.set("A3", "=A2*1.1")
    wb.add_sheet("Notes").set("A1", "hi")
    nb = to_notebook(wb)
    assert "workbook" in nb["metadata"]["abax"]          # envelope embedded
    wb2 = from_notebook(nb)
    assert [s.name for s in wb2.sheets] == ["Data", "Notes"]
    assert wb2.sheet.get_raw(2, 0) == "=A2*1.1"           # formula preserved, not its value
    assert wb2.sheet.get("A3") == 11.0


def test_notebook_foreign_falls_back_to_table_scan():
    foreign = {
        "cells": [{"cell_type": "markdown", "metadata": {},
                   "source": ["## T\n", "\n", "| a | b |\n", "|---|---|\n", "| 1 | 2 |\n"]}],
        "metadata": {}, "nbformat": 4, "nbformat_minor": 5,
    }
    wb = from_notebook(foreign)
    assert [s.name for s in wb.sheets] == ["T"]


# --- R ---------------------------------------------------------------------


def test_r_export_data_frame():
    s = _grid([["x", "y"], ["1", "a"], ["2", "b"]])
    wb = Workbook.__new__(Workbook)
    wb.sheets = [s]
    wb.active = 0
    src = to_r(wb)
    assert "data.frame(" in src
    assert "x = c(1, 2)" in src
    assert 'y = c("a", "b")' in src


def test_r_roundtrip():
    src = (
        'mydata <- data.frame(\n'
        '  id = c(1, 2, 3),\n'
        '  label = c("a", "b", "c"),\n'
        '  stringsAsFactors = FALSE\n'
        ')\n'
    )
    wb = from_r(src)
    s = wb.sheets[0]
    assert s.get("A1") == "id"
    assert s.get("B1") == "label"
    assert s.get("A4") == 3
    assert s.get("B2") == "a"


def test_r_bare_vector():
    wb = from_r("scores <- c(10, 20, 30)\n")
    s = wb.get_sheet("scores")
    assert s is not None
    assert s.get("A1") == "scores"
    assert s.get("A2") == 10


# --- exchange (generic JSON) ----------------------------------------------


def test_exchange_records_list():
    obj = [{"name": "a", "qty": 1}, {"name": "b", "qty": 2}]
    wb = workbook_from_json(obj)
    s = wb.sheet
    assert s.get("A1") == "name"
    assert s.get("B1") == "qty"
    assert s.get("A3") == "b"
    assert s.get("B3") == 2


def test_exchange_envelope_dict_of_columns():
    obj = {"app": "someapp", "schema_version": 1, "data": {"x": [1, 2], "y": [3, 4]}}
    wb = workbook_from_json(obj)
    assert wb.sheet.get("A1") == "x"
    assert wb.sheet.get("B3") == 4


def test_exchange_qrpn_stack_and_registers():
    obj = {
        "app": "qrpn-voyager",
        "schema_version": 1,
        "data": {"stack": [1, 2, 3], "registers": {"A": 10, "B": 20}},
    }
    wb = workbook_from_json(obj)
    stack = wb.get_sheet("stack")
    regs = wb.get_sheet("registers")
    assert stack.get("A2") == 1
    assert regs.get("A2") == "A"
    assert regs.get("B2") == 10


def test_exchange_loads_native_workbook():
    wb = Workbook()
    wb.sheet.set("A1", "5")
    wb.sheet.set("B1", "=A1*2")
    env = wb.to_envelope()
    wb2 = workbook_from_json(json.loads(json.dumps(env)))
    assert wb2.sheet.get("B1") == 10
