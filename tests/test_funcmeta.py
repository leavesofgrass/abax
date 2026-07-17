"""funcmeta — categories, blurbs, and descriptions for every function."""

from __future__ import annotations

from abax.core.completion import function_names
from abax.core.funcmeta import CATEGORIES, catalog, category_key, describe


def test_every_function_lands_in_a_category():
    labels = {label for label, _ in CATEGORIES.values()}
    for name in function_names():
        d = describe(name)
        assert d["category"] in labels, name
        assert d["description"], name
        assert d["signature"], name


def test_catalog_partitions_the_registry():
    cat = catalog()
    names = [n for group in cat.values() for n in group]
    assert sorted(names) == sorted(function_names())   # complete, no dupes
    for group in cat.values():
        assert group == sorted(group)


def test_common_functions_are_well_placed():
    assert describe("SUM")["category"] == "Math & trig"
    assert describe("VLOOKUP")["category"] == "Lookup & reference"
    assert describe("UNIQUE")["category"] == "Dynamic arrays"
    assert describe("DBM2W")["category"] == "Radio & RF"
    assert describe("PMT")["category"] == "Financial"
    assert describe("IF")["category"] == "Logical & information"
    assert describe("DSUM")["category"] == "Database"


def test_handwritten_descriptions_and_blurbs():
    d = describe("XLOOKUP")
    assert "lookup" in d["description"].lower()
    assert d["category_blurb"]                          # family guidance exists
    # Case-insensitive by name.
    assert describe("sum")["name"] == "SUM"


def test_udf_categorized_as_user(monkeypatch):
    import abax.core.functions as fns

    def my_udf(args):
        """Doubles the input."""
        return 2 * args[0]

    my_udf.__module__ = "usermacros"                    # not an abax module
    monkeypatch.setitem(fns.FUNCTIONS, "MYUDF", my_udf)
    assert category_key("MYUDF") == "user"
    d = describe("MYUDF")
    assert d["category"] == "User-defined"
    assert d["description"] == "Doubles the input."     # docstring fallback
