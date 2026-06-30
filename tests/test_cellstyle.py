"""Tests for the per-cell visual style model (``qcell.core.format.cellstyle``)."""

from __future__ import annotations

import pytest

from qcell.core.format.cellstyle import ALIGNMENTS, CellStyle, merge, toggle


def test_is_empty():
    assert CellStyle().is_empty() is True
    assert CellStyle(bold=True).is_empty() is False
    assert CellStyle(align="left").is_empty() is False
    assert CellStyle(text_color="#000000").is_empty() is False


def test_to_dict_default_is_empty():
    assert CellStyle().to_dict() == {}


def test_to_dict_only_non_defaults():
    assert CellStyle(bold=True, align="center").to_dict() == {
        "bold": True,
        "align": "center",
    }


def test_to_dict_all_fields():
    s = CellStyle(
        bold=True,
        italic=True,
        underline=True,
        align="right",
        text_color="#112233",
        bg_color="#ffcc00",
    )
    assert s.to_dict() == {
        "bold": True,
        "italic": True,
        "underline": True,
        "align": "right",
        "text_color": "#112233",
        "bg_color": "#ffcc00",
    }


def test_from_dict_basic():
    s = CellStyle.from_dict({"bold": True, "bg_color": "#ffcc00"})
    assert s.bold is True
    assert s.bg_color == "#ffcc00"
    assert s.italic is False


def test_from_dict_empty():
    assert CellStyle.from_dict({}) == CellStyle()


def test_from_dict_ignores_unknown():
    s = CellStyle.from_dict({"unknown": 1, "italic": True})
    assert s == CellStyle(italic=True)


@pytest.mark.parametrize(
    "s",
    [
        CellStyle(),
        CellStyle(bold=True),
        CellStyle(bold=True, align="center"),
        CellStyle(italic=True, underline=True, text_color="#abcdef"),
        CellStyle(
            bold=True,
            italic=True,
            underline=True,
            align="left",
            text_color="#010203",
            bg_color="#0a0b0c",
        ),
    ],
)
def test_round_trip(s):
    assert CellStyle.from_dict(s.to_dict()) == s


def test_with_changes_toggles_only_bold():
    s = CellStyle()
    out = s.with_changes(bold=True)
    assert out == CellStyle(bold=True)
    assert s == CellStyle()  # original unchanged (frozen)


def test_with_changes_align_ok():
    assert CellStyle().with_changes(align="center").align == "center"


def test_with_changes_bad_align_raises():
    with pytest.raises(ValueError):
        CellStyle().with_changes(align="middle")


def test_with_changes_bad_color_raises():
    with pytest.raises(ValueError):
        CellStyle().with_changes(text_color="red")


def test_with_changes_good_color_ok():
    assert CellStyle().with_changes(text_color="#ABCDEF").text_color == "#ABCDEF"


def test_with_changes_unknown_field_raises():
    with pytest.raises(ValueError):
        CellStyle().with_changes(nope=1)


def test_with_changes_empty_align_allowed():
    assert CellStyle(align="left").with_changes(align="").align == ""


def test_with_changes_empty_color_allowed():
    assert CellStyle(bg_color="#ffffff").with_changes(bg_color="").bg_color == ""


def test_frozen():
    s = CellStyle()
    with pytest.raises(AttributeError):       # frozen dataclass -> FrozenInstanceError
        s.bold = True  # type: ignore[misc]


def test_merge():
    base = CellStyle(bold=True)
    out = merge(base, italic=True)
    assert out == CellStyle(bold=True, italic=True)


def test_merge_validates():
    with pytest.raises(ValueError):
        merge(CellStyle(), align="bogus")


def test_toggle_on():
    assert toggle(CellStyle(), "bold").bold is True


def test_toggle_off():
    assert toggle(CellStyle(bold=True), "bold").bold is False


def test_toggle_italic_underline():
    assert toggle(CellStyle(), "italic").italic is True
    assert toggle(CellStyle(underline=True), "underline").underline is False


def test_toggle_non_boolean_field_raises():
    with pytest.raises(ValueError):
        toggle(CellStyle(), "align")


def test_alignments_constant():
    assert ALIGNMENTS == ("", "left", "center", "right")
