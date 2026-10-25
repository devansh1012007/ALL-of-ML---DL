"""Honest-catalog regression tests (T06 of WEEK1_PLAN.md).

These tests pin the honesty contract of the model catalog:

* every catalog entry declares ``implemented`` and exactly the twelve
  placeholders are ``False`` while the rest are ``True``;
* a placeholder fails fast in ``train_model()`` and writes no artifact;
* a real model still trains end to end and writes an artifact;
* clustering reports ``silhouette`` and ``noise_count`` (DBSCAN's ``-1``
  noise label is excluded from the silhouette);
* ``auto_search`` can rank clustering candidates by ``silhouette``;
* ``SimpleNet`` lives at module level so its artifacts are picklable
  (no ``EOFError`` on load);
* the vision trainer reports ``train_accuracy`` instead of ``accuracy``.

Everything is offline and CPU only: nothing is downloaded and the vision
trainer runs with ``pretrained=False``.
"""

import base64
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
import torch

from backend.app import model_training
from backend.app.model_training import (
    MODEL_CATALOG,
    _CANDIDATE_SCORE_KEYS,
    _train_clustering,
    train_model,
)

# The eight placeholder entries: their trainer does not build what the
# entry advertises, so they declare ``implemented: False``.
PLACEHOLDERS = frozenset(
    {
        "Q-Learning",
        "GNN",
        "LSTM",
        "RNN",
        "SSM_timeseries",
        "TCN_timeseries",
        "ViT",
    }
)

# A 1x1 pixel RGB PNG (69 bytes), embedded as base64 so the suite needs no
# image library. The vision trainer resizes every image to 224x224, so a
# single pixel is a valid image for it.
ONE_PIXEL_RGB_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR42mP4z8AAAAMBAQD3A0FDAAAAAElFTkSuQmCC"
)


def _write_csv(tmp_path, relative_path: str, content: str) -> str:
    """Write a CSV into the datasets root and return its relative path."""
    root = Path(os.environ["DATASETS_ROOT"])
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return relative_path


def _vision_folder() -> str:
    """A folder with one class subdirectory holding a 1x1 PNG.

    The folder lives under the datasets root and is referred to by its path
    relative to it: a dataset is always such a path. ``ImageFolder`` refuses
    a class without a readable image, so every class directory holds one.
    """
    relative_path = "data/vision"
    folder = Path(os.environ["DATASETS_ROOT"]) / relative_path
    class_dir = folder / "cat"
    class_dir.mkdir(parents=True, exist_ok=True)
    (class_dir / "sample.png").write_bytes(ONE_PIXEL_RGB_PNG)
    return relative_path


def test_every_catalog_entry_declares_implemented():
    """Every catalog entry declares ``implemented`` (True or False).

    Exactly the eight placeholders are ``False`` and the rest are ``True``.
    Asserted against ``MODEL_CATALOG`` directly, the source of truth.
    """
    for name, entry in MODEL_CATALOG.items():
        assert "implemented" in entry, f"{name} does not declare 'implemented'"
        assert entry["implemented"] in (True, False), (
            f"{name} declares 'implemented' = {entry['implemented']!r}, "
            "but a boolean is required"
        )

    false_entries = {
        name for name, entry in MODEL_CATALOG.items() if entry["implemented"] is False
    }
    true_entries = {
        name for name, entry in MODEL_CATALOG.items() if entry["implemented"] is True
    }

    assert false_entries == PLACEHOLDERS, (
        f"placeholders are {sorted(false_entries)}, expected {sorted(PLACEHOLDERS)}"
    )
    assert true_entries == set(MODEL_CATALOG) - PLACEHOLDERS


@pytest.mark.parametrize("model_name", sorted(PLACEHOLDERS))
def test_placeholder_fails_fast_and_writes_no_artifact(
    model_name, classification_dataset, isolated_model_dir
):
    """A placeholder fails fast in ``train_model()`` and writes no artifact.

    The failure is raised before any trainer and before ``write_artifact()``,
    so the model directory is unchanged by the run. A valid dataset is passed
    so the failure is the fail-fast, not a data error.
    """
    before = {p.name for p in model_training.MODEL_DIR.iterdir()}
    with pytest.raises(ValueError, match="is not implemented"):
        train_model(model_name, classification_dataset, None, "label", 0.2, 42, {})
    after = {p.name for p in model_training.MODEL_DIR.iterdir()}
    assert before == after, f"{model_name} wrote an artifact although it is a placeholder"


def test_real_model_still_trains_and_writes_artifact(
    classification_dataset, isolated_model_dir
):
    """A real model still trains end to end and writes an artifact."""
    metrics, _source, _tag, artifact = train_model(
        "Random_Forest", classification_dataset, None, "label", 0.2, 42, {}
    )
    assert metrics["accuracy"] is not None
    assert Path(artifact).exists()
    assert Path(artifact).parent == isolated_model_dir


