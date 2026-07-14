"""Embedded chart objects: model, envelope schema v3, rendering, remapping."""

import json

import pytest

from abax.core.chartobj import (
    CHART_KINDS,
    ChartError,
    ChartObject,
    new_chart_id,
    render_chart,
)
from abax.core.workbook import SCHEMA_VERSION, Workbook


def _numbers_sheet(wb, rows=8):
    """Two numeric columns with headers, plus a text label column in C."""
    s = wb.sheet
    s.set("A1", "alpha")
    s.set("B1", "beta")
    for i in range(2, rows + 2):
        s.set(f"A{i}", str(i * 2))
        s.set(f"B{i}", str(100 - i))
        s.set(f"C{i}", f"row{i}")
    return s


# --- model & persistence ----------------------------------------------------

class TestModelAndEnvelope:
    def test_round_trip_through_envelope(self, tmp_path):
        wb = Workbook()
        _numbers_sheet(wb)
        wb.sheet.charts.append(ChartObject(
            id="chart1", kind="line", source="A1:B9", title="Trend",
            anchor=(2, 4), width=500, height=300))
        wb.sheet.charts.append(ChartObject(
            id="chart2", kind="histogram", source="A2:A9",
            options={"bins": 4}))
        path = tmp_path / "book.abax"
        wb.save_json(path)

        env = json.loads(path.read_text())
        assert env["schema_version"] == SCHEMA_VERSION == 3
        wb2 = Workbook.load_json(path)
        assert [ch.to_dict() for ch in wb2.sheet.charts] == \
               [ch.to_dict() for ch in wb.sheet.charts]
        assert wb2.sheet.charts[0].anchor == (2, 4)
        assert wb2.sheet.charts[1].options == {"bins": 4}

    def test_charts_key_omitted_when_empty(self, tmp_path):
        wb = Workbook()
        wb.sheet.set("A1", "1")
        env = wb.to_envelope()
        assert "charts" not in env["data"]["sheets"][0]

    def test_v2_file_loads_with_no_charts(self):
        env = {"app": "abax", "schema_version": 2,
               "data": {"active": 0, "names": {},
                        "sheets": [{"name": "S", "cells": {"A1": "5"}}]}}
        wb = Workbook.from_envelope(env)
        assert wb.sheet.charts == []
        assert wb.sheet.get_value(0, 0) == 5

    def test_new_chart_id_picks_smallest_free(self):
        charts = [ChartObject(id="chart1", kind="bar", source="A1"),
                  ChartObject(id="chart3", kind="bar", source="A1")]
        assert new_chart_id(charts) == "chart2"
        assert new_chart_id([]) == "chart1"


# --- rendering ----------------------------------------------------------------

