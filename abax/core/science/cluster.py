"""Pure-Python clustering: k-means, agglomerative, DBSCAN, silhouette.

A small, dependency-free clustering toolkit for use inside abax. Points are
plain ``list[list[float]]`` (each inner list a feature vector). Everything runs
in IEEE doubles via the stdlib :mod:`math` module; any randomness is funnelled
through a seeded :class:`random.Random` so results are fully reproducible.

Algorithms: :func:`kmeans` (Lloyd's iteration with k-means++ seeding) plus
:func:`kmeans_predict` for assigning new points; :func:`agglomerative` (bottom-up
hierarchical clustering with single/complete/average linkage); :func:`dbscan`
(density-based, with noise labelled ``-1``). Quality is measured by
:func:`silhouette_score`, and the "how many clusters?" helpers
:func:`elbow` (inertia per ``k``) and :func:`best_k_silhouette` (the ``k`` with
the highest mean silhouette) wrap k-means to suggest a cluster count. Bad
arguments raise :class:`ClusterError` rather than returning a bogus result.
"""

from __future__ import annotations

import math
import random

NOISE = -1


class ClusterError(Exception):
    """Raised when a clustering routine cannot produce a valid result."""


def _check_points(points: list[list[float]]) -> int:
    """Validate ``points`` is non-empty and rectangular; return feature width."""
    if not points:
        raise ClusterError("points must be non-empty")
    dim = len(points[0])
    for p in points:
        if len(p) != dim:
            raise ClusterError("ragged feature lengths")
    return dim


def euclidean(a: list[float], b: list[float]) -> float:
    """Return the Euclidean distance between vectors ``a`` and ``b``."""
    if len(a) != len(b):
        raise ClusterError("vectors must have equal length")
    return math.sqrt(sum((x - y) * (x - y) for x, y in zip(a, b)))


def _sq_dist(a: list[float], b: list[float]) -> float:
    """Return the squared Euclidean distance between ``a`` and ``b``."""
    return sum((x - y) * (x - y) for x, y in zip(a, b))


def _mean(vectors: list[list[float]], dim: int) -> list[float]:
    """Return the component-wise mean of a non-empty list of vectors."""
    n = len(vectors)
    return [sum(v[j] for v in vectors) / n for j in range(dim)]


def _kmeans_pp_init(
    points: list[list[float]], k: int, rng: random.Random
) -> list[list[float]]:
    """Choose ``k`` initial centroids by the k-means++ scheme."""
    first = rng.randrange(len(points))
    centroids = [list(points[first])]
    # Squared distance to the nearest chosen centroid.
    nearest = [_sq_dist(p, centroids[0]) for p in points]
    while len(centroids) < k:
        total = sum(nearest)
        if total <= 0.0:
            # All remaining points coincide with chosen centroids; pick any.
            idx = rng.randrange(len(points))
        else:
            target = rng.random() * total
            cumulative = 0.0
            idx = len(points) - 1
            for i, w in enumerate(nearest):
                cumulative += w
                if cumulative >= target:
                    idx = i
                    break
        centroids.append(list(points[idx]))
        for i, p in enumerate(points):
            d = _sq_dist(p, centroids[-1])
            if d < nearest[i]:
                nearest[i] = d
    return centroids


