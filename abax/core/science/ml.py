"""Lightweight machine learning — a no-numpy ML module.

Everything here is implemented by hand with the standard library only
(``math``, no numpy), reusing the in-house linear-algebra engines
(:mod:`abax.core.science.eigen` for the symmetric eigensystem and
:mod:`abax.core.science.matrix` for linear solves). Data is plain Python:

* ``X`` is a ``list[list[float]]`` — rows are samples, columns are features.
* ``y`` is a ``list[float]`` (targets) or ``list[int]`` (class labels).

The surface covers the classic teaching staples:

* :func:`standardize` — column-wise z-score normalisation
* :func:`pca` — principal component analysis (covariance eigendecomposition)
* :func:`linear_regression` / :func:`predict_linear` / :func:`r_squared`
* :func:`knn_classify` / :func:`knn_predict` — k-nearest-neighbours voting
* :func:`logistic_regression` and friends — binary logistic regression (GD)

Bad input (empty/ragged ``X``, shape mismatches, out-of-range parameters,
singular systems) raises :class:`MLError`.

Pure stdlib → core.
"""

from __future__ import annotations

import math

from abax.core.science import eigen, matrix

Matrix = list[list[float]]
Vector = list[float]

EPS = 1e-12


class MLError(Exception):
    """Raised for invalid data, shape mismatches, or numerical failure."""


# --------------------------------------------------------------------------- #
# Validation helpers.
# --------------------------------------------------------------------------- #

def _validate_X(X: Matrix) -> tuple[int, int]:
    """Validate that ``X`` is a non-empty rectangular numeric matrix.

    Returns ``(n_samples, n_features)``. Raises :class:`MLError` otherwise.
    """
    if not isinstance(X, list) or not X:
        raise MLError("X must be a non-empty list of rows")
    n_features: int | None = None
    for row in X:
        if not isinstance(row, list) or not row:
            raise MLError("each row of X must be a non-empty list")
        if n_features is None:
            n_features = len(row)
        elif len(row) != n_features:
            raise MLError("X is ragged (rows of differing length)")
        for value in row:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise MLError("X entries must be numeric")
    assert n_features is not None
    return len(X), n_features


def _validate_y(y: Vector, n_samples: int) -> None:
    """Validate that ``y`` is a numeric vector of length ``n_samples``."""
    if not isinstance(y, list) or len(y) != n_samples:
        raise MLError("y must be a vector with one entry per row of X")
    for value in y:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MLError("y entries must be numeric")


# --------------------------------------------------------------------------- #
# Standardisation.
# --------------------------------------------------------------------------- #

def standardize(X: Matrix) -> tuple[Matrix, Vector, Vector]:
    """Column-wise z-score normalisation.

    Returns ``(X_std, means, stds)`` where each column of ``X_std`` has zero
    mean and (population) unit variance. A zero-variance column is mapped to
    all zeros (its ``std`` is treated as ``1`` to avoid division by zero, but
    the reported ``stds`` entry is the true ``0``).

    Raises :class:`MLError` on empty/ragged ``X``.
    """
    n, m = _validate_X(X)
    means = [0.0] * m
    stds = [0.0] * m
    for j in range(m):
        col = [float(X[i][j]) for i in range(n)]
        mean = sum(col) / n
        var = sum((v - mean) ** 2 for v in col) / n
        means[j] = mean
        stds[j] = math.sqrt(var)

    X_std: Matrix = []
    for i in range(n):
        row: Vector = []
        for j in range(m):
            denom = stds[j] if stds[j] > EPS else 1.0
            row.append((float(X[i][j]) - means[j]) / denom)
        X_std.append(row)
    return X_std, means, stds


# --------------------------------------------------------------------------- #
# Principal component analysis.
# --------------------------------------------------------------------------- #

