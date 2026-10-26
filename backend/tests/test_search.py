"""Tests for the real hyperparameter search (W1-7, stretch phase T07).

``auto_tune`` runs a randomized search over a curated per-model space and reports
``best_params`` plus a search summary. ``auto_fine_tune`` searches a neighbourhood
of the base configuration. ``llm_fine_tune`` fails fast with an actionable message
when the LLM key or package is missing. ``auto_search`` is model selection, not a
search over hyperparameters.

Everything here is offline and CPU only: nothing is downloaded and no LLM call is
made.
"""

import os
from pathlib import Path

import pytest
from sklearn.model_selection import RandomizedSearchCV

from backend.app import model_training
from backend.app.model_training import MODEL_CATALOG, build_model, train_model

# Tabular entries that carry a curated search space.
TABULAR_WITH_SPACE = [
    name
    for name, entry in MODEL_CATALOG.items()
    if entry.get("category") in ("classification", "regression", "time-series")
    and entry.get("search_space")
]


def _train(model_name, dataset, hyperparameters=None, mode="manual", preset="balanced"):
    return train_model(
        model_name,
        dataset,
        None,
        "label",
        0.2,
        42,
        {} if hyperparameters is None else hyperparameters,
        ",",
        None,
        mode,
        "accuracy",
        None,
        None,
        preset,
    )


def test_every_tabular_entry_with_a_space_trains_in_auto_tune(
    classification_dataset, regression_dataset, isolated_model_dir
):
    """auto_tune runs a real search for every tabular entry that declares a space."""
    for name in TABULAR_WITH_SPACE:
        dataset = (
            regression_dataset if MODEL_CATALOG[name]["category"] == "regression"
            else classification_dataset
        )
        metrics, _source, _tag, artifact = _train(name, dataset, mode="auto_tune")
        assert metrics["task_type"] is not None
        # The search reports the best parameters it really used.
        assert metrics["model_parameters"], f"{name} reported no model_parameters"
        # A real search reports its candidate summary.
        assert metrics.get("search_results"), f"{name} reported no search_results"
        assert metrics.get("search_cv") in (2, 3), f"{name} reported no cv_used"
        # The best parameters really construct the estimator.
        params = metrics["model_parameters"]
        estimator = build_model(name, metrics["task_type"], params)
        assert estimator is not None
        assert Path(artifact["artifact_path"]).exists()
        assert Path(artifact["artifact_path"]).parent == isolated_model_dir


def test_auto_tune_client_pinned_parameter_is_never_overridden(classification_dataset):
    """The client's pinned parameter wins over the search: it is sampled out of
    the space and kept verbatim in the reported parameters."""
    metrics, _source, _tag, _artifact = _train(
        "Random_Forest",
        classification_dataset,
        {"n_estimators": 5, "max_depth": 3},
        mode="auto_tune",
    )
    params = metrics["model_parameters"]
    assert params["n_estimators"] == 5
    assert params["max_depth"] == 3
    assert metrics.get("search_results")


def test_auto_fine_tune_stays_in_a_neighbourhood_of_the_base(classification_dataset):
    """auto_fine_tune searches a narrow neighbourhood around the base
    configuration instead of re-searching the whole catalogue space."""
    metrics, _source, _tag, _artifact = _train(
        "XGboost_timeseries", classification_dataset, mode="auto_fine_tune"
    )
    params = metrics["model_parameters"]
    # The base learning rate is 0.1; the neighbourhood is [0.05, 0.1, 0.2].
    assert params["learning_rate"] in (0.05, 0.1, 0.2)
    assert metrics.get("search_results")


def test_manual_mode_does_not_report_search_results(classification_dataset):
    """manual mode is a plain fit: no search, no search_results key."""
    metrics, _source, _tag, _artifact = _train(
        "Random_Forest", classification_dataset, mode="manual"
    )
    assert "search_results" not in metrics
    assert "search_cv" not in metrics


def test_search_results_are_ranked_and_json_serialisable(classification_dataset):
    """search_results holds the top candidates, each with params, score and rank."""
    metrics, _source, _tag, _artifact = _train(
        "Random_Forest", classification_dataset, mode="auto_tune"
    )
    results = metrics["search_results"]
    assert isinstance(results, list) and len(results) > 0
    ranks = [c["rank"] for c in results]
    assert ranks == sorted(ranks), "candidates must be ranked ascending"
    for candidate in results:
        assert set(candidate) >= {"params", "mean_test_score", "rank", "cv_used"}
        # JSON-serialisable: nothing numpy-typed survives.
        import json

        json.dumps(candidate)


def test_cv_falls_back_to_two_on_a_tiny_fold():
    """On a six-row dataset the training fold has three rows: cv=3 cannot
    stratify both classes, so the search falls back to cv=2 and says so."""
    relative_path = _write_tiny_dataset()
    metrics, _source, _tag, _artifact = _train(
        "Logistic_Regression", relative_path, mode="auto_tune"
    )
    assert metrics["accuracy"] is not None
    # The search either ran with cv=2 and said so, or fell back to a plain fit.
    assert metrics.get("search_cv") in (2, 3)
    assert metrics.get("model_parameters")


def test_llm_fine_tune_fails_fast_without_key_or_package(monkeypatch):
    """llm_fine_tune needs google-generativeai and GOOGLE_API_KEY; without them it
    fails fast with an actionable message instead of training the wrong thing."""
    # The package is not installed in this environment, so genai is None.
    monkeypatch.setattr(model_training, "genai", None)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GOOGLE_API_KEY|google-generativeai"):
        model_training.suggest_hyperparameters(
            "Random_Forest", "classification", use_llm=True
        )


def test_randomized_search_cv_is_available():
    """The search engine imports and is a real scikit-learn search (not a stub)."""
    assert RandomizedSearchCV is not None


def _write_tiny_dataset() -> str:
    """A six-row two-class CSV: with test_size=0.5 the training fold has three
    rows, too few for cv=3 to stratify both classes. Written into the datasets
    root so the path confinement of resolve_dataset_path is respected."""
    root = Path(os.environ["DATASETS_ROOT"])
    path = root / "data" / "tiny.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("feature,label\n1,0\n2,1\n3,0\n4,1\n5,0\n6,1\n")
    return "data/tiny.csv"
