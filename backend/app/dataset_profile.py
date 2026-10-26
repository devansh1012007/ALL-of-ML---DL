"""Look at the data before training (plan C6).

Why this module exists
----------------------
A user who uploads a CSV currently trains blind: nothing shows what the
columns hold, whether the label is balanced, whether rows are duplicated or
time-ordered, and whether one feature alone predicts the label (the leaking
column that makes every reported accuracy a lie). Looking at the data first
is what makes a notebook feel safe; this module gives the product that step.

``compute_profile`` answers, in one pass over the file:

* per column: type, missing fraction, distinct count, range and mean (or the
  top categories), and whether it looks like an identifier;
* for the dataset: the label distribution and imbalance ratio, the duplicate
  fraction, the constant columns, the strongly correlated pairs, a hint that
  the rows are time-ordered, and the **leakage suspects** - a single feature
  that alone predicts the label with a score above 0.98, measured with a
  one-feature decision stump on a sample. A single leaking column is the most
  common reason a very high accuracy is wrong, and it is cheap to detect.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# The sample sizes: the profile of a big file must stay cheap.
MAX_PROFILE_ROWS = 20000
LEAKAGE_SAMPLE_ROWS = 5000
LEAKAGE_SCORE_THRESHOLD = 0.98
CORRELATION_THRESHOLD = 0.9
TOP_CATEGORIES = 5


def file_sha256(path: Path) -> str:
    """The content hash of a dataset file (the caching key of the profile)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _column_profile(series: pd.Series) -> Dict[str, Any]:
    non_null = series.dropna()
    missing_fraction = float(series.isna().mean()) if len(series) else 0.0
    distinct = int(non_null.nunique())
    profile: Dict[str, Any] = {
        "name": str(series.name),
        "missing_fraction": round(missing_fraction, 4),
        "distinct_count": distinct,
    }
    if len(non_null) == 0:
        profile["type"] = "empty"
        return profile
    if pd.api.types.is_bool_dtype(series) or pd.api.types.is_numeric_dtype(series):
        values = pd.to_numeric(non_null, errors="coerce").dropna()
        profile["type"] = "numeric"
        if len(values):
            profile["min"] = float(values.min())
            profile["max"] = float(values.max())
            profile["mean"] = float(values.mean())
        # An identifier look: integers that are (almost) all distinct and
        # grow with the row - the column that memorises the row.
        if distinct == len(non_null) and len(non_null) > 10 and values.is_monotonic_increasing:
            profile["identifier_like"] = True
    else:
        profile["type"] = "categorical"
        counts = non_null.value_counts().head(TOP_CATEGORIES)
        profile["top_categories"] = [
            {"value": str(value), "count": int(count)} for value, count in counts.items()
        ]
        if distinct == len(non_null) and len(non_null) > 10:
            profile["identifier_like"] = True
    return profile


def _leakage_score(feature: pd.Series, label: pd.Series) -> Optional[float]:
    """The one-feature decision stump score of plan C6.

    For a numeric feature the stump is the best split at the median; for a
    categorical feature the stump is "predict the majority label of each
    value". A score above 0.98 on a sample means the feature alone predicts
    the label: the model will look perfect and be worthless.
    """
    frame = pd.DataFrame({"feature": feature, "label": label}).dropna()
    if len(frame) < 20:
        return None
    if frame["label"].nunique() < 2:
        return None
    y = frame["label"]
    if pd.api.types.is_numeric_dtype(frame["feature"]):
        values = frame["feature"]
        # A coarse search over the quantiles: enough for a detector, cheap
        # for any column length.
        best = 0.0
        for q in (0.25, 0.5, 0.75):
            split = values.quantile(q)
            left_mask = values <= split
            for mask in (left_mask, ~left_mask):
                if mask.sum() == 0:
                    continue
                majority = y[mask].value_counts().idxmax()
                score = float((y[mask] == majority).mean()) * float(mask.mean())
                best = max(best, score)
            # The stump scores the whole sample: both sides together.
            left_majority = y[left_mask].value_counts().idxmax() if left_mask.any() else None
            right_majority = y[~left_mask].value_counts().idxmax() if (~left_mask).any() else None
            if left_majority is not None and right_majority is not None:
                correct = ((y == left_majority) & left_mask) | ((y == right_majority) & ~left_mask)
                best = max(best, float(correct.mean()))
        return best
    # A categorical feature: the majority label of every value.
    correct = 0
    for _, group in frame.groupby("feature")["label"]:
        correct += int((group == group.value_counts().idxmax()).sum())
    return correct / len(frame)


