"""Command palette: fuzzy scoring + the rofi/dmenu-style filter widget."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("qcell.gui._qtcompat")

from qcell.gui._qtcompat import QApplication  # noqa: E402
from qcell.gui.command_palette import CommandPalette, fuzzy_score  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# --- fuzzy_score (pure, no Qt) -------------------------------------------
def test_fuzzy_score_empty_query_matches_everything():
    assert fuzzy_score("", "anything") == 0.0


def test_fuzzy_score_non_subsequence_misses():
    assert fuzzy_score("xyz", "Save") is None
    assert fuzzy_score("sav", "New") is None


def test_fuzzy_score_subsequence_matches():
    assert fuzzy_score("save", "Save As…") is not None
    assert fuzzy_score("pgb", "Pivot / group-by") is not None   # scattered but in order


def test_fuzzy_score_prefers_word_starts():
    # 'pg' as two word-initials beats a scattered in-word match.
    assert fuzzy_score("pg", "Pivot / group-by") > fuzzy_score("pg", "Paging")


# --- CommandPalette widget ------------------------------------------------
def _actions():
    calls = {"new": 0, "save": 0, "saveas": 0, "pivot": 0}

    def mk(key):
        def _run():
            calls[key] += 1
        return _run

    actions = {
        "New": mk("new"),
        "Save": mk("save"),
        "Save As…": mk("saveas"),
        "Pivot / group-by…": mk("pivot"),
    }
    return actions, calls


def test_palette_lists_all_initially(app):
    actions, _ = _actions()
    pal = CommandPalette(None, actions)
    assert pal._list.count() == len(actions)


def test_palette_filters_on_query(app):
    actions, _ = _actions()
    pal = CommandPalette(None, actions)
    pal._input.setText("sa")                  # emits textChanged -> _refilter
    labels = [pal._list.item(i).text() for i in range(pal._list.count())]
    assert labels == ["Save", "Save As…"] or set(labels) == {"Save", "Save As…"}


def test_palette_accept_runs_highlighted(app):
    actions, calls = _actions()
    pal = CommandPalette(None, actions)
    pal._input.setText("pivot")
    pal._accept_current()
    assert pal.chosen() is actions["Pivot / group-by…"]
    pal.chosen()()
    assert calls["pivot"] == 1


def test_palette_move_clamps(app):
    actions, _ = _actions()
    pal = CommandPalette(None, actions)
    pal._move(100)
    assert pal._list.currentRow() == pal._list.count() - 1
    pal._move(-100)
    assert pal._list.currentRow() == 0
