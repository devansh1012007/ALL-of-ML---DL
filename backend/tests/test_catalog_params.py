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

import base64
import os
from pathlib import Path

import joblib
import pandas as pd
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

# Source of truth for the catalog models that are actually implemented (they
# train end to end). Deliberately NOT derived from ``MODEL_CATALOG``: a
# silently-changed ``implemented`` flag must not be able to slip through this
# expectation table, the same way ``EXPECTED_CATEGORY_BY_MODEL`` guards the
# routing categories.
IMPLEMENTED = frozenset(
    {
        "Autoencoder",
        "BERT",
        "BERT2BERT",
        "CATboost_timeseries",
        "DBSCAN",
        "DQN",
        "DistilBERT",
        "GMM",
        "GNN",
        "GPT",
        "HDBSCAN",
        "HMM_timeseries",
        "Hierarchical_Clustering",
        "K-Mean",
        "KNN",
        "LLaMA",
        "LSTM",
        "Logistic_Regression",
        "MLR",
        "MiniLM",
        "PCA",
        "PPO",
        "Q-Learning",
        "RNN",
        "Random_Forest",
        "ResNet",
        "ResNet50",
        "SSM_timeseries",
        "SVM",
        "TCN_timeseries",
        "UMAP",
        "ViT",
        "XGboost_timeseries",
        "lightGBM_timeseries",
        "self-attenetion_transformer",
        "seq2seq",
        "t-SNE",
    }
)
# UL2 is retired with a permanent reason (plan F6): it is the one entry that
# is not implemented and not coming back.
RETIRED = frozenset({"UL2"})

# Catalog models that are advertised but not implemented: ``train_model()``
# fails fast for them before any trainer runs and before any artifact is
# written. The complement of ``IMPLEMENTED`` within the catalog.
NOT_IMPLEMENTED = set(MODEL_CATALOG) - IMPLEMENTED

# The trainer each category selects, after the phases 3 to 5 plan: every
# family has its own module, and "time-series" (the boosters) trains as a
# tabular model through build_model() unless the request asks for the
# forecasting mode.
CATEGORY_TO_TRAINER = {
    "classification": "model_training.build_model",
    "regression": "model_training.build_model",
    "time-series": "model_training.build_model",
    "clustering": "clustering.train_clustering_model",
    "timeseries": "forecasting.train_forecaster",
    "graph": "graph_models.train_gnn",
    "autoencoder": "model_training._train_autoencoder",
    "reinforcement-learning": "rl.train_q_learning|rl.train_deep_rl",
    "nlp": "textmodels.train_*",
    "vision": "vision.train_image_model",
}

# (module attribute path, recorder name) monkeypatched so the test can see
# which trainer ``train_model`` dispatched to.
RECORDED_TRAINERS = (
    ("model_training", "build_model"),
    ("model_training", "_train_autoencoder"),
    ("clustering", "train_clustering_model"),
    ("forecasting", "train_forecaster"),
    ("graph_models", "train_gnn"),
    ("rl", "train_q_learning"),
    ("rl", "train_deep_rl"),
    ("textmodels", "train_text_classifier"),
    ("textmodels", "train_language_model"),
    ("textmodels", "train_seq2seq"),
    ("textmodels", "train_llama_lora"),
    ("vision", "train_image_model"),
)

# The trainer a specific model is expected to reach (the NLP entries route by
# their declared task; Q-Learning is its own trainer).
TRAINER_BY_MODEL = {
    "Q-Learning": "rl.train_q_learning",
    "PPO": "rl.train_deep_rl",
    "DQN": "rl.train_deep_rl",
    "GPT": "textmodels.train_language_model",
    "LLaMA": "textmodels.train_llama_lora",
    "seq2seq": "textmodels.train_seq2seq",
    "BERT2BERT": "textmodels.train_seq2seq",
}

