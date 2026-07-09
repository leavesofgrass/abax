"""Tests for the recursive formula dependency tracer (abax.core.deptrace)."""

from __future__ import annotations

from abax.core.deptrace import (
    DepNode,
    render_ascii,
    trace_dependents,
    trace_precedents,
)
from abax.core.reference import parse_a1
from abax.core.sheet import Sheet


def _sheet(**cells: str) -> Sheet:
    """Build a Sheet from ``A1="=B1+C1"`` keyword pairs (A1-ref -> raw text)."""
    sheet = Sheet()
    for ref, raw in cells.items():
        sheet.set(ref, raw)
    return sheet


def _child_a1s(node: DepNode) -> list[str]:
    return [c.a1 for c in node.children]


# --- trace_precedents -------------------------------------------------------


def test_precedents_tree_shape():
    # A1 = B1 + C1 ; B1 literal ; C1 = B1*2 (B1 is a shared precedent).
    sheet = _sheet(A1="=B1+C1", B1="5", C1="=B1*2")
    root = trace_precedents(sheet, *parse_a1("A1"))

    assert root.a1 == "A1"
    assert root.cell == (0, 0)
    assert _child_a1s(root) == ["B1", "C1"]

    b1, c1 = root.children
    assert b1.a1 == "B1" and b1.children == []      # literal: no precedents
    assert c1.a1 == "C1"
    # C1 expands into its own precedent B1 — the shared cell reappears here.
    assert _child_a1s(c1) == ["B1"]


def test_shared_precedent_appears_under_both_branches():
    # D1 feeds both B1 and C1, which both feed A1: D1 shows up twice.
    sheet = _sheet(A1="=B1+C1", B1="=D1", C1="=D1*2", D1="7")
    root = trace_precedents(sheet, *parse_a1("A1"))
    b1, c1 = root.children
    assert _child_a1s(b1) == ["D1"]
    assert _child_a1s(c1) == ["D1"]


def test_self_reference_cycle_flagged():
    sheet = _sheet(A1="=A1")
    root = trace_precedents(sheet, *parse_a1("A1"))
    assert root.a1 == "A1"
    assert len(root.children) == 1
    cyc = root.children[0]
    assert cyc.a1 == "A1"
    assert cyc.cyclic is True
    assert cyc.children == []       # a cycle-closing node does not recurse


def test_indirect_cycle_flagged():
    # A1 -> B1 -> A1 : the second A1 closes the cycle.
    sheet = _sheet(A1="=B1", B1="=A1")
    root = trace_precedents(sheet, *parse_a1("A1"))
    b1 = root.children[0]
    assert b1.a1 == "B1"
    assert b1.children[0].a1 == "A1"
    assert b1.children[0].cyclic is True


def test_max_depth_stops_recursion():
    # A chain A1<-B1<-C1<-D1; depth 1 keeps only the first hop.
    sheet = _sheet(A1="=B1", B1="=C1", C1="=D1", D1="1")
    root = trace_precedents(sheet, *parse_a1("A1"), max_depth=1)
    assert _child_a1s(root) == ["B1"]
    assert root.children[0].children == []      # stopped before expanding B1


def test_blank_and_literal_dont_raise():
    sheet = _sheet(A1="=B1+Z9", B1="42")   # Z9 is blank
    root = trace_precedents(sheet, *parse_a1("A1"))
    assert _child_a1s(root) == ["B1", "Z9"]
    z9 = root.children[1]
    assert z9.a1 == "Z9" and z9.children == []


def test_malformed_precedent_does_not_crash():
    sheet = Sheet()
    sheet.set("A1", "=B1")
    # Inject a malformed formula directly so precedent extraction would raise.
    sheet._cells[parse_a1("B1")] = sheet._cells[parse_a1("A1")].__class__("=SUM(")
    root = trace_precedents(sheet, *parse_a1("A1"))
    b1 = root.children[0]
    assert b1.a1 == "B1"
    assert b1.children == []     # malformed formula degrades to no precedents


# --- trace_dependents -------------------------------------------------------


def test_dependents_tree_shape():
    # B1 feeds A1 and C1; A1 also feeds C1.  Ask: what depends on B1?
    sheet = _sheet(A1="=B1", C1="=B1+A1", B1="5")
    root = trace_dependents(sheet, *parse_a1("B1"))
    assert root.a1 == "B1"
    # Direct dependents of B1 are A1 and C1 (row-major order).
    assert _child_a1s(root) == ["A1", "C1"]
    a1 = root.children[0]
    # A1's dependent is C1.
    assert _child_a1s(a1) == ["C1"]


def test_dependents_self_cycle_flagged():
    sheet = _sheet(A1="=A1")
    root = trace_dependents(sheet, *parse_a1("A1"))
    assert len(root.children) == 1
    assert root.children[0].cyclic is True


# --- render_ascii -----------------------------------------------------------


def test_render_ascii_connectors_and_snippets():
    sheet = _sheet(A1="=B1+C1", B1="5", C1="=B1*2")
    root = trace_precedents(sheet, *parse_a1("A1"))
    out = render_ascii(root)

    # Root line shows A1 with its formula snippet, flush-left (no connector).
    lines = out.splitlines()
    assert lines[0] == "A1 =B1+C1"
    # Box-drawing connectors present.
    assert "├─" in out
    assert "└─" in out
    # The snippets ride along.
    assert "B1 5" in out
    assert "C1 =B1*2" in out


def test_render_ascii_marks_cycle():
    sheet = _sheet(A1="=A1")
    out = render_ascii(trace_precedents(sheet, *parse_a1("A1")))
    assert "(cycle)" in out


def test_render_ascii_guide_lines():
    # Two children where the first has its own child forces a │ guide line.
    sheet = _sheet(A1="=B1+C1", B1="=D1", C1="9", D1="1")
    out = render_ascii(trace_precedents(sheet, *parse_a1("A1")))
    assert "│" in out
