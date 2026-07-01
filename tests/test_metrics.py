"""Tests for :mod:`abax.core.science.metrics` (pure-stdlib model-evaluation utilities)."""

from __future__ import annotations

import pytest

from abax.core.science.metrics import (
    MetricsError,
    accuracy,
    auc,
    confusion_matrix,
    cross_val_score,
    kfold_indices,
    precision_recall_f1,
    roc_curve,
    train_test_split,
)

# --------------------------------------------------------------------------- #
# train_test_split
# --------------------------------------------------------------------------- #

def test_train_test_split_sizes_and_partition():
    X = list(range(8))
    y = [i % 2 for i in range(8)]
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_frac=0.25, seed=0)

    assert len(X_train) == 6
    assert len(X_test) == 2
    assert len(y_train) == 6
    assert len(y_test) == 2

    # Disjoint and covering.
    assert set(X_train).isdisjoint(set(X_test))
    assert set(X_train) | set(X_test) == set(X)

    # Labels travel with their samples.
    for xi, yi in zip(X_train, y_train):
        assert yi == xi % 2
    for xi, yi in zip(X_test, y_test):
        assert yi == xi % 2


def test_train_test_split_reproducible():
    X = list(range(8))
    y = list(range(8))
    a = train_test_split(X, y, test_frac=0.25, seed=42)
    b = train_test_split(X, y, test_frac=0.25, seed=42)
    assert a == b
    c = train_test_split(X, y, test_frac=0.25, seed=7)
    assert c != a  # different seed -> different shuffle (extremely likely)


def test_train_test_split_errors():
    with pytest.raises(MetricsError):
        train_test_split([1, 2, 3], [1, 2], test_frac=0.25)
    with pytest.raises(MetricsError):
        train_test_split([1, 2, 3], [1, 2, 3], test_frac=0.0)
    with pytest.raises(MetricsError):
        train_test_split([1, 2, 3], [1, 2, 3], test_frac=1.0)
    with pytest.raises(MetricsError):
        train_test_split([1], [1], test_frac=0.25)


# --------------------------------------------------------------------------- #
# kfold_indices
# --------------------------------------------------------------------------- #

def test_kfold_indices_partition():
    pairs = kfold_indices(10, k=5, seed=0)
    assert len(pairs) == 5

    seen: list[int] = []
    for train_idx, test_idx in pairs:
        assert len(test_idx) == 2
        # Train is exactly the complement of test.
        assert set(train_idx) == set(range(10)) - set(test_idx)
        assert set(train_idx).isdisjoint(set(test_idx))
        seen.extend(test_idx)

    # Every index appears in exactly one test set.
    assert sorted(seen) == list(range(10))


def test_kfold_indices_uneven():
    pairs = kfold_indices(11, k=5, seed=1)
    sizes = sorted(len(test) for _, test in pairs)
    assert sizes == [2, 2, 2, 2, 3]
    seen = [i for _, test in pairs for i in test]
    assert sorted(seen) == list(range(11))


def test_kfold_indices_errors():
    with pytest.raises(MetricsError):
        kfold_indices(10, k=1)
    with pytest.raises(MetricsError):
        kfold_indices(3, k=5)


# --------------------------------------------------------------------------- #
# confusion_matrix / accuracy
# --------------------------------------------------------------------------- #

def test_confusion_matrix_basic():
    labels, matrix = confusion_matrix([0, 0, 1, 1], [0, 1, 1, 1])
    assert labels == [0, 1]
    # true=0: one pred 0, one pred 1 -> [1, 1]
    # true=1: zero pred 0, two pred 1 -> [0, 2]
    assert matrix == [[1, 1], [0, 2]]


def test_confusion_matrix_explicit_labels():
    labels, matrix = confusion_matrix([0, 0, 1, 1], [0, 1, 1, 1], labels=[1, 0])
    assert labels == [1, 0]
    # true=1 row first: [2, 0]; true=0 row: [1, 1]
    assert matrix == [[2, 0], [1, 1]]


def test_confusion_matrix_error():
    with pytest.raises(MetricsError):
        confusion_matrix([0, 1], [0])


def test_accuracy():
    assert accuracy([0, 0, 1, 1], [0, 1, 1, 1]) == pytest.approx(0.75)
    assert accuracy([1, 1, 1], [1, 1, 1]) == pytest.approx(1.0)
    with pytest.raises(MetricsError):
        accuracy([1, 2], [1])


