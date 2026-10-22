"""Regression tests for the model catalog.

They encode the invariants that the catalog bugs violated:

* every catalog model must reach the trainer its category selects - the routing
  is asserted against the *intended* category of every entry, so a change of a
  category in the catalog (or a misrouting in ``train_model``) fails the suite
  instead of silently training the model with the wrong trainer;
* every catalog model that routes through ``build_model()`` must be
  constructible from its own catalog params, for the classification *and* the
  regression task type (the catalog used to carry trainer-level keys such as
  ``test_size`` and estimator-invalid keys such as ``probability``);
* the tabular flow must train in every non-LLM mode and the modes must actually
  change the parameters they apply.

Everything here is offline and CPU only: no model, dataset or checkpoint is
downloaded.
"""

import os
from pathlib import Path

import pytest
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.svm import SVC, SVR

from backend.app import model_training
from backend.app.model_training import MODEL_CATALOG, build_model, train_model

# The repository's artifact directory. ``write_artifact()`` reads the ``MODEL_DIR``
# module global when it is called and the conftest fixture redirects it into a
# temporary directory, so the value captured here is the one the production code
# would use without the fixture.
REPO_MODEL_DIR = model_training.MODEL_DIR

# The intended category of every catalog entry. This table is the expectation the
# suite checks the production catalog against: it is deliberately *not* derived
# from ``MODEL_CATALOG``, otherwise a change of a category in the catalog would
# silently change the expectation and the routing bug would slip through again.
EXPECTED_CATEGORY_BY_MODEL = {
    "K-Mean": "clustering",
    "HMM_timeseries": "clustering",
    "GMM": "clustering",
    "Hierarchical_Clustering": "clustering",
    "PCA": "clustering",
    "t-SNE": "clustering",
    "UMAP": "clustering",
    "DBSCAN": "clustering",
    "HDBSCAN": "clustering",
    "Random_Forest": "classification",
    "Logistic_Regression": "classification",
    "MLR": "regression",
    "KNN": "classification",
    "SVM": "classification",
    "XGboost_timeseries": "time-series",
    "lightGBM_timeseries": "time-series",
    "CATboost_timeseries": "time-series",
    "PPO": "reinforcement-learning",
    "DQN": "reinforcement-learning",
    "Q-Learning": "reinforcement-learning",
    "Autoencoder": "autoencoder",
    "BERT2BERT": "nlp",
    "self-attenetion_transformer": "nlp",
    "seq2seq": "nlp",
    "UL2": "nlp",
    "GNN": "graph",
    "BERT": "nlp",
    "DistilBERT": "nlp",
    "GPT": "nlp",
    "LLaMA": "nlp",
    "LSTM": "timeseries",
    "MiniLM": "nlp",
    "ResNet": "vision",
    "ResNet50": "vision",
    "RNN": "timeseries",
    "SSM_timeseries": "timeseries",
    "TCN_timeseries": "timeseries",
    "ViT": "vision",
}

# The trainer each category has to select. "time-series" is the category of the
# boosting models: they train as tabular models through build_model(), while
# "timeseries" (LSTM/RNN/SSM/TCN) selects the torch trainer.
CATEGORY_TO_TRAINER = {
    "classification": "build_model",
    "regression": "build_model",
    "time-series": "build_model",
    "clustering": "_train_clustering",
    "timeseries": "_train_torch_regression_or_classification",
    "graph": "_train_torch_regression_or_classification",
    "autoencoder": "_train_torch_regression_or_classification",
    "reinforcement-learning": "_train_rl_model",
    "nlp": "_train_transformer_text_classifier",
    "vision": "_train_resnet_image_model",
}

# The trainers that are monkeypatched with a recorder, so the test can see which
# one ``train_model`` dispatched to.
RECORDED_TRAINERS = (
    "build_model",
    "_train_clustering",
    "_train_rl_model",
    "_train_transformer_text_classifier",
    "_train_torch_regression_or_classification",
    "_train_resnet_image_model",
)

# Models that only need scikit-learn (or the boosting libraries) and therefore
# have to train end to end on the synthetic dataset.
OFFLINE_TRAINABLE_MODELS = frozenset(
    {
        "Random_Forest",
        "Logistic_Regression",
        "MLR",
        "KNN",
        "SVM",
        "XGboost_timeseries",
        "lightGBM_timeseries",
        "CATboost_timeseries",
        "K-Mean",
        "GMM",
        "Hierarchical_Clustering",
        "PCA",
        "t-SNE",
        "DBSCAN",
    }
)