def pca(
    X: Matrix, n_components: int | None = None
) -> tuple[Matrix, Vector, Matrix]:
    """Principal component analysis via covariance eigendecomposition.

    The columns of ``X`` are centred, the covariance matrix ``Cᵀ·C/(n-1)`` of
    the centred data is formed, and :func:`eigen.eigen_symmetric` provides its
    eigenpairs (eigenvectors come back as **columns**, in descending eigenvalue
    order). The top ``n_components`` (default: all features) are kept.

    Returns ``(components, explained_variance_ratio, transformed)``:

    * ``components`` — the principal axes as **rows** (descending order),
    * ``explained_variance_ratio`` — the kept components' share of total
      variance (the full ratios sum to ~1; the kept slice is reported),
    * ``transformed`` — the centred ``X`` projected onto ``components``.

    Raises :class:`MLError` on empty/ragged ``X`` or ``n_components`` out of
    the range ``1..n_features``.
    """
    n, m = _validate_X(X)
    if n_components is None:
        n_components = m
    if not isinstance(n_components, int) or n_components < 1 or n_components > m:
        raise MLError("n_components must be an int in 1..n_features")

    # Centre each column.
    means = [sum(X[i][j] for i in range(n)) / n for j in range(m)]
    centered = [[float(X[i][j]) - means[j] for j in range(m)] for i in range(n)]

    # Covariance matrix Cᵀ·C / (n - 1).
    denom = (n - 1) if n > 1 else 1
    cov: Matrix = [[0.0] * m for _ in range(m)]
    for a in range(m):
        for b in range(a, m):
            s = sum(centered[i][a] * centered[i][b] for i in range(n))
            val = s / denom
            cov[a][b] = val
            cov[b][a] = val

    eigvals, eigvecs = eigen.eigen_symmetric(cov)

    total = sum(eigvals)
    if abs(total) < EPS:
        ratios_all = [0.0] * m
    else:
        ratios_all = [v / total for v in eigvals]

    # Eigenvectors are columns; a component is a column -> transpose to a row.
    components = [
        [eigvecs[r][c] for r in range(m)] for c in range(n_components)
    ]
    explained_variance_ratio = ratios_all[:n_components]

    # Project centred data onto the kept components: transformed = centered @ Vᵀ.
    transformed: Matrix = []
    for i in range(n):
        row = [
            sum(centered[i][k] * components[c][k] for k in range(m))
            for c in range(n_components)
        ]
        transformed.append(row)

    return components, explained_variance_ratio, transformed


# --------------------------------------------------------------------------- #
# Multiple linear regression.
# --------------------------------------------------------------------------- #

def linear_regression(X: Matrix, y: Vector) -> tuple[Vector, float]:
    """Multiple linear regression via the normal equations.

    Augments ``X`` with a column of ones (the intercept) and solves
    ``(AᵀA) b = Aᵀy`` with :func:`matrix.solve`. Returns
    ``(coefficients_per_feature, intercept)``.

    Raises :class:`MLError` on a shape mismatch or a singular normal-equation
    system.
    """
    n, m = _validate_X(X)
    _validate_y(y, n)

    # Augmented design matrix A = [X | 1].
    A = [[float(X[i][j]) for j in range(m)] + [1.0] for i in range(n)]
    p = m + 1

    # Normal equations: AᵀA b = Aᵀy.
    ata: Matrix = [[0.0] * p for _ in range(p)]
    aty: Vector = [0.0] * p
    for a in range(p):
        for b in range(a, p):
            s = sum(A[i][a] * A[i][b] for i in range(n))
            ata[a][b] = s
            ata[b][a] = s
        aty[a] = sum(A[i][a] * float(y[i]) for i in range(n))

    try:
        beta = matrix.solve(ata, aty)
    except matrix.MatrixError as exc:
        raise MLError(f"linear_regression: {exc}") from exc

    coeffs = beta[:m]
    intercept = beta[m]
    return coeffs, intercept


def predict_linear(coeffs: Vector, intercept: float, X: Matrix) -> Vector:
    """Return the linear-model predictions ``X·coeffs + intercept``.

    Raises :class:`MLError` if a row's width does not match ``len(coeffs)``.
    """
    n, m = _validate_X(X)
    if len(coeffs) != m:
        raise MLError("predict_linear: coeffs length must match n_features")
    out: Vector = []
    for i in range(n):
        out.append(
            sum(float(X[i][j]) * coeffs[j] for j in range(m)) + float(intercept)
        )
    return out


def r_squared(y_true: Vector, y_pred: Vector) -> float:
    """Return the coefficient of determination ``R²``.

    Raises :class:`MLError` if the vectors differ in length or are empty.
    """
    if not isinstance(y_true, list) or not isinstance(y_pred, list):
        raise MLError("r_squared: inputs must be lists")
    if len(y_true) != len(y_pred) or not y_true:
        raise MLError("r_squared: vectors must be non-empty and equal length")
    mean = sum(float(v) for v in y_true) / len(y_true)
    ss_tot = sum((float(v) - mean) ** 2 for v in y_true)
    ss_res = sum((float(t) - float(p)) ** 2 for t, p in zip(y_true, y_pred))
    if ss_tot < EPS:
        # No variance in the target: perfect iff residuals vanish.
        return 1.0 if ss_res < EPS else 0.0
    return 1.0 - ss_res / ss_tot


# --------------------------------------------------------------------------- #
# k-nearest-neighbours classification.
# --------------------------------------------------------------------------- #

def _euclidean2(a: Vector, b: Vector) -> float:
    """Return the squared euclidean distance between two equal-length vectors."""
    return sum((float(a[i]) - float(b[i])) ** 2 for i in range(len(a)))