class TestRendering:
    @pytest.mark.parametrize("kind", [k for k in CHART_KINDS
                                      if k not in ("heatmap", "scatter")])
    def test_column_kinds_render_svg(self, kind):
        wb = Workbook()
        _numbers_sheet(wb)
        ch = ChartObject(id="c", kind=kind, source="A1:B9", title="T-" + kind)
        svg = render_chart(wb, wb.sheet.name, ch)
        assert svg.lstrip().startswith("<svg")
        assert "T-" + kind in svg

    def test_scatter_renders_pairs(self):
        wb = Workbook()
        _numbers_sheet(wb)
        svg = render_chart(wb, wb.sheet.name,
                           ChartObject(id="c", kind="scatter", source="A1:B9"))
        assert svg.lstrip().startswith("<svg") and "circle" in svg

    def test_heatmap_renders_matrix(self):
        wb = Workbook()
        s = wb.sheet
        for r in range(3):
            for c in range(3):
                s.set_cell(r, c, str(r * 3 + c + 1))
        svg = render_chart(wb, s.name,
                           ChartObject(id="c", kind="heatmap", source="A1:C3"))
        assert svg.lstrip().startswith("<svg")

    def test_line_series_named_from_header(self):
        wb = Workbook()
        _numbers_sheet(wb)
        svg = render_chart(wb, wb.sheet.name,
                           ChartObject(id="c", kind="line", source="A1:B9"))
        assert "alpha" in svg and "beta" in svg

    def test_bar_categories_from_text_first_column(self):
        wb = Workbook()
        s = wb.sheet
        for i, (label, v) in enumerate([("ants", "3"), ("bees", "7"),
                                        ("cats", "5")], start=1):
            s.set(f"A{i}", label)
            s.set(f"B{i}", v)
        svg = render_chart(wb, s.name,
                           ChartObject(id="c", kind="bar", source="A1:B3"))
        assert "ants" in svg and "cats" in svg

    def test_sheet_qualified_source(self):
        wb = Workbook()
        data = wb.add_sheet("Data")
        for i in range(1, 6):
            data.set(f"A{i}", str(i))
        svg = render_chart(wb, wb.sheet.name,
                           ChartObject(id="c", kind="histogram",
                                       source="Data!A1:A5"))
        assert svg.lstrip().startswith("<svg")

    def test_render_reflects_recalc(self):
        wb = Workbook()
        s = wb.sheet
        s.set("A1", "1")
        s.set("A2", "=A1*10")
        ch = ChartObject(id="c", kind="bar", source="A1:A2")
        before = render_chart(wb, s.name, ch)
        s.set("A1", "7")                     # =A1*10 now recomputes to 70
        after = render_chart(wb, s.name, ch)
        assert before != after

    def test_non_numeric_cells_are_skipped(self):
        wb = Workbook()
        s = wb.sheet
        for i, v in enumerate(["1", "oops", "3", "", "5"], start=1):
            s.set(f"A{i}", v)
        svg = render_chart(wb, s.name,
                           ChartObject(id="c", kind="box", source="A1:A5"))
        assert svg.lstrip().startswith("<svg")

    def test_unknown_kind_raises(self):
        wb = Workbook()
        with pytest.raises(ChartError, match="unknown chart kind"):
            render_chart(wb, wb.sheet.name,
                         ChartObject(id="c", kind="pie3d", source="A1"))

    def test_missing_sheet_raises(self):
        wb = Workbook()
        with pytest.raises(ChartError, match="does not exist"):
            render_chart(wb, wb.sheet.name,
                         ChartObject(id="c", kind="bar", source="Nope!A1:A3"))

    def test_blank_source_raises(self):
        wb = Workbook()
        with pytest.raises(ChartError, match="no source range"):
            render_chart(wb, wb.sheet.name,
                         ChartObject(id="c", kind="bar", source=""))

    def test_empty_data_still_renders_frame(self):
        wb = Workbook()
        svg = render_chart(wb, wb.sheet.name,
                           ChartObject(id="c", kind="line", source="A1:B3"))
        assert svg.lstrip().startswith("<svg")


# --- structural edits ---------------------------------------------------------

class TestStructuralEdits:
    def test_insert_rows_shifts_anchor_and_source(self):
        wb = Workbook()
        _numbers_sheet(wb)
        ch = ChartObject(id="c", kind="line", source="A1:B9", anchor=(4, 1))
        wb.sheet.charts.append(ch)
        wb.sheet.insert_rows(0, 2)
        assert ch.anchor == (6, 1)
        assert ch.source == "A3:B11"

    def test_delete_cols_shifts_source(self):
        wb = Workbook()
        _numbers_sheet(wb)
        ch = ChartObject(id="c", kind="line", source="B1:B9", anchor=(0, 5))
        wb.sheet.charts.append(ch)
        wb.sheet.delete_cols(0, 1)          # col A goes away
        assert ch.source == "A1:A9"
        assert ch.anchor == (0, 4)

    def test_source_wholly_deleted_blanks_out(self):
        wb = Workbook()
        _numbers_sheet(wb)
        ch = ChartObject(id="c", kind="line", source="B1:B9", anchor=(0, 0))
        wb.sheet.charts.append(ch)
        wb.sheet.delete_cols(1, 1)          # the whole source column
        assert ch.source == ""
        with pytest.raises(ChartError):
            render_chart(wb, wb.sheet.name, ch)

    def test_anchor_row_deleted_clamps_chart_survives(self):
        wb = Workbook()
        _numbers_sheet(wb)
        ch = ChartObject(id="c", kind="line", source="A1:B9", anchor=(3, 0))
        wb.sheet.charts.append(ch)
        wb.sheet.delete_rows(3, 1)
        assert ch in wb.sheet.charts
        assert ch.anchor == (3, 0)          # clamped to the edit point

    def test_cross_sheet_source_tracks_other_sheets_edit(self):
        wb = Workbook()
        data = wb.add_sheet("Data")
        for i in range(1, 6):
            data.set(f"A{i}", str(i))
        ch = ChartObject(id="c", kind="histogram", source="Data!A1:A5")
        wb.sheet.charts.append(ch)
        data.insert_rows(0, 3)
        assert ch.source == "Data!A4:A8"
        # And an edit on the chart's HOST sheet leaves the foreign ref alone.
        wb.sheet.insert_rows(0, 5)
        assert ch.source == "Data!A4:A8"