def kmeans(
    points: list[list[float]],
    k: int,
    max_iter: int = 100,
    seed: int = 0,
) -> tuple[list[int], list[list[float]], float]:
    """Cluster ``points`` into ``k`` groups by k-means (k-means++ seeded).

    Returns ``(labels, centroids, inertia)`` where ``labels[i]`` is in
    ``0..k-1``, ``centroids`` is ``k`` vectors, and ``inertia`` is the sum of
    squared distances from each point to its assigned centroid. Empty clusters
    are re-seeded to the farthest point. Raises :class:`ClusterError` if
    ``k < 1``, ``k > len(points)``, ``points`` is empty, or feature lengths are
    ragged.
    """
    dim = _check_points(points)
    if k < 1:
        raise ClusterError("k must be at least 1")
    if k > len(points):
        raise ClusterError("k must not exceed the number of points")

    rng = random.Random(seed)
    centroids = _kmeans_pp_init(points, k, rng)
    labels = [0] * len(points)

    for _ in range(max_iter):
        changed = False
        for i, p in enumerate(points):
            best, best_d = 0, _sq_dist(p, centroids[0])
            for c in range(1, k):
                d = _sq_dist(p, centroids[c])
                if d < best_d:
                    best, best_d = c, d
            if labels[i] != best:
                changed = True
            labels[i] = best

        members: list[list[list[float]]] = [[] for _ in range(k)]
        for i, p in enumerate(points):
            members[labels[i]].append(p)

        new_centroids: list[list[float]] = []
        for c in range(k):
            if members[c]:
                new_centroids.append(_mean(members[c], dim))
            else:
                # Re-seed an empty cluster to the farthest point overall.
                far_i, far_d = 0, -1.0
                for i, p in enumerate(points):
                    d = _sq_dist(p, centroids[labels[i]])
                    if d > far_d:
                        far_i, far_d = i, d
                new_centroids.append(list(points[far_i]))
                changed = True
        centroids = new_centroids

        if not changed:
            break

    inertia = sum(_sq_dist(p, centroids[labels[i]]) for i, p in enumerate(points))
    return labels, centroids, inertia


def kmeans_predict(point: list[float], centroids: list[list[float]]) -> int:
    """Return the index of the centroid nearest to ``point``."""
    if not centroids:
        raise ClusterError("centroids must be non-empty")
    best, best_d = 0, _sq_dist(point, centroids[0])
    for c in range(1, len(centroids)):
        d = _sq_dist(point, centroids[c])
        if d < best_d:
            best, best_d = c, d
    return best


def _cluster_distance(
    a: list[int],
    b: list[int],
    points: list[list[float]],
    linkage: str,
) -> float:
    """Return the linkage distance between two clusters (index lists)."""
    dists = [euclidean(points[i], points[j]) for i in a for j in b]
    if linkage == "single":
        return min(dists)
    if linkage == "complete":
        return max(dists)
    if linkage == "average":
        return sum(dists) / len(dists)
    raise ClusterError(f"unknown linkage: {linkage!r}")


def agglomerative(
    points: list[list[float]],
    k: int,
    linkage: str = "average",
) -> list[int]:
    """Bottom-up hierarchical clustering of ``points`` into ``k`` clusters.

    ``linkage`` is one of ``"single"``, ``"complete"``, ``"average"``. Starting
    from singleton clusters, the two closest clusters (by the chosen linkage)
    are merged repeatedly until ``k`` remain. Returns labels in ``0..k-1``.
    Raises :class:`ClusterError` on bad ``k`` or an unknown linkage.
    """
    _check_points(points)
    if linkage not in ("single", "complete", "average"):
        raise ClusterError(f"unknown linkage: {linkage!r}")
    if k < 1:
        raise ClusterError("k must be at least 1")
    if k > len(points):
        raise ClusterError("k must not exceed the number of points")

    clusters: list[list[int]] = [[i] for i in range(len(points))]
    while len(clusters) > k:
        best_pair = (0, 1)
        best_d = _cluster_distance(clusters[0], clusters[1], points, linkage)
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                d = _cluster_distance(clusters[a], clusters[b], points, linkage)
                if d < best_d:
                    best_d = d
                    best_pair = (a, b)
        a, b = best_pair
        clusters[a].extend(clusters[b])
        del clusters[b]

    labels = [0] * len(points)
    for label, cluster in enumerate(clusters):
        for i in cluster:
            labels[i] = label
    return labels


def silhouette_score(points: list[list[float]], labels: list[int]) -> float:
    """Return the mean silhouette coefficient over all ``points``.

    For each point, ``a`` is the mean distance to other points in its own
    cluster and ``b`` is the smallest mean distance to points in any other
    cluster; the silhouette is ``(b - a) / max(a, b)``. Raises
    :class:`ClusterError` if there are fewer than two clusters or any cluster
    is empty.
    """
    _check_points(points)
    if len(points) != len(labels):
        raise ClusterError("points and labels must have equal length")

    groups: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        groups.setdefault(lab, []).append(i)
    if len(groups) < 2:
        raise ClusterError("need at least two clusters")
    for members in groups.values():
        if not members:
            raise ClusterError("clusters must be non-empty")

    total = 0.0
    for i, p in enumerate(points):
        own = groups[labels[i]]
        if len(own) > 1:
            a = sum(euclidean(p, points[j]) for j in own if j != i) / (len(own) - 1)
        else:
            a = 0.0
        b = math.inf
        for lab, members in groups.items():
            if lab == labels[i]:
                continue
            mean_d = sum(euclidean(p, points[j]) for j in members) / len(members)
            if mean_d < b:
                b = mean_d
        denom = max(a, b)
        total += 0.0 if denom == 0.0 else (b - a) / denom
    return total / len(points)


