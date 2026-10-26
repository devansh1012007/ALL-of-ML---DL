"""The preprocessing and evaluation contract of the tabular models.

A reported "accuracy" on a messy CSV used to be misleading, or missing: a text
column or a NaN crashed most estimators, the split was not stratified, nothing
said what a model that always predicts the majority class would score, and the
artifact did not know its own columns. These tests pin the replacement:

* a messy CSV trains, and the report says what was done to it;
* every score comes with its baseline and a cross-validation;
* the artifact is a bundle that can predict rows it has never seen;
* the test rows never influence the preprocessing.
"""

import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from backend.app.model_training import (
    MODEL_CATALOG,
    infer_task_type,
    score_candidate,
    train_model,
)
from backend.app.tabular import (
    FeatureInputError,
    TabularModelBundle,
    analyze_features,
    coerce_features,
    cross_validate_pipeline,
    split_data,
)


def _write_csv(relative_path: str, frame: pd.DataFrame) -> str:
    root = Path(os.environ["DATASETS_ROOT"])
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return relative_path


def _messy_frame(n_rows: int = 240, seed: int = 7) -> pd.DataFrame:
    """Numbers with holes, a text column, an identifier and a row without label."""
    rng = np.random.RandomState(seed)
    frame = pd.DataFrame(
        {
            "age": rng.randint(18, 70, n_rows).astype(float),
            "city": rng.choice(["north", "south", "east"], n_rows),
            "user_id": [f"user-{i}" for i in range(n_rows)],
            "score": rng.normal(size=n_rows),
        }
    )
    frame.loc[rng.choice(n_rows, 25, replace=False), "age"] = np.nan
    frame.loc[rng.choice(n_rows, 20, replace=False), "city"] = np.nan
    signal = frame["score"] + (frame["city"] == "north") * 1.2 + rng.normal(scale=0.4, size=n_rows)
    frame["label"] = np.where(signal > 0.4, "churn", "stay")
    frame.loc[3, "label"] = np.nan
    return frame


@pytest.fixture(scope="module")
def messy_dataset():
    return _write_csv("data/messy_tabular.csv", _messy_frame())


def _train(model_name, dataset, **kwargs):
    defaults = dict(
        label_column="label",
        test_size=0.2,
        random_state=42,
        hyperparameters={},
    )
    defaults.update(kwargs)
    return train_model(
        model_name,
        dataset,
        None,
        defaults.pop("label_column"),
        defaults.pop("test_size"),
        defaults.pop("random_state"),
        defaults.pop("hyperparameters"),
        **defaults,
    )


@pytest.mark.parametrize(
    "model_name",
    ["Random_Forest", "Logistic_Regression", "SVM", "KNN", "XGboost_timeseries"],
)
def test_a_messy_csv_trains_and_the_report_says_what_was_done(model_name, messy_dataset):
    metrics, _, _, artifact = _train(model_name, messy_dataset)

    report = metrics["preprocessing"]
    assert report["numeric_columns"] == ["age", "score"]
    assert report["categorical_columns"] == ["city"]
    # The identifier is dropped, with the reason, instead of being one-hot
    # encoded into one column per row.
    assert [d["column"] for d in report["dropped_columns"]] == ["user_id"]
    assert "identifier" in report["dropped_columns"][0]["reason"]
    assert report["rows_dropped_missing_label"] == 1
    assert report["missing_cells_imputed"] == 45
    assert report["stratified_split"] is True
    assert report["scaled"] is (model_name in ("Logistic_Regression", "SVM", "KNN"))
    assert metrics["train_size"] + metrics["test_size"] == 239
    assert Path(artifact["artifact_path"]).exists()


