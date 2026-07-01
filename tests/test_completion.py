"""Formula autocomplete: token extraction, candidate filtering, UDF inclusion."""

from __future__ import annotations

from abax.core.completion import (
    apply_completion,
    common_prefix,
    complete,
    current_token,
    function_names,
    signature,
)


def test_current_token_basic():
    assert current_token("=SU", 3) == ("SU", 1)
    assert current_token("=SUM(A1)+AV", 11) == ("AV", 9)


def test_current_token_ignores_strings():
    # cursor inside a quoted string -> no token
    token, _ = current_token('=IF(A1, "hel', 12)
    assert token == ""


def test_current_token_not_on_name():
    assert current_token("=1+", 3)[0] == ""
    assert current_token("=A1+", 4)[0] == ""  # operator boundary


def test_complete_requires_formula():
    assert complete("SUM", require_formula=True) == []
    assert "SUM" in complete("=SUM")


def test_complete_filters_by_prefix():
    cands = complete("=SU")
    assert "SUM" in cands
    assert "SUMIF" in cands
    assert "AVERAGE" not in cands


def test_complete_is_case_insensitive():
    assert "VLOOKUP" in complete("=vlo")


def test_common_prefix():
    assert common_prefix(["SUM", "SUMIF", "SUMPRODUCT"]) == "SUM"
    assert common_prefix(["SUM", "AVERAGE"]) == ""
    assert common_prefix([]) == ""


def test_apply_completion_inserts_paren():
    new_text, cursor = apply_completion("=SU", 3, "SUM")
    assert new_text == "=SUM("
    assert cursor == len(new_text)


def test_apply_completion_midformula():
    text = "=1+SU"
    new_text, cursor = apply_completion(text, len(text), "SUMIF")
    assert new_text == "=1+SUMIF("


def test_signature_known_and_fallback():
    assert "VLOOKUP(" in signature("VLOOKUP")
    assert signature("DEFINITELYNOTAFUNCTION").endswith("(...)")


def test_active_call_basic():
    from abax.core.completion import active_call

    assert active_call("=SUM(", 5) == ("SUM", 0)
    assert active_call("=SUM(1,", 7) == ("SUM", 1)
    assert active_call("=SUM(1,2,", 9) == ("SUM", 2)


def test_active_call_innermost():
    from abax.core.completion import active_call

    # cursor inside the inner IF, after its first comma
    text = "=SUM(1, IF(A1,"
    assert active_call(text, len(text)) == ("IF", 1)


def test_active_call_ignores_commas_in_strings():
    from abax.core.completion import active_call

    text = '=CONCAT("a,b,c",'
    assert active_call(text, len(text)) == ("CONCAT", 1)


def test_active_call_none_outside_call():
    from abax.core.completion import active_call

    assert active_call("=1+2", 4) is None
    assert active_call("=SUM(1)", 7) is None  # call already closed


def test_signature_hint_and_format():
    from abax.core.completion import format_hint, signature_hint

    hint = signature_hint("=VLOOKUP(A1, B1:C9, ", None)
    assert hint["name"] == "VLOOKUP"
    assert hint["arg_index"] == 2
    rendered = format_hint(hint)
    assert "»col_index«" in rendered


def test_format_hint_clamps_variadic():
    from abax.core.completion import format_hint, signature_hint

    hint = signature_hint("=SUM(1, 2, 3, ", None)  # past listed params
    rendered = format_hint(hint)
    assert "»" in rendered  # highlights the last (repeating) param


def test_udf_appears_after_install():
    from abax.core.functions import FUNCTIONS

    assert "MYUDF" not in function_names()
    FUNCTIONS["MYUDF"] = lambda args: 1  # simulate an installed UDF
    try:
        assert "MYUDF" in function_names()
        assert "MYUDF" in complete("=MYU")
    finally:
        del FUNCTIONS["MYUDF"]


def test_complete_includes_names_sheets_constants():
    out = complete("=SU", names=("Subtotal",), sheets=("Summary",))
    assert "SUM" in out and "Subtotal" in out and "Summary" in out
    assert out.index("SUM") < out.index("Subtotal")          # functions first
    assert "TRUE" in complete("=TR") and "FALSE" in complete("=FA")
    # names/sheets only offered when passed; bare function completion unchanged
    assert "Subtotal" not in complete("=SU")


def test_apply_completion_paren_only_for_functions():
    assert apply_completion("=SU", 3, "SUM") == ("=SUM(", 5)        # function -> "("
    assert apply_completion("=Va", 3, "Vals") == ("=Vals", 5)       # name -> bare


def test_is_function():
    from abax.core.completion import is_function

    assert is_function("sum") and is_function("FSPL")
    assert not is_function("Vals")
