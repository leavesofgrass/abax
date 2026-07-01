"""Console namespace builder (abax.core.console_ns) — bound to a workbook."""

from __future__ import annotations

from abax.core.console_ns import build_namespace
from abax.core.workbook import Workbook


def test_namespace_has_expected_keys():
    ns = build_namespace(Workbook())
    for k in ("doc", "wb", "sheet", "cell", "put", "refresh", "rpn",
              "matrix", "stats", "read_matrix", "sheet_to_df", "df_to_sheet"):
        assert k in ns


def test_put_and_cell_bound_to_workbook():
    wb = Workbook()
    ns = build_namespace(wb)
    ns["put"]("A1", "7")
    assert wb.sheet.get("A1") == 7
    assert ns["cell"]("A1") == 7


def test_refresh_callback_fires_on_write():
    calls = []
    ns = build_namespace(Workbook(), refresh=lambda: calls.append(1))
    ns["write_matrix"]("A1", [[1.0, 2.0]])
    assert calls
