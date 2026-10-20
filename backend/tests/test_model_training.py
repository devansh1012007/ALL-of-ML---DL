import tempfile
from pathlib import Path

import pytest

from backend.app.model_training import (
    MODEL_CATALOG,
    _prepare_dataset,
    normalize_model_name,
    suggest_hyperparameters,
    train_model,
)


def test_local_dataset_not_found():
    with pytest.raises(FileNotFoundError):
        _prepare_dataset("missing_dataset.csv", None, "label", ",", None)


def test_prepare_dataset_missing_label(tmp_path):
    data_file = tmp_path / "missing_label.csv"
    data_file.write_text("feature1,feature2\n1,2\n3,4\n")
    with pytest.raises(ValueError) as excinfo:
        _prepare_dataset(str(data_file), None, "label", ",", None)
    assert "label column" in str(excinfo.value)


def test_suggest_hyperparameters_fallback():
    suggested = suggest_hyperparameters("Random_Forest", "classification", "accuracy", None, None)
    assert isinstance(suggested, dict)
    assert "n_estimators" in suggested


def test_resnet50_catalog_entry():
    assert "ResNet50" in MODEL_CATALOG
    assert MODEL_CATALOG["ResNet50"]["params"]["model_name"] == "resnet50"


def test_train_model_auto_fine_tune_tabular(tmp_path):
    data_file = tmp_path / "simple.csv"
    # Three rows per class: with test_size=0.5 the training fold keeps both
    # classes, otherwise the solver raises "needs samples of at least 2 classes".
    data = "feature,label\n1,0\n2,1\n3,0\n4,1\n5,0\n6,1\n"
    data_file.write_text(data)
    metrics, source, tag, artifact = train_model(
        "Logistic_Regression",
        str(data_file),
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
    assert tag == str(data_file)
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
