"""Tests for abax.core.science.bayes (Gaussian + Multinomial naive Bayes)."""

from __future__ import annotations

import pytest

from abax.core.science.bayes import BayesError, GaussianNB, MultinomialNB

# --------------------------------------------------------------------------- #
# GaussianNB.
# --------------------------------------------------------------------------- #

def _blobs_2d():
    """Two well-separated 2-D Gaussian-ish blobs labelled 0 and 1."""
    X = [
        [0.0, 0.0], [0.2, -0.1], [-0.1, 0.2], [0.1, 0.1], [-0.2, -0.2],
        [10.0, 10.0], [10.2, 9.9], [9.8, 10.1], [10.1, 10.2], [9.9, 9.8],
    ]
    y = [0, 0, 0, 0, 0, 1, 1, 1, 1, 1]
    return X, y


def test_gaussian_train_accuracy_and_query():
    X, y = _blobs_2d()
    clf = GaussianNB().fit(X, y)

    preds = clf.predict(X)
    correct = sum(1 for p, t in zip(preds, y) if p == t)
    assert correct / len(y) >= 0.95

    # A query clearly in blob 1.
    assert clf.predict([[10.0, 10.0]]) == [1]
    assert clf.predict([[0.0, 0.0]]) == [0]


def test_gaussian_predict_proba_sums_and_dominance():
    X, y = _blobs_2d()
    clf = GaussianNB().fit(X, y)

    proba = clf.predict_proba([[10.0, 10.0], [0.0, 0.0]])
    for row in proba:
        assert sum(row) == pytest.approx(1.0)

    cls = clf.classes()
    # Column for class 1 dominates the first query; class 0 the second.
    assert proba[0][cls.index(1)] > 0.99
    assert proba[1][cls.index(0)] > 0.99


def test_gaussian_classes_sorted():
    X = [[0.0], [1.0], [10.0], [11.0]]
    y = [2, 2, 0, 0]
    clf = GaussianNB().fit(X, y)
    assert clf.classes() == [0, 2]


def test_gaussian_1d_separated():
    X = [[0.0], [0.5], [1.0], [20.0], [20.5], [21.0]]
    y = [0, 0, 0, 1, 1, 1]
    clf = GaussianNB().fit(X, y)
    assert clf.predict(X) == y


def test_gaussian_constant_feature_no_crash():
    # Second feature is constant (zero variance) within and across classes.
    X = [
        [0.0, 5.0], [0.5, 5.0], [1.0, 5.0],
        [10.0, 5.0], [10.5, 5.0], [11.0, 5.0],
    ]
    y = [0, 0, 0, 1, 1, 1]
    clf = GaussianNB().fit(X, y)
    proba = clf.predict_proba(X)
    for row in proba:
        assert sum(row) == pytest.approx(1.0)
    assert clf.predict([[10.5, 5.0]]) == [1]


# --------------------------------------------------------------------------- #
# MultinomialNB.
# --------------------------------------------------------------------------- #

def _bow():
    """Bag-of-words counts; vocab=[cat, dog, money, stock]. Two classes."""
    #              cat dog money stock
    X = [
        [3, 2, 0, 0],   # pets
        [2, 4, 0, 0],   # pets
        [4, 1, 0, 0],   # pets
        [0, 0, 3, 2],   # finance
        [0, 0, 2, 4],   # finance
        [0, 0, 4, 1],   # finance
    ]
    y = ["pets", "pets", "pets", "finance", "finance", "finance"]
    return X, y


def test_multinomial_predictions():
    X, y = _bow()
    clf = MultinomialNB().fit(X, y)
    assert clf.predict(X) == y
    # Clear pets / finance documents.
    assert clf.predict([[5, 5, 0, 0]]) == ["pets"]
    assert clf.predict([[0, 0, 5, 5]]) == ["finance"]


def test_multinomial_predict_proba_sums():
    X, y = _bow()
    clf = MultinomialNB().fit(X, y)
    proba = clf.predict_proba([[5, 5, 0, 0], [0, 0, 5, 5]])
    for row in proba:
        assert sum(row) == pytest.approx(1.0)
    cls = clf.classes()
    assert proba[0][cls.index("pets")] > 0.5
    assert proba[1][cls.index("finance")] > 0.5


def test_multinomial_classes_sorted():
    X, y = _bow()
    clf = MultinomialNB().fit(X, y)
    assert clf.classes() == ["finance", "pets"]


def test_multinomial_negative_raises():
    X = [[1, 2], [3, -1]]
    y = [0, 1]
    with pytest.raises(BayesError):
        MultinomialNB().fit(X, y)


def test_multinomial_negative_predict_raises():
    X, y = _bow()
    clf = MultinomialNB().fit(X, y)
    with pytest.raises(BayesError):
        clf.predict([[-1, 0, 0, 0]])


# --------------------------------------------------------------------------- #
# Error paths shared by both.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("cls", [GaussianNB, MultinomialNB])
def test_empty_X_raises(cls):
    with pytest.raises(BayesError):
        cls().fit([], [])


@pytest.mark.parametrize("cls", [GaussianNB, MultinomialNB])
def test_ragged_X_raises(cls):
    with pytest.raises(BayesError):
        cls().fit([[1, 2], [3]], [0, 1])


@pytest.mark.parametrize("cls", [GaussianNB, MultinomialNB])
def test_len_mismatch_raises(cls):
    with pytest.raises(BayesError):
        cls().fit([[1, 2], [3, 4]], [0])


@pytest.mark.parametrize("cls", [GaussianNB, MultinomialNB])
def test_unfitted_predict_raises(cls):
    with pytest.raises(BayesError):
        cls().predict([[1, 2]])


@pytest.mark.parametrize("cls", [GaussianNB, MultinomialNB])
def test_wrong_feature_count_raises(cls):
    clf = cls().fit([[1, 2], [3, 4], [10, 11], [12, 13]], [0, 0, 1, 1])
    with pytest.raises(BayesError):
        clf.predict([[1, 2, 3]])
