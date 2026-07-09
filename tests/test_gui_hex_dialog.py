"""Offscreen tests for the streaming hex viewer dialog.

Run with:  QT_QPA_PLATFORM=offscreen py -m pytest tests/test_gui_hex_dialog.py -q
"""

from __future__ import annotations

from abax.gui._qtcompat import QApplication
from abax.gui.dialogs.hex_dialog import HexDialog

_APP = QApplication.instance() or QApplication([])


def _make_dialog() -> HexDialog:
    # The dialog only passes `window` to QDialog as parent; None is a valid
    # parent, so a real window is unnecessary for these tests.
    return HexDialog(None)


def test_load_path_renders_hex_and_ascii(tmp_path) -> None:
    # Printable "Hello" plus non-printable bytes (NUL and 0xFF).
    data = b"Hello\x00\xffWorld"
    p = tmp_path / "sample.bin"
    p.write_bytes(data)

    dlg = _make_dialog()
    dlg.load_path(str(p))
    text = dlg._dump.toPlainText()

    # Uppercase hex for 'H' (0x48), NUL (0x00) and 0xFF must appear.
    assert "48 65 6C 6C 6F" in text  # "Hello"
    assert "00 FF" in text
    # ASCII gutter renders printables literally and others as '.'.
    assert "|Hello..World|" in text
    # Status label reports the file size.
    assert "12 bytes" in dlg._status.text()


def test_next_prev_page_moves_top(tmp_path) -> None:
    p = tmp_path / "big.bin"
    p.write_bytes(bytes(range(256)) * 8)  # 2048 bytes, many pages.

    dlg = HexDialog(None, rows_per_page=4)  # 64 bytes per page.
    dlg.load_path(str(p))
    assert dlg._top == 0

    dlg.next_page()
    assert dlg._top == 64
    dlg.next_page()
    assert dlg._top == 128

    dlg.prev_page()
    assert dlg._top == 64

    # Prev never goes below zero.
    dlg.prev_page()
    dlg.prev_page()
    assert dlg._top == 0


def test_load_bytes(tmp_path) -> None:
    dlg = _make_dialog()
    dlg.load_bytes(b"ABC\x01\x02")
    text = dlg._dump.toPlainText()
    assert "41 42 43 01 02" in text  # "ABC" + two control bytes
    assert "|ABC..|" in text


def test_goto_offset_hex_and_decimal(tmp_path) -> None:
    p = tmp_path / "seek.bin"
    p.write_bytes(bytes(range(256)) * 4)  # 1024 bytes.

    dlg = HexDialog(None, rows_per_page=2)
    dlg.load_path(str(p))

    dlg._goto.setText("0x1F0")
    dlg._go_to_offset()
    assert dlg._top == 0x1F0  # already row-aligned

    dlg._goto.setText("100")
    dlg._go_to_offset()
    assert dlg._top == 96  # 100 aligned down to a 16-byte row


def test_missing_and_empty_file_do_not_crash(tmp_path) -> None:
    dlg = _make_dialog()
    dlg.load_path(str(tmp_path / "does_not_exist.bin"))
    assert "Could not open" in dlg._status.text()

    empty = tmp_path / "empty.bin"
    empty.write_bytes(b"")
    dlg.load_path(str(empty))
    assert "0 bytes" in dlg._status.text()
    assert dlg._dump.toPlainText() == ""
