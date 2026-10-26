"""The chart data of a run (plan E1): what the trainers record, capped.

Why this module exists
----------------------
The run page used to show two numbers (a score and its baseline) and a
confusion matrix. That is not enough to answer "why is this model good or
bad": the answer needs the curves (training loss, ROC, precision-recall), the
errors (residuals, error histogram) and the importances.

The data is computed **at training time** from the held-out rows the trainer
already holds, written into the ``charts`` column of the run, and served by
``GET /runs/{id}/charts`` - never by the run list. Every array is capped
(points and bytes), because a list of a hundred runs that carries a hundred
sets of curve points is slow for the reason the pagination fixed.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import roc_curve, precision_recall_curve

# The caps (plan E1): every array that leaves the trainer is bounded, so a
# run page stays light whatever the dataset was.
MAX_CURVE_POINTS = 200
MAX_SCATTER_POINTS = 500
RESIDUAL_BINS = 30
CALIBRATION_BINS = 10
MAX_IMPORTANCES = 20
# The serialized charts of one run stay under this (a safety net on top of
# the per-array caps).
MAX_CHART_BYTES = 256 * 1024


def _finite(values: Sequence[float]) -> List[float]:
    out = []
    for value in values:
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(v):
            out.append(v)
    return out


def _downsample(values: Sequence[Any], limit: int = MAX_CURVE_POINTS) -> List[Any]:
    """Keep at most ``limit`` evenly spaced points of a series."""
    values = list(values)
    if len(values) <= limit:
        return values
    step = len(values) / limit
    return [values[int(i * step)] for i in range(limit)]


def cap_charts(charts: Dict[str, Any]) -> Dict[str, Any]:
    """Cap every array of the chart data (a test asserts the cap)."""
    capped: Dict[str, Any] = {}

    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            if len(value) > MAX_SCATTER_POINTS * 2:
                value = _downsample(value, MAX_SCATTER_POINTS * 2)
            return [walk(v) for v in value]
        if isinstance(value, float) and not np.isfinite(value):
            return None
        return value

    for key, value in charts.items():
        capped[key] = walk(value)
    return capped


def build_classification_charts(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    probabilities: Optional[np.ndarray],
    class_labels: Optional[Sequence[Any]] = None,
    confusion: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """The curves and error views of a classification run (plan E1).

    ROC per class (one against the rest) and precision-recall come from the
    probabilities; the calibration bins and the probability histogram say
    whether the scores can be read as confidences; the confusion matrix is
    row-normalised so the errors of the rare classes are visible.
    """
    charts: Dict[str, Any] = {}
    classes = list(class_labels) if class_labels is not None else sorted(set(y_true))
    n_classes = len(classes)

    if confusion is not None and confusion.size:
        row_sums = confusion.sum(axis=1, keepdims=True)
        safe = np.where(row_sums > 0, row_sums, 1)
        charts["confusion"] = {
            "labels": [str(c) for c in classes],
            "matrix": (confusion / safe).round(4).tolist(),
            "counts": confusion.tolist(),
        }

    if probabilities is not None and n_classes >= 2 and len(y_true) == len(probabilities):
        probs = np.asarray(probabilities, dtype=float)
        binary = n_classes == 2
        roc_curves: List[Dict[str, Any]] = []
        pr_curves: List[Dict[str, Any]] = []
        for index, label in enumerate(classes):
            if index >= 10:
                break
            scores = probs[:, 1] if binary else probs[:, index]
            truth = (np.asarray(y_true) == index).astype(int)
            if truth.sum() in (0, len(truth)):
                continue  # the class never appears: the curve is undefined
            fpr, tpr, _ = roc_curve(truth, scores)
            roc_curves.append(
                {
                    "class": str(label),
                    "fpr": _downsample(_finite(fpr)),
                    "tpr": _downsample(_finite(tpr)),
                }
            )
            precision, recall, _ = precision_recall_curve(truth, scores)
            pr_curves.append(
                {
                    "class": str(label),
                    "precision": _downsample(_finite(precision)),
                    "recall": _downsample(_finite(recall)),
                }
            )
        if roc_curves:
            charts["roc"] = roc_curves
        if pr_curves:
            charts["precision_recall"] = pr_curves

        # The histogram of the predicted probability of the positive class
        # (binary) or of the maximum (multiclass): how confident the model is.
        confident = probs[:, 1] if binary else probs.max(axis=1)
        counts, edges = np.histogram(confident, bins=20, range=(0.0, 1.0))
        charts["probability_histogram"] = {
            "counts": counts.tolist(),
            "edges": edges.round(4).tolist(),
        }

        # The calibration bins: mean predicted score against the observed
        # frequency, the honest version of "the model is 80% sure".
        predicted = probs[:, 1] if binary else probs.max(axis=1)
        truth = (np.asarray(y_true) == (1 if binary else np.argmax(probs, axis=1))).astype(int)
        try:
            bin_index = np.clip(
                (predicted * CALIBRATION_BINS).astype(int), 0, CALIBRATION_BINS - 1
            )
            bins = []
            for b in range(CALIBRATION_BINS):
                mask = bin_index == b
                if mask.any():
                    bins.append(
                        {
                            "bin": b,
                            "mean_predicted": float(predicted[mask].mean()),
                            "observed": float(truth[mask].mean()),
                            "count": int(mask.sum()),
                        }
                    )
            if bins:
                charts["calibration"] = bins
        except Exception:  # pragma: no cover - a chart must never fail a run
            pass

    return charts


def build_regression_charts(
    y_true: np.ndarray, y_pred: np.ndarray
) -> Dict[str, Any]:
    """The error views of a regression run (plan E1)."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    residuals = y_true - y_pred
    charts: Dict[str, Any] = {}

    keep = min(len(y_true), MAX_SCATTER_POINTS)
    if len(y_true) > keep:
        indices = np.linspace(0, len(y_true) - 1, keep).astype(int)
    else:
        indices = np.arange(len(y_true))
    charts["predicted_vs_actual"] = {
        "actual": _finite(y_true[indices]),
        "predicted": _finite(y_pred[indices]),
    }

    counts, edges = np.histogram(residuals[np.isfinite(residuals)], bins=RESIDUAL_BINS)
    charts["residual_histogram"] = {
        "counts": counts.tolist(),
        "edges": edges.round(6).tolist(),
    }
    charts["residuals_vs_predicted"] = {
        "predicted": _finite(y_pred[indices]),
        "residual": _finite(residuals[indices]),
    }
    return charts