def knn_classify(
    train_X: Matrix, train_y: Vector, query: Vector, k: int = 3
) -> float:
    """Classify ``query`` by majority vote among its ``k`` nearest neighbours.

    Distance is euclidean. Ties in the vote are broken in favour of the class
    whose nearest member is closer to ``query``.

    Raises :class:`MLError` on empty/ragged training data, a shape mismatch, or
    a bad ``k``.
    """
    n, m = _validate_X(train_X)
    _validate_y(train_y, n)
    if not isinstance(query, list) or len(query) != m:
        raise MLError("knn_classify: query length must match n_features")
    if not isinstance(k, int) or k < 1:
        raise MLError("knn_classify: k must be a positive integer")
    k = min(k, n)

    dists = [(_euclidean2(train_X[i], query), float(train_y[i])) for i in range(n)]
    dists.sort(key=lambda d: d[0])
    nearest = dists[:k]

    votes: dict[float, int] = {}
    nearest_dist: dict[float, float] = {}
    for dist, label in nearest:
        votes[label] = votes.get(label, 0) + 1
        if label not in nearest_dist or dist < nearest_dist[label]:
            nearest_dist[label] = dist

    # Most votes, then nearest member, then smaller label for determinism.
    best = min(
        votes,
        key=lambda lbl: (-votes[lbl], nearest_dist[lbl], lbl),
    )
    return best


def knn_predict(
    train_X: Matrix, train_y: Vector, queries: Matrix, k: int = 3
) -> Vector:
    """Classify every row of ``queries`` via :func:`knn_classify`.

    Raises :class:`MLError` on invalid training data or ``queries``.
    """
    _validate_X(queries)
    return [knn_classify(train_X, train_y, q, k) for q in queries]


# --------------------------------------------------------------------------- #
# Binary logistic regression (batch gradient descent).
# --------------------------------------------------------------------------- #

def _sigmoid(z: float) -> float:
    """Numerically stable logistic sigmoid (argument clamped to avoid overflow)."""
    if z < -60.0:
        return 0.0
    if z > 60.0:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def logistic_regression(
    X: Matrix, y: Vector, lr: float = 0.1, epochs: int = 1000
) -> tuple[Vector, float]:
    """Binary logistic regression via batch gradient descent.

    Labels must be ``0``/``1``. Features are standardised internally for stable
    descent, and the learned weights/bias are mapped back to the original
    feature space before returning. Returns ``(weights, bias)``.

    Raises :class:`MLError` on bad shapes, non-binary labels, or bad
    hyper-parameters.
    """
    n, m = _validate_X(X)
    _validate_y(y, n)
    for value in y:
        if value not in (0, 0.0, 1, 1.0):
            raise MLError("logistic_regression: labels must be 0 or 1")
    if not isinstance(epochs, int) or epochs < 1:
        raise MLError("logistic_regression: epochs must be a positive integer")
    if not isinstance(lr, (int, float)) or lr <= 0:
        raise MLError("logistic_regression: lr must be positive")

    X_std, means, stds = standardize(X)
    safe_stds = [s if s > EPS else 1.0 for s in stds]
    labels = [float(v) for v in y]

    w = [0.0] * m
    b = 0.0
    for _ in range(epochs):
        grad_w = [0.0] * m
        grad_b = 0.0
        for i in range(n):
            z = b + sum(w[j] * X_std[i][j] for j in range(m))
            err = _sigmoid(z) - labels[i]
            grad_b += err
            for j in range(m):
                grad_w[j] += err * X_std[i][j]
        inv = 1.0 / n
        b -= lr * grad_b * inv
        for j in range(m):
            w[j] -= lr * grad_w[j] * inv

    # Map back from standardised space: z = b + Σ w_j (x_j - mean_j)/std_j.
    weights = [w[j] / safe_stds[j] for j in range(m)]
    bias = b - sum(w[j] * means[j] / safe_stds[j] for j in range(m))
    return weights, bias


def logistic_predict_proba(weights: Vector, bias: float, X: Matrix) -> Vector:
    """Return per-row sigmoid probabilities ``σ(X·weights + bias)``.

    Raises :class:`MLError` if a row's width does not match ``len(weights)``.
    """
    n, m = _validate_X(X)
    if len(weights) != m:
        raise MLError("logistic_predict_proba: weights length must match features")
    out: Vector = []
    for i in range(n):
        z = float(bias) + sum(float(X[i][j]) * weights[j] for j in range(m))
        out.append(_sigmoid(z))
    return out


def logistic_predict(
    weights: Vector, bias: float, X: Matrix, threshold: float = 0.5
) -> list[int]:
    """Return hard 0/1 predictions by thresholding the sigmoid probabilities."""
    return [
        1 if p >= threshold else 0
        for p in logistic_predict_proba(weights, bias, X)
    ]