# --------------------------------------------------------------------------- #
# precision_recall_f1
# --------------------------------------------------------------------------- #

def test_prf_binary():
    p, r, f1 = precision_recall_f1([0, 0, 1, 1], [0, 1, 1, 1], positive=1)
    assert p == pytest.approx(2 / 3)
    assert r == pytest.approx(1.0)
    assert f1 == pytest.approx(0.8)


def test_prf_default_positive_is_max_label():
    # Default positive label is max -> 1, same as explicit above.
    p, r, f1 = precision_recall_f1([0, 0, 1, 1], [0, 1, 1, 1])
    assert p == pytest.approx(2 / 3)
    assert r == pytest.approx(1.0)
    assert f1 == pytest.approx(0.8)


def test_prf_macro():
    p, r, f1 = precision_recall_f1([0, 0, 1, 1], [0, 1, 1, 1], average="macro")
    # class 0: tp=1, fp=0, fn=1 -> precision 1.0, recall 0.5, f1 2/3
    # class 1: tp=2, fp=1, fn=0 -> precision 2/3, recall 1.0, f1 0.8
    assert p == pytest.approx((1.0 + 2 / 3) / 2)
    assert r == pytest.approx((0.5 + 1.0) / 2)
    assert f1 == pytest.approx(((2 / 3) + 0.8) / 2)


def test_prf_errors():
    with pytest.raises(MetricsError):
        precision_recall_f1([0, 1], [0])
    with pytest.raises(MetricsError):
        precision_recall_f1([0, 1], [0, 1], average="weighted")


# --------------------------------------------------------------------------- #
# roc_curve / auc
# --------------------------------------------------------------------------- #

def test_roc_auc_perfect():
    y_true = [0, 0, 1, 1]
    scores = [0.1, 0.2, 0.8, 0.9]  # ranking matches labels
    fpr, tpr, thresholds = roc_curve(y_true, scores)

    assert fpr[0] == 0.0 and tpr[0] == 0.0
    assert fpr[-1] == pytest.approx(1.0)
    assert tpr[-1] == pytest.approx(1.0)
    # thresholds sorted by decreasing threshold.
    finite = thresholds[1:]
    assert finite == sorted(finite, reverse=True)
    # All rates within [0, 1].
    assert all(0.0 <= v <= 1.0 for v in fpr)
    assert all(0.0 <= v <= 1.0 for v in tpr)

    assert auc(fpr, tpr) == pytest.approx(1.0)


def test_roc_auc_reversed():
    y_true = [0, 0, 1, 1]
    scores = [0.9, 0.8, 0.2, 0.1]  # reversed ranking
    fpr, tpr, _ = roc_curve(y_true, scores)
    assert auc(fpr, tpr) == pytest.approx(0.0)
    assert all(0.0 <= v <= 1.0 for v in fpr)
    assert all(0.0 <= v <= 1.0 for v in tpr)


def test_roc_curve_errors():
    with pytest.raises(MetricsError):
        roc_curve([0, 1], [0.5])
    with pytest.raises(MetricsError):
        roc_curve([0, 1, 2], [0.1, 0.2, 0.3])  # not binary
    with pytest.raises(MetricsError):
        roc_curve([1, 1, 1], [0.1, 0.2, 0.3])  # no negatives


def test_auc_simple():
    # Unit square triangle: area 0.5.
    assert auc([0.0, 1.0], [0.0, 1.0]) == pytest.approx(0.5)
    assert auc([0.0, 1.0], [1.0, 1.0]) == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# cross_val_score
# --------------------------------------------------------------------------- #

class MajorityClassModel:
    """Trivial classifier predicting the most common training label."""

    def __init__(self) -> None:
        self.majority = None

    def fit(self, X, y) -> None:
        counts: dict = {}
        for label in y:
            counts[label] = counts.get(label, 0) + 1
        self.majority = max(counts, key=counts.get)

    def predict(self, X) -> list:
        return [self.majority for _ in X]


def test_cross_val_score():
    X = list(range(10))
    y = [0, 1] * 5  # balanced 2-class
    scores = cross_val_score(MajorityClassModel, X, y, k=5, seed=0)
    assert len(scores) == 5
    assert all(0.0 <= s <= 1.0 for s in scores)


def test_cross_val_score_error():
    with pytest.raises(MetricsError):
        cross_val_score(MajorityClassModel, [1, 2, 3], [1, 2], k=2)