# Models that only need scikit-learn (or the boosting libraries) and therefore
# have to train end to end on the synthetic dataset.
OFFLINE_TRAINABLE_MODELS = frozenset(
    {
        "Autoencoder",
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

# A 1x1 pixel RGB PNG (69 bytes), embedded as base64 so the suite needs no
# image library. The vision trainer resizes every image to 224x224, so a single
# pixel is a valid image for it - what the dataset needs is a *readable* file
# per class, because ``ImageFolder`` refuses a class without one.
ONE_PIXEL_RGB_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR42mP4z8AAAAMBAQD3A0FDAAAAAElFTkSuQmCC"
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
    """Record which trainer ``train_model`` dispatches to.

    The trainers live in their own modules since the phases 3 to 5 plan; the
    recorder patches the module attribute ``train_model`` calls, so the
    dispatch is observed exactly where it happens.
    """
    import importlib

    calls = []
    for module_name, attribute in RECORDED_TRAINERS:
        module = importlib.import_module(f"backend.app.{module_name}")
        recorder_name = f"{module_name}.{attribute}"
        original = getattr(module, attribute)

        def recorder(*args, _name=recorder_name, _original=original, **kwargs):
            calls.append(_name)
            return _original(*args, **kwargs)

        monkeypatch.setattr(module, attribute, recorder)
    return calls


def _image_folder():
    """A folder with class subdirectories, as the vision models expect.

    The folder lives in the datasets root and is referred to by its path
    relative to it: a dataset is always such a path.

    Every class directory holds a real image file: ``ImageFolder`` refuses a
    class without a readable image ("Found no valid file for the classes ..."),
    so an empty directory is not a dataset.
    """
    relative_path = "data/images"
    folder = Path(os.environ["DATASETS_ROOT"]) / relative_path
    for class_name in ("cat", "dog"):
        class_dir = folder / class_name
        class_dir.mkdir(parents=True, exist_ok=True)
        for index in (1, 2):
            (class_dir / f"{class_name}{index}.png").write_bytes(ONE_PIXEL_RGB_PNG)
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
    # The source-of-truth set of implemented models has to agree with the
    # ``implemented`` flag of every catalog entry: a silently-changed flag
    # must fail this assertion instead of slipping through.
    assert IMPLEMENTED == {k for k, v in MODEL_CATALOG.items() if v.get("implemented")}


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
        # The text trainers download their checkpoint; the smoke tests of the
        # catalog (test_model_smoke.py) cover them with tiny configurations.
        pytest.skip("the NLP trainers download pretrained checkpoints")

    # Some trainers (catboost) write scratch files into the working directory.
    monkeypatch.chdir(tmp_path)

    env_id = "CartPole-v1"
    if expected_category == "vision":
        dataset = _image_folder()
    elif expected_category == "graph":
        dataset = _graph_zip(tmp_path)
    elif expected_category == "regression":
        # MLR is a regressor: it needs a continuous label, a classification label
        # would be scored with a classification metric.
        dataset = regression_dataset
    else:
        dataset = classification_dataset

    metrics = None
    error = None
    artifact = None
    hyperparameters = None
    if expected_category == "vision":
        # The catalog asks for the pretrained weights, and downloading them is
        # not something a unit test does: the suite stays offline, as the
        # module promises. The trainer itself runs exactly the same way.
        hyperparameters = {"pretrained": False, "image_size": 64, "epochs": 1}
    elif expected_category == "timeseries":
        # A short series with a small window: the routing test is about where
        # the call goes, not about the forecast quality.
        hyperparameters = {"window": 3, "horizon": 1, "epochs": 1}
    elif model_name == "Q-Learning":
        # The Q-table contract: a discrete environment (plan F2). CartPole is
        # refused with the supported environments named.
        env_id = "FrozenLake-v1"
        hyperparameters = {"training_steps": 400}
    elif expected_category == "reinforcement-learning":
        hyperparameters = {"training_steps": 200}
    try:
        metrics, _source, _tag, artifact = _train(
            model_name, dataset, hyperparameters, env_id=env_id
        )
    except Exception as exc:  # noqa: BLE001 - the error is inspected below
        error = exc

    # Placeholder models fail fast in ``train_model()``: the error is raised
    # before any trainer runs and before any artifact is written, so no trainer
    # was dispatched and there is no artifact.
    if model_name in NOT_IMPLEMENTED:
        assert error is not None, f"{model_name} is a placeholder but did not raise"
        assert "is not implemented" in str(error), (
            f"{model_name} raised {error!r}, which is not a not-implemented error"
        )
        assert recorded_trainers == [], (
            f"{model_name} dispatched to {recorded_trainers} although it is a placeholder"
        )
        assert artifact is None, f"{model_name} wrote an artifact although it is a placeholder"
        return

    expected_for_model = TRAINER_BY_MODEL.get(model_name, expected_trainer)
    assert recorded_trainers == [expected_for_model], (
        f"{model_name} (category {expected_category}) was routed to {recorded_trainers}, "
        f"but {expected_for_model} is expected"
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

    if expected_category == "vision":
        # The vision trainer really ran (plan C3): a stratified split with a
        # validation part, the metrics measured on it and a baseline.
        assert metrics["task_type"] == "classification"
        assert metrics["classes"] == 2
        assert metrics["val_accuracy"] is not None
        assert metrics["baseline_accuracy"] is not None
        assert metrics["train_size"] + metrics["test_size"] == 4
        assert Path(artifact["artifact_path"]).exists()
    elif expected_category == "timeseries":
        # The forecasting contract (plan F3): the naive baselines are reported
        # next to the model's error, on a chronological split.
        assert metrics["task_type"] == "timeseries"
        assert metrics["baseline_naive_mae"] is not None
        assert metrics["beats_naive"] in (True, False)
        assert Path(artifact["artifact_path"]).exists()
    elif expected_category == "reinforcement-learning":
        # The honest evaluation (plan C5/F2): fresh episodes with fixed seeds
        # and a random-policy baseline.
        assert metrics["task_type"] == "reinforcement-learning"
        assert metrics["mean_return"] is not None
        assert metrics["baseline_mean_return"] is not None
        assert Path(artifact["artifact_path"]).exists()
    elif model_name in OFFLINE_TRAINABLE_MODELS:
        if expected_category == "autoencoder":
            assert metrics["task_type"] == "autoencoder"
            assert metrics["reconstruction_mse"] < metrics["baseline_mse"]
        elif expected_category == "clustering":
            # The clustering metrics of plan C2: the sizes and (where the
            # model is not the density kind) the honest scores.
            assert metrics["cluster_count"] >= 1
            assert metrics["train_size"] + metrics["test_size"] == 60
        elif expected_category == "regression":
            # A regressor must not be scored with a classification metric.
            assert metrics["task_type"] == "regression"
            assert metrics["r2"] is not None
            assert metrics["accuracy"] is None
        else:
            assert metrics["task_type"] == "classification"
            assert metrics["accuracy"] is not None
        assert Path(artifact["artifact_path"]).exists()


def _graph_zip(tmp_path):
    """A graph dataset of plan F4: a zip with nodes.csv and edges.csv.

    Two communities with informative structure: the features are noise, the
    label comes from the community, so the graph is what carries the signal.
    """
    import io
    import zipfile

    rng = pd.Series(range(40)).apply(lambda _: __import__("numpy").random.default_rng(_))
    import numpy as np

    generator = np.random.default_rng(0)
    n = 40
    labels = ["a", "b"] * (n // 2)
    nodes = pd.DataFrame(
        {
            "node_id": [f"n{i}" for i in range(n)],
            "x": generator.normal(size=n),
            "label": labels,
        }
    )
    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            same = labels[i] == labels[j]
            if generator.random() < (0.4 if same else 0.02):
                edges.append((f"n{i}", f"n{j}"))
    edge_frame = pd.DataFrame(edges, columns=["source", "target"])
    zip_path = tmp_path / "graph.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("nodes.csv", nodes.to_csv(index=False))
        archive.writestr("edges.csv", edge_frame.to_csv(index=False))
    # The trainer resolves the dataset through the registry root.
    import shutil as _shutil

    destination = Path(os.environ["DATASETS_ROOT"]) / "data" / "graph.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    _shutil.copy(zip_path, destination)
    return "data/graph.zip"


def _feature_count(dataset):
    """The number of feature columns of a CSV dataset (the label excluded)."""
    frame = pd.read_csv(Path(os.environ["DATASETS_ROOT"]) / dataset)
    return len([column for column in frame.columns if column != "label"])


def test_the_artifact_of_a_torch_trainer_is_a_bundle_that_loads(
    classification_dataset, regression_dataset
):
    """A torch artifact is a bundle directory that loads back and predicts.

    The torch trainers used to pickle the module (which breaks the moment the
    class moves). Since the bundle contract (plan C1) the artifact is a
    directory with a ``state_dict``, a ``config.json`` and the manifest, and
    the loader rebuilds the architecture from the registry. The round trip is
    exercised on the RNN forecaster, trained tiny on the synthetic dataset.
    """
    if model_training.torch is None:
        pytest.skip("torch is not installed")

    metrics, _source, _tag, artifact = _train(
        "RNN",
        regression_dataset,
        {"window": 4, "horizon": 2, "epochs": 2, "hidden_size": 8},
    )
    from backend.app.bundles import load_any_artifact

    bundle = load_any_artifact(Path(artifact["artifact_path"]), artifact["artifact_sha256"])
    assert bundle.kind == "timeseries"

    # The loaded bundle forecasts: the last window rows, in the trained order.
    frame = pd.read_csv(Path(os.environ["DATASETS_ROOT"]) / regression_dataset)
    schema = bundle.schema()
    rows = frame[schema["features"]].tail(schema["window"]).to_numpy().tolist()
    answer = bundle.infer({"window_rows": rows})
    assert len(answer["predictions"]) == schema["horizon"]


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
    from backend.app.model_training import _TRAINER_OWNED_PARAMS

    params = {
        name: value
        for name, value in MODEL_CATALOG[model_name].get("params", {}).items()
        # The trainer-owned keys (the forecasting contract of plan F3) steer
        # the training loop, never the estimator constructor.
        if name not in _TRAINER_OWNED_PARAMS
    }
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
    assert metrics["train_size"] + metrics["test_size"] == 60
    assert Path(artifact["artifact_path"]).exists()


def test_training_writes_the_artifact_into_the_temporary_model_dir(
    classification_dataset, isolated_model_dir
):
    """The suite must not write artifacts into the repository's models/ directory."""
    _metrics, _source, _tag, artifact = _train("Logistic_Regression", classification_dataset)
    # The artifact is a bundle directory since plan C1; it still has to land
    # in the redirected models/ directory, never in the repository.
    artifact_path = Path(artifact["artifact_path"])
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
    assert Path(artifact["artifact_path"]).exists()
    assert Path(artifact["artifact_path"]).parent == isolated_model_dir


def test_auto_fine_tune_changes_the_applied_parameters(classification_dataset):
    """auto_tune searches the curated space, auto_fine_tune searches a
    neighbourhood of the base configuration, and the client's pinned parameter
    wins in every mode (auto_tune is no longer a no-op equal to manual)."""
    manual = _train(
        "XGboost_timeseries", classification_dataset, {"n_estimators": 5}, mode="manual"
    )[0]
    tuned = _train(
        "XGboost_timeseries", classification_dataset, {"n_estimators": 5}, mode="auto_tune"
    )[0]
    fine_tuned = _train(
        "XGboost_timeseries", classification_dataset, {"n_estimators": 5}, mode="auto_fine_tune"
    )[0]

    # The client's pinned parameter wins in every mode.
    for metrics in (manual, tuned, fine_tuned):
        assert metrics["model_parameters"]["n_estimators"] == 5

    # auto_tune runs a real randomized search over the curated space.
    assert tuned.get("search_results"), "auto_tune must report search results"
    assert tuned["model_parameters"]["learning_rate"] in (0.01, 0.1, 0.2)

    # auto_fine_tune runs the same engine on a neighbourhood of the base.
    assert fine_tuned.get("search_results"), "auto_fine_tune must report search results"
    assert fine_tuned["model_parameters"]["learning_rate"] in (0.05, 0.1, 0.2)


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

    def recorder(model_name, task_type, params, **kwargs):
        estimator = original(model_name, task_type, params, **kwargs)
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


@pytest.mark.parametrize("mode", ["manual", "auto_search"])
def test_preset_scales_the_effective_parameters_in_every_mode(mode, classification_dataset):
    """A preset is effective in every mode, even with an empty hyperparameters dict.

    auto_tune and auto_fine_tune are not parametrised here: they run a randomized
    search whose best parameters override the catalogue defaults, so their exact
    effective n_estimators depends on the search outcome (the preset still scales
    those best parameters, which test_search.py covers).
    """
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