def test_every_classification_score_comes_with_its_baseline_and_a_cross_validation(
    messy_dataset,
):
    metrics, *_ = _train("Random_Forest", messy_dataset)

    assert metrics["task_type"] == "classification"
    for key in (
        "accuracy",
        "balanced_accuracy",
        "precision_macro",
        "recall_macro",
        "f1_macro",
        "baseline_accuracy",
        "roc_auc",
    ):
        assert isinstance(metrics[key], float), key
    # The model has to beat "always answer the most frequent class", or its
    # accuracy says nothing.
    assert metrics["accuracy"] > metrics["baseline_accuracy"]
    assert metrics["mse"] is None and metrics["r2"] is None

    matrix = metrics["confusion_matrix"]
    assert matrix["labels"] == ["churn", "stay"]
    assert np.asarray(matrix["matrix"]).sum() == metrics["test_size"]

    cv = metrics["cv"]
    assert cv["folds"] == 5
    assert set(cv["scores"]) == {"accuracy", "f1_macro"}
    assert cv["scores"]["accuracy"]["std"] >= 0.0
    assert metrics["cv_metric"] == "accuracy"
    assert metrics["cv_score_mean"] == cv["scores"]["accuracy"]["mean"]


def test_a_regression_reports_error_metrics_and_a_baseline(regression_dataset):
    metrics, *_ = _train("Random_Forest", regression_dataset)

    assert metrics["task_type"] == "regression"
    for key in ("mse", "rmse", "mae", "r2", "baseline_rmse"):
        assert isinstance(metrics[key], float), key
    assert metrics["rmse"] == pytest.approx(metrics["mse"] ** 0.5)
    assert metrics["rmse"] < metrics["baseline_rmse"]
    assert metrics["accuracy"] is None
    assert set(metrics["cv"]["scores"]) == {"r2", "rmse", "mae"}


def test_the_split_is_stratified_so_the_rare_class_reaches_the_test_rows():
    y = pd.Series([0] * 95 + [1] * 5)
    X = pd.DataFrame({"x": np.arange(100.0)})

    _, _, y_train, y_test, stratified, _warnings = split_data(X, y, "classification", 0.2, 1)

    assert stratified is True
    assert (y_test == 1).sum() == 1 and (y_train == 1).sum() == 4


def test_the_split_falls_back_when_a_class_is_too_small_to_stratify():
    y = pd.Series([0] * 30 + [1])
    X = pd.DataFrame({"x": np.arange(31.0)})

    *_, stratified, _warnings = split_data(X, y, "classification", 0.2, 1)

    assert stratified is False


def test_cross_validation_says_why_it_was_skipped():
    from sklearn.dummy import DummyClassifier

    X = pd.DataFrame({"x": np.arange(6.0)})
    y = np.array([0, 0, 0, 0, 0, 1])

    disabled = cross_validate_pipeline(DummyClassifier(), X, y, "classification", 0, 1)
    too_small = cross_validate_pipeline(DummyClassifier(), X, y, "classification", 5, 1)

    assert disabled["folds"] == 0 and "disabled" in disabled["skipped"]
    assert too_small["folds"] == 0 and "too few rows" in too_small["skipped"]


def test_cv_folds_zero_turns_the_cross_validation_off(messy_dataset):
    metrics, *_ = _train("Logistic_Regression", messy_dataset, cv_folds=0)

    assert metrics["cv"]["folds"] == 0
    assert "cv_score_mean" not in metrics


def test_the_artifact_is_a_bundle_that_predicts_rows_it_has_never_seen(messy_dataset):
    _, _, _, artifact = _train("Random_Forest", messy_dataset)

    bundle = joblib.load(Path(artifact["artifact_path"]) / "model.joblib")
    assert isinstance(bundle, TabularModelBundle)
    schema = bundle.schema()
    assert [f["name"] for f in schema["features"]] == ["age", "score", "city"]
    assert schema["classes"] == ["churn", "stay"]
    city = next(f for f in schema["features"] if f["name"] == "city")
    assert set(city["categories"]) == {"north", "south", "east"}

    result = bundle.infer(
        [
            {"age": 40, "city": "north", "score": 2.5},
            {"age": None, "city": "east", "score": -2.5},
        ]
    )

    # The labels come back as the labels of the CSV, not as 0 and 1.
    assert set(result["predictions"]) <= {"churn", "stay"}
    assert result["predictions"] == ["churn", "stay"]
    assert len(result["probabilities"]) == 2
    assert sum(result["probabilities"][0].values()) == pytest.approx(1.0)
    assert result["warnings"] == []


