"""Clustering with preprocessing, held-out scoring and honest metrics (plan C2).

Why this module exists
----------------------
The old trainer handed the raw columns to the estimator, so a CSV with text
or missing values simply failed, and every score was computed on the very
rows the model was fitted on - a silhouette that rewards overfitting, with
no baseline to read it against.

The new contract (plan C2):

* the feature analysis and the preprocessor of the tabular path are reused
  (impute, one-hot, standardise), so a messy CSV trains instead of failing;
* 20 percent of the rows are held out when the model has an out-of-sample
  step (``predict`` or ``transform``), and the scores that support it are
  computed on those rows;
* the metrics are the honest set: silhouette (on a sample, because it is
  quadratic), Davies-Bouldin, Calinski-Harabasz, the cluster sizes, the
  noise fraction of the density methods, BIC and AIC for the mixture, and
  the stability - the adjusted Rand index between two fits with different
  seeds, the check that clusters are not an accident of the seed;
* the baseline is the silhouette of random labels with the same cluster
  sizes (about zero), so a number can be read;
* prediction exists where the model can assign new rows (K-Means, GMM,
  Birch-like, and the projections), and the bundle says so where it cannot
  (t-SNE, agglomerative, the density methods) - the endpoint answers with
  the reason instead of guessing. For DBSCAN, assigning a new row to the
  nearest core sample within ``eps`` is the documented option.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, DBSCAN, KMeans
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from sklearn.metrics import (
    adjusted_rand_score,
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_score,
)
from sklearn.mixture import GaussianMixture
from sklearn.model_selection import train_test_split

from .bundles import BundleError, register_loader
from .charts import build_cluster_charts, cap_charts
from .tabular import (
    FeaturePlan,
    analyze_features,
    build_preprocessor,
    coerce_features,
    describe_features,
)

# The silhouette is quadratic in the rows: it is computed on a sample.
SILHOUETTE_SAMPLE = 5000
# The fraction of the rows held out when the model has an out-of-sample step.
HELD_OUT_FRACTION = 0.2

try:
    import hdbscan as hdbscan_module
except ImportError:  # pragma: no cover - the package is optional
    hdbscan_module = None

try:
    import umap as umap_module
except ImportError:  # pragma: no cover - the package is optional
    umap_module = None

try:
    from hmmlearn import hmm as hmm_module
except ImportError:  # pragma: no cover - the package is optional
    hmm_module = None


# --- the bundle -----------------------------------------------------------------


class ClusteringBundle:
    """The artifact of a clustering or embedding run (plan C1/C2).

    ``predicts`` says whether the model can assign or project new rows; the
    predict endpoint refuses (with the reason) when it cannot.
    """

    kind = "clustering"
    request_kind = "rows"

    def __init__(
        self,
        model: Any,
        preprocessor: Any,
        plan: FeaturePlan,
        feature_schema: List[Dict[str, Any]],
        model_name: str,
        labels: Optional[np.ndarray] = None,
        predicts: bool = False,
        mode: str = "assign",
        noise_label: int = -1,
        eps: Optional[float] = None,
    ):
        self.model = model
        self.preprocessor = preprocessor
        self.plan = plan
        self.feature_schema = feature_schema
        self.model_name = model_name
        self.labels = labels
        self.predicts = predicts
        self.mode = mode  # "assign" (cluster ids) or "project" (coordinates)
        self.noise_label = noise_label
        self.eps = eps

    def schema(self) -> Dict[str, Any]:
        return {
            "request_kind": self.request_kind,
            "kind": self.kind,
            "model_name": self.model_name,
            "features": self.feature_schema,
            "can_predict": self.predicts,
            "output": (
                "the cluster id of each row"
                if self.mode == "assign"
                else "the projected coordinates of each row"
            ),
            "max_rows": 1000,
        }

    def infer(self, request: Dict[str, Any]) -> Dict[str, Any]:
        if not self.predicts:
            raise BundleError(
                "This clustering model cannot assign new rows: it only "
                "describes the rows it was fitted on."
            )
        from .tabular import prepare_rows

        rows = request.get("rows") or []
        if not rows:
            raise ValueError("The request has no row.")
        frame, warnings_list = prepare_rows(self.plan, self.feature_schema, rows)
        Z = self.preprocessor.transform(frame)
        if self.mode == "project":
            coordinates = self.model.transform(Z)
            return {
                "predictions": [
                    [round(float(v), 6) for v in row] for row in np.asarray(coordinates)
                ],
                "warnings": warnings_list,
            }
        if isinstance(self.model, DBSCAN):
            # The documented option of plan C2: a new row joins the nearest
            # core sample when it is within eps, and is noise otherwise.
            from sklearn.neighbors import NearestNeighbors

            core = self.model.components_
            neighbours = NearestNeighbors(n_neighbors=1).fit(core)
            distances, indices = neighbours.kneighbors(Z)
            assignments = []
            for distance, index in zip(distances[:, 0], indices[:, 0]):
                if distance <= (self.eps or self.model.eps):
                    assignments.append(int(self.model.labels_[self.model.core_sample_indices_][index]))
                else:
                    assignments.append(int(self.noise_label))
            return {"predictions": assignments, "warnings": warnings_list}
        predictions = self.model.predict(Z)
        return {"predictions": [int(v) for v in np.asarray(predictions)], "warnings": warnings_list}

    def save(self, directory) -> None:
        import joblib
        from pathlib import Path

        joblib.dump(self, Path(directory) / "model.joblib")

    @classmethod
    def load(cls, directory, manifest=None) -> "ClusteringBundle":
        import joblib
        from pathlib import Path

        return joblib.load(Path(directory) / "model.joblib")


register_loader("clustering", ClusteringBundle.load)


# --- the trainer -----------------------------------------------------------------


def _estimator(model_name: str, params: Dict[str, Any]) -> Tuple[Any, str, bool]:
    """Build the estimator; answer (model, mode, has_out_of_sample)."""
    if model_name == "K-Mean":
        return KMeans(**params), "assign", True
    if model_name == "GMM":
        return GaussianMixture(**params), "assign", True
    if model_name == "HMM_timeseries":
        if hmm_module is None:
            raise RuntimeError("hmmlearn is not installed")
        return hmm_module.GaussianHMM(**params), "assign", True
    if model_name == "Hierarchical_Clustering":
        return AgglomerativeClustering(**params), "assign", False
    if model_name == "DBSCAN":
        return DBSCAN(**params), "assign", False
    if model_name == "HDBSCAN":
        if hdbscan_module is None:
            raise RuntimeError("hdbscan is not installed")
        return hdbscan_module.HDBSCAN(**params), "assign", False
    if model_name == "PCA":
        return PCA(**params), "project", True
    if model_name == "UMAP":
        if umap_module is None:
            raise RuntimeError("umap is not installed")
        return umap_module.UMAP(**params), "project", True
    if model_name == "t-SNE":
        return TSNE(**params), "project", False
    raise ValueError(f"Unsupported clustering model: {model_name}")


def _fit_labels(model: Any, Z: np.ndarray) -> np.ndarray:
    if hasattr(model, "fit_predict"):
        labels = model.fit_predict(Z)
    else:
        model.fit(Z)
        if hasattr(model, "labels_"):
            labels = model.labels_
        elif hasattr(model, "predict"):
            labels = model.predict(Z)
        else:
            labels = np.full(len(Z), -1)
    return np.asarray(labels)


def _honest_scores(Z: np.ndarray, labels: np.ndarray) -> Dict[str, Any]:
    """The honest clustering metrics of plan C2, noise excluded."""
    non_noise = labels != -1
    unique = np.unique(labels[non_noise]) if non_noise.any() else np.array([])
    scores: Dict[str, Any] = {
        "silhouette": None,
        "davies_bouldin": None,
        "calinski_harabasz": None,
        "silhouette_baseline": None,
    }
    if len(unique) >= 2 and non_noise.sum() >= 3:
        Z_used, y_used = Z[non_noise], labels[non_noise]
        # The silhouette is quadratic: it is computed on a sample.
        if len(Z_used) > SILHOUETTE_SAMPLE:
            indices = np.random.default_rng(0).choice(
                len(Z_used), SILHOUETTE_SAMPLE, replace=False
            )
            Z_scored, y_scored = Z_used[indices], y_used[indices]
        else:
            Z_scored, y_scored = Z_used, y_used
        try:
            scores["silhouette"] = round(float(silhouette_score(Z_scored, y_scored)), 4)
        except Exception:
            pass
        # The baseline: random labels with the same cluster sizes score about
        # zero, which is what makes a number readable (plan C2).
        try:
            rng = np.random.default_rng(0)
            shuffled = rng.permutation(y_scored)
            scores["silhouette_baseline"] = round(
                float(silhouette_score(Z_scored, shuffled)), 4
            )
        except Exception:
            pass
        try:
            scores["davies_bouldin"] = round(float(davies_bouldin_score(Z_used, y_used)), 4)
        except Exception:
            pass
        try:
            scores["calinski_harabasz"] = round(
                float(calinski_harabasz_score(Z_used, y_used)), 2
            )
        except Exception:
            pass
    return scores


def train_clustering_model(
    model_name: str,
    dataset: pd.DataFrame,
    label_column: str,
    params: Dict[str, Any],
    test_size: float = 0.2,
    random_state: int = 42,
) -> Tuple[Dict[str, Any], ClusteringBundle]:
    """Train a clustering model on the preprocessed features (plan C2)."""
    X_raw = dataset.drop(columns=[label_column]) if label_column in dataset.columns else dataset
    plan = analyze_features(X_raw)
    X = coerce_features(X_raw, plan)

    estimator_params = {
        k: v for k, v in params.items() if k not in ("test_size", "random_state", "forecasting", "window", "horizon")
    }
    model, mode, has_out_of_sample = _estimator(model_name, estimator_params)

    # The held-out rows of plan C2: only when the model can say something
    # about rows it was not fitted on. A density method or a t-SNE embedding
    # has no out-of-sample step, so every row is a training row for it.
    if has_out_of_sample:
        X_train, X_test = train_test_split(
            X, test_size=test_size, random_state=random_state
        )
    else:
        X_train, X_test = X, X.iloc[0:0]
    preprocessor = build_preprocessor(plan, scale=True)
    Z_train = preprocessor.fit_transform(X_train)

    labels_train = _fit_labels(model, Z_train)

    # The stability of plan C2: two fits with different seeds, compared with
    # the adjusted Rand index. Only the models whose result depends on a seed
    # have something to measure.
    stability = None
    if "random_state" in params or model_name in ("K-Mean", "GMM", "UMAP", "HMM_timeseries"):
        try:
            second_params = dict(estimator_params)
            if "random_state" in _param_names(model):
                second_params["random_state"] = (int(params.get("random_state", random_state)) + 1)
            second_model, _, _ = _estimator(model_name, second_params)
            labels_second = _fit_labels(second_model, Z_train)
            if len(np.unique(labels_train)) >= 1 and len(np.unique(labels_second)) >= 1:
                stability = round(float(adjusted_rand_score(labels_train, labels_second)), 4)
        except Exception:
            stability = None

    metrics: Dict[str, Any] = {
        "task_type": "clustering",
        "model_name": model_name,
        "train_size": int(len(X_train)),
        "test_size": int(len(X_test)) if has_out_of_sample else 0,
        "cluster_count": int(pd.Series(labels_train).nunique()),
        "noise_count": int((labels_train == -1).sum()),
        "noise_fraction": round(float((labels_train == -1).mean()), 4),
        "cluster_sizes": {
            str(int(label)): int(count)
            for label, count in sorted(pd.Series(labels_train).value_counts().items())
        },
        "stability_ari": stability,
        "artifact_kind": ClusteringBundle.kind,
    }
    metrics.update(_honest_scores(Z_train, labels_train))

    # The held-out scores of plan C2, where the model supports them.
    if has_out_of_sample and len(X_test) > 0:
        Z_test = preprocessor.transform(X_test)
        try:
            if mode == "assign":
                held_labels = model.predict(Z_test)
                metrics["held_out_silhouette"] = _honest_scores(Z_test, np.asarray(held_labels))[
                    "silhouette"
                ]
            elif isinstance(model, PCA):
                # The honest number of a projection: the variance the
                # components explain on rows they were not fitted on.
                variance = model.explained_variance_ratio_
                metrics["explained_variance"] = [
                    round(float(v), 4) for v in np.asarray(variance)
                ]
                metrics["held_out_reconstruction_mse"] = round(
                    float(np.mean((Z_test - model.inverse_transform(model.transform(Z_test))) ** 2)),
                    6,
                )
        except Exception:
            pass

    if isinstance(model, GaussianMixture):
        try:
            metrics["bic"] = round(float(model.bic(Z_train)), 2)
            metrics["aic"] = round(float(model.aic(Z_train)), 2)
        except Exception:
            pass
    if isinstance(model, DBSCAN):
        metrics["eps"] = float(model.eps)

    # The chart data of plan E1: a 2-D PCA projection of a sample with the
    # labels, and the cluster sizes.
    charts: Dict[str, Any] = {}
    try:
        sample = Z_train
        labels_sample = labels_train
        if len(Z_train) > 1000:
            indices = np.random.default_rng(0).choice(len(Z_train), 1000, replace=False)
            sample, labels_sample = Z_train[indices], labels_train[indices]
        if sample.shape[1] > 2:
            projection = PCA(n_components=2, random_state=random_state).fit_transform(sample)
        else:
            projection = np.asarray(sample)
        charts["scatter"] = {
            "x": [round(float(v), 4) for v in projection[:, 0]],
            "y": [round(float(v), 4) for v in projection[:, 1]],
            "label": [str(int(v)) for v in labels_sample],
        }
        charts["cluster_sizes"] = metrics["cluster_sizes"]
        metrics["_charts"] = cap_charts(charts)
    except Exception:
        pass

    bundle = ClusteringBundle(
        model=model,
        preprocessor=preprocessor,
        plan=plan,
        feature_schema=describe_features(X_train, plan),
        model_name=model_name,
        labels=labels_train,
        predicts=has_out_of_sample,
        mode=mode,
        eps=float(model.eps) if isinstance(model, DBSCAN) else None,
    )
    return metrics, bundle


def _param_names(model: Any) -> List[str]:
    """The parameter names an estimator accepts."""
    try:
        return list(model.get_params().keys())
    except Exception:
        return []