def cv_fold_chart(cv: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The score of every fold (plan E1), when the cross-validation ran."""
    scores = (cv or {}).get("scores") or {}
    for metric in ("accuracy", "f1_macro", "r2"):
        entry = scores.get(metric)
        if entry and entry.get("mean") is not None:
            return {
                "metric": metric,
                "mean": entry["mean"],
                "std": entry.get("std"),
            }
    return None


def permutation_importances(
    predict_fn: Callable[[pd.DataFrame], np.ndarray],
    X_test: pd.DataFrame,
    y_test: np.ndarray,
    scorer: Callable[[np.ndarray, np.ndarray], float],
    plan: Any,
    seed: int = 42,
    max_features: int = MAX_IMPORTANCES,
) -> List[Dict[str, Any]]:
    """The permutation importances of a model on the held-out rows (plan D5).

    One column at a time is shuffled and the score is measured again: the
    drop is the importance. It works for any model (a coefficient is only a
    coefficient), it costs one prediction per column, and it is computed on
    the rows the model never trained on - which is where the question is
    asked. Deterministic through ``seed``.
    """
    if X_test is None or len(X_test) == 0 or not getattr(plan, "columns", None):
        return []
    rng = np.random.default_rng(seed)
    try:
        baseline = float(scorer(np.asarray(y_test), np.asarray(predict_fn(X_test))))
    except Exception:
        return []

    importances: List[Dict[str, Any]] = []
    for column in list(plan.columns)[:200]:
        shuffled = X_test.copy()
        values = shuffled[column].to_numpy().copy()
        if len(np.unique(values)) < 2:
            continue
        rng.shuffle(values)
        shuffled[column] = values
        try:
            score = float(scorer(np.asarray(y_test), np.asarray(predict_fn(shuffled))))
        except Exception:
            continue
        importances.append(
            {"feature": str(column), "importance": round(baseline - score, 6)}
        )
    importances.sort(key=lambda entry: abs(entry["importance"]), reverse=True)
    return importances[:max_features]


def build_cluster_charts(
    projection: np.ndarray, labels: np.ndarray, cluster_sizes: Dict[str, int]
) -> Dict[str, Any]:
    """The scatter of a clustering run: a 2-D PCA projection with the labels."""
    projection = np.asarray(projection, dtype=float)
    keep = min(len(projection), 1000)
    if len(projection) > keep:
        indices = np.linspace(0, len(projection) - 1, keep).astype(int)
        projection = projection[indices]
        labels = np.asarray(labels)[indices]
    return {
        "scatter": {
            "x": _finite(projection[:, 0]) if projection.ndim == 2 else [],
            "y": _finite(projection[:, 1]) if projection.ndim == 2 else [],
            "label": [str(v) for v in np.asarray(labels).tolist()],
        },
        "cluster_sizes": cluster_sizes,
    }


def build_error_histogram(errors: np.ndarray, threshold: Optional[float] = None) -> Dict[str, Any]:
    """The reconstruction-error histogram of an autoencoder run."""
    errors = np.asarray(errors, dtype=float)
    finite = errors[np.isfinite(errors)]
    counts, edges = np.histogram(finite, bins=30)
    return {
        "counts": counts.tolist(),
        "edges": edges.round(6).tolist(),
        "threshold": threshold,
    }
