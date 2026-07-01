"""Model-evaluation utilities — splitting, cross-validation, and metrics.

A dependency-free toolkit (no numpy / sklearn) for the common machine-learning
evaluation chores: shuffling data into train/test splits, building k-fold
cross-validation index partitions, and scoring predictions via the confusion
matrix, accuracy, precision / recall / F1, and ROC / AUC.

Everything is computed from raw counts (TP / FP / FN / TN) so the module needs
nothing beyond :mod:`math` and :mod:`random`. Determinism comes from a private
:class:`random.Random` seeded per call, so the same ``seed`` always yields the
same shuffle.

Conventions
-----------
* ``X`` / ``y`` are parallel sequences (any indexable / iterable of samples and
  labels); they are materialised into lists internally.
* Labels may be any hashable, orderable value (commonly ``0`` / ``1`` ints).
* ROC works on binary problems: labels in ``{0, 1}`` or any two labels where the
  larger compares as the positive class; ``scores`` are decision scores for that
  positive class (higher == more positive).
* :func:`auc` integrates by the trapezoidal rule with ``xs`` ascending — pass
  ``auc(fpr, tpr)`` since :func:`roc_curve` returns ``fpr`` ascending.
"""

from __future__ import annotations

import math
import random


class MetricsError(Exception):
    """Raised on any evaluation error (length mismatch, bad parameter, …)."""


def train_test_split(
    X,
    y,
    test_frac: float = 0.25,
    seed: int = 0,
) -> tuple[list, list, list, list]:
    """Shuffle ``X`` / ``y`` and split into ``(X_train, X_test, y_train, y_test)``.

    Indices are shuffled with ``random.Random(seed)`` (so the split is
    reproducible) and the trailing ``round(n * test_frac)`` samples become the
    test set. Requires ``0 < test_frac < 1`` and at least two samples.
    """
    X = list(X)
    y = list(y)
    if len(X) != len(y):
        raise MetricsError("X and y must have the same length")
    n = len(X)
    if n < 2:
        raise MetricsError("need at least 2 samples to split")
    if not 0.0 < test_frac < 1.0:
        raise MetricsError("test_frac must be in (0, 1)")

    indices = list(range(n))
    random.Random(seed).shuffle(indices)

    n_test = round(n * test_frac)
    n_test = max(1, min(n - 1, n_test))
    test_idx = indices[:n_test]
    train_idx = indices[n_test:]

    X_train = [X[i] for i in train_idx]
    X_test = [X[i] for i in test_idx]
    y_train = [y[i] for i in train_idx]
    y_test = [y[i] for i in test_idx]
    return X_train, X_test, y_train, y_test


def kfold_indices(n: int, k: int = 5, seed: int = 0) -> list[tuple[list[int], list[int]]]:
    """Partition ``range(n)`` into ``k`` shuffled, near-equal folds.

    Returns ``k`` ``(train_idx, test_idx)`` pairs; the test sets are disjoint and
    together cover every index exactly once. Requires ``2 <= k <= n``.
    """
    if k < 2:
        raise MetricsError("k must be at least 2")
    if k > n:
        raise MetricsError("k cannot exceed the number of samples")

    indices = list(range(n))
    random.Random(seed).shuffle(indices)

    # Near-equal fold sizes: the first (n % k) folds get one extra index.
    base, extra = divmod(n, k)
    folds: list[list[int]] = []
    start = 0
    for f in range(k):
        size = base + (1 if f < extra else 0)
        folds.append(indices[start:start + size])
        start += size

    pairs: list[tuple[list[int], list[int]]] = []
    for f in range(k):
        test_idx = folds[f]
        train_idx = [i for g in range(k) if g != f for i in folds[g]]
        pairs.append((train_idx, test_idx))
    return pairs


def confusion_matrix(y_true, y_pred, labels=None) -> tuple[list, list[list[int]]]:
    """Return ``(labels, matrix)`` with ``matrix[i][j]`` = count of true=labels[i], pred=labels[j].

    ``labels`` defaults to the sorted unique values across ``y_true`` and
    ``y_pred``.
    """
    y_true = list(y_true)
    y_pred = list(y_pred)
    if len(y_true) != len(y_pred):
        raise MetricsError("y_true and y_pred must have the same length")

    if labels is None:
        labels = sorted(set(y_true) | set(y_pred))
    else:
        labels = list(labels)

    index = {label: i for i, label in enumerate(labels)}
    matrix = [[0 for _ in labels] for _ in labels]
    for t, p in zip(y_true, y_pred):
        if t in index and p in index:
            matrix[index[t]][index[p]] += 1
    return labels, matrix


def accuracy(y_true, y_pred) -> float:
    """Fraction of predictions that match ``y_true`` exactly."""
    y_true = list(y_true)
    y_pred = list(y_pred)
    if len(y_true) != len(y_pred):
        raise MetricsError("y_true and y_pred must have the same length")
    if not y_true:
        raise MetricsError("cannot compute accuracy of an empty sequence")
    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    return correct / len(y_true)