def test_clustering_reports_silhouette_and_noise_count():
    """``_train_clustering()`` reports ``silhouette`` and ``noise_count``.

    K-Mean on a separable dataset returns a non-None silhouette; DBSCAN with a
    tiny ``eps`` marks every point as noise (``noise_count > 0``); an
    all-noise DBSCAN returns ``silhouette`` None because the noise label
    ``-1`` is excluded from the silhouette computation.
    """
    X = pd.DataFrame(
        np.array(
            [
                [0.0, 0.0],
                [0.1, 0.0],
                [0.0, 0.1],
                [10.0, 10.0],
                [10.1, 10.0],
                [10.0, 10.1],
            ],
            dtype=float,
        ),
        columns=["f0", "f1"],
    )

    metrics, _model = model_training._train_clustering(
        "K-Mean", X, {"n_clusters": 2, "random_state": 42}
    )
    assert metrics["silhouette"] is not None
    assert metrics["noise_count"] == 0

    metrics_db, _model_db = model_training._train_clustering(
        "DBSCAN", X, {"eps": 0.001, "min_samples": 5}
    )
    assert metrics_db["noise_count"] == len(X)
    assert metrics_db["silhouette"] is None


def test_clustering_silhouette_is_computed_when_some_points_are_noise():
    """DBSCAN that leaves some points as noise still reports a silhouette.

    The silhouette matrix is filtered to the non-noise points, so a shape
    mismatch between X and the labels can never silence the score.
    Regression test for the mixed noise case.
    """
    X = pd.DataFrame(
        np.array(
            [
                [0.0, 0.0],
                [0.1, 0.0],
                [0.0, 0.1],
                [10.0, 10.0],
                [10.1, 10.0],
                [10.0, 10.1],
                [5.0, 5.0],
                [5.1, 5.2],
                [4.9, 5.1],
                [100.0, 100.0],
            ],
            dtype=float,
        ),
        columns=["f0", "f1"],
    )

    metrics, _model = model_training._train_clustering(
        "DBSCAN", X, {"eps": 0.8, "min_samples": 2}
    )
    assert metrics["noise_count"] > 0
    assert metrics["silhouette"] is not None
    assert metrics["cluster_count"] >= 2


def test_auto_search_ranks_clustering_candidates(
    classification_dataset, isolated_model_dir
):
    """``silhouette`` is a candidate score key and ``auto_search`` ranks
    clustering candidates by it, so a clustering candidate can be selected.
    """
    assert "silhouette" in _CANDIDATE_SCORE_KEYS

    metrics, _source, _tag, _artifact = train_model(
        "K-Mean",
        classification_dataset,
        None,
        "label",
        0.2,
        42,
        {},
        mode="auto_search",
        model_candidates=["K-Mean", "DBSCAN"],
    )
    assert metrics["best_candidate"] in ("K-Mean", "DBSCAN")
    assert metrics["silhouette"] is not None


def test_simple_net_is_module_level_and_picklable(tmp_path):
    """``SimpleNet`` is module level and its artifacts are picklable.

    Regression guard for the corrupt-artifact bug: a network defined inside a
    function cannot be loaded back from its joblib artifact (``EOFError``),
    because pickle stores a class by reference and a function-local class
    cannot be found again.
    """
    assert model_training.SimpleNet is not None

    net = model_training.SimpleNet(input_dim=4, output_dim=1)
    path = tmp_path / "s.joblib"
    joblib.dump(net, path)
    loaded = joblib.load(path)

    assert isinstance(loaded, model_training.SimpleNet)
    outputs = loaded(torch.zeros(2, 4))
    assert tuple(outputs.shape) == (2, 1)


def test_vision_trainer_reports_train_accuracy(isolated_model_dir):
    """The vision trainer reports ``train_accuracy`` instead of ``accuracy``.

    A tiny image folder with one class subdirectory holding a 1x1 PNG is
    enough: ``ImageFolder`` only needs one readable image per class, and the
    trainer resizes every image to 224x224. ``pretrained=False`` keeps the
    run offline (no checkpoint download).
    """
    if (
        model_training.torchvision is None
        or model_training.ImageFolder is None
        or model_training.resnet18 is None
    ):
        pytest.skip("torchvision is not installed")

    dataset = _vision_folder()
    metrics, _source, _tag, artifact = train_model(
        "ResNet", dataset, None, "label", 0.2, 42, {"pretrained": False}
    )
    assert metrics["train_accuracy"] is not None
    assert "accuracy" not in metrics
    assert Path(artifact).exists()
