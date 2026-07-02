"""Oracle tests for the cluster-count selection helpers.

Builds three well-separated 2-D blobs (fixed seed via :class:`random.Random`)
and checks that:

* :func:`best_k_silhouette` over ``k = 2..6`` recovers ``k = 3``;
* the elbow inertia is strictly decreasing in ``k``;
* the GMM BIC (:func:`gmm_model_selection`) is minimised at ``k = 3``.
"""

from __future__ import annotations

import random

from abax.core.science.cluster import best_k_silhouette, elbow
from abax.core.science.gmm import gmm_model_selection

# Three tight, well-separated blobs -> the true cluster count is 3.
_CENTERS = [(0.0, 0.0), (10.0, 0.0), (5.0, 9.0)]
_PER_BLOB = 20
_SPREAD = 0.35


def _three_blobs(seed: int = 12345) -> list[list[float]]:
    """Return ~60 points drawn from three tight, well-separated Gaussians."""
    rng = random.Random(seed)
    points: list[list[float]] = []
    for cx, cy in _CENTERS:
        for _ in range(_PER_BLOB):
            points.append([rng.gauss(cx, _SPREAD), rng.gauss(cy, _SPREAD)])
    return points


POINTS = _three_blobs()
K_RANGE = range(2, 7)  # k = 2..6


def test_best_k_silhouette_recovers_three():
    best_k, scores = best_k_silhouette(POINTS, K_RANGE, seed=0)
    assert best_k == 3
    # Every candidate k was scored, in range order.
    assert [k for k, _ in scores] == [2, 3, 4, 5, 6]
    # k=3 truly has the highest mean silhouette.
    by_k = dict(scores)
    assert by_k[3] == max(by_k.values())


def test_elbow_inertia_monotonically_decreasing():
    curve = elbow(POINTS, K_RANGE, seed=0)
    assert [k for k, _ in curve] == [2, 3, 4, 5, 6]
    inertias = [inertia for _, inertia in curve]
    # More clusters can only reduce (never increase) within-cluster inertia.
    for prev, nxt in zip(inertias, inertias[1:]):
        assert nxt < prev


def test_gmm_model_selection_bic_minimized_at_three():
    result = gmm_model_selection(POINTS, K_RANGE, seed=0)
    assert result["best_bic"] == 3
    # The scores table covers every k with finite BIC/AIC.
    ks = [k for k, _bic, _aic in result["scores"]]
    assert ks == [2, 3, 4, 5, 6]
    bic_by_k = {k: bic for k, bic, _aic in result["scores"]}
    assert bic_by_k[3] == min(bic_by_k.values())