# Raised by the trainers when a model name is unknown to them.
UNSUPPORTED_MODEL_MARKERS = (
    "Unsupported model",
    "Unsupported clustering model",
    "Unsupported RL model",
)

# A model that needs an optional dependency that is not installed may fail, but
# only with that dependency error - never with a data error.
MISSING_DEPENDENCY_MARKERS = ("is not installed", "is required")

# The catalog entries that route through build_model().
TABULAR_MODELS = tuple(
    sorted(
        name
        for name, category in EXPECTED_CATEGORY_BY_MODEL.items()
        if category in ("classification", "regression", "time-series")
    )
)

# The estimator every catalog entry has to build, per task type.
EXPECTED_ESTIMATOR_BY_MODEL = {
    "Random_Forest": {
        "classification": RandomForestClassifier,
        "regression": RandomForestRegressor,
    },
    "Logistic_Regression": {
        "classification": LogisticRegression,
        "regression": LogisticRegression,
    },
    "MLR": {
        "classification": LinearRegression,
        "regression": LinearRegression,
    },
    "KNN": {
        "classification": KNeighborsClassifier,
        "regression": KNeighborsRegressor,
    },
    "SVM": {
        "classification": SVC,
        "regression": SVR,
    },
}


def _boosting_estimator(model_name: str, task_type: str):
    """The booster class of a boosting entry, or None when it is not installed."""
    if model_name == "XGboost_timeseries":
        library = model_training.xgb
        prefix = "XGB"
    elif model_name == "lightGBM_timeseries":
        library = model_training.lgb
        prefix = "LGBM"
    elif model_name == "CATboost_timeseries":
        library = model_training.cb
        prefix = "CatBoost"
    else:
        raise AssertionError(f"{model_name} is not a boosting model")
    if library is None:
        return None
    return getattr(library, f"{prefix}{'Classifier' if task_type == 'classification' else 'Regressor'}")


def _expected_estimator(model_name: str, task_type: str):
    if model_name in EXPECTED_ESTIMATOR_BY_MODEL:
        return EXPECTED_ESTIMATOR_BY_MODEL[model_name][task_type]
    return _boosting_estimator(model_name, task_type)


@pytest.fixture
def recorded_trainers(monkeypatch):
    """Record which trainer ``train_model`` dispatches to."""
    calls = []
    for name in RECORDED_TRAINERS:
        original = getattr(model_training, name)

        def recorder(*args, _name=name, _original=original, **kwargs):
            calls.append(_name)
            return _original(*args, **kwargs)

        monkeypatch.setattr(model_training, name, recorder)
    return calls


def _image_folder():
    """A folder with class subdirectories, as the vision models expect.

    The folder lives in the datasets root and is referred to by its path
    relative to it: a dataset is always such a path.
    """
    relative_path = "data/images"
    folder = Path(os.environ["DATASETS_ROOT"]) / relative_path
    for class_name in ("cat", "dog"):
        (folder / class_name).mkdir(parents=True, exist_ok=True)
    return relative_path


def _train(
    model_name,
    dataset,
    hyperparameters=None,
    mode="manual",
    env_id="CartPole-v1",
    preset="balanced",
    model_candidates=None,
):
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
        env_id,
        model_candidates,
        preset,
    )


def test_every_catalog_model_has_an_expected_routing():
    """The expectation table has to cover the catalog exactly."""
    assert sorted(MODEL_CATALOG) == sorted(EXPECTED_CATEGORY_BY_MODEL)
    assert set(EXPECTED_CATEGORY_BY_MODEL.values()) <= set(CATEGORY_TO_TRAINER)


