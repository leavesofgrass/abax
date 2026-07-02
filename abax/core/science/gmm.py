"""Gaussian Mixture Model clustering via Expectation-Maximization (no numpy).

A small, dependency-free Gaussian mixture implementation for use inside abax.
Data is plain Python: ``X`` is a ``list[list[float]]`` whose rows are samples
and columns are features. Each mixture component uses a **diagonal** covariance
(a per-feature variance vector), which is numerically robust and keeps the math
to stdlib :mod:`math`. Any randomness is funnelled through a seeded
:class:`random.Random` so fits are fully reproducible.

The EM loop alternates an E-step (responsibilities, computed in log space with a
per-row max subtraction for stability) with an M-step (re-estimate the weights,
means, and floored variances). Initial means are chosen by a k-means++-style
seeding pass. Bad input (empty/ragged ``X``, too few samples, ``n_components``
out of range) raises :class:`GMMError`.

The module-level :func:`gmm_model_selection` sweeps a range of component counts
and reports the BIC/AIC per ``k`` plus the argmin of each — a "how many
components?" helper mirroring the k-means elbow/silhouette tools.

Pure stdlib -> core.
"""

from __future__ import annotations

import math
import random

Matrix = list[list[float]]
Vector = list[float]

_LOG_2PI = math.log(2.0 * math.pi)


class GMMError(Exception):
    """Raised for invalid data, shape mismatches, or bad parameters."""


def _validate_X(X: Matrix) -> tuple[int, int]:
    """Validate that ``X`` is a non-empty rectangular numeric matrix.

    Returns ``(n_samples, n_features)``. Raises :class:`GMMError` otherwise.
    """
    if not isinstance(X, list) or not X:
        raise GMMError("X must be a non-empty list of rows")
    n_features: int | None = None
    for row in X:
        if not isinstance(row, list) or not row:
            raise GMMError("each row of X must be a non-empty list")
        if n_features is None:
            n_features = len(row)
        elif len(row) != n_features:
            raise GMMError("X is ragged (rows of differing length)")
        for value in row:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise GMMError("X entries must be numeric")
    assert n_features is not None
    return len(X), n_features


def _log_gauss(x: Vector, mean: Vector, var: Vector) -> float:
    """Return the log-pdf of ``x`` under a diagonal Gaussian.

    ``-0.5 * sum(log(2*pi*var_d) + (x_d - mean_d)**2 / var_d)`` over features.
    Variances are assumed already floored to a positive value by the caller.
    """
    total = 0.0
    for d in range(len(x)):
        v = var[d]
        diff = float(x[d]) - mean[d]
        total += _LOG_2PI + math.log(v) + (diff * diff) / v
    return -0.5 * total


def _logsumexp(values: Vector) -> float:
    """Return ``log(sum(exp(values)))`` stably via max subtraction."""
    m = max(values)
    if m == -math.inf:
        return -math.inf
    return m + math.log(sum(math.exp(v - m) for v in values))


