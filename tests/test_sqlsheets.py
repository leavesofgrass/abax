"""Tests for :mod:`abax.core.sqlsheets` — SQL over spreadsheet sheets."""

from __future__ import annotations

import pytest

from abax.core.sheet import Sheet
from abax.core.sqlsheets import SqlError, result_to_sheet, run_sql


def _make_sheet(name, rows):
    """Build a Sheet from a list of row-lists (row 0 is the header)."""
    sheet = Sheet(name=name)
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            sheet.set_cell(r, c, str(val))
    return sheet


def _people():
    return _make_sheet(
        "People",
        [
            ["name", "age", "dept_id"],
            ["Alice", "30", "1"],
            ["Bob", "45", "2"],
            ["Carol", "28", "1"],
            ["Dave", "52", "2"],
        ],
    )


def _depts():
    return _make_sheet(
        "Depts",
        [
            ["dept_id", "dept_name"],
            ["1", "Engineering"],
            ["2", "Sales"],
        ],
    )


def test_select_where():
    cols, rows = run_sql({"People": _people()}, "SELECT name FROM People WHERE age > 40")
    assert cols == ["name"]
    assert sorted(r[0] for r in rows) == ["Bob", "Dave"]


def test_group_by_aggregate():
    cols, rows = run_sql(
        {"People": _people()},
        "SELECT dept_id, COUNT(*), SUM(age) FROM People GROUP BY dept_id ORDER BY dept_id",
    )
    assert cols[0] == "dept_id"
    # dept 1: Alice(30)+Carol(28)=58, count 2; dept 2: Bob(45)+Dave(52)=97, count 2.
    result = {row[0]: (row[1], row[2]) for row in rows}
    assert result[1] == (2, 58)
    assert result[2] == (2, 97)


def test_join_across_sheets():
    cols, rows = run_sql(
        {"People": _people(), "Depts": _depts()},
        "SELECT People.name, Depts.dept_name FROM People "
        "JOIN Depts ON People.dept_id = Depts.dept_id "
        "WHERE Depts.dept_name = 'Sales' ORDER BY People.name",
    )
    assert cols == ["name", "dept_name"]
    assert rows == [("Bob", "Sales"), ("Dave", "Sales")]


def test_numeric_type_inference():
    # age must be summed numerically (58/97), not string-concatenated.
    _cols, rows = run_sql(
        {"People": _people()},
        "SELECT SUM(age) FROM People",
    )
    total = rows[0][0]
    assert total == 155
    assert isinstance(total, int)


def test_result_to_sheet_roundtrip():
    cols, rows = run_sql(
        {"People": _people()},
        "SELECT name, age FROM People WHERE name = 'Alice'",
    )
    out = result_to_sheet(cols, rows, name="Result")
    assert out.name == "Result"
    assert out.get_value(0, 0) == "name"
    assert out.get_value(0, 1) == "age"
    # Row below the header holds Alice's data (stringified).
    assert out.get_value(1, 0) == "Alice"
    assert out.get_value(1, 1) == 30  # "30" re-parses as int on read
    nrows, ncols = out.used_bounds()
    assert (nrows, ncols) == (2, 2)


def test_bad_sql_raises():
    with pytest.raises(SqlError):
        run_sql({"People": _people()}, "SELECT * FROM NoSuchTable")
    with pytest.raises(SqlError):
        run_sql({"People": _people()}, "THIS IS NOT SQL")
