"""Matplotlib chart backend: same model, same data, PNG/SVG output."""

import pytest

pytest.importorskip("matplotlib")

from abax.core.chartobj import CHART_KINDS, ChartError, ChartObject  # noqa: E402
from abax.core.workbook import Workbook  # noqa: E402
from abax.engine import chartmpl  # noqa: E402
from abax.engine.chartmpl import render_chart_mpl  # noqa: E402

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _numbers_sheet(wb, rows=8):
    s = wb.sheet
    s.set("A1", "alpha")
    s.set("B1", "beta")
    for i in range(2, rows + 2):
        s.set(f"A{i}", str(i * 2))
        s.set(f"B{i}", str(100 - i))
    return s


class TestMplBackend:
    @pytest.mark.parametrize("kind", [k for k in CHART_KINDS if k != "heatmap"])
    def test_every_kind_renders_png(self, kind):
        wb = Workbook()
        _numbers_sheet(wb)
        ch = ChartObject(id="c", kind=kind, source="A1:B9", title="T")
        out = render_chart_mpl(wb, wb.sheet.name, ch)
        assert isinstance(out, bytes) and out.startswith(PNG_MAGIC)

    def test_heatmap_renders_png(self):
        wb = Workbook()
        for r in range(3):
            for c in range(3):
                wb.sheet.set_cell(r, c, str(r * 3 + c + 1))
        ch = ChartObject(id="c", kind="heatmap", source="A1:C3")
        out = render_chart_mpl(wb, wb.sheet.name, ch)
        assert out.startswith(PNG_MAGIC)

    def test_svg_format(self):
        wb = Workbook()
        _numbers_sheet(wb)
        ch = ChartObject(id="c", kind="line", source="A1:B9")
        out = render_chart_mpl(wb, wb.sheet.name, ch, fmt="svg")
        assert isinstance(out, str) and "<svg" in out

    def test_bad_format_rejected(self):
        wb = Workbook()
        _numbers_sheet(wb)
        ch = ChartObject(id="c", kind="line", source="A1:B9")
        with pytest.raises(ValueError, match="fmt"):
            render_chart_mpl(wb, wb.sheet.name, ch, fmt="pdf")

    def test_model_errors_propagate(self):
        wb = Workbook()
        with pytest.raises(ChartError):
            render_chart_mpl(wb, wb.sheet.name,
                             ChartObject(id="c", kind="pie3d", source="A1"))

    def test_missing_matplotlib_raises_hint(self, monkeypatch):
        wb = Workbook()
        _numbers_sheet(wb)
        ch = ChartObject(id="c", kind="line", source="A1:B9")
        monkeypatch.setattr(chartmpl, "HAS_MATPLOTLIB", False)
        with pytest.raises(RuntimeError, match="abax\\[charts\\]"):
            render_chart_mpl(wb, wb.sheet.name, ch)

    def test_recalc_changes_output(self):
        wb = Workbook()
        s = wb.sheet
        s.set("A1", "1")
        s.set("A2", "=A1*10")
        ch = ChartObject(id="c", kind="bar", source="A1:A2")
        before = render_chart_mpl(wb, s.name, ch)
        s.set("A1", "9")
        after = render_chart_mpl(wb, s.name, ch)
        assert before != after