def compute_profile(path: Path, label_column: Optional[str] = None) -> Dict[str, Any]:
    """The profile of a tabular CSV: the columns, the label, the warnings."""
    frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError("The dataset contains no rows.")

    if len(frame) > MAX_PROFILE_ROWS:
        frame = frame.sample(MAX_PROFILE_ROWS, random_state=0)

    columns = [_column_profile(frame[name]) for name in frame.columns]

    result: Dict[str, Any] = {
        "rows": int(len(frame)),
        "columns_count": int(frame.shape[1]),
        "columns": columns,
        "duplicate_row_fraction": round(
            float(1.0 - frame.duplicated().mean() if len(frame) else 0.0), 4
        ),
        "constant_columns": [
            str(name) for name in frame.columns if frame[name].nunique(dropna=True) <= 1
        ],
    }

    label = label_column if label_column in frame.columns else None
    if label is not None:
        counts = frame[label].value_counts()
        result["label"] = {
            "column": str(label),
            "classes": int(len(counts)),
            "distribution": [
                {"value": str(value), "count": int(count)} for value, count in counts.items()
            ],
            "imbalance_ratio": (
                round(float(counts.iloc[0] / counts.iloc[-1]), 3) if len(counts) > 1 else 1.0
            ),
            "missing_fraction": round(float(frame[label].isna().mean()), 4),
        }

        # The leakage suspects (plan C6): a single feature that alone
        # predicts the label. Sampled, one stump per column, capped.
        suspects = []
        sample = frame.sample(min(len(frame), LEAKAGE_SAMPLE_ROWS), random_state=0)
        for name in frame.columns:
            if name == label:
                continue
            score = _leakage_score(sample[name], sample[label])
            if score is not None and score >= LEAKAGE_SCORE_THRESHOLD:
                suspects.append({"column": str(name), "score": round(score, 4)})
        suspects.sort(key=lambda entry: entry["score"], reverse=True)
        result["leakage_suspects"] = suspects[:10]

    # The strongly correlated numeric pairs: a pair at 0.9+ is either a leak
    # or a redundancy, and either way the user should know.
    numeric = frame.select_dtypes(include=[np.number])
    correlated = []
    if numeric.shape[1] >= 2 and numeric.shape[1] <= 60:
        try:
            matrix = numeric.corr(method="spearman").abs()
            names = list(matrix.columns)
            for i in range(len(names)):
                for j in range(i + 1, len(names)):
                    value = matrix.iloc[i, j]
                    if pd.notna(value) and value >= CORRELATION_THRESHOLD:
                        correlated.append(
                            {
                                "columns": [str(names[i]), str(names[j])],
                                "correlation": round(float(value), 3),
                            }
                        )
        except Exception:  # a non-finite correlation must not fail the profile
            pass
    result["correlated_pairs"] = correlated[:20]

    # The time-order hint: when the first numeric column grows monotonically
    # with the row index, the rows are (very likely) a time series, and a
    # shuffled split would leak the future into the training rows.
    ordered_hint = False
    if len(frame) >= 30:
        for name in frame.columns[: min(6, len(frame.columns))]:
            series = frame[name]
            if pd.api.types.is_numeric_dtype(series):
                diff = series.diff().dropna()
                if len(diff) >= 10 and (diff > 0).mean() > 0.98:
                    ordered_hint = True
                    result["time_ordered_column"] = str(name)
                    break
    result["rows_look_time_ordered"] = ordered_hint

    return result
