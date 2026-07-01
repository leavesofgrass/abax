"""Tests for abax.core.io.sqlite_io — SQLite import/export round-trips."""

from __future__ import annotations

import sqlite3

from abax.core.io.sqlite_io import (
    list_tables,
    load_database,
    load_table,
    save_table,
)
from abax.core.sheet import Sheet


def _make_db(path: str) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE people (name TEXT, age INTEGER, note TEXT)")
        conn.executemany(
            "INSERT INTO people (name, age, note) VALUES (?, ?, ?)",
            [("Alice", 30, "hi"), ("Bob", 25, None)],
        )
        conn.execute("CREATE TABLE widgets (id INTEGER, label TEXT)")
        conn.executemany(
            "INSERT INTO widgets (id, label) VALUES (?, ?)",
            [(1, "gear"), (2, "spring")],
        )
        conn.commit()
    finally:
        conn.close()


def test_list_tables_sorted(tmp_path):
    db = str(tmp_path / "t.db")
    _make_db(db)
    assert list_tables(db) == ["people", "widgets"]


def test_list_tables_excludes_internal(tmp_path):
    db = str(tmp_path / "t.db")
    conn = sqlite3.connect(db)
    try:
        # autoincrement creates an internal sqlite_sequence table
        conn.execute("CREATE TABLE a (id INTEGER PRIMARY KEY AUTOINCREMENT)")
        conn.commit()
    finally:
        conn.close()
    assert list_tables(db) == ["a"]


def test_load_table_header_and_data(tmp_path):
    db = str(tmp_path / "t.db")
    _make_db(db)
    sheet = load_table(db, "people")
    assert sheet.name == "people"
    # header row
    assert sheet.get_raw(0, 0) == "name"
    assert sheet.get_raw(0, 1) == "age"
    assert sheet.get_raw(0, 2) == "note"
    # data rows, values as text
    assert sheet.get_raw(1, 0) == "Alice"
    assert sheet.get_raw(1, 1) == "30"
    assert sheet.get_raw(1, 2) == "hi"
    assert sheet.get_raw(2, 0) == "Bob"
    # NULL -> empty cell
    assert sheet.get_raw(2, 2) == ""
    # 1 header + 2 data rows, 3 cols
    assert sheet.used_bounds() == (3, 3)


def test_load_table_custom_name(tmp_path):
    db = str(tmp_path / "t.db")
    _make_db(db)
    sheet = load_table(db, "people", name="Folks")
    assert sheet.name == "Folks"


def test_load_table_query(tmp_path):
    db = str(tmp_path / "t.db")
    _make_db(db)
    sheet = load_table(db, "SELECT name FROM people WHERE age > 28")
    assert sheet.name == "query"
    assert sheet.get_raw(0, 0) == "name"
    assert sheet.get_raw(1, 0) == "Alice"
    # only one matching row
    assert sheet.used_bounds() == (2, 1)


def _sheet_with_data() -> Sheet:
    s = Sheet("export")
    s.set_cell(0, 0, "city")
    s.set_cell(0, 1, "pop")
    s.set_cell(1, 0, "Reno")
    s.set_cell(1, 1, "250000")
    s.set_cell(2, 0, "Elko")
    # leave (2,1) empty -> NULL
    return s


def test_save_table_roundtrip(tmp_path):
    db = str(tmp_path / "out.db")
    s = _sheet_with_data()
    save_table(s, db, "cities")

    conn = sqlite3.connect(db)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(cities)").fetchall()]
        assert cols == ["city", "pop"]
        rows = conn.execute("SELECT city, pop FROM cities ORDER BY city").fetchall()
    finally:
        conn.close()
    assert rows == [("Elko", None), ("Reno", "250000")]


def test_save_table_replace(tmp_path):
    db = str(tmp_path / "out.db")
    s = _sheet_with_data()
    save_table(s, db, "cities")
    save_table(s, db, "cities", if_exists="replace")

    conn = sqlite3.connect(db)
    try:
        n = conn.execute("SELECT COUNT(*) FROM cities").fetchone()[0]
    finally:
        conn.close()
    assert n == 2  # replaced, not doubled


def test_save_table_append(tmp_path):
    db = str(tmp_path / "out.db")
    s = _sheet_with_data()
    save_table(s, db, "cities")
    save_table(s, db, "cities", if_exists="append")

    conn = sqlite3.connect(db)
    try:
        n = conn.execute("SELECT COUNT(*) FROM cities").fetchone()[0]
    finally:
        conn.close()
    assert n == 4  # appended


def test_save_table_fail(tmp_path):
    db = str(tmp_path / "out.db")
    s = _sheet_with_data()
    save_table(s, db, "cities")
    try:
        save_table(s, db, "cities", if_exists="fail")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for if_exists='fail'")


def test_save_table_blank_header_fallback(tmp_path):
    db = str(tmp_path / "out.db")
    s = Sheet("x")
    s.set_cell(0, 0, "name")
    # (0,1) blank header -> col_2 fallback
    s.set_cell(1, 0, "a")
    s.set_cell(1, 1, "b")
    save_table(s, db, "things")

    conn = sqlite3.connect(db)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(things)").fetchall()]
        rows = conn.execute("SELECT * FROM things").fetchall()
    finally:
        conn.close()
    assert cols == ["name", "col_2"]
    assert rows == [("a", "b")]


def test_save_table_weird_identifiers(tmp_path):
    db = str(tmp_path / "out.db")
    s = Sheet("x")
    s.set_cell(0, 0, 'odd"name; drop')
    s.set_cell(1, 0, "v")
    save_table(s, db, "weird")

    conn = sqlite3.connect(db)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(weird)").fetchall()]
        rows = conn.execute("SELECT * FROM weird").fetchall()
    finally:
        conn.close()
    assert len(cols) == 1
    assert rows == [("v",)]


def test_load_database(tmp_path):
    db = str(tmp_path / "t.db")
    _make_db(db)
    wb = load_database(db)
    names = sorted(s.name for s in wb.sheets)
    assert names == ["people", "widgets"]
    people = wb.get_sheet("people")
    assert people.get_raw(0, 0) == "name"
