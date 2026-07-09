"""Tests for the streaming hex viewer model.

The key behaviour under test is the *windowed read*: a request for rows in the
middle of a file must seek there and decode those bytes only — proving the
model never reads from offset zero, so it can browse files larger than RAM.
"""

from __future__ import annotations

from abax.core.hexview import HexRow, HexView


def _make_file(tmp_path):
    """A 256-byte file whose byte at offset i == i (0x00..0xFF).

    This mixes non-printable (0x00..0x1F, 0x7F..0xFF) and printable (0x20..0x7E)
    bytes, and each byte's value equals its offset — so any decoding error
    (e.g. reading from the wrong place) is trivially visible.
    """
    p = tmp_path / "ramp.bin"
    p.write_bytes(bytes(range(256)))
    return p


def test_rows_window_in_middle_seeks_not_from_zero(tmp_path):
    view = HexView(_make_file(tmp_path))
    with view:
        assert view.size == 256
        # Window in the MIDDLE: offset 0x40, two rows of 16 bytes.
        rows = view.rows(0x40, 2, width=16)
        assert len(rows) == 2

        first = rows[0]
        assert isinstance(first, HexRow)
        assert first.offset == 0x40
        # Bytes 0x40..0x4F == "40 41 ... 4F".
        assert first.hexes == [f"{b:02X}" for b in range(0x40, 0x50)]
        # 0x40..0x4F are all printable: "@ABCDEFGHIJKLMNO".
        assert first.ascii == "@ABCDEFGHIJKLMNO"

        second = rows[1]
        assert second.offset == 0x50
        assert second.hexes[0] == "50"


def test_ascii_non_printable_becomes_dot(tmp_path):
    view = HexView(_make_file(tmp_path))
    with view:
        # Offset 0: bytes 0x00..0x0F are all control chars -> all dots.
        row = view.rows(0, 1, width=16)[0]
        assert row.ascii == "." * 16
        assert row.hexes[0] == "00"


def test_format_rows_layout(tmp_path):
    view = HexView(_make_file(tmp_path))
    with view:
        dump = view.format_rows(0x40, 1, width=16)
        expected_hex = " ".join(f"{b:02X}" for b in range(0x40, 0x50))
        assert dump == f"00000040  {expected_hex}  |@ABCDEFGHIJKLMNO|"


def test_format_rows_short_last_row_padding(tmp_path):
    p = tmp_path / "small.bin"
    p.write_bytes(b"Hello")  # 5 bytes, one short row
    with HexView(p) as view:
        dump = view.format_rows(0, 1, width=16)
        # Gutter must still start in the same column despite the short row.
        assert dump.endswith("|Hello|")
        assert "48 65 6C 6C 6F" in dump
        # 8 offset digits + 2 spaces + (16*3-1)=47 hex col + 2 spaces = 59.
        assert dump.index("|") == 59


def test_past_eof_is_short_or_empty(tmp_path):
    view = HexView(_make_file(tmp_path))
    with view:
        # Last window is short: 240 bytes read yields one full row + ...
        rows = view.rows(0xF8, 4, width=16)  # 0xF8 = 248, 8 bytes left
        assert len(rows) == 1
        assert rows[0].offset == 0xF8
        assert len(rows[0].hexes) == 8  # short row: only 8 bytes remain
        assert rows[0].ascii == "." * 8  # 0xF8..0xFF all non-printable

        # Start exactly at EOF -> empty.
        assert view.rows(256, 4, width=16) == []
        # Start past EOF -> empty.
        assert view.rows(999, 4, width=16) == []


def test_zero_byte_file_yields_no_rows(tmp_path):
    p = tmp_path / "empty.bin"
    p.write_bytes(b"")
    with HexView(p) as view:
        assert view.size == 0
        assert view.rows(0, 4, width=16) == []
        assert view.format_rows(0, 4, width=16) == ""


def test_from_bytes(tmp_path):
    data = b"\x00\x01ABC\xff"
    view = HexView.from_bytes(data)
    assert view.size == len(data)
    rows = view.rows(0, 1, width=8)
    assert len(rows) == 1
    assert rows[0].hexes == ["00", "01", "41", "42", "43", "FF"]
    assert rows[0].ascii == "..ABC."
    # from_bytes still supports mid-buffer windows.
    mid = view.rows(2, 1, width=2)
    assert mid[0].offset == 2
    assert mid[0].hexes == ["41", "42"]
    assert mid[0].ascii == "AB"