def _binary_counts(y_true, y_pred, positive) -> tuple[int, int, int, int]:
    """Tally ``(tp, fp, fn, tn)`` for ``positive`` against the rest."""
    tp = fp = fn = tn = 0
    for t, p in zip(y_true, y_pred):
        t_pos = t == positive
        p_pos = p == positive
        if t_pos and p_pos:
            tp += 1
        elif not t_pos and p_pos:
            fp += 1
        elif t_pos and not p_pos:
            fn += 1
        else:
            tn += 1
    return tp, fp, fn, tn


def _prf_from_counts(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    """Precision, recall, F1 from counts (zero where the denominator is zero)."""
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


def precision_recall_f1(
    y_true,
    y_pred,
    positive=None,
    average: str = "binary",
) -> tuple[float, float, float]:
    """Return ``(precision, recall, f1)``.

    ``average="binary"`` scores the ``positive`` class (default: the maximum
    label seen). ``average="macro"`` returns the unweighted mean of the
    per-class metrics over every label.
    """
    y_true = list(y_true)
    y_pred = list(y_pred)
    if len(y_true) != len(y_pred):
        raise MetricsError("y_true and y_pred must have the same length")
    if not y_true:
        raise MetricsError("cannot score an empty sequence")

    labels = sorted(set(y_true) | set(y_pred))

    if average == "binary":
        if positive is None:
            positive = max(labels)
        tp, fp, fn, _ = _binary_counts(y_true, y_pred, positive)
        return _prf_from_counts(tp, fp, fn)

    if average == "macro":
        precisions = []
        recalls = []
        f1s = []
        for label in labels:
            tp, fp, fn, _ = _binary_counts(y_true, y_pred, label)
            pr, rc, f1 = _prf_from_counts(tp, fp, fn)
            precisions.append(pr)
            recalls.append(rc)
            f1s.append(f1)
        m = len(labels)
        return sum(precisions) / m, sum(recalls) / m, sum(f1s) / m

    raise MetricsError(f"unknown average: {average!r}")


def roc_curve(y_true, scores) -> tuple[list[float], list[float], list[float]]:
    """Compute the ROC curve for a binary problem.

    ``y_true`` must contain exactly two distinct labels (or one — interpreted
    against an implicit other); the larger label is treated as positive.
    ``scores`` are decision scores for the positive class (higher == positive).

    Returns ``(fpr, tpr, thresholds)`` sorted by *decreasing* threshold, with the
    curve starting at ``(0, 0)`` and ending at ``(1, 1)``. The leading point uses
    a threshold of ``+inf``.
    """
    y_true = list(y_true)
    scores = list(scores)
    if len(y_true) != len(scores):
        raise MetricsError("y_true and scores must have the same length")
    if not y_true:
        raise MetricsError("cannot compute a ROC curve for an empty sequence")

    unique = sorted(set(y_true))
    if len(unique) > 2:
        raise MetricsError("roc_curve requires binary y_true")
    positive = unique[-1]

    labels = [1 if t == positive else 0 for t in y_true]
    total_pos = sum(labels)
    total_neg = len(labels) - total_pos
    if total_pos == 0 or total_neg == 0:
        raise MetricsError("roc_curve requires both positive and negative samples")

    # Sort by score descending; sweep the threshold downward.
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

    fpr: list[float] = [0.0]
    tpr: list[float] = [0.0]
    thresholds: list[float] = [math.inf]

    tp = 0
    fp = 0
    i = 0
    n = len(order)
    while i < n:
        threshold = scores[order[i]]
        # Consume every sample tied at this threshold before recording a point.
        while i < n and scores[order[i]] == threshold:
            if labels[order[i]] == 1:
                tp += 1
            else:
                fp += 1
            i += 1
        tpr.append(tp / total_pos)
        fpr.append(fp / total_neg)
        thresholds.append(threshold)

    return fpr, tpr, thresholds


def auc(xs, ys) -> float:
    """Area under the curve defined by ``(xs, ys)`` via the trapezoidal rule.

    ``xs`` must be ascending (as :func:`roc_curve` returns ``fpr``); call as
    ``auc(fpr, tpr)``.
    """
    xs = list(xs)
    ys = list(ys)
    if len(xs) != len(ys):
        raise MetricsError("xs and ys must have the same length")
    if len(xs) < 2:
        return 0.0
    area = 0.0
    for i in range(1, len(xs)):
        area += (xs[i] - xs[i - 1]) * (ys[i] + ys[i - 1]) / 2.0
    return area


def cross_val_score(model_factory, X, y, k: int = 5, seed: int = 0) -> list[float]:
    """Run k-fold cross-validation and return the per-fold accuracies.

    For each fold a fresh ``model = model_factory()`` is fit on the training
    split (``model.fit(X_train, y_train)``) and scored by :func:`accuracy` on the
    held-out fold (``model.predict(X_test)``). ``model_factory`` is a zero-arg
    callable returning an object exposing ``.fit`` and ``.predict``.
    """
    X = list(X)
    y = list(y)
    if len(X) != len(y):
        raise MetricsError("X and y must have the same length")

    scores: list[float] = []
    for train_idx, test_idx in kfold_indices(len(X), k=k, seed=seed):
        X_train = [X[i] for i in train_idx]
        y_train = [y[i] for i in train_idx]
        X_test = [X[i] for i in test_idx]
        y_test = [y[i] for i in test_idx]

        model = model_factory()
        model.fit(X_train, y_train)
        preds = list(model.predict(X_test))
        scores.append(accuracy(y_test, preds))
    return scores
