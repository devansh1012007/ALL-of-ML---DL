"""Preprocessing, evaluation and the artifact of the tabular models.

Why this module exists
----------------------
The tabular trainers used to hand the raw columns of a CSV to the estimator.
That has three consequences that make a reported "accuracy" misleading:

* a text column or a missing value crashed most estimators, so a messy CSV
  could not be trained at all (and the ones that survived, like the boosters,
  silently treated the data differently from the others);
* the single, unstratified hold-out split gave one noisy number, and nothing
  said what a model that always predicts the majority class would score;
* the artifact was a bare estimator: nothing recorded which columns it expects,
  so it could not be used on new data without the training code.

This module fixes the three together, because they are one contract:

* ``analyze_features`` / ``build_preprocessor``: numeric columns are imputed
  (median) and, for the models that need it, standardised; categorical columns
  are imputed (most frequent) and one-hot encoded; identifier-like columns are
  dropped and reported. The preprocessor lives *inside* the pipeline, so it is
  fitted on the training rows only (and refitted per fold in the search and the
  cross-validation) - there is no leakage of the test rows.
* ``split_data`` / ``evaluate_holdout`` / ``cross_validate_pipeline``: a
  stratified hold-out split, task-correct metrics and a baseline to compare
  them with, and a k-fold cross-validation of the final pipeline.
* ``TabularModelBundle``: the artifact. It carries the fitted pipeline *and*
  the schema of the features, so the server can answer a prediction request
  for a row it has never seen.

The module has no dependency on ``model_training`` (which builds the
estimators and calls into this module), so there is no import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import KFold, StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, OneHotEncoder, StandardScaler

# A categorical column with more distinct values than this *and* mostly unique
# values is an identifier or free text: one-hot encoding it would add one
# column per row and teach the model to memorise the row.
MAX_CATEGORIES = 50
IDENTIFIER_UNIQUE_RATIO = 0.5

# How many distinct values of a categorical column the schema keeps. Past this
# the list is marked truncated, and "unseen category" is no longer reported.
SCHEMA_CATEGORY_LIMIT = 200

# The models whose result depends on the scale of the features. The trees and
# the boosters do not need it, and keeping their features in the original units
# keeps the feature importances readable.
SCALE_SENSITIVE_MODELS = frozenset({"Logistic_Regression", "MLR", "KNN", "SVM"})

# A cross-validation fold has to be able to hold both a training and a test part.
MIN_ROWS_PER_FOLD = 2


class FeatureInputError(ValueError):
    """A row sent for a prediction cannot be turned into the model's features.

    The message names the column and the value, so the client can fix it.
    """


# --- feature analysis --------------------------------------------------------


@dataclass
class FeaturePlan:
    """Which columns the model uses, and how each of them is treated."""

    numeric: List[str] = field(default_factory=list)
    categorical: List[str] = field(default_factory=list)
    dropped: List[Dict[str, str]] = field(default_factory=list)

    @property
    def columns(self) -> List[str]:
        return [*self.numeric, *self.categorical]


def _is_numeric(series: pd.Series) -> bool:
    # bool is numeric here: True/False become 1/0, which is what every
    # estimator would do with them anyway.
    return bool(
        pd.api.types.is_bool_dtype(series) or pd.api.types.is_numeric_dtype(series)
    )


def analyze_features(X: pd.DataFrame) -> FeaturePlan:
    """Decide, from the columns alone (never from the label), how to treat them."""
    plan = FeaturePlan()
    for column in X.columns:
        series = X[column]
        non_null = series.dropna()
        if non_null.empty:
            plan.dropped.append({"column": str(column), "reason": "every value is missing"})
            continue
        if _is_numeric(series):
            plan.numeric.append(column)
            continue
        distinct = int(non_null.nunique())
        if distinct > MAX_CATEGORIES and distinct / len(non_null) > IDENTIFIER_UNIQUE_RATIO:
            plan.dropped.append(
                {
                    "column": str(column),
                    "reason": (
                        f"looks like an identifier or free text ({distinct} distinct "
                        f"values in {len(non_null)} rows)"
                    ),
                }
            )
            continue
        plan.categorical.append(column)
    if not plan.columns:
        raise ValueError(
            "No usable feature column is left: every column of the dataset is the "
            "label, empty, or looks like an identifier."
        )
    return plan


def coerce_features(X: pd.DataFrame, plan: FeaturePlan) -> pd.DataFrame:
    """Give the columns of ``X`` the types the pipeline was trained on.

    The same function runs at training and at prediction time, so a column is
    never typed differently in the two places. A numeric column that holds a
    value that is not a number raises ``FeatureInputError`` (a silent NaN would
    hide a typo behind an imputed value).
    """
    out = pd.DataFrame(index=X.index)
    for column in plan.numeric:
        series = X[column] if column in X.columns else pd.Series(np.nan, index=X.index)
        if pd.api.types.is_bool_dtype(series):
            series = series.astype(float)
        elif not pd.api.types.is_numeric_dtype(series):
            converted = pd.to_numeric(series, errors="coerce")
            bad = series.notna() & converted.isna()
            if bool(bad.any()):
                raise FeatureInputError(
                    f"column '{column}' must be numeric, got "
                    f"{series[bad].iloc[0]!r}"
                )
            series = converted
        out[column] = series.astype(float)
    for column in plan.categorical:
        series = X[column] if column in X.columns else pd.Series(np.nan, index=X.index)
        # Plain strings with a real NaN for "missing": this is what the
        # imputer and the encoder expect, whatever string dtype pandas uses.
        values = series.astype(object)
        out[column] = values.where(series.notna(), np.nan).map(
            lambda v: v if (isinstance(v, float) and np.isnan(v)) else str(v)
        )
    return out[plan.columns]


def build_preprocessor(plan: FeaturePlan, scale: bool) -> ColumnTransformer:
    """The unfitted preprocessor of a plan. It is fitted inside the pipeline."""
    numeric_steps: List[Tuple[str, Any]] = [("impute", SimpleImputer(strategy="median"))]
    if scale:
        numeric_steps.append(("scale", StandardScaler()))
    transformers: List[Tuple[str, Any, List[str]]] = []
    if plan.numeric:
        transformers.append(("numeric", Pipeline(numeric_steps), list(plan.numeric)))
    if plan.categorical:
        transformers.append(
            (
                "categorical",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        (
                            "onehot",
                            OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                        ),
                    ]
                ),
                list(plan.categorical),
            )
        )
    return ColumnTransformer(transformers, sparse_threshold=0.0)


def describe_features(X: pd.DataFrame, plan: FeaturePlan) -> List[Dict[str, Any]]:
    """The schema a client needs to build a prediction request.

    ``X`` is the coerced training frame. For every column: its kind, what a
    sensible default is (median / most frequent value) and its range or its
    categories.
    """
    schema: List[Dict[str, Any]] = []
    for column in plan.numeric:
        series = X[column]
        non_null = series.dropna()
        schema.append(
            {
                "name": str(column),
                "kind": "numeric",
                "min": float(non_null.min()),
                "max": float(non_null.max()),
                "default": float(non_null.median()),
                "missing_rate": float(series.isna().mean()),
            }
        )
    for column in plan.categorical:
        series = X[column]
        counts = series.dropna().value_counts()
        categories = [str(v) for v in counts.index[:SCHEMA_CATEGORY_LIMIT]]
        schema.append(
            {
                "name": str(column),
                "kind": "categorical",
                "categories": categories,
                "categories_truncated": bool(len(counts) > SCHEMA_CATEGORY_LIMIT),
                "default": categories[0],
                "missing_rate": float(series.isna().mean()),
            }
        )
    return schema


def preprocessing_report(
    X_raw: pd.DataFrame,
    plan: FeaturePlan,
    scale: bool,
    rows_without_label: int,
    stratified: Optional[bool] = None,
    task_type_source: str = "inferred",
) -> Dict[str, Any]:
    """The JSON summary of what was done to the data, stored with the run."""
    used = X_raw[plan.columns]
    return {
        "numeric_columns": [str(c) for c in plan.numeric],
        "categorical_columns": [str(c) for c in plan.categorical],
        "dropped_columns": plan.dropped,
        "missing_cells_imputed": int(used.isna().sum().sum()),
        "rows_dropped_missing_label": int(rows_without_label),
        "scaled": bool(scale),
        "stratified_split": stratified,
        "task_type_source": task_type_source,
    }


# --- splitting and evaluation ------------------------------------------------


def split_data(
    X: pd.DataFrame,
    y: pd.Series,
    task_type: str,
    test_size: float,
    random_state: int,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, bool]:
    """A hold-out split, stratified on the label whenever that is possible.

    An unstratified split of an imbalanced label can leave a class out of the
    test rows, which makes every metric meaningless. Stratifying needs at least
    two rows per class and room for every class in both parts; when that does
    not hold the split is a plain one, and the report says so.
    """
    stratify = None
    if task_type == "classification":
        counts = y.value_counts()
        n_test = int(np.ceil(test_size * len(y)))
        n_train = len(y) - n_test
        n_classes = len(counts)
        if counts.min() >= 2 and n_test >= n_classes and n_train >= n_classes:
            stratify = y
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=stratify
    )
    return X_train, X_test, y_train, y_test, stratify is not None


def _json(value: Any) -> Any:
    """A plain Python value (numpy scalars and NaN do not survive a JSON column)."""
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, np.ndarray):
        return [_json(v) for v in value.tolist()]
    if isinstance(value, (list, tuple)):
        return [_json(v) for v in value]
    return value


def evaluate_holdout(
    task_type: str,
    y_train: np.ndarray,
    y_test: np.ndarray,
    predictions: np.ndarray,
    probabilities: Optional[np.ndarray] = None,
    class_labels: Optional[Sequence[Any]] = None,
) -> Dict[str, Any]:
    """Task-correct metrics on the rows the model never saw, with a baseline.

    ``accuracy`` alone is how a model that always answers "no" looks good on a
    95%-"no" dataset, so the baseline (the majority class, or the training
    mean) is reported next to every score, and the classification metrics
    include the ones that notice an ignored class (balanced accuracy, macro F1).
    """
    if task_type == "classification":
        labels = np.arange(len(class_labels)) if class_labels is not None else None
        majority = pd.Series(y_train).value_counts().idxmax()
        metrics: Dict[str, Any] = {
            "accuracy": _json(accuracy_score(y_test, predictions)),
            "balanced_accuracy": _json(balanced_accuracy_score(y_test, predictions)),
            "precision_macro": _json(
                precision_score(y_test, predictions, average="macro", zero_division=0)
            ),
            "recall_macro": _json(
                recall_score(y_test, predictions, average="macro", zero_division=0)
            ),
            "f1_macro": _json(f1_score(y_test, predictions, average="macro", zero_division=0)),
            "baseline_accuracy": _json(float(np.mean(y_test == majority))),
            "confusion_matrix": {
                "labels": [_json(c) for c in (class_labels if class_labels is not None else [])],
                "matrix": _json(confusion_matrix(y_test, predictions, labels=labels)),
            },
        }
        if probabilities is not None:
            try:
                if probabilities.shape[1] == 2:
                    metrics["roc_auc"] = _json(roc_auc_score(y_test, probabilities[:, 1]))
                elif len(np.unique(y_test)) == probabilities.shape[1]:
                    metrics["roc_auc"] = _json(
                        roc_auc_score(y_test, probabilities, multi_class="ovr", average="macro")
                    )
            except ValueError:
                # Only one class in the test rows: the AUC is not defined.
                pass
        return metrics

    mse = float(mean_squared_error(y_test, predictions))
    train_mean = float(np.mean(y_train))
    return {
        "mse": _json(mse),
        "rmse": _json(float(np.sqrt(mse))),
        "mae": _json(mean_absolute_error(y_test, predictions)),
        "r2": _json(r2_score(y_test, predictions)),
        "baseline_rmse": _json(float(np.sqrt(np.mean((y_test - train_mean) ** 2)))),
    }


def cross_validate_pipeline(
    pipeline: Pipeline,
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    task_type: str,
    folds: int,
    random_state: int,
) -> Dict[str, Any]:
    """A k-fold cross-validation of the final pipeline on the training rows.

    The test rows are not touched: the hold-out score stays the unbiased one,
    and the cross-validation says how much a score moves between samples of the
    same data. The preprocessor is part of the pipeline, so it is refitted in
    every fold. The folds adapt to the data (a class with three rows allows at
    most three stratified folds) and, when no valid fold count is left, the
    result says why it was skipped instead of failing the run.
    """
    if folds < 2:
        return {"folds": 0, "skipped": "cross-validation is disabled (cv_folds < 2)"}

    n_rows = len(y_train)
    effective = min(folds, n_rows // MIN_ROWS_PER_FOLD)
    if task_type == "classification":
        # A stratified fold needs every class in every part.
        effective = min(effective, int(pd.Series(y_train).value_counts().min()))
        scoring = {"accuracy": "accuracy", "f1_macro": "f1_macro"}
    else:
        scoring = {
            "r2": "r2",
            "rmse": "neg_root_mean_squared_error",
            "mae": "neg_mean_absolute_error",
        }
    if effective < 2:
        return {
            "folds": 0,
            "skipped": (
                f"too few rows for cross-validation ({n_rows} training rows"
                + (", the rarest class has too few of them" if task_type == "classification" else "")
                + ")"
            ),
        }
    if task_type == "classification":
        splitter: Any = StratifiedKFold(effective, shuffle=True, random_state=random_state)
    else:
        splitter = KFold(effective, shuffle=True, random_state=random_state)

    try:
        raw = cross_validate(
            pipeline, X_train, y_train, cv=splitter, scoring=scoring, error_score=np.nan
        )
    except Exception as exc:  # a failed cross-validation must not fail the run
        return {"folds": 0, "skipped": f"cross-validation failed: {type(exc).__name__}"}

    scores: Dict[str, Dict[str, Optional[float]]] = {}
    for name in scoring:
        values = np.asarray(raw[f"test_{name}"], dtype=float)
        if name in ("rmse", "mae"):
            values = -values  # scikit-learn negates the errors so that bigger is better
        values = values[np.isfinite(values)]
        if values.size == 0:
            continue
        scores[name] = {
            "mean": _json(float(values.mean())),
            "std": _json(float(values.std())),
        }
    if not scores:
        return {"folds": 0, "skipped": "every fold failed"}
    return {"folds": int(effective), "scores": scores}


def prepare_rows(
    plan: FeaturePlan, feature_schema: List[Dict[str, Any]], rows: List[Dict[str, Any]]
) -> Tuple[pd.DataFrame, List[str]]:
    """Turn the rows of a prediction request into the features of a model.

    Returns the coerced frame and the warnings for what does not match the
    training data: columns that were sent but are not features, features that
    were not sent (imputed, exactly as in training) and categories the model
    never saw. A value that is not a number raises ``FeatureInputError``.
    """
    warnings: List[str] = []
    frame = pd.DataFrame(rows)
    known = set(plan.columns)
    unknown = [c for c in frame.columns if c not in known]
    missing = [c for c in plan.columns if c not in frame.columns]
    if unknown:
        warnings.append(f"ignored unknown column(s): {sorted(map(str, unknown))}")
    if missing:
        warnings.append(
            f"column(s) {missing} were not sent: they are treated as missing "
            "and imputed the way they were in training"
        )
    coerced = coerce_features(frame, plan)

    for entry in feature_schema:
        if entry["kind"] != "categorical" or entry.get("categories_truncated"):
            continue
        name = entry["name"]
        if name not in frame.columns:
            continue
        seen = set(entry["categories"])
        unseen = sorted({v for v in coerced[name].dropna().unique() if v not in seen})
        if unseen:
            warnings.append(
                f"column '{name}' holds value(s) never seen in training: {unseen[:5]}"
            )
    return coerced, warnings


# --- the artifact ------------------------------------------------------------


class TabularModelBundle:
    """A fitted pipeline together with everything needed to use it on new rows.

    This is what ``write_artifact`` stores for a supervised tabular run. The
    class lives at module level so ``joblib`` can pickle and load it.
    """

    kind = "tabular"
    format_version = 1

    def __init__(
        self,
        *,
        pipeline: Pipeline,
        plan: FeaturePlan,
        model_name: str,
        task_type: str,
        label_column: str,
        feature_schema: List[Dict[str, Any]],
        label_encoder: Optional[LabelEncoder],
    ) -> None:
        self.pipeline = pipeline
        self.plan = plan
        self.model_name = model_name
        self.task_type = task_type
        self.label_column = label_column
        self.feature_schema = feature_schema
        self.label_encoder = label_encoder

    # -- what the client may ask about the model
    @property
    def classes(self) -> List[Any]:
        if self.label_encoder is None:
            return []
        return [_json(c) for c in self.label_encoder.classes_]

    def schema(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "model_name": self.model_name,
            "task_type": self.task_type,
            "label_column": self.label_column,
            "features": self.feature_schema,
            "dropped_columns": self.plan.dropped,
            "classes": self.classes,
        }

    # -- prediction
    def _frame(self, rows: List[Dict[str, Any]]) -> Tuple[pd.DataFrame, List[str]]:
        return prepare_rows(self.plan, self.feature_schema, rows)

    def infer(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Predict every row. Raises ``FeatureInputError`` for an unusable value."""
        frame, warnings = self._frame(rows)
        raw = self.pipeline.predict(frame)
        result: Dict[str, Any] = {"task_type": self.task_type, "warnings": warnings}
        if self.task_type == "classification":
            assert self.label_encoder is not None
            result["predictions"] = [
                _json(v) for v in self.label_encoder.inverse_transform(raw.astype(int))
            ]
            result["classes"] = self.classes
            if hasattr(self.pipeline, "predict_proba"):
                proba = self.pipeline.predict_proba(frame)
                result["probabilities"] = [
                    {str(c): _json(float(p)) for c, p in zip(self.classes, row)}
                    for row in proba
                ]
        else:
            result["predictions"] = [_json(float(v)) for v in raw]
        return result

    def predict(self, rows: pd.DataFrame) -> np.ndarray:
        """Predict a frame (the label of a classification, decoded)."""
        frame, _ = self._frame(rows.to_dict(orient="records"))
        raw = self.pipeline.predict(frame)
        if self.label_encoder is not None:
            return self.label_encoder.inverse_transform(raw.astype(int))
        return raw


