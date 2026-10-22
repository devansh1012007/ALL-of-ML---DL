"""Tests for the training of a model.

The dataset of a training is a path *relative to the datasets root*, and it
always comes from the registry - never from the client. The tests write their
datasets into the temporary root of the test run and refer to them by that
relative path.
"""

import os
from pathlib import Path

import pytest

from backend.app.model_training import (
    MODEL_CATALOG,
    _prepare_dataset,
    normalize_model_name,
    suggest_hyperparameters,
    train_model,
)


def _write(relative_path: str, content: str) -> str:
    """Write a file into the datasets root and return its relative path."""
    root = Path(os.environ["DATASETS_ROOT"])
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return relative_path


def test_local_dataset_not_found():
    with pytest.raises(FileNotFoundError):
        _prepare_dataset("missing_dataset.csv", None, "label", ",", None)


def test_prepare_dataset_missing_label():
    relative_path = _write(
        "data/missing_label.csv", "feature1,feature2\n1,2\n3,4\n"
    )
    with pytest.raises(ValueError) as excinfo:
        _prepare_dataset(relative_path, None, "label", ",", None)
    assert "label column" in str(excinfo.value)


def test_a_dataset_outside_of_the_root_is_refused(tmp_path):
    """A path that leaves the datasets root is not a dataset.

    Before the registry existed, the client sent a path and the server read
    it: an absolute path was used as it was, so any file of the server could
    be read. The root is the boundary now.
    """
    outside = tmp_path / "outside.csv"
    outside.write_text("feature,label\n1,0\n2,1\n")

    with pytest.raises(ValueError) as excinfo:
        _prepare_dataset(str(outside), None, "label", ",", None)
    assert "outside" in str(excinfo.value)

    with pytest.raises(ValueError):
        _prepare_dataset("../../etc/passwd", None, "label", ",", None)


def test_suggest_hyperparameters_fallback():
    suggested = suggest_hyperparameters("Random_Forest", "classification", "accuracy", None, None)
    assert isinstance(suggested, dict)
    assert "n_estimators" in suggested


def test_resnet50_catalog_entry():
    assert "ResNet50" in MODEL_CATALOG
    assert MODEL_CATALOG["ResNet50"]["params"]["model_name"] == "resnet50"


def test_train_model_auto_fine_tune_tabular():
    # Three rows per class: with test_size=0.5 the training fold keeps both
    # classes, otherwise the solver raises "needs samples of at least 2 classes".
    relative_path = _write(
        "data/simple.csv", "feature,label\n1,0\n2,1\n3,0\n4,1\n5,0\n6,1\n"
    )
    metrics, source, tag, artifact = train_model(
        "Logistic_Regression",
        relative_path,
        None,
        "label",
        0.5,
        42,
        {},
        ",",
        None,
        "auto_fine_tune",
    )
    assert source == "local"
    assert tag == relative_path
    assert metrics.get("accuracy") is not None
    assert Path(artifact).exists()


def test_train_resnet50_missing_dataset():
    with pytest.raises(ValueError):
        train_model(
            "ResNet50",
            "nonexistent_image_folder",
            None,
            "label",
            0.2,
            42,
            {},
            ",",
            None,
            "manual",
        )