@pytest.mark.parametrize("model_name", sorted(MODEL_CATALOG))
def test_catalog_model_is_routed_to_the_expected_trainer(
    model_name,
    recorded_trainers,
    classification_dataset,
    regression_dataset,
    tmp_path,
    monkeypatch,
):
    """Every catalog model must reach the trainer its category selects.

    The expected trainer is derived from the *intended* category of the entry, so
    neither a changed category in the catalog nor a misrouting in ``train_model``
    can slip through: the category of the catalog entry is compared with the
    expectation and the trainer that was actually used is compared with the
    trainer that category selects.
    """
    expected_category = EXPECTED_CATEGORY_BY_MODEL[model_name]
    expected_trainer = CATEGORY_TO_TRAINER[expected_category]

    assert MODEL_CATALOG[model_name].get("category") == expected_category, (
        f"{model_name} has the category {MODEL_CATALOG[model_name].get('category')!r}, "
        f"but {expected_category!r} is expected"
    )

    if expected_category == "nlp":
        pytest.skip("the NLP trainer downloads pretrained checkpoints")

    # Some trainers (catboost) write scratch files into the working directory.
    monkeypatch.chdir(tmp_path)

    if expected_category == "vision":
        dataset = _image_folder()
    elif expected_category == "regression":
        # MLR is a regressor: it needs a continuous label, a classification label
        # would be scored with a classification metric.
        dataset = regression_dataset
    else:
        dataset = classification_dataset

    metrics = None
    error = None
    artifact = None
    try:
        metrics, _source, _tag, artifact = _train(model_name, dataset)
    except Exception as exc:  # noqa: BLE001 - the error is inspected below
        error = exc

    assert recorded_trainers == [expected_trainer], (
        f"{model_name} (category {expected_category}) was routed to {recorded_trainers}, "
        f"but {expected_trainer} is expected"
    )
    if error is not None:
        assert not any(marker in str(error) for marker in UNSUPPORTED_MODEL_MARKERS), (
            f"{model_name} is routed to a trainer that does not support it: {error}"
        )
        if model_name in OFFLINE_TRAINABLE_MODELS:
            raise AssertionError(f"{model_name} failed to train: {error!r}")
        assert any(marker in str(error) for marker in MISSING_DEPENDENCY_MARKERS), (
            f"{model_name} failed with {error!r}, which is neither a successful "
            "training nor a missing-optional-dependency error"
        )
        return

    if model_name in OFFLINE_TRAINABLE_MODELS:
        if expected_category == "clustering":
            assert metrics["sample_count"] == 60
        elif expected_category == "regression":
            # A regressor must not be scored with a classification metric.
            assert metrics["task_type"] == "regression"
            assert metrics["r2"] is not None
            assert metrics["accuracy"] is None
        else:
            assert metrics["task_type"] == "classification"
            assert metrics["accuracy"] is not None
        assert Path(artifact).exists()


@pytest.mark.parametrize("task_type", ["classification", "regression"])
@pytest.mark.parametrize("model_name", TABULAR_MODELS)
def test_catalog_params_construct_estimator(model_name, task_type):
    """A catalog entry that routes through build_model() must be constructible.

    Both task types are exercised: the regression branch of ``build_model()`` used
    to be dead code and hid real bugs (SVR rejected "probability", the regressors
    rejected "test_size").
    """
    params = dict(MODEL_CATALOG[model_name].get("params", {}))
    estimator = build_model(model_name, task_type, params)
    assert estimator is not None

    expected_class = _expected_estimator(model_name, task_type)
    if expected_class is None:
        pytest.skip("the boosting library is not installed")
    assert isinstance(estimator, expected_class), (
        f"{model_name} ({task_type}) built {type(estimator).__name__}, "
        f"but {expected_class.__name__} is expected"
    )


@pytest.mark.parametrize("task_type", ["classification", "regression"])
@pytest.mark.parametrize("model_name", TABULAR_MODELS)
def test_regression_branch_uses_the_catalog_params(model_name, task_type):
    """The estimator has to be built from the params of its catalog entry."""
    params = dict(MODEL_CATALOG[model_name].get("params", {}))
    estimator = build_model(model_name, task_type, params)
    expected_class = _expected_estimator(model_name, task_type)
    if expected_class is None:
        pytest.skip("the boosting library is not installed")
    estimator_params = estimator.get_params() if hasattr(estimator, "get_params") else {}
    for param_name, param_value in params.items():
        assert estimator_params.get(param_name, getattr(estimator, param_name, None)) == param_value, (
            f"{model_name} ({task_type}) did not receive the catalog parameter "
            f"{param_name}={param_value!r}"
        )


def test_unknown_parameter_name_still_raises_type_error():
    """A typo must not be swallowed: a blanket signature filter is forbidden."""
    with pytest.raises(TypeError):
        build_model("Logistic_Regression", "classification", {"not_a_real_parameter": 1})


def test_unknown_client_hyperparameter_is_rejected(classification_dataset):
    """A typo in the client hyperparameters must reach the constructor."""
    with pytest.raises(TypeError):
        _train("Logistic_Regression", classification_dataset, {"not_a_real_parameter": 1})


def test_train_size_inside_the_params_does_not_raise():
    """``test_size`` belongs to the training loop, not to the estimator."""
    estimator = build_model("Logistic_Regression", "classification", {"C": 1.0, "test_size": 0.25})
    assert estimator is not None
    assert estimator.C == 1.0
    assert not hasattr(estimator, "test_size")