def elbow(
    points: list[list[float]],
    k_range,
    seed: int = 0,
) -> list[tuple[int, float]]:
    """Return ``(k, inertia)`` for each ``k`` in ``k_range`` (the elbow curve).

    Runs :func:`kmeans` at every ``k`` and records its within-cluster inertia
    (sum of squared distances to the assigned centroid). Inertia decreases as
    ``k`` grows; the "elbow" — where the drop flattens — is a common visual cue
    for a good ``k``. Pairs come back in the order ``k_range`` is iterated.
    Raises :class:`ClusterError` if ``k_range`` is empty or any ``k`` is invalid
    (via :func:`kmeans`).
    """
    _check_points(points)
    ks = [int(k) for k in k_range]
    if not ks:
        raise ClusterError("k_range must be non-empty")
    out: list[tuple[int, float]] = []
    for k in ks:
        _labels, _centroids, inertia = kmeans(points, k, seed=seed)
        out.append((k, inertia))
    return out


def best_k_silhouette(
    points: list[list[float]],
    k_range,
    seed: int = 0,
) -> tuple[int, list[tuple[int, float]]]:
    """Choose the ``k`` maximising the mean silhouette over ``k_range``.

    For each ``k`` in ``k_range`` (each must be ``>= 2``, since the silhouette
    needs at least two clusters) this runs :func:`kmeans` and scores the labels
    with :func:`silhouette_score`. Returns ``(best_k, scores)`` where ``scores``
    is the list of ``(k, mean_silhouette)`` pairs and ``best_k`` is the ``k`` of
    the highest-scoring entry (first one wins on ties). Raises
    :class:`ClusterError` if ``k_range`` is empty or contains a ``k < 2``.
    """
    _check_points(points)
    ks = [int(k) for k in k_range]
    if not ks:
        raise ClusterError("k_range must be non-empty")
    if any(k < 2 for k in ks):
        raise ClusterError("silhouette needs k >= 2")
    scores: list[tuple[int, float]] = []
    for k in ks:
        labels, _centroids, _inertia = kmeans(points, k, seed=seed)
        scores.append((k, silhouette_score(points, labels)))
    best_k = max(scores, key=lambda pair: pair[1])[0]
    return best_k, scores


def dbscan(points: list[list[float]], eps: float, min_samples: int) -> list[int]:
    """Density-based clustering of ``points`` (DBSCAN).

    A point is a core point if at least ``min_samples`` points (including
    itself) lie within distance ``eps``; clusters grow outward from core
    points. Returns labels in ``0..m-1``, with density-unreachable points
    labelled :data:`NOISE` (``-1``). Raises :class:`ClusterError` for
    ``eps <= 0`` or ``min_samples < 1``.
    """
    _check_points(points)
    if eps <= 0.0:
        raise ClusterError("eps must be positive")
    if min_samples < 1:
        raise ClusterError("min_samples must be at least 1")

    n = len(points)
    labels = [NOISE] * n
    visited = [False] * n

    def region_query(idx: int) -> list[int]:
        return [j for j in range(n) if euclidean(points[idx], points[j]) <= eps]

    cluster_id = -1
    for i in range(n):
        if visited[i]:
            continue
        visited[i] = True
        neighbours = region_query(i)
        if len(neighbours) < min_samples:
            continue  # leave as NOISE for now
        cluster_id += 1
        labels[i] = cluster_id
        seeds = list(neighbours)
        s = 0
        while s < len(seeds):
            j = seeds[s]
            s += 1
            if not visited[j]:
                visited[j] = True
                j_neighbours = region_query(j)
                if len(j_neighbours) >= min_samples:
                    for nb in j_neighbours:
                        if nb not in seeds:
                            seeds.append(nb)
            if labels[j] == NOISE:
                labels[j] = cluster_id
    return labels
