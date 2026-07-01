"""Naive Bayes classifiers — a no-numpy implementation.

Two classic naive Bayes models, hand-written with the standard library only
(``math`` and ``collections``, no numpy). Data is plain Python:

* ``X`` is a ``list[list[float]]`` — rows are samples, columns are features.
* ``y`` is a ``list`` of class labels (any sortable hashable values).

The surface covers:

* :class:`GaussianNB` — continuous features modelled as per-class Gaussians.
* :class:`MultinomialNB` — non-negative count features (e.g. bag-of-words)
  with Laplace (additive) smoothing.

Both classifiers work entirely in log-space and softmax-normalise (after
subtracting the per-row maximum) for numerical stability. Probabilities are
returned with columns ordered as :meth:`classes`.

Bad input (empty/ragged ``X``, shape mismatches, negative counts) raises
:class:`BayesError`.

Pure stdlib → core.
"""

from __future__ import annotations

import math
from collections import defaultdict

Matrix = list[list[float]]

EPS = 1e-12
_LOG_2PI = math.log(2.0 * math.pi)


class BayesError(Exception):
    """Raised for invalid data, shape mismatches, or unfitted use."""


# --------------------------------------------------------------------------- #
# Validation helpers.
# --------------------------------------------------------------------------- #

def _validate_X(X: Matrix) -> tuple[int, int]:
    """Validate that ``X`` is a non-empty rectangular numeric matrix.

    Returns ``(n_samples, n_features)``. Raises :class:`BayesError` otherwise.
    """
    if not isinstance(X, list) or not X:
        raise BayesError("X must be a non-empty list of rows")
    n_features: int | None = None
    for row in X:
        if not isinstance(row, list) or not row:
            raise BayesError("each row of X must be a non-empty list")
        if n_features is None:
            n_features = len(row)
        elif len(row) != n_features:
            raise BayesError("X is ragged (rows of differing length)")
        for value in row:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise BayesError("X entries must be numeric")
    assert n_features is not None
    return len(X), n_features


def _validate_xy(X: Matrix, y: list) -> tuple[int, int]:
    """Validate ``X`` and that ``y`` is a label vector of matching length."""
    n, m = _validate_X(X)
    if not isinstance(y, list) or len(y) != n:
        raise BayesError("y must be a list with one label per row of X")
    return n, m


def _softmax_rows(log_likelihoods: Matrix) -> Matrix:
    """Convert per-row log-scores to normalised probabilities (stable softmax).

    Each row has its maximum subtracted before exponentiation to avoid
    overflow, then is normalised to sum to one.
    """
    out: Matrix = []
    for row in log_likelihoods:
        top = max(row)
        exps = [math.exp(v - top) for v in row]
        total = sum(exps)
        if total <= 0.0:
            # Degenerate; fall back to a uniform distribution.
            k = len(exps)
            out.append([1.0 / k] * k)
        else:
            out.append([e / total for e in exps])
    return out


# --------------------------------------------------------------------------- #
# Gaussian naive Bayes.
# --------------------------------------------------------------------------- #

class GaussianNB:
    """Gaussian naive Bayes for continuous features.

    Each feature is modelled, per class, as an independent Gaussian with the
    class-conditional (population) mean and variance. A fraction
    ``var_smoothing`` of the largest feature variance is added to every
    variance to guard against zero-variance (constant) features.
    """

    def __init__(self, var_smoothing: float = 1e-9) -> None:
        if not isinstance(var_smoothing, (int, float)) or var_smoothing < 0:
            raise BayesError("var_smoothing must be a non-negative number")
        self.var_smoothing = float(var_smoothing)
        self._classes: list = []
        self._log_prior: dict = {}
        self._mean: dict = {}
        self._var: dict = {}
        self._n_features: int = 0

    def fit(self, X: Matrix, y: list) -> "GaussianNB":
        """Estimate per-class priors, means, and variances.

        Per class the prior is ``count / total``. Per feature the (population)
        mean and variance are computed; ``var_smoothing * max_feature_variance``
        is added to every variance.

        Raises :class:`BayesError` on empty/ragged ``X`` or ``len(X) != len(y)``.
        """
        n, m = _validate_xy(X, y)

        groups: dict[object, list[int]] = defaultdict(list)
        for i, label in enumerate(y):
            groups[label].append(i)

        try:
            classes = sorted(groups)
        except TypeError as exc:
            raise BayesError("class labels must be sortable") from exc

        # Overall per-feature population variance → smoothing epsilon.
        col_means = [sum(float(X[i][j]) for i in range(n)) / n for j in range(m)]
        max_var = 0.0
        for j in range(m):
            v = sum((float(X[i][j]) - col_means[j]) ** 2 for i in range(n)) / n
            if v > max_var:
                max_var = v
        epsilon = self.var_smoothing * max_var

        self._classes = classes
        self._log_prior = {}
        self._mean = {}
        self._var = {}
        self._n_features = m

        for label in classes:
            idx = groups[label]
            count = len(idx)
            self._log_prior[label] = math.log(count / n)
            means = [sum(float(X[i][j]) for i in idx) / count for j in range(m)]
            variances = []
            for j in range(m):
                var = sum((float(X[i][j]) - means[j]) ** 2 for i in idx) / count
                variances.append(var + epsilon)
            self._mean[label] = means
            self._var[label] = variances

        return self

    def _check_fitted(self) -> None:
        if not self._classes:
            raise BayesError("classifier is not fitted")

    def _joint_log_likelihood(self, X: Matrix) -> Matrix:
        """Return per-row ``[log p(class) + Σ log N(x|class)]`` for each class."""
        self._check_fitted()
        n, m = _validate_X(X)
        if m != self._n_features:
            raise BayesError("X has the wrong number of features")
        out: Matrix = []
        for i in range(n):
            row = []
            for label in self._classes:
                means = self._mean[label]
                variances = self._var[label]
                total = self._log_prior[label]
                for j in range(m):
                    var = variances[j]
                    diff = float(X[i][j]) - means[j]
                    total += -0.5 * (_LOG_2PI + math.log(var)) - (diff * diff) / (2.0 * var)
                row.append(total)
            out.append(row)
        return out

    def predict_proba(self, X: Matrix) -> Matrix:
        """Return per-row class probabilities (columns ordered as :meth:`classes`).

        Scores are accumulated in log-space (log prior + sum of log Gaussian
        pdfs) then softmax-normalised so each row sums to one.
        """
        return _softmax_rows(self._joint_log_likelihood(X))

    def predict(self, X: Matrix) -> list:
        """Return the most probable class label for each row of ``X``."""
        jll = self._joint_log_likelihood(X)
        return [self._classes[row.index(max(row))] for row in jll]

    def classes(self) -> list:
        """Return the sorted unique class labels (predict_proba column order)."""
        self._check_fitted()
        return list(self._classes)