def test_client_supplied_test_size_does_not_break_a_clustering_model(classification_dataset):
    """A client may send ``test_size``; the clustering path has to survive it."""
    metrics, _source, _tag, artifact = _train(
        "K-Mean", classification_dataset, {"test_size": 0.3}
    )
    assert metrics["sample_count"] == 60
    assert Path(artifact).exists()


def test_training_writes_the_artifact_into_the_temporary_model_dir(
    classification_dataset, isolated_model_dir
):
    """The suite must not write artifacts into the repository's models/ directory."""
    _metrics, _source, _tag, artifact = _train("Logistic_Regression", classification_dataset)
    artifact_path = Path(artifact)
    assert artifact_path.exists()
    assert artifact_path.parent == isolated_model_dir
    assert artifact_path.parent != REPO_MODEL_DIR


@pytest.mark.parametrize("mode", ["manual", "auto_tune", "auto_fine_tune"])
def test_train_model_tabular_modes(mode, classification_dataset, isolated_model_dir):
    """A tabular model must train in every non-LLM mode."""
    metrics, source, tag, artifact = _train(
        "Logistic_Regression", classification_dataset, {"C": 2.0}, mode=mode
    )
    assert source == "local"
    assert tag == str(classification_dataset)
    assert metrics.get("accuracy") is not None
    # The hyperparameter of the request has to be applied in every mode.
    assert metrics["model_parameters"]["C"] == 2.0
    assert Path(artifact).exists()
    assert Path(artifact).parent == isolated_model_dir


def test_auto_fine_tune_changes_the_applied_parameters(classification_dataset):
    """The modes have to differ: auto_fine_tune lowers the learning rate."""
    manual = _train(
        "XGboost_timeseries", classification_dataset, {"n_estimators": 5}, mode="manual"
    )[0]
    tuned = _train(
        "XGboost_timeseries", classification_dataset, {"n_estimators": 5}, mode="auto_tune"
    )[0]
    fine_tuned = _train(
        "XGboost_timeseries", classification_dataset, {"n_estimators": 5}, mode="auto_fine_tune"
    )[0]

    for metrics in (manual, tuned, fine_tuned):
        assert metrics["model_parameters"]["n_estimators"] == 5
    assert tuned["model_parameters"]["learning_rate"] == manual["model_parameters"]["learning_rate"]
    assert (
        fine_tuned["model_parameters"]["learning_rate"]
        < manual["model_parameters"]["learning_rate"]
    )


# --- training presets --------------------------------------------------------
#
# A preset is a set of adjustments (``TRAINING_PRESETS``) that scales the
# parameters of a run. The contract the frontend renders is the *effective* set
# of parameters that ``train_model`` reports in ``metrics["model_parameters"]``:
#
#     effective = {**preset(catalog + mode_suggestions), **preset(client_values)}
#
# The preset is applied exactly once - in ``auto_search`` it is applied by the
# leaf call of the recursion, not by the caller as well - and the client's own
# values still win over the scaled catalog defaults.

# The catalog default of Random_Forest / XGboost_timeseries.
CATALOG_N_ESTIMATORS = 100
# The conservative preset scales n_estimators by 0.7 (with a floor of 10).
CONSERVATIVE_N_ESTIMATORS = 70
# The aggressive preset scales n_estimators by 1.5.
AGGRESSIVE_N_ESTIMATORS = 150
# The catalog learning rate of XGboost_timeseries.
CATALOG_LEARNING_RATE = 0.1


@pytest.fixture
def built_models(monkeypatch):
    """Record every estimator that ``build_model`` constructed successfully.

    Only successful constructions are recorded: a candidate that blows up in the
    constructor (an unknown parameter, for example) must not show up as a
    trained candidate.
    """
    built = []
    original = model_training.build_model

    def recorder(model_name, task_type, params):
        estimator = original(model_name, task_type, params)
        built.append({"model": model_name, "params": dict(params)})
        return estimator

    monkeypatch.setattr(model_training, "build_model", recorder)
    return built


def _effective_parameters(
    model_name,
    dataset,
    mode="manual",
    preset="balanced",
    hyperparameters=None,
    model_candidates=None,
):
    """The effective parameters ``train_model`` reports for a run."""
    if mode == "auto_search" and model_candidates is None:
        # A single candidate keeps the reported effective set unambiguous.
        model_candidates = [model_name]
    metrics, _source, _tag, _artifact = _train(
        model_name,
        dataset,
        hyperparameters=hyperparameters,
        mode=mode,
        preset=preset,
        model_candidates=model_candidates,
    )
    return metrics["model_parameters"]