class GaussianMixture:
    """Diagonal-covariance Gaussian mixture fitted by Expectation-Maximization.

    Parameters mirror the familiar scikit-learn surface: ``n_components`` mixture
    components, at most ``max_iter`` EM iterations, convergence when the average
    log-likelihood improves by less than ``tol``, ``reg_covar`` added to (and
    used as a floor for) every variance to avoid collapse, and ``seed`` for the
    reproducible k-means++-style initialisation.

    After :meth:`fit`, the learned parameters are available as ``means_``
    (component means), ``covariances_`` (per-component variance vectors),
    ``weights_`` (mixture weights), with ``converged_``, ``n_iter_``, and
    ``lower_bound_`` (final average log-likelihood) describing the fit.
    """

    def __init__(
        self,
        n_components: int = 2,
        max_iter: int = 100,
        tol: float = 1e-4,
        reg_covar: float = 1e-6,
        seed: int = 0,
    ) -> None:
        self.n_components = n_components
        self.max_iter = max_iter
        self.tol = tol
        self.reg_covar = reg_covar
        self.seed = seed

        self.means_: Matrix = []
        self.covariances_: Matrix = []
        self.weights_: Vector = []
        self.converged_: bool = False
        self.n_iter_: int = 0
        self.lower_bound_: float = -math.inf

    # ------------------------------------------------------------------ #
    # Initialisation.
    # ------------------------------------------------------------------ #

    def _init_means(self, X: Matrix, rng: random.Random) -> Matrix:
        """Pick ``n_components`` means via k-means++-style seeding."""
        n = len(X)
        first = rng.randrange(n)
        means: Matrix = [list(map(float, X[first]))]

        def sq_dist(a: list[float], b: Vector) -> float:
            return sum((float(a[d]) - b[d]) ** 2 for d in range(len(b)))

        nearest = [sq_dist(X[i], means[0]) for i in range(n)]
        while len(means) < self.n_components:
            total = sum(nearest)
            if total <= 0.0:
                idx = rng.randrange(n)
            else:
                target = rng.random() * total
                cumulative = 0.0
                idx = n - 1
                for i, w in enumerate(nearest):
                    cumulative += w
                    if cumulative >= target:
                        idx = i
                        break
            means.append(list(map(float, X[idx])))
            for i in range(n):
                d = sq_dist(X[i], means[-1])
                if d < nearest[i]:
                    nearest[i] = d
        return means

    # ------------------------------------------------------------------ #
    # Fit.
    # ------------------------------------------------------------------ #

    def fit(self, X: Matrix) -> "GaussianMixture":
        """Fit the mixture to ``X`` by Expectation-Maximization.

        Raises :class:`GMMError` on empty/ragged ``X``, ``n_components < 1``, or
        fewer samples than components.
        """
        if not isinstance(self.n_components, int) or self.n_components < 1:
            raise GMMError("n_components must be a positive integer")
        n, m = _validate_X(X)
        if n < self.n_components:
            raise GMMError("len(X) must be at least n_components")

        rng = random.Random(self.seed)
        k = self.n_components

        # Per-feature variance of the whole dataset (population), floored.
        col_means = [sum(float(X[i][d]) for i in range(n)) / n for d in range(m)]
        col_var = [
            sum((float(X[i][d]) - col_means[d]) ** 2 for i in range(n)) / n
            for d in range(m)
        ]
        base_var = [max(v, 0.0) + self.reg_covar for v in col_var]

        means = self._init_means(X, rng)
        covariances = [list(base_var) for _ in range(k)]
        weights = [1.0 / k for _ in range(k)]

        prev_ll = -math.inf
        self.converged_ = False
        self.n_iter_ = 0
        self.lower_bound_ = -math.inf

        for iteration in range(1, self.max_iter + 1):
            # ---- E-step: responsibilities in log space. ----
            log_weights = [
                math.log(w) if w > 0.0 else -math.inf for w in weights
            ]
            resp: Matrix = []
            total_ll = 0.0
            for i in range(n):
                log_terms = [
                    log_weights[c] + _log_gauss(X[i], means[c], covariances[c])
                    for c in range(k)
                ]
                row_lse = _logsumexp(log_terms)
                total_ll += row_lse
                if row_lse == -math.inf:
                    # Degenerate row; fall back to uniform responsibility.
                    resp.append([1.0 / k for _ in range(k)])
                else:
                    resp.append([math.exp(t - row_lse) for t in log_terms])

            avg_ll = total_ll / n
            self.n_iter_ = iteration
            self.lower_bound_ = avg_ll

            # ---- M-step: re-estimate weights, means, variances. ----
            new_weights: Vector = []
            new_means: Matrix = []
            new_cov: Matrix = []
            for c in range(k):
                nk = sum(resp[i][c] for i in range(n))
                new_weights.append(nk / n)
                denom = nk if nk > 0.0 else 1e-12
                mean_c = [
                    sum(resp[i][c] * float(X[i][d]) for i in range(n)) / denom
                    for d in range(m)
                ]
                var_c = [
                    sum(
                        resp[i][c] * (float(X[i][d]) - mean_c[d]) ** 2
                        for i in range(n)
                    )
                    / denom
                    + self.reg_covar
                    for d in range(m)
                ]
                # Floor every variance to stay strictly positive.
                var_c = [max(v, self.reg_covar) for v in var_c]
                new_means.append(mean_c)
                new_cov.append(var_c)

            weights, means, covariances = new_weights, new_means, new_cov

            if prev_ll != -math.inf and avg_ll - prev_ll < self.tol:
                self.converged_ = True
                break
            prev_ll = avg_ll

        self.means_ = means
        self.covariances_ = covariances
        self.weights_ = weights
        return self

    # ------------------------------------------------------------------ #
    # Inference helpers.
    # ------------------------------------------------------------------ #

    def _check_fitted(self) -> None:
        if not self.means_:
            raise GMMError("model is not fitted; call fit() first")

    def _log_resp(self, X: Matrix) -> tuple[Matrix, Vector]:
        """Return ``(log_responsibilities, per_row_logsumexp)`` for ``X``."""
        self._check_fitted()
        n, m = _validate_X(X)
        if m != len(self.means_[0]):
            raise GMMError("X feature count does not match the fitted model")
        k = self.n_components
        log_weights = [
            math.log(w) if w > 0.0 else -math.inf for w in self.weights_
        ]
        log_resp: Matrix = []
        row_lse: Vector = []
        for i in range(n):
            log_terms = [
                log_weights[c]
                + _log_gauss(X[i], self.means_[c], self.covariances_[c])
                for c in range(k)
            ]
            lse = _logsumexp(log_terms)
            row_lse.append(lse)
            if lse == -math.inf:
                log_resp.append([math.log(1.0 / k) for _ in range(k)])
            else:
                log_resp.append([t - lse for t in log_terms])
        return log_resp, row_lse

    def predict_proba(self, X: Matrix) -> Matrix:
        """Return per-row responsibilities; each row sums to ``1``.

        Raises :class:`GMMError` if the model is unfitted or ``X`` mismatches.
        """
        log_resp, _ = self._log_resp(X)
        return [[math.exp(v) for v in row] for row in log_resp]

    def predict(self, X: Matrix) -> list[int]:
        """Return the argmax-responsibility component index for each row."""
        proba = self.predict_proba(X)
        labels: list[int] = []
        for row in proba:
            best, best_p = 0, row[0]
            for c in range(1, len(row)):
                if row[c] > best_p:
                    best, best_p = c, row[c]
            labels.append(best)
        return labels

    def score(self, X: Matrix) -> float:
        """Return the average log-likelihood of ``X`` under the model."""
        _, row_lse = self._log_resp(X)
        return sum(row_lse) / len(row_lse)

    # ------------------------------------------------------------------ #
    # Model-selection criteria.
    # ------------------------------------------------------------------ #

    def _n_params(self) -> int:
        """Free parameters: ``K*(2D) + (K-1)`` (means + variances + weights)."""
        self._check_fitted()
        k = self.n_components
        d = len(self.means_[0])
        return k * (2 * d) + (k - 1)

    def bic(self, X: Matrix) -> float:
        """Bayesian information criterion: ``-2*loglik + n_params*ln(n)``."""
        n, _ = _validate_X(X)
        loglik_total = self.score(X) * n
        return -2.0 * loglik_total + self._n_params() * math.log(n)

    def aic(self, X: Matrix) -> float:
        """Akaike information criterion: ``-2*loglik + 2*n_params``."""
        n, _ = _validate_X(X)
        loglik_total = self.score(X) * n
        return -2.0 * loglik_total + 2.0 * self._n_params()


