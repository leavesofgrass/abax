"""Tests for abax.core.science.trees — CART decision tree + random forest."""

from __future__ import annotations

import pytest

from abax.core.science.trees import (
    DecisionTreeClassifier,
    RandomForestClassifier,
    TreeError,
)


def _accuracy(pred: list, y: list) -> float:
    return sum(p == t for p, t in zip(pred, y)) / len(y)


# --------------------------------------------------------------------------- #
# Decision tree.
# --------------------------------------------------------------------------- #

def test_linearly_separable_train_and_holdout():
    X = [
        [0.0, 0.0], [0.5, 0.2], [0.1, 0.4], [0.3, 0.1],
        [5.0, 5.0], [4.8, 5.2], [5.1, 4.7], [4.9, 5.3],
    ]
    y = ["A", "A", "A", "A", "B", "B", "B", "B"]
    clf = DecisionTreeClassifier().fit(X, y)
    assert _accuracy(clf.predict(X), y) == 1.0
    # held-out point near (0, 0) -> A
    assert clf.predict_one([0.2, 0.2]) == "A"
    assert clf.predict([[4.9, 4.9]]) == ["B"]


def test_threshold_rule_recovered():
    # y = 1 if x0 > 2 else 0
    X = [[0.0], [1.0], [2.0], [3.0], [4.0], [5.0]]
    y = [0, 0, 0, 1, 1, 1]
    clf = DecisionTreeClassifier().fit(X, y)
    assert _accuracy(clf.predict(X), y) == 1.0
    assert clf.depth() in (1, 2)


def test_xor_needs_depth_two():
    base = [
        ([0.0, 0.0], 0),
        ([0.0, 1.0], 1),
        ([1.0, 0.0], 1),
        ([1.0, 1.0], 0),
    ]
    X: list[list[float]] = []
    y: list[int] = []
    for _ in range(3):
        for row, label in base:
            X.append(list(row))
            y.append(label)
    clf = DecisionTreeClassifier().fit(X, y)
    assert _accuracy(clf.predict(X), y) == 1.0
    assert clf.depth() >= 2


def test_entropy_criterion_separable():
    X = [
        [0.0, 0.0], [0.5, 0.2], [0.1, 0.4], [0.3, 0.1],
        [5.0, 5.0], [4.8, 5.2], [5.1, 4.7], [4.9, 5.3],
    ]
    y = ["A", "A", "A", "A", "B", "B", "B", "B"]
    clf = DecisionTreeClassifier(criterion="entropy").fit(X, y)
    assert _accuracy(clf.predict(X), y) == 1.0


def test_max_depth_one_is_a_stump():
    base = [
        ([0.0, 0.0], 0),
        ([0.0, 1.0], 1),
        ([1.0, 0.0], 1),
        ([1.0, 1.0], 0),
    ]
    X = [list(r) for r, _ in base] * 3
    y = [lbl for _, lbl in base] * 3
    clf = DecisionTreeClassifier(max_depth=1).fit(X, y)
    assert clf.depth() == 1


# --------------------------------------------------------------------------- #
# Random forest.
# --------------------------------------------------------------------------- #

def test_forest_separable_and_reproducible():
    X = [
        [0.0, 0.0], [0.5, 0.2], [0.1, 0.4], [0.3, 0.1],
        [5.0, 5.0], [4.8, 5.2], [5.1, 4.7], [4.9, 5.3],
    ]
    y = ["A", "A", "A", "A", "B", "B", "B", "B"]
    f1 = RandomForestClassifier(seed=0).fit(X, y)
    assert _accuracy(f1.predict(X), y) == 1.0
    f2 = RandomForestClassifier(seed=0).fit(X, y)
    assert f1.predict(X) == f2.predict(X)


# --------------------------------------------------------------------------- #
# Error paths.
# --------------------------------------------------------------------------- #

def test_empty_X_raises():
    with pytest.raises(TreeError):
        DecisionTreeClassifier().fit([], [])


def test_ragged_X_raises():
    with pytest.raises(TreeError):
        DecisionTreeClassifier().fit([[1.0, 2.0], [3.0]], [0, 1])


def test_length_mismatch_raises():
    with pytest.raises(TreeError):
        DecisionTreeClassifier().fit([[1.0], [2.0]], [0])


def test_unknown_criterion_raises():
    with pytest.raises(TreeError):
        DecisionTreeClassifier(criterion="nope")


def test_forest_error_paths():
    with pytest.raises(TreeError):
        RandomForestClassifier().fit([], [])
    with pytest.raises(TreeError):
        RandomForestClassifier().fit([[1.0], [2.0]], [0])