def test_the_bundle_warns_about_what_the_row_does_not_match(messy_dataset):
    _, _, _, artifact = _train("Logistic_Regression", messy_dataset)
    bundle = joblib.load(Path(artifact["artifact_path"]) / "model.joblib")

    result = bundle.infer([{"age": 30, "city": "atlantis", "extra": 1}])

    text = " ".join(result["warnings"])
    assert "unknown column" in text and "extra" in text
    assert "not sent" in text and "score" in text
    assert "never seen in training" in text and "atlantis" in text
    assert len(result["predictions"]) == 1


def test_a_value_that_is_not_a_number_is_an_error_not_a_silent_nan(messy_dataset):
    _, _, _, artifact = _train("Logistic_Regression", messy_dataset)
    bundle = joblib.load(Path(artifact["artifact_path"]) / "model.joblib")

    with pytest.raises(FeatureInputError, match="column 'age' must be numeric"):
        bundle.infer([{"age": "forty", "city": "north", "score": 1.0}])


def test_a_numeric_label_keeps_its_original_values(classification_dataset):
    _, _, _, artifact = _train("Random_Forest", classification_dataset)
    bundle = joblib.load(Path(artifact["artifact_path"]) / "model.joblib")

    result = bundle.infer([{f"feature_{i}": 1.5 for i in range(4)}])

    assert result["predictions"] == [1]
    assert bundle.classes == [0, 1]


def test_a_model_that_cannot_fit_the_label_says_so_in_plain_words(regression_dataset):
    with pytest.raises(ValueError, match="Logistic_Regression is a classification model"):
        _train("Logistic_Regression", regression_dataset, task_type="regression")


def test_task_type_overrides_the_guess(classification_dataset):
    # The label has two distinct values, so it is guessed as classification;
    # asking for a regression on it is the caller's call and is honoured.
    metrics, *_ = _train("Random_Forest", classification_dataset, task_type="regression")

    assert metrics["task_type"] == "regression"
    assert metrics["preprocessing"]["task_type_source"] == "request"


def test_an_unknown_task_type_is_refused(classification_dataset):
    with pytest.raises(ValueError, match="task_type must be one of"):
        _train("Random_Forest", classification_dataset, task_type="forecast")


def test_a_label_with_one_class_is_refused():
    dataset = _write_csv(
        "data/one_class.csv",
        pd.DataFrame({"x": np.arange(20.0), "label": ["a"] * 20}),
    )
    with pytest.raises(ValueError, match="single class"):
        _train("Random_Forest", dataset)


def test_a_dataset_without_usable_features_is_refused():
    frame = pd.DataFrame({"empty": [np.nan] * 12, "label": [0, 1] * 6})
    with pytest.raises(ValueError, match="No usable feature column"):
        analyze_features(frame.drop(columns=["label"]))


def test_auto_tune_searches_the_whole_pipeline_on_a_messy_csv(messy_dataset):
    metrics, *_ = _train("Random_Forest", messy_dataset, mode="auto_tune")

    assert metrics["search_results"]
    for candidate in metrics["search_results"]:
        # The pipeline prefix is an implementation detail: the parameters are
        # reported under the names of the estimator.
        assert all(not key.startswith("model__") for key in candidate["params"])
    assert metrics["preprocessing"]["categorical_columns"] == ["city"]


def test_auto_search_ranks_the_candidates_on_the_cross_validated_score(messy_dataset):
    metrics, *_ = _train(
        "Random_Forest",
        messy_dataset,
        mode="auto_search",
        model_candidates=["Random_Forest", "Logistic_Regression"],
    )

    assert metrics["best_candidate"] in ("Random_Forest", "Logistic_Regression")