# ---------------------------------------------------------------------- #
# "How many components?" model selection.
# ---------------------------------------------------------------------- #


def gmm_model_selection(
    X: Matrix,
    k_range,
    max_iter: int = 100,
    seed: int = 0,
) -> dict:
    """Fit a GMM at each ``k`` in ``k_range`` and score it by BIC and AIC.

    For every candidate ``k`` (the number of mixture components) a fresh
    :class:`GaussianMixture` is fitted to ``X`` and its Bayesian / Akaike
    information criteria recorded. Both criteria trade fit against complexity, so
    the ``k`` that *minimises* them is the suggested component count.

    Returns a dict with keys:

    * ``"scores"`` — list of ``(k, bic, aic)`` triples, in ``k_range`` order;
    * ``"best_bic"`` — the ``k`` with the smallest BIC;
    * ``"best_aic"`` — the ``k`` with the smallest AIC.

    Raises :class:`GMMError` if ``k_range`` is empty (bad ``X`` or ``k`` values
    propagate from :meth:`GaussianMixture.fit`).
    """
    ks = [int(k) for k in k_range]
    if not ks:
        raise GMMError("k_range must be non-empty")
    scores: list[tuple[int, float, float]] = []
    for k in ks:
        model = GaussianMixture(n_components=k, max_iter=max_iter, seed=seed)
        model.fit(X)
        scores.append((k, model.bic(X), model.aic(X)))
    best_bic = min(scores, key=lambda t: t[1])[0]
    best_aic = min(scores, key=lambda t: t[2])[0]
    return {"scores": scores, "best_bic": best_bic, "best_aic": best_aic}
