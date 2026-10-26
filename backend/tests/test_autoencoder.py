"""The autoencoder is a real one: encoder, bottleneck, decoder.

It used to be a placeholder (``implemented: False``) because the only trainer it
could reach was a generic network that fitted a label. These tests pin what
"real" means:

* the network learns a structure that exists in the data (its error beats the
  trivial reconstruction by a wide margin) and flags a row that breaks it;
* ``encode`` is the bottleneck of *the trained network*, not a look-alike: the
  decoder applied to the code gives exactly what the network predicts;
* the metrics are measured on rows it did not train on, with the baseline next
  to them;
* a wrong parameter is an error, not a silent default.
"""

import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from backend.app.model_training import MODEL_CATALOG, train_model
from backend.app.tabular import AutoencoderBundle


def _structured_dataset(name="data/structured.csv", n_rows=400, seed=0):
    """Six columns that are really two numbers (plus noise), a category, a label."""
    rng = np.random.RandomState(seed)
    z = rng.normal(size=(n_rows, 2))
    frame = pd.DataFrame(
        {
            "a": z[:, 0],
            "b": 2 * z[:, 0] + rng.normal(scale=0.05, size=n_rows),
            "c": z[:, 1],
            "d": -z[:, 1] + rng.normal(scale=0.05, size=n_rows),
            "kind": rng.choice(["x", "y"], n_rows),
            "label": 0,
        }
    )
    path = Path(os.environ["DATASETS_ROOT"]) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return name


def _train(dataset, **params):
    return train_model("Autoencoder", dataset, None, "label", 0.2, 42, params)


def test_the_catalog_entry_is_real_and_says_what_it_reports():
    entry = MODEL_CATALOG["Autoencoder"]

    assert entry["implemented"] is True
    assert "test_results" in entry and "planned_test_results" not in entry
    assert "expected_reconstruction_mse" in entry["test_results"]
    # Nothing in the catalog that the network cannot do: there is no dropout.
    assert "dropout_rate" not in entry["params"]


def test_it_learns_the_structure_and_beats_the_trivial_reconstruction():
    metrics, *_ = _train(_structured_dataset(), latent_dim=2, hidden_units=8, epochs=400)

    assert metrics["task_type"] == "autoencoder"
    # Six columns that are two numbers: a 2-unit bottleneck reproduces them.
    assert metrics["reconstruction_mse"] < 0.5 * metrics["baseline_mse"]
    assert metrics["reconstruction_r2"] > 0.5
    assert metrics["latent_dim"] == 2
    assert metrics["train_size"] + metrics["test_size"] == 400
    assert metrics["artifact_kind"] == "autoencoder"


def test_a_row_that_breaks_the_structure_is_flagged_and_a_normal_one_is_not():
    # Three units: the two numbers behind the columns, and the (random) category.
    _, _, _, artifact = _train(
        _structured_dataset(), latent_dim=3, hidden_units=8, epochs=400
    )
    bundle = joblib.load(Path(artifact["artifact_path"]) / "model.joblib")
    assert isinstance(bundle, AutoencoderBundle)

    result = bundle.infer(
        [
            {"a": 0.5, "b": 1.0, "c": -0.3, "d": 0.3, "kind": "x"},  # b = 2a, d = -c: fits
            {"a": 0.5, "b": -4.0, "c": -0.3, "d": 3.0, "kind": "x"},  # breaks both
        ]
    )

    assert result["is_anomaly"] == [False, True]
    normal, broken = result["reconstruction_error"]
    assert broken > 10 * normal
    assert broken > result["threshold"] > normal


def test_the_anomaly_threshold_is_the_quantile_of_the_training_errors():
    metrics, _, _, artifact = _train(
        _structured_dataset(), latent_dim=2, hidden_units=8, anomaly_quantile=0.9
    )
    bundle = joblib.load(Path(artifact["artifact_path"]) / "model.joblib")

    assert bundle.quantile == 0.9
    assert metrics["anomaly_threshold"] == pytest.approx(bundle.threshold)
    # Held-out rows from the same distribution: about 10% are above a 90% threshold.
    assert metrics["test_anomaly_rate"] < 0.25


@pytest.mark.parametrize("hidden_units, bottleneck_layers", [(0, 1), (8, 2)])
def test_encode_is_the_bottleneck_of_the_trained_network(hidden_units, bottleneck_layers):
    """The decoder applied to the code gives exactly what the network predicts.

    If ``encode`` were a look-alike (a different projection), the code and the
    network would disagree, and the returned latent vectors would mean nothing.
    """
    _, _, _, artifact = _train(
        _structured_dataset(), latent_dim=3, hidden_units=hidden_units, epochs=100
    )
    bundle = joblib.load(Path(artifact["artifact_path"]) / "model.joblib")
    assert bundle.bottleneck_layers == bottleneck_layers

    frame = pd.DataFrame(
        {"a": [0.1, -1.0], "b": [0.2, 1.5], "c": [0.0, 0.7], "d": [0.1, -0.5], "kind": ["x", "y"]}
    )
    matrix = bundle.preprocessor.transform(frame)
    code = bundle.encode(matrix)
    assert code.shape == (2, 3)

    network = bundle.network
    activations = code
    for layer in range(bottleneck_layers, len(network.coefs_)):
        activations = activations @ network.coefs_[layer] + network.intercepts_[layer]
        if layer < len(network.coefs_) - 1:
            activations = np.maximum(activations, 0.0)  # relu on every hidden layer
    np.testing.assert_allclose(activations, network.predict(matrix), rtol=1e-9, atol=1e-9)


def test_the_label_column_is_ignored_and_the_report_says_which_columns_were_used():
    metrics, *_ = _train(_structured_dataset(), latent_dim=2)

    report = metrics["preprocessing"]
    assert report["numeric_columns"] == ["a", "b", "c", "d"]
    assert report["categorical_columns"] == ["kind"]
    assert "label" not in report["numeric_columns"]
    assert metrics["feature_count"] == 5


@pytest.mark.parametrize(
    "params, error, message",
    [
        ({"latent_dimension": 2}, TypeError, "unexpected parameter"),
        ({"activation": "swish"}, ValueError, "activation must be one of"),
        ({"latent_dim": 0}, ValueError, "latent_dim must be at least 1"),
        ({"anomaly_quantile": 1.5}, ValueError, "anomaly_quantile"),
    ],
)
def test_a_wrong_parameter_is_an_error_and_not_a_silent_default(params, error, message):
    with pytest.raises(error, match=message):
        _train(_structured_dataset(), **params)
