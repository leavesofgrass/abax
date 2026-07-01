"""Tests for :mod:`abax.core.science.cluster`."""

from __future__ import annotations

import pytest

from abax.core.science.cluster import (
    ClusterError,
    agglomerative,
    dbscan,
    euclidean,
    kmeans,
    kmeans_predict,
    silhouette_score,
)

# Two well-separated 2-D blobs: five near (0,0), five near (10,10).
BLOB_A = [[0.0, 0.0], [0.5, 0.2], [0.1, 0.4], [0.3, -0.2], [-0.2, 0.1]]
BLOB_B = [[10.0, 10.0], [10.5, 9.8], [9.7, 10.2], [10.2, 10.3], [9.9, 9.6]]
POINTS = BLOB_A + BLOB_B
A_IDX = set(range(len(BLOB_A)))
B_IDX = set(range(len(BLOB_A), len(POINTS)))


def _partition(labels: list[int]) -> set[frozenset[int]]:
    """Reduce labels to the induced partition (relabeling-invariant)."""
    groups: dict[int, set[int]] = {}
    for i, lab in enumerate(labels):
        groups.setdefault(lab, set()).add(i)
    return {frozenset(g) for g in groups.values()}


def test_euclidean():
    assert euclidean([0.0, 0.0], [3.0, 4.0]) == pytest.approx(5.0)


def test_kmeans_separates_blobs():
    labels, centroids, inertia = kmeans(POINTS, 2, seed=0)
    a_labels = {labels[i] for i in A_IDX}
    b_labels = {labels[i] for i in B_IDX}
    assert len(a_labels) == 1
    assert len(b_labels) == 1
    assert a_labels != b_labels
    assert len(centroids) == 2
    assert inertia > 0.0
    assert inertia < 5.0


def test_kmeans_reproducible():
    labels1, _, _ = kmeans(POINTS, 2, seed=0)
    labels2, _, _ = kmeans(POINTS, 2, seed=0)
    assert _partition(labels1) == _partition(labels2)


def test_kmeans_predict():
    _, centroids, _ = kmeans(POINTS, 2, seed=0)
    near_origin = kmeans_predict([0.1, 0.1], centroids)
    near_ten = kmeans_predict([10.0, 10.0], centroids)
    assert near_origin != near_ten
    # The near-origin centroid is the one closest to (0,0).
    assert near_origin == kmeans_predict([0.0, 0.0], centroids)


@pytest.mark.parametrize("linkage", ["single", "complete", "average"])
def test_agglomerative_separates_blobs(linkage):
    labels = agglomerative(POINTS, 2, linkage=linkage)
    assert _partition(labels) == {frozenset(A_IDX), frozenset(B_IDX)}


def test_silhouette_high_for_separated():
    labels, _, _ = kmeans(POINTS, 2, seed=0)
    score = silhouette_score(POINTS, labels)
    assert score > 0.7


def test_dbscan_finds_two_clusters_and_outlier():
    pts = POINTS + [[100.0, 100.0]]
    labels = dbscan(pts, eps=2.0, min_samples=2)
    assert labels[-1] == -1  # the outlier is noise
    cluster_labels = {lab for lab in labels if lab != -1}
    assert len(cluster_labels) == 2
    # The two blobs land in different clusters.
    assert len({labels[i] for i in A_IDX}) == 1
    assert len({labels[i] for i in B_IDX}) == 1
    assert {labels[i] for i in A_IDX} != {labels[i] for i in B_IDX}


def test_kmeans_errors():
    with pytest.raises(ClusterError):
        kmeans(POINTS, 0)
    with pytest.raises(ClusterError):
        kmeans(POINTS, len(POINTS) + 1)
    with pytest.raises(ClusterError):
        kmeans([], 1)
    with pytest.raises(ClusterError):
        kmeans([[1.0, 2.0], [3.0]], 1)  # ragged


def test_agglomerative_errors():
    with pytest.raises(ClusterError):
        agglomerative(POINTS, 0)
    with pytest.raises(ClusterError):
        agglomerative(POINTS, len(POINTS) + 1)
    with pytest.raises(ClusterError):
        agglomerative(POINTS, 2, linkage="ward")


def test_silhouette_errors():
    # Fewer than two clusters.
    with pytest.raises(ClusterError):
        silhouette_score(POINTS, [0] * len(POINTS))


def test_dbscan_errors():
    with pytest.raises(ClusterError):
        dbscan(POINTS, eps=0.0, min_samples=2)
    with pytest.raises(ClusterError):
        dbscan(POINTS, eps=1.0, min_samples=0)
    with pytest.raises(ClusterError):
        dbscan([], eps=1.0, min_samples=1)
