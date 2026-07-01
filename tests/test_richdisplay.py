"""IPython rich-display protocol + Sheet Markdown + console displayhook."""

from __future__ import annotations

from abax.core import richdisplay as RD
from abax.core.sheet import Sheet


class _Rich:
    def _repr_html_(self):
        return "<b>hi</b>"

    def _repr_markdown_(self):
        return "**hi**"

    def __repr__(self):
        return "Rich()"


class _Bundle:
    def _repr_mimebundle_(self):
        return {"text/html": "<i>x</i>", "application/json": "{}"}


class _Broken:
    def __repr__(self):
        raise RuntimeError("boom")


def test_mime_bundle_collects_all_formats():
    b = RD.mime_bundle(_Rich())
    assert b["text/html"] == "<b>hi</b>"
    assert b["text/markdown"] == "**hi**"
    assert b["text/plain"] == "Rich()"


def test_mime_bundle_honors_combined_hook():
    b = RD.mime_bundle(_Bundle())
    assert b["text/html"] == "<i>x</i>"
    assert b["application/json"] == "{}"
    assert "text/plain" in b                      # always present


def test_best_text_prefers_markdown_then_repr():
    assert RD.best_text(_Rich()) == "**hi**"
    assert RD.best_text(123) == "123"
    assert RD.best_text("abc") == "'abc'"


def test_broken_repr_does_not_raise():
    assert "unreprable" in RD.best_text(_Broken())


def test_sheet_markdown_table():
    s = Sheet()
    s.set_cell(0, 0, "name")
    s.set_cell(0, 1, "val")
    s.set_cell(1, 0, "x")
    s.set_cell(1, 1, "42")
    md = s._repr_markdown_()
    assert md.startswith("**")
    assert "| | A | B |" in md
    assert "| **1** | name | val |" in md
    assert RD.best_text(s) == md                  # console picks the Markdown


def test_sheet_markdown_bounds_and_empty():
    assert "empty" in Sheet()._repr_markdown_()
    big = Sheet()
    for r in range(40):
        big.set_cell(r, 0, str(r))
    md = big._repr_markdown_()
    assert "more rows" in md                       # truncated past 20 rows


def test_console_worker_renders_rich_result():
    from abax.console_worker import Worker
    from abax.core.workbook import Workbook

    s = Sheet()
    s.set_cell(0, 0, "hdr")
    wb = Workbook.from_sheets([s]) if hasattr(Workbook, "from_sheets") else Workbook()
    w = Worker()
    env = wb.to_envelope()
    assert "| | A |" in w.handle("sheet()", env)["output"]   # rich table echoed
    assert w.handle("2 + 2", env)["output"].strip() == "4"   # plain repr
    assert w.handle("y = 7", env)["output"] == ""            # statement: no echo
