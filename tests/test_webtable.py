"""Tests for the HTML-table extractor — pure stdlib, local fixture strings only.

Every case feeds a literal HTML string straight to the parser; nothing touches
the network. The fixtures cover thead/tbody flattening, entity decoding, nested
inline markup, colspan/rowspan, multiple and nested tables, and the
largest-table convenience.
"""

from __future__ import annotations

import pytest

from abax.core.io.webtable import (
    WebTableError,
    largest_table_from_html,
    tables_from_html,
)

# --- basic extraction ------------------------------------------------------

_SIMPLE = """
<html><body>
<table>
  <thead><tr><th>Name</th><th>Age</th></tr></thead>
  <tbody>
    <tr><td>Alice</td><td>30</td></tr>
    <tr><td>Bob</td><td>25</td></tr>
  </tbody>
</table>
</body></html>
"""


def test_thead_and_tbody_flatten_into_one_grid():
    tables = tables_from_html(_SIMPLE)
    assert tables == [
        [["Name", "Age"], ["Alice", "30"], ["Bob", "25"]]
    ]


def test_no_table_returns_empty_list():
    assert tables_from_html("<p>nothing here</p>") == []
    assert tables_from_html("") == []


def test_th_and_td_both_become_cells():
    html = "<table><tr><th>h1</th><td>d1</td></tr></table>"
    assert tables_from_html(html) == [[["h1", "d1"]]]


# --- text normalisation ----------------------------------------------------


def test_entities_are_unescaped():
    html = "<table><tr><td>a &amp; b</td><td>&lt;x&gt;</td></tr></table>"
    assert tables_from_html(html) == [[["a & b", "<x>"]]]


def test_nested_inline_markup_is_flattened_to_text():
    html = "<table><tr><td>go <a href='u'>here</a> <b>now</b></td></tr></table>"
    assert tables_from_html(html) == [[["go here now"]]]


def test_whitespace_is_collapsed_and_trimmed():
    html = "<table><tr><td>  lots\n   of   space  </td></tr></table>"
    assert tables_from_html(html) == [[["lots of space"]]]


def test_br_becomes_a_space():
    html = "<table><tr><td>line1<br>line2<br/>line3</td></tr></table>"
    assert tables_from_html(html) == [[["line1 line2 line3"]]]


def test_script_and_style_bodies_are_dropped():
    html = (
        "<table><tr><td>keep<script>var x=1;</script>"
        "<style>td{color:red}</style></td></tr></table>"
    )
    assert tables_from_html(html) == [[["keep"]]]


def test_empty_cells_are_empty_strings():
    html = "<table><tr><td></td><td>x</td></tr></table>"
    assert tables_from_html(html) == [[["", "x"]]]


# --- spans -----------------------------------------------------------------


def test_colspan_repeats_cell_text_across_columns():
    html = (
        "<table>"
        "<tr><td colspan='2'>wide</td><td>x</td></tr>"
        "<tr><td>a</td><td>b</td><td>c</td></tr>"
        "</table>"
    )
    assert tables_from_html(html) == [
        [["wide", "wide", "x"], ["a", "b", "c"]]
    ]


def test_rowspan_carries_cell_into_following_rows():
    html = (
        "<table>"
        "<tr><td rowspan='2'>R</td><td>1</td></tr>"
        "<tr><td>2</td></tr>"
        "</table>"
    )
    assert tables_from_html(html) == [[["R", "1"], ["R", "2"]]]


def test_rowspan_and_colspan_keep_grid_rectangular():
    # A 3-row span in column 0 plus a colspan should stay column-aligned.
    html = (
        "<table>"
        "<tr><td rowspan='3'>span</td><td colspan='2'>top</td></tr>"
        "<tr><td>m1</td><td>m2</td></tr>"
        "<tr><td>b1</td><td>b2</td></tr>"
        "</table>"
    )
    grid = tables_from_html(html)[0]
    assert grid == [
        ["span", "top", "top"],
        ["span", "m1", "m2"],
        ["span", "b1", "b2"],
    ]
    # rectangular: every row the same width.
    assert len({len(r) for r in grid}) == 1


def test_bad_span_value_is_treated_as_one():
    html = "<table><tr><td colspan='oops'>x</td><td>y</td></tr></table>"
    assert tables_from_html(html) == [[["x", "y"]]]


def test_ragged_rows_are_padded_to_widest():
    html = "<table><tr><td>a</td></tr><tr><td>b</td><td>c</td></tr></table>"
    assert tables_from_html(html) == [[["a", ""], ["b", "c"]]]


# --- malformed / lenient parsing -------------------------------------------


def test_unclosed_td_and_tr_still_parse():
    # Real-world sloppiness: no </td> or </tr>.
    html = "<table><tr><td>a<td>b<tr><td>c<td>d</table>"
    assert tables_from_html(html) == [[["a", "b"], ["c", "d"]]]


def test_cells_outside_a_row_start_an_implicit_row():
    html = "<table><td>a</td><td>b</td></table>"
    assert tables_from_html(html) == [[["a", "b"]]]


# --- multiple and nested tables --------------------------------------------


def test_multiple_tables_return_multiple_grids():
    html = (
        "<table><tr><td>t1</td></tr></table>"
        "<table><tr><td>t2</td></tr></table>"
    )
    assert tables_from_html(html) == [[["t1"]], [["t2"]]]


def test_nested_table_is_its_own_grid_inner_before_outer():
    html = (
        "<table><tr>"
        "<td>outer<table><tr><td>inner</td></tr></table></td>"
        "<td>after</td>"
        "</tr></table>"
    )
    tables = tables_from_html(html)
    # Inner table appears first (its </table> closes first); the outer cell text
    # does not absorb the inner table's text.
    assert tables == [[["inner"]], [["outer", "after"]]]


# --- largest_table_from_html ----------------------------------------------


def test_largest_table_picks_the_biggest_by_cell_count():
    html = (
        "<table><tr><td>nav</td></tr></table>"  # 1 cell
        "<table>"
        "<tr><td>a</td><td>b</td></tr>"
        "<tr><td>c</td><td>d</td></tr>"
        "</table>"  # 4 cells
    )
    assert largest_table_from_html(html) == [["a", "b"], ["c", "d"]]


def test_largest_table_tie_breaks_on_first():
    html = (
        "<table><tr><td>first</td></tr></table>"
        "<table><tr><td>second</td></tr></table>"
    )
    assert largest_table_from_html(html) == [["first"]]


def test_largest_table_raises_without_a_table():
    with pytest.raises(WebTableError):
        largest_table_from_html("<p>no tables</p>")