@pytest.mark.parametrize("mode", ["manual", "auto_tune", "auto_fine_tune", "auto_search"])
def test_preset_scales_the_effective_parameters_in_every_mode(mode, classification_dataset):
    """A preset is effective in every mode, even with an empty hyperparameters dict."""
    conservative = _effective_parameters(
        "Random_Forest", classification_dataset, mode=mode, preset="conservative"
    )
    balanced = _effective_parameters(
        "Random_Forest", classification_dataset, mode=mode, preset="balanced"
    )

    assert balanced["n_estimators"] == CATALOG_N_ESTIMATORS, (
        f"the balanced preset must leave the catalog default untouched in {mode}"
    )
    assert conservative["n_estimators"] == CONSERVATIVE_N_ESTIMATORS, (
        f"the conservative preset must scale n_estimators in {mode}"
    )


def test_preset_scales_the_learning_rate_of_the_boosting_models(classification_dataset):
    """The conservative preset scales the learning rate of a catalog default."""
    conservative = _effective_parameters(
        "XGboost_timeseries", classification_dataset, preset="conservative"
    )

    assert conservative["learning_rate"] == pytest.approx(CATALOG_LEARNING_RATE * 0.1)
    assert conservative["n_estimators"] == CONSERVATIVE_N_ESTIMATORS


def test_aggressive_preset_scales_the_effective_parameters(classification_dataset):
    """The aggressive preset raises the learning rate and the number of estimators."""
    aggressive = _effective_parameters(
        "XGboost_timeseries", classification_dataset, preset="aggressive"
    )

    assert aggressive["n_estimators"] == AGGRESSIVE_N_ESTIMATORS
    assert aggressive["learning_rate"] == pytest.approx(CATALOG_LEARNING_RATE * 2)


def test_client_hyperparameters_win_over_the_preset_scaled_catalog_defaults(
    classification_dataset,
):
    """The client's own value is scaled by the preset and still wins over the base."""
    forest = _effective_parameters(
        "Random_Forest",
        classification_dataset,
        preset="conservative",
        hyperparameters={"n_estimators": 5},
    )
    # The client's value is scaled (max(10, int(5 * 0.7))) and wins over the
    # scaled catalog default (70).
    assert forest["n_estimators"] == max(10, int(5 * 0.7))

    boosting = _effective_parameters(
        "XGboost_timeseries",
        classification_dataset,
        preset="conservative",
        hyperparameters={"n_estimators": 5},
    )
    assert boosting["n_estimators"] == max(10, int(5 * 0.7))
    # The base the client overrides is scaled by the preset as well.
    assert boosting["learning_rate"] == pytest.approx(CATALOG_LEARNING_RATE * 0.1)


def test_auto_search_applies_the_preset_exactly_once(classification_dataset, built_models):
    """The preset must not be applied twice by the auto_search recursion."""
    metrics, _source, _tag, _artifact = _train(
        "Random_Forest",
        classification_dataset,
        hyperparameters={"n_estimators": CATALOG_N_ESTIMATORS},
        mode="auto_search",
        preset="conservative",
        model_candidates=["Random_Forest", "Logistic_Regression"],
    )

    forest = [entry for entry in built_models if entry["model"] == "Random_Forest"]
    assert forest, "the Random_Forest candidate was not trained"
    # 70, not the double-applied 49 (70 * 0.7).
    assert forest[0]["params"]["n_estimators"] == CONSERVATIVE_N_ESTIMATORS

    assert metrics["best_candidate"] in ("Random_Forest", "Logistic_Regression")
    # The reported effective parameters are the ones the winner was built with.
    best = next(
        entry for entry in built_models if entry["model"] == metrics["best_candidate"]
    )
    assert metrics["model_parameters"] == best["params"]


def test_auto_search_keeps_a_candidate_that_does_not_accept_a_client_parameter(
    classification_dataset, built_models
):
    """A candidate that does not accept a client parameter must still be trained."""
    metrics, _source, _tag, _artifact = _train(
        "Random_Forest",
        classification_dataset,
        hyperparameters={"C": 5.0},
        mode="auto_search",
        preset="balanced",
        model_candidates=["Random_Forest", "Logistic_Regression"],
    )

    built = {entry["model"]: entry["params"] for entry in built_models}
    assert set(built) == {"Random_Forest", "Logistic_Regression"}, (
        "every candidate has to be trained, also the one that does not accept "
        f"the client's parameter (trained: {sorted(built)})"
    )
    assert metrics["best_candidate"] in ("Random_Forest", "Logistic_Regression")
    # The parameter is only forwarded to the candidate that declares it.
    assert "C" not in built["Random_Forest"]
    assert built["Logistic_Regression"]["C"] == 5.0