# --------------------------------------------------------------------------- #
# Multinomial naive Bayes.
# --------------------------------------------------------------------------- #

class MultinomialNB:
    """Multinomial naive Bayes for non-negative count features.

    Suited to bag-of-words data. Per class the prior is ``count / total`` and
    the smoothed per-feature likelihood is

        ``p(feature | class) = (count_fc + alpha) / (total_c + alpha * n_features)``

    where ``alpha`` is the Laplace (additive) smoothing parameter.
    """

    def __init__(self, alpha: float = 1.0) -> None:
        if not isinstance(alpha, (int, float)) or alpha <= 0:
            raise BayesError("alpha must be a positive number")
        self.alpha = float(alpha)
        self._classes: list = []
        self._log_prior: dict = {}
        self._log_likelihood: dict = {}
        self._n_features: int = 0

    def fit(self, X: Matrix, y: list) -> "MultinomialNB":
        """Estimate per-class priors and smoothed feature log-likelihoods.

        ``X`` entries must be non-negative counts.

        Raises :class:`BayesError` on negative entries or shape problems.
        """
        n, m = _validate_xy(X, y)
        for row in X:
            for value in row:
                if value < 0:
                    raise BayesError("MultinomialNB requires non-negative counts")

        groups: dict[object, list[int]] = defaultdict(list)
        for i, label in enumerate(y):
            groups[label].append(i)

        try:
            classes = sorted(groups)
        except TypeError as exc:
            raise BayesError("class labels must be sortable") from exc

        self._classes = classes
        self._log_prior = {}
        self._log_likelihood = {}
        self._n_features = m

        for label in classes:
            idx = groups[label]
            self._log_prior[label] = math.log(len(idx) / n)
            feature_counts = [
                sum(float(X[i][j]) for i in idx) for j in range(m)
            ]
            total = sum(feature_counts) + self.alpha * m
            self._log_likelihood[label] = [
                math.log((feature_counts[j] + self.alpha) / total)
                for j in range(m)
            ]

        return self

    def _check_fitted(self) -> None:
        if not self._classes:
            raise BayesError("classifier is not fitted")

    def _joint_log_likelihood(self, X: Matrix) -> Matrix:
        """Return per-row ``[log p(class) + Σ x_f · log p(f|class)]`` per class."""
        self._check_fitted()
        n, m = _validate_X(X)
        if m != self._n_features:
            raise BayesError("X has the wrong number of features")
        for row in X:
            for value in row:
                if value < 0:
                    raise BayesError("MultinomialNB requires non-negative counts")
        out: Matrix = []
        for i in range(n):
            row = []
            for label in self._classes:
                logp = self._log_likelihood[label]
                total = self._log_prior[label]
                for j in range(m):
                    total += float(X[i][j]) * logp[j]
                row.append(total)
            out.append(row)
        return out

    def predict_proba(self, X: Matrix) -> Matrix:
        """Return per-row class probabilities (columns ordered as :meth:`classes`).

        Scores are accumulated in log-space then softmax-normalised so each row
        sums to one.
        """
        return _softmax_rows(self._joint_log_likelihood(X))

    def predict(self, X: Matrix) -> list:
        """Return the most probable class label for each row of ``X``."""
        jll = self._joint_log_likelihood(X)
        return [self._classes[row.index(max(row))] for row in jll]

    def classes(self) -> list:
        """Return the sorted unique class labels (predict_proba column order)."""
        self._check_fitted()
        return list(self._classes)