class AutoencoderBundle:
    """A fitted autoencoder with its preprocessing and its anomaly threshold.

    The network is an encoder-bottleneck-decoder that was trained to reproduce
    its own (standardised) input; ``infer`` returns, for every row, how badly
    it was reproduced (the reconstruction error), whether that is unusual for
    the training data (above ``threshold``), and the bottleneck code of the row.
    """

    kind = "autoencoder"
    format_version = 1

    def __init__(
        self,
        *,
        preprocessor: ColumnTransformer,
        network: Any,
        bottleneck_layers: int,
        activation: str,
        plan: FeaturePlan,
        threshold: float,
        quantile: float,
        feature_schema: List[Dict[str, Any]],
        model_name: str = "Autoencoder",
    ) -> None:
        self.preprocessor = preprocessor
        self.network = network
        self.bottleneck_layers = bottleneck_layers
        self.activation = activation
        self.plan = plan
        self.threshold = threshold
        self.quantile = quantile
        self.feature_schema = feature_schema
        self.model_name = model_name
        self.task_type = "autoencoder"

    @staticmethod
    def _activate(name: str, values: np.ndarray) -> np.ndarray:
        if name == "relu":
            return np.maximum(values, 0.0)
        if name == "tanh":
            return np.tanh(values)
        if name == "logistic":
            return 1.0 / (1.0 + np.exp(-values))
        return values  # identity

    def encode(self, matrix: np.ndarray) -> np.ndarray:
        """The bottleneck code: the forward pass up to the narrowest layer."""
        activations = matrix
        for layer in range(self.bottleneck_layers):
            activations = self._activate(
                self.activation,
                activations @ self.network.coefs_[layer] + self.network.intercepts_[layer],
            )
        return activations

    def reconstruction_error(self, matrix: np.ndarray) -> np.ndarray:
        """The mean squared error of every row, in the standardised space."""
        return np.mean((matrix - self.network.predict(matrix)) ** 2, axis=1)

    def schema(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "model_name": self.model_name,
            "task_type": self.task_type,
            "label_column": None,
            "features": self.feature_schema,
            "dropped_columns": self.plan.dropped,
            "classes": [],
            "anomaly_threshold": _json(self.threshold),
        }

    def infer(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        frame, warnings = prepare_rows(self.plan, self.feature_schema, rows)
        matrix = self.preprocessor.transform(frame)
        errors = self.reconstruction_error(matrix)
        return {
            "task_type": self.task_type,
            "warnings": warnings,
            "reconstruction_error": [_json(float(e)) for e in errors],
            "is_anomaly": [bool(e > self.threshold) for e in errors],
            "threshold": _json(self.threshold),
            "latent": _json(self.encode(matrix)),
        }
