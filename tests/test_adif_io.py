"""Tests for the ADIF logbook import/export module."""

from __future__ import annotations

from qcell.core.io.adif_io import (
    grid_to_records,
    parse_adif,
    records_to_grid,
    to_adif,
)

SAMPLE = """ADIF export from somewhere
<ADIF_VER:5>3.1.4
<PROGRAMID:6>logger
<EOH>
<CALL:4>W1AW <QSO_DATE:8>20240115 <TIME_ON:4>1830
<BAND:3>20m <MODE:3>SSB <RST_SENT:2>59 <RST_RCVD:2>59 <EOR>
<CALL:6>DL1ABC <QSO_DATE:8>20240116 <TIME_ON:4>0745
<BAND:3>40m <MODE:2>CW <RST_SENT:3>599 <RST_RCVD:3>599 <EOR>
"""


def test_parse_sample_two_records():
    records = parse_adif(SAMPLE)
    assert len(records) == 2
    first, second = records
    assert first["CALL"] == "W1AW"
    assert first["QSO_DATE"] == "20240115"
    assert first["TIME_ON"] == "1830"
    assert first["BAND"] == "20m"
    assert first["MODE"] == "SSB"
    assert first["RST_SENT"] == "59"
    assert first["RST_RCVD"] == "59"
    assert second["CALL"] == "DL1ABC"
    assert second["MODE"] == "CW"
    assert second["RST_RCVD"] == "599"


def test_case_insensitive_field_names():
    records = parse_adif("<call:4>W1AW<eor>")
    assert records == [{"CALL": "W1AW"}]


def test_parse_no_header():
    text = "<CALL:4>W1AW<QSO_DATE:8>20240115<EOR>"
    records = parse_adif(text)
    assert records == [{"CALL": "W1AW", "QSO_DATE": "20240115"}]


def test_roundtrip_parse_of_to_adif():
    recs = [
        {"CALL": "W1AW", "QSO_DATE": "20240115", "MODE": "SSB"},
        {"CALL": "DL1ABC", "QSO_DATE": "20240116", "MODE": "CW"},
    ]
    assert parse_adif(to_adif(recs)) == recs


def test_value_with_angle_bracket_survives():
    # A comment value containing < and > must survive the length-based parse.
    value = "beam <heading> 3<5"
    recs = [{"CALL": "W1AW", "COMMENT": value}]
    out = to_adif(recs)
    parsed = parse_adif(out)
    assert parsed == recs
    assert parsed[0]["COMMENT"] == value


def test_utf8_length_in_to_adif():
    recs = [{"NAME": "José"}]
    out = to_adif(recs)
    # "José" is 5 bytes in UTF-8.
    assert "<NAME:5>José" in out
    assert parse_adif(out) == recs


def test_records_to_grid_union_order():
    recs = [
        {"CALL": "W1AW", "MODE": "SSB"},
        {"CALL": "DL1ABC", "BAND": "40m"},
    ]
    headers, rows = records_to_grid(recs)
    assert headers == ["CALL", "MODE", "BAND"]
    assert rows == [["W1AW", "SSB", ""], ["DL1ABC", "", "40m"]]


def test_records_to_grid_explicit_fields():
    recs = [{"CALL": "W1AW", "MODE": "SSB"}]
    headers, rows = records_to_grid(recs, fields=["CALL", "BAND"])
    assert headers == ["CALL", "BAND"]
    assert rows == [["W1AW", ""]]


def test_grid_roundtrip():
    recs = [
        {"CALL": "W1AW", "MODE": "SSB"},
        {"CALL": "DL1ABC", "BAND": "40m"},
    ]
    headers, rows = records_to_grid(recs)
    assert grid_to_records(headers, rows) == recs


def test_grid_to_records_skips_empty_cells():
    headers = ["CALL", "MODE", "BAND"]
    rows = [["W1AW", "SSB", ""]]
    assert grid_to_records(headers, rows) == [{"CALL": "W1AW", "MODE": "SSB"}]
