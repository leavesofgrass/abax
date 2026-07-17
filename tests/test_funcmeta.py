"""funcmeta — categories, blurbs, and descriptions for every function."""

from __future__ import annotations

from abax.core._funcmeta_generated import GENERATED_DESCRIPTIONS
from abax.core.completion import function_names
from abax.core.funcmeta import CATEGORIES, DESCRIPTIONS, EXAMPLES, catalog, category_key, describe


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


def test_r_distributions_are_statistics():
    """The R.* distribution family (gnumeric_fns) and the dotted compat
    aliases (dist_dotted) are Statistics, not the Specialty fall-through."""
    assert category_key("R.DNORM") == "stats"
    assert describe("R.DNORM")["category"] == "Statistics"
    assert describe("R.PBINOM")["category"] == "Statistics"
    assert describe("R.QCHISQ")["category"] == "Statistics"
    # Dotted compat aliases were already module-mapped; keep them that way.
    assert describe("CHISQ.DIST")["category"] == "Statistics"
    assert describe("F.TEST")["category"] == "Statistics"


def test_handwritten_descriptions_and_blurbs():
    d = describe("XLOOKUP")
    assert "lookup" in d["description"].lower()
    assert d["category_blurb"]                          # family guidance exists
    # Case-insensitive by name.
    assert describe("sum")["name"] == "SUM"


def test_description_coverage_floor():
    """Most registered functions get a real description (hand-written or
    harvested from docs/formula-reference.md), not the category fallback."""
    covered = 0
    for name in function_names():
        expected = DESCRIPTIONS.get(name) or GENERATED_DESCRIPTIONS.get(name)
        if expected is not None:
            assert describe(name)["description"] == expected, name
            covered += 1
    assert covered >= 625                       # actual: 627 of 642 today


def test_generated_descriptions_are_clean():
    """No markdown artifacts, nothing empty, nothing absurdly long — and the
    hand-written style (capitalized-ish, trailing period) is matched."""
    assert GENERATED_DESCRIPTIONS
    for name, desc in GENERATED_DESCRIPTIONS.items():
        assert desc and desc == desc.strip(), name
        assert len(desc) <= 200, (name, desc)
        for artifact in ("*", "[", "`", "|"):
            assert artifact not in desc, (name, desc)
        assert desc.endswith("."), (name, desc)


def test_handwritten_wins_over_generated():
    """A name present in both dicts resolves to the hand-written text."""
    both = sorted(set(DESCRIPTIONS) & set(GENERATED_DESCRIPTIONS))
    assert "SUM" in both                        # documented *and* hand-written
    for name in both:
        assert describe(name)["description"] == DESCRIPTIONS[name], name


def test_no_known_family_functions_in_specialty():
    """Functions belonging to a known family must not fall through to Specialty."""
    known_family_members = {
        # stats
        "AVG", "CHIDIST", "CHIINV", "CHISQ.DIST.RT", "CHISQ.INV.RT",
        "CONFIDENCE", "CONFIDENCE.NORM", "COVARIANCE.P", "F.DIST.RT",
        "F.INV.RT", "FDIST", "FINV", "FORECAST", "FORECAST.LINEAR",
        "INTERCEPT", "MODE.SNGL", "NORM.DIST", "NORM.INV", "NORM.S.INV",
        "NORMDIST", "NORMINV", "NORMSDIST", "NORMSINV", "PERCENTILE.INC",
        "QUARTILE.INC", "RMS", "RSQ", "SLOPE", "STDEV.P", "STDEV.S",
        "TDIST", "TINV", "TTEST", "VAR.P", "VAR.S",
        # engineering
        "COMPLEX", "CONVERT", "IMABS", "IMAGINARY", "IMARGUMENT",
        "IMCONJUGATE", "IMCOS", "IMCOSH", "IMCOT", "IMCSC", "IMCSCH",
        "IMDIV", "IMEXP", "IMLN", "IMLOG10", "IMLOG2", "IMPOWER",
        "IMPRODUCT", "IMREAL", "IMSEC", "IMSECH", "IMSIN", "IMSINH",
        "IMSQRT", "IMSUB", "IMSUM", "IMTAN", "IMTANH",
        # math
        "CEILING.MATH", "FLOOR.MATH", "MDETERM", "INTERP",
        # text
        "ARRAYTOTEXT", "VALUETOTEXT",
    }
    registered = set(function_names())
    for name in sorted(known_family_members & registered):
        cat = category_key(name)
        assert cat != "other", f"{name} is in Specialty but should be categorized"


def test_describe_includes_example():
    d = describe("SUM")
    assert "example" in d
    assert d["example"].startswith("=")


def test_examples_are_valid_formulas():
    for name, ex in EXAMPLES.items():
        assert ex.startswith("="), f"{name} example must start with ="
        assert name in ex.upper() or name.replace(".", "") in ex.upper(), \
            f"{name} example should contain the function name"


def test_examples_coverage():
    assert len(EXAMPLES) >= 50, f"Expected at least 50 examples, got {len(EXAMPLES)}"


def test_describe_example_empty_for_uncurated():
    """Functions without a curated example get an empty string, not a KeyError."""
    d = describe("SERIESSUM")
    assert d["example"] == ""


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
