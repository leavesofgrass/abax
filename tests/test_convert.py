"""File-conversion facade (abax.engine.convert): tabular via the engine, docs
via pandoc."""

from __future__ import annotations

import os

import pytest

from abax.engine import convert


def _csv(tmp_path, name="data.csv", text="a,b\n1,2\n3,4\n"):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


def test_tabular_csv_to_json(tmp_path):
    src = _csv(tmp_path)
    kind = convert.convert_file(src, str(tmp_path / "out.json"))
    assert kind == "tabular"
    assert (tmp_path / "out.json").exists()


def test_tabular_csv_to_markdown_table(tmp_path):
    src = _csv(tmp_path)
    convert.convert_file(src, str(tmp_path / "out.md"))
    text = (tmp_path / "out.md").read_text()
    assert "| a" in text and "| b" in text     # a Markdown table, not prose


def test_batch_reports_each_file(tmp_path):
    good = _csv(tmp_path, "good.csv")
    missing = str(tmp_path / "nope.csv")
    results = convert.batch_convert([good, missing], str(tmp_path), ".json")
    assert len(results) == 2
    by_src = {os.path.basename(s): (d, e) for s, d, e in results}
    assert by_src["good.csv"][1] is None            # converted
    assert by_src["nope.csv"][0] is None             # failed
    assert "no such file" in by_src["nope.csv"][1]


def test_same_source_and_dest_errors(tmp_path):
    src = _csv(tmp_path, "x.csv")
    with pytest.raises(convert.ConvertError):
        convert.convert_file(src, src)


def test_document_conversion_routes_to_pandoc(tmp_path):
    """A document target uses pandoc — run it if present, else assert a clear error."""
    md = tmp_path / "doc.md"
    md.write_text("# Title\n\nHello **world**.\n")
    dst = str(tmp_path / "doc.html")
    if convert.pandoc_available():
        assert convert.convert_file(str(md), dst) == "document"
        assert os.path.exists(dst)
        assert "world" in open(dst, encoding="utf-8").read()
    else:
        with pytest.raises(convert.ConvertError) as ei:
            convert.convert_file(str(md), dst)
        assert "pandoc" in str(ei.value).lower()
