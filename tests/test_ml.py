"""Tests for abax.core.science.ml — no-numpy machine learning."""

from __future__ import annotations

import math

import pytest

from abax.core.science import ml

# --------------------------------------------------------------------------- #
# Linear regression.
# --------------------------------------------------------------------------- #

def test_linear_regression_recovers_coefficients():
    X = [
        [1.0, 1.0],
        [2.0, 1.0],
        [3.0, 2.0],
        [4.0, 5.0],
        [1.0, 7.0],
        [6.0, 2.0],
    ]
    # y = 2*x1 + 3*x2 + 1, exactly.
    y = [2 * r[0] + 3 * r[1] + 1 for r in X]

    coeffs, intercept = ml.linear_regression(X, y)
    assert coeffs[0] == pytest.approx(2.0, abs=1e-6)
    assert coeffs[1] == pytest.approx(3.0, abs=1e-6)
    assert intercept == pytest.approx(1.0, abs=1e-6)

    y_pred = ml.predict_linear(coeffs, intercept, X)
    assert ml.r_squared(y, y_pred) == pytest.approx(1.0, abs=1e-9)


def test_predict_linear_values():
    coeffs = [2.0, 3.0]
    intercept = 1.0
    X = [[1.0, 1.0], [0.0, 0.0]]
    assert ml.predict_linear(coeffs, intercept, X) == pytest.approx([6.0, 1.0])


def test_r_squared_perfect_and_zero_variance():
    assert ml.r_squared([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)
    # Constant target, perfect prediction.
    assert ml.r_squared([5.0, 5.0], [5.0, 5.0]) == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Standardize.
# --------------------------------------------------------------------------- #

def test_standardize_zero_mean_unit_std():
    X = [[1.0, 10.0], [2.0, 20.0], [3.0, 30.0], [4.0, 40.0]]
    X_std, means, stds = ml.standardize(X)
    n = len(X)
    for j in range(2):
        col = [X_std[i][j] for i in range(n)]
        mean = sum(col) / n
        var = sum((v - mean) ** 2 for v in col) / n
        assert mean == pytest.approx(0.0, abs=1e-9)
        assert math.sqrt(var) == pytest.approx(1.0, abs=1e-9)
    assert means == pytest.approx([2.5, 25.0])


def test_standardize_zero_variance_column():
    X = [[5.0, 1.0], [5.0, 2.0], [5.0, 3.0]]
    X_std, means, stds = ml.standardize(X)
    assert [row[0] for row in X_std] == pytest.approx([0.0, 0.0, 0.0])
    assert stds[0] == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# PCA.
# --------------------------------------------------------------------------- #

def test_pca_along_diagonal():
    # Data lying mostly along y = x.
    X = [
        [-2.0, -2.1],
        [-1.0, -0.9],
        [0.0, 0.1],
        [1.0, 1.0],
        [2.0, 1.9],
        [3.0, 3.1],
    ]
    components, ratios, transformed = ml.pca(X)

    assert len(components) == 2
    assert len(transformed) == len(X)
    assert len(transformed[0]) == 2

    # First component aligned with [1,1]/sqrt(2) up to sign.
    pc1 = components[0]
    expected = [1 / math.sqrt(2), 1 / math.sqrt(2)]
    aligned = all(
        pc1[i] == pytest.approx(expected[i], abs=1e-2) for i in range(2)
    ) or all(
        pc1[i] == pytest.approx(-expected[i], abs=1e-2) for i in range(2)
    )
    assert aligned

    assert ratios[0] > 0.95
    assert sum(ratios) == pytest.approx(1.0, abs=1e-9)


def test_pca_n_components():
    X = [[1.0, 2.0, 3.0], [4.0, 5.0, 7.0], [7.0, 8.0, 8.0], [2.0, 1.0, 0.0]]
    components, ratios, transformed = ml.pca(X, n_components=1)
    assert len(components) == 1
    assert len(transformed[0]) == 1
    assert len(ratios) == 1
    assert 0.0 <= ratios[0] <= 1.0


# --------------------------------------------------------------------------- #
# k-NN.
# --------------------------------------------------------------------------- #

def test_knn_classify_separable():
    train_X = [
        [0.0, 0.0], [0.5, 0.2], [0.1, 0.4],
        [5.0, 5.0], [4.8, 5.2], [5.2, 4.9],
    ]
    train_y = [0, 0, 0, 1, 1, 1]

    assert ml.knn_classify(train_X, train_y, [0.2, 0.1], k=3) == 0
    assert ml.knn_classify(train_X, train_y, [5.1, 5.0], k=3) == 1


def test_knn_predict_maps_list():
    train_X = [[0.0], [1.0], [10.0], [11.0]]
    train_y = [0, 0, 1, 1]
    out = ml.knn_predict(train_X, train_y, [[0.5], [10.5]], k=1)
    assert out == [0, 1]


# --------------------------------------------------------------------------- #
# Logistic regression.
# --------------------------------------------------------------------------- #

def test_logistic_regression_separable():
    X = [[x] for x in (-3.0, -2.0, -1.0, -0.5, 0.5, 1.0, 2.0, 3.0)]
    y = [0, 0, 0, 0, 1, 1, 1, 1]

    weights, bias = ml.logistic_regression(X, y, lr=0.5, epochs=2000)

    probas = ml.logistic_predict_proba(weights, bias, X)
    assert all(0.0 < p < 1.0 for p in probas)

    preds = ml.logistic_predict(weights, bias, X)
    accuracy = sum(1 for p, t in zip(preds, y) if p == t) / len(y)
    assert accuracy >= 0.9


def test_logistic_regression_2d_separable():
    X = [
        [0.0, 0.0], [1.0, 0.5], [0.5, 1.0], [1.0, 1.0],
        [5.0, 5.0], [6.0, 5.5], [5.5, 6.0], [6.0, 6.0],
    ]
    y = [0, 0, 0, 0, 1, 1, 1, 1]
    weights, bias = ml.logistic_regression(X, y, lr=0.5, epochs=2000)
    preds = ml.logistic_predict(weights, bias, X)
    accuracy = sum(1 for p, t in zip(preds, y) if p == t) / len(y)
    assert accuracy >= 0.9


def test_logistic_predict_thresholds():
    weights, bias = [1000.0], -500.0  # very steep boundary near x=0.5
    assert ml.logistic_predict(weights, bias, [[0.0], [1.0]]) == [0, 1]


# --------------------------------------------------------------------------- #
# Error paths.
# --------------------------------------------------------------------------- #

def test_empty_X_raises():
    with pytest.raises(ml.MLError):
        ml.standardize([])
    with pytest.raises(ml.MLError):
        ml.pca([])


def test_ragged_X_raises():
    with pytest.raises(ml.MLError):
        ml.standardize([[1.0, 2.0], [3.0]])


def test_shape_mismatch_raises():
    with pytest.raises(ml.MLError):
        ml.linear_regression([[1.0], [2.0]], [1.0])  # y too short


def test_bad_n_components_raises():
    X = [[1.0, 2.0], [3.0, 4.0]]
    with pytest.raises(ml.MLError):
        ml.pca(X, n_components=0)
    with pytest.raises(ml.MLError):
        ml.pca(X, n_components=5)


def test_logistic_non_binary_labels_raises():
    with pytest.raises(ml.MLError):
        ml.logistic_regression([[0.0], [1.0]], [0, 2])
