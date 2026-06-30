"""Image faceplate loads art from an EXTERNAL folder (synthetic, offscreen).

qcell ships no artwork; these tests build a throwaway asset dir in tmp_path and
verify the resolver + the compositing widget against it.
"""

from __future__ import annotations

import os
import struct

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("qcell.gui._qtcompat")

from qcell.gui._qtcompat import QApplication  # noqa: E402


def _make_png(path, w, h):
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR"
        + struct.pack(">II", w, h) + b"\x08\x06\x00\x00\x00" + b"\x00\x00\x00\x00")


def _make_assets(d):
    (d / "keys").mkdir(parents=True, exist_ok=True)
    _make_png(d / "background.png", 558, 350)
    (d / "16c.kml").write_text(
        'display offset 73 29 size 305 55\n'
        'button 36 image "key_36.png" offset 16 130\n'
        'button 11 image "key_11.png" offset 16 74\n')
    return d


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_find_assets_dir_prefers_settings(tmp_path):
    from qcell.gui.calc.image_faceplate import find_assets_dir

    d = _make_assets(tmp_path / "voyager" / "16c")
    assert find_assets_dir(str(tmp_path / "voyager"), "16c") == d


def test_find_assets_dir_none_when_absent(tmp_path):
    from qcell.gui.calc.image_faceplate import find_assets_dir

    # an empty dir (no background.png / kml) under a model that won't match the
    # well-known fallbacks for a bogus model name
    assert find_assets_dir(str(tmp_path / "nothing"), "zz_nomodel") is None


def test_image_faceplate_composites_external_art(app, tmp_path):
    from qcell.core.calc.rpn16 import Voyager16Keypad
    from qcell.gui.calc.image_faceplate import ImageFaceplate

    d = _make_assets(tmp_path / "16c")
    fp = ImageFaceplate(Voyager16Keypad(), d)
    assert (fp._base.width(), fp._base.height()) == (558, 350)
    assert fp.display() == "0 h"          # 16C boots in hex
    fp._press(11)                         # button 11 == hex digit A
    assert "A" in fp.display()            # the press reached the keypad