def test_score_candidate_prefers_the_cross_validated_score():
    metrics = {"accuracy": 0.99, "cv": {"scores": {"accuracy": {"mean": 0.70, "std": 0.1}}}}

    assert score_candidate(metrics, "accuracy") == pytest.approx(0.70)
    # Without a cross-validation the hold-out score is used, as before.
    assert score_candidate({"accuracy": 0.9}, "accuracy") == pytest.approx(0.9)
    # Error metrics are negated: lower is better.
    assert score_candidate({"rmse": 2.0}, "rmse") == -2.0


def test_the_task_type_guess():
    assert infer_task_type(pd.Series(["a", "b", "a"])) == "classification"
    assert infer_task_type(pd.Series([True, False, True])) == "classification"
    assert infer_task_type(pd.Series([0, 1, 2, 1, 0])) == "classification"
    assert infer_task_type(pd.Series(np.arange(100.0))) == "regression"
    # Few distinct values, but measurements: not classes.
    assert infer_task_type(pd.Series([0.5, 1.5, 2.5, 1.5, 0.5])) == "regression"
    # Floats that hold whole numbers (a class column that had a NaN) are classes.
    assert infer_task_type(pd.Series([0.0, 1.0, 1.0, 0.0])) == "classification"


def test_coercion_types_the_columns_the_way_training_did():
    plan = analyze_features(
        pd.DataFrame({"n": [1.0, 2.0, 3.0, 4.0], "c": ["a", "b", "a", "b"], "flag": [True, False, True, True]})
    )

    frame = coerce_features(
        pd.DataFrame({"n": ["1", "2"], "c": ["x", None], "flag": [True, False]}), plan
    )

    assert frame["n"].tolist() == [1.0, 2.0]
    assert frame["flag"].tolist() == [1.0, 0.0]
    assert frame["c"].iloc[0] == "x" and pd.isna(frame["c"].iloc[1])


def test_the_preprocessing_is_fitted_on_the_training_rows_only(messy_dataset):
    """The imputer of the artifact holds the median of the *training* rows.

    If the test rows had been used, the statistic would be the median of all
    the rows: that is the leakage the pipeline exists to prevent. The split is
    rebuilt here with the same arguments, so the expected median is exact.
    """
    from sklearn.preprocessing import LabelEncoder

    frame = _messy_frame()
    frame = frame[frame["label"].notna()]
    features = frame.drop(columns=["label"])
    plan = analyze_features(features)
    encoded = pd.Series(LabelEncoder().fit_transform(frame["label"]), index=frame.index)
    X_train, *_ = split_data(coerce_features(features, plan), encoded, "classification", 0.2, 42)
    median_of_the_training_rows = float(X_train["age"].median())
    median_of_every_row = float(frame["age"].median())
    # The test is only meaningful if the two differ for this dataset.
    assert median_of_the_training_rows != median_of_every_row

    _, _, _, artifact = _train("Logistic_Regression", messy_dataset, cv_folds=0)
    bundle = joblib.load(Path(artifact["artifact_path"]) / "model.joblib")
    numeric = bundle.pipeline.named_steps["prep"].named_transformers_["numeric"]

    assert numeric.named_steps["impute"].statistics_[0] == pytest.approx(median_of_the_training_rows)


def test_the_neighbourhood_search_never_leaves_the_range_of_a_fraction():
    from backend.app.model_training import _neighborhood_space

    space = _neighborhood_space({"subsample": 0.8, "colsample_bytree": 1.0, "learning_rate": 0.1})

    assert max(space["subsample"]) <= 1.0 and 0.8 in space["subsample"]
    assert max(space["colsample_bytree"]) <= 1.0
    # An unbounded float is still explored on both sides.
    assert space["learning_rate"] == [0.05, 0.1, 0.2]
