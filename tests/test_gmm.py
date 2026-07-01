"""Tests for the diagonal-covariance Gaussian mixture (``abax.core.science.gmm``)."""

from __future__ import annotations

import math
import random

import pytest

from abax.core.science.gmm import GaussianMixture, GMMError


def _two_blobs(seed: int = 1) -> tuple[list[list[float]], list[int]]:
    """Two well-separated 2-D blobs around (0,0) and (8,8), ~20 pts each.

    Returns ``(X, truth)`` where ``truth[i]`` is the originating blob (0 or 1),
    used to compare induced 2-partitions independent of component labelling.
    """
    rng = random.Random(seed)
    X: list[list[float]] = []
    truth: list[int] = []
    for _ in range(20):
        X.append([rng.gauss(0.0, 0.3), rng.gauss(0.0, 0.3)])
        truth.append(0)
    for _ in range(20):
        X.append([rng.gauss(8.0, 0.3), rng.gauss(8.0, 0.3)])
        truth.append(1)
    return X, truth


def _same_partition(labels: list[int], truth: list[int]) -> bool:
    """True if ``labels`` induces the same 2-partition as ``truth``."""
    groups: dict[int, set[int]] = {}
    for lab, t in zip(labels, truth):
        groups.setdefault(t, set()).add(lab)
    # Each truth group must map to exactly one (distinct) predicted label.
    used = [next(iter(s)) for s in groups.values() if len(s) == 1]
    return len(used) == len(groups) and len(set(used)) == len(groups)


def test_two_blobs_partition_and_convergence():
    X, truth = _two_blobs()
    gmm = GaussianMixture(2, seed=0).fit(X)
    labels = gmm.predict(X)
    assert _same_partition(labels, truth)
    assert gmm.converged_ is True
    assert gmm.n_iter_ <= gmm.max_iter


def test_predict_proba_rows_sum_to_one_and_confident():
    X, _ = _two_blobs()
    gmm = GaussianMixture(2, seed=0).fit(X)
    proba = gmm.predict_proba(X)
    for row in proba:
        assert sum(row) == pytest.approx(1.0)

    # A point deep inside the (8,8) blob -> ~1.0 responsibility for its comp.
    deep = gmm.predict_proba([[8.0, 8.0]])[0]
    assert max(deep) == pytest.approx(1.0, abs=1e-6)


def test_reproducible_same_seed():
    X, _ = _two_blobs()
    a = GaussianMixture(2, seed=0).fit(X).predict(X)
    b = GaussianMixture(2, seed=0).fit(X).predict(X)
    assert a == b


def test_score_finite_and_constant_feature_ok():
    X, _ = _two_blobs()
    s = GaussianMixture(2, seed=0).fit(X).score(X)
    assert math.isfinite(s)

    # Second feature is constant -> reg_covar must keep variance positive.
    const = [[float(i), 5.0] for i in range(10)]
    gmm = GaussianMixture(3, seed=0).fit(const)
    assert math.isfinite(gmm.score(const))


def test_bic_aic_finite_and_k2_beats_k1():
    X, _ = _two_blobs()
    g2 = GaussianMixture(2, seed=0).fit(X)
    g1 = GaussianMixture(1, seed=0).fit(X)
    assert math.isfinite(g2.bic(X))
    assert math.isfinite(g2.aic(X))
    assert math.isfinite(g1.bic(X))
    # True structure is k=2; it should be preferred (lower BIC).
    assert g2.bic(X) < g1.bic(X)


def test_error_empty_X():
    with pytest.raises(GMMError):
        GaussianMixture(2).fit([])


def test_error_ragged_rows():
    with pytest.raises(GMMError):
        GaussianMixture(2).fit([[1.0, 2.0], [3.0]])


def test_error_n_components_below_one():
    with pytest.raises(GMMError):
        GaussianMixture(0).fit([[1.0], [2.0]])


def test_error_too_few_samples():
    with pytest.raises(GMMError):
        GaussianMixture(3).fit([[1.0], [2.0]])
