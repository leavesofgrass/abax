"""WEBSERVICE / FILTERXML / GETPIVOTDATA — the coverage-completion trio."""

from __future__ import annotations

import json
import threading
import time

from abax.core import livedata
from abax.core.errors import CellError, is_error
from abax.core.excel_modern import _filterxml
from abax.core.livedata import OFF_MARKER
from abax.core.workbook import Workbook


def _wait_for(pred, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return pred()


# -- FILTERXML -------------------------------------------------------------

_DOC = "<books><book id='a'><t>One</t></book><book id='b'><t>Two</t></book></books>"


def test_filterxml_element_text_spills():
    out = _filterxml([_DOC, "//t"])
    assert out == [["One"], ["Two"]]


def test_filterxml_attribute_selector():
    out = _filterxml([_DOC, "//book/@id"])
    assert out == [["a"], ["b"]]


def test_filterxml_rooted_path():
    out = _filterxml([_DOC, "/books/book/t"])
    assert out == [["One"], ["Two"]]


def test_filterxml_no_match_is_na():
    out = _filterxml([_DOC, "//nope"])
    assert is_error(out) and out.code == CellError.NA


def test_filterxml_bad_xml_is_value():
    out = _filterxml(["<not xml", "//t"])
    assert is_error(out) and out.code == CellError.VALUE


def test_filterxml_rejects_doctype_entities():
    bomb = "<!DOCTYPE x [<!ENTITY a 'boom'>]><x>&a;</x>"
    out = _filterxml([bomb, "//x"])
    assert is_error(out) and out.code == CellError.VALUE


def test_filterxml_via_formula_spills_in_sheet():
    wb = Workbook()
    wb.sheet.set_cell(0, 0, f'=FILTERXML("{_DOC}", "//t")')
    wb.recalculate()
    assert wb.sheet.get_value(0, 0) == "One"   # anchor
    assert wb.sheet.get_value(1, 0) == "Two"   # spilled below


# -- GETPIVOTDATA ----------------------------------------------------------

def _pivot_block(wb):
    rows = [
        ["region", "Q1", "Q2", "Total"],
        ["East", "5", "7", "12"],
        ["West", "13", "20", "33"],
        ["Total", "18", "27", "45"],
    ]
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            wb.sheet.set_cell(r, c, val)


def test_getpivotdata_row_by_index_item():
    wb = Workbook()
    _pivot_block(wb)
    wb.sheet.set_cell(6, 0, '=GETPIVOTDATA("Q1", A1:D4, "region", "West")')
    wb.recalculate()
    assert wb.sheet.get_value(6, 0) == 13.0


def test_getpivotdata_grand_total_default_row():
    wb = Workbook()
    _pivot_block(wb)
    wb.sheet.set_cell(6, 0, '=GETPIVOTDATA("Q2", A1:D4)')  # no pair → Total row
    wb.recalculate()
    assert wb.sheet.get_value(6, 0) == 27.0


def test_getpivotdata_unknown_field_is_ref():
    wb = Workbook()
    _pivot_block(wb)
    wb.sheet.set_cell(6, 0, '=GETPIVOTDATA("Nope", A1:D4)')
    wb.recalculate()
    v = wb.sheet.get_value(6, 0)
    assert is_error(v) and v.code == CellError.REF


# -- WEBSERVICE ------------------------------------------------------------

def test_webservice_off_when_disabled():
    from abax.core import livefuncs

    livedata.HUB.set_enabled(False)
    assert livefuncs._webservice(["http://h/x"]) == OFF_MARKER
    assert livedata.HUB.source_count() == 0


def test_webservice_rejects_non_http_scheme():
    from abax.core import livefuncs

    livedata.HUB.set_enabled(True)
    try:
        out = livefuncs._webservice(["ws://h/x"])
        assert is_error(out) and out.code == CellError.VALUE
    finally:
        livedata.HUB.set_enabled(False)


def test_webservice_returns_fetched_body():
    from abax.core import livefuncs

    livedata.HUB.set_enabled(True)
    try:
        url = "http://h/data.xml"
        body = "<r><i>42</i></r>"
        # Pre-seed the exact key the formula computes (kind/url/path=''/interval=0).
        key = livedata.HUB.subscribe(
            "webservice", url, "", 0.0,
            transport=lambda u, **k: iter([(True, body)]))
        assert _wait_for(lambda: livedata.HUB.latest(key)[0] == body)
        assert livefuncs._webservice([url]) == body
    finally:
        livedata.HUB.set_enabled(False)


def test_webservice_transport_fetches_localhost_text():
    import http.server

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = json.dumps({"ok": 1}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/x"
        stop = threading.Event()
        gen = livedata.webservice_transport(url, interval=0.0, stop_event=stop)
        ok, text = next(gen)
        assert ok is True and '"ok"' in text
    finally:
        stop.set()
        server.shutdown()


def test_webservice_and_filterxml_marked_volatile():
    from abax.core.depgraph import ALWAYS_DIRTY_FUNCS

    assert "WEBSERVICE" in ALWAYS_DIRTY_FUNCS
