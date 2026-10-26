"""Honest-catalog regression tests (the contract of plan F0).

These tests pin the honesty contract of the model catalog after the phases
3 to 5 work:

* every catalog entry declares ``implemented`` and exactly one entry is
  ``False`` - UL2, retired with a permanent reason (plan F6: 20 billion
  parameters cannot be trained or served on the hardware this product
  targets);
* a retired entry fails fast in ``train_model()`` and writes no artifact;
* every implemented entry computes ``available`` with a reason (plan F8);
* clustering reports the honest metrics of plan C2 (the silhouette on the
  non-noise rows, the noise count, the baseline of random labels);
* ``auto_search`` can rank clustering candidates by ``silhouette``;
* the vision trainer reports validation accuracy with a baseline instead of
  an accuracy accumulated over its own training batches (plan C3);
* Q-Learning is the real table of plan F2: FrozenLake solved, CartPole
  refused with the supported environments named.

Everything is offline and CPU only: nothing is downloaded (the vision
trainer runs with ``pretrained=False``, the text smoke tests live in
``test_model_smoke.py`` with tiny configurations).
"""

import base64
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from backend.app import model_training
from backend.app.model_training import (
    MODEL_CATALOG,
    _CANDIDATE_SCORE_KEYS,
    train_model,
)

# The one entry that is not implemented and not coming back: UL2 is retired
# with a permanent reason (plan F6). Everything else is real now.
RETIRED = frozenset({"UL2"})

# A 1x1 pixel RGB PNG (69 bytes), embedded as base64 so the suite needs no
# image library. The vision trainer resizes every image, so a single pixel
# is a valid image for it.
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
    """A folder with two class subdirectories holding two 1x1 PNGs each.

    Two images per class is the minimum of the stratified split of plan C3:
    one lands in the training part, one in the validation part.
    """
    relative_path = "data/vision"
    folder = Path(os.environ["DATASETS_ROOT"]) / relative_path
    for class_name in ("cat", "dog"):
        class_dir = folder / class_name
        class_dir.mkdir(parents=True, exist_ok=True)
        (class_dir / "sample1.png").write_bytes(ONE_PIXEL_RGB_PNG)
        (class_dir / "sample2.png").write_bytes(ONE_PIXEL_RGB_PNG)
    return relative_path


def test_every_catalog_entry_declares_implemented():
    """Every catalog entry declares ``implemented`` (True or False).

    Exactly UL2 is ``False`` - retired with a permanent reason - and the
    rest are ``True``. Asserted against ``MODEL_CATALOG`` directly, the
    source of truth.
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

    assert false_entries == RETIRED, (
        f"the not-implemented entries are {sorted(false_entries)}, "
        f"expected {sorted(RETIRED)}"
    )
    assert true_entries == set(MODEL_CATALOG) - RETIRED


def test_the_retired_entry_declares_a_permanent_reason():
    """The retired entry says why it is retired, and is hidden (plan F6)."""
    entry = MODEL_CATALOG["UL2"]
    assert entry.get("not_supported"), "the retired entry must carry its reason"
    assert "20 billion" in entry["not_supported"]
    assert entry.get("hidden") is True, "the retired entry is not listed"


@pytest.mark.parametrize("model_name", sorted(RETIRED))
def test_retired_entry_fails_fast_and_writes_no_artifact(
    model_name, classification_dataset, isolated_model_dir
):
    """A retired entry fails fast in ``train_model()`` and writes no artifact.

    The failure is raised before any trainer and before ``write_artifact()``,
    so the model directory is unchanged by the run. A valid dataset is passed
    so the failure is the fail-fast, not a data error.
    """
    before = {p.name for p in model_training.MODEL_DIR.iterdir()}
    with pytest.raises(ValueError, match="is not implemented"):
        train_model(model_name, classification_dataset, None, "label", 0.2, 42, {})
    after = {p.name for p in model_training.MODEL_DIR.iterdir()}
    assert before == after, f"{model_name} wrote an artifact although it is retired"


def test_the_availability_of_every_entry_has_a_reason():
    """``model_availability`` answers available + reason for every entry (F8)."""
    for name in MODEL_CATALOG:
        entry = model_training.get_model_entry(name)
        availability = model_training.model_availability(entry)
        assert "available" in availability
        if availability["available"]:
            assert availability["reason"] is None
        else:
            assert availability["reason"], f"{name} is unavailable without a reason"


def test_the_llama_entry_needs_a_gpu_here():
    """LLaMA declares ``requires_gpu`` and is unavailable on a CPU-only
    deployment, with a reason that says so (plans F6, F8)."""
    entry = model_training.get_model_entry("LLaMA")
    assert entry["requires_gpu"] is True
    availability = model_training.model_availability(entry)
    try:
        import torch

        has_cuda = torch.cuda.is_available()
    except ImportError:
        has_cuda = False
    if not has_cuda:
        assert availability["available"] is False
        assert "GPU" in availability["reason"]


def test_real_model_still_trains_and_writes_artifact(
    classification_dataset, isolated_model_dir
):
    """A real model still trains end to end and writes a bundle artifact."""
    metrics, _source, _tag, artifact = train_model(
        "Random_Forest", classification_dataset, None, "label", 0.2, 42, {}
    )
    assert metrics["accuracy"] is not None
    assert Path(artifact["artifact_path"]).exists()
    assert Path(artifact["artifact_path"]).parent == isolated_model_dir
    assert artifact["artifact_sha256"], "the artifact record carries its checksum"
    assert artifact["artifact_bytes"] > 0


def test_the_artifact_checksum_guards_the_manifest(
    classification_dataset, isolated_model_dir
):
    """A file altered inside the artifact directory is refused (plan C1).

    The path guard stops files outside ``models/``; the checksum closes the
    gap that remains after it: a file tampered with inside ``models/`` is
    refused instead of executed.
    """
    from backend.app.bundles import BundleError, load_any_artifact

    _metrics, _source, _tag, artifact = train_model(
        "Random_Forest", classification_dataset, None, "label", 0.2, 42, {}
    )
    bundle = load_any_artifact(Path(artifact["artifact_path"]), artifact["artifact_sha256"])
    assert bundle.kind == "tabular"

    # Tamper with the model file: the manifest hash no longer matches the
    # recorded checksum, and the load is refused.
    model_file = Path(artifact["artifact_path"]) / "model.joblib"
    model_file.write_bytes(b"tampered")
    with pytest.raises(BundleError, match="checksum"):
        load_any_artifact(Path(artifact["artifact_path"]), artifact["artifact_sha256"])


def test_clustering_reports_the_honest_metrics():
    """The clustering trainer reports the honest metrics of plan C2.

    K-Mean on a separable dataset returns a silhouette well above the random
    labels baseline; DBSCAN with a tiny ``eps`` marks every point as noise
    (and the silhouette stays None, because the noise label is excluded).
    """
    from backend.app import clustering

    X = pd.DataFrame(
        np.array(
            [
                [0.0, 0.0],
                [0.1, 0.0],
                [0.0, 0.1],
                [10.0, 10.0],
                [10.1, 10.0],
                [10.0, 10.1],
                [50.0, 50.0],
                [50.1, 50.0],
                [50.0, 50.1],
                [50.2, 50.0],
            ],
            dtype=float,
        ),
        columns=["f0", "f1"],
    )

    metrics, _bundle = clustering.train_clustering_model(
        "K-Mean", X, "label", {"n_clusters": 3, "random_state": 42}
    )
    assert metrics["cluster_count"] == 3
    assert metrics["noise_count"] == 0
    assert metrics["silhouette"] is not None
    assert metrics["silhouette_baseline"] is not None
    assert metrics["silhouette"] > metrics["silhouette_baseline"]
    assert metrics["davies_bouldin"] is not None
    assert metrics["calinski_harabasz"] is not None
    # The held-out rows of plan C2: the model has a predict step, so 20
    # percent of the rows are scored out of sample.
    assert metrics["test_size"] == 2
    assert metrics["train_size"] == 8

    metrics_db, bundle_db = clustering.train_clustering_model(
        "DBSCAN", X, "label", {"eps": 0.001, "min_samples": 5}
    )
    # The density methods have no out-of-sample step, so every *training*
    # row is noise with a tiny eps - and the silhouette stays None.
    assert metrics_db["noise_count"] == metrics_db["train_size"]
    assert metrics_db["silhouette"] is None
    # The density methods have no out-of-sample step: the bundle says so.
    assert bundle_db.predicts is False


def test_clustering_silhouette_is_computed_when_some_points_are_noise():
    """DBSCAN that leaves some points as noise still reports a silhouette.

    The silhouette matrix is filtered to the non-noise points, so a shape
    mismatch between X and the labels can never silence the score.
    Regression test for the mixed noise case.
    """
    from backend.app import clustering

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

    # The features are standardised on the clustering path (plan C2), so the
    # eps is chosen for the scaled space: the three tight groups are ~0.005
    # apart inside and ~0.23 between, and the far outlier is the noise.
    metrics, _model = clustering.train_clustering_model(
        "DBSCAN", X, "label", {"eps": 0.1, "min_samples": 2}
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


def test_vision_trainer_reports_validation_accuracy(isolated_model_dir):
    """The vision trainer reports the validation metrics of plan C3.

    A tiny image folder with two classes of two 1x1 PNGs is enough: the
    split stratifies (one image per class in each part), and the trainer
    reports the validation accuracy **next to the majority baseline** -
    the honest version of the number the old trainer accumulated over its
    own training batches. ``pretrained=False`` keeps the run offline.
    """
    if (
        model_training.torchvision is None
        or model_training.ImageFolder is None
        or model_training.resnet18 is None
    ):
        pytest.skip("torchvision is not installed")

    dataset = _vision_folder()
    metrics, _source, _tag, artifact = train_model(
        "ResNet", dataset, None, "label", 0.2, 42,
        {"pretrained": False, "image_size": 64, "epochs": 1},
    )
    assert metrics["task_type"] == "classification"
    assert metrics["val_accuracy"] is not None
    assert metrics["baseline_accuracy"] is not None
    assert metrics["train_size"] + metrics["test_size"] == 4
    # The accuracy accumulated over the training batches is gone.
    assert "train_accuracy" not in metrics
    assert Path(artifact["artifact_path"]).exists()


def test_q_learning_solves_frozenlake_and_refuses_cartpole(isolated_model_dir):
    """The tabular Q-learning of plan F2.

    On the non-slippery 4x4 FrozenLake the greedy policy reaches a success
    rate of 1.0 within a few thousand steps and beats the random baseline;
    a continuous environment (CartPole) is refused with the supported
    environments named; the same seed gives the same table.
    """
    from backend.app import rl

    if rl._gymnasium() is None:
        pytest.skip("gymnasium is not installed")

    metrics, bundle = rl.train_q_learning(
        "FrozenLake-v1",
        {"training_steps": 4000, "epsilon_decay": 0.999, "random_state": 7},
    )
    assert metrics["task_type"] == "reinforcement-learning"
    assert metrics["mean_return"] > metrics["baseline_mean_return"]
    assert metrics["success_rate"] == 1.0
    assert metrics["beats_random_baseline"] is True

    # The same seed gives the same table (plan F2).
    _m2, bundle2 = rl.train_q_learning(
        "FrozenLake-v1",
        {"training_steps": 4000, "epsilon_decay": 0.999, "random_state": 7},
    )
    assert np.array_equal(bundle.q_table, bundle2.q_table)

    # The bundle answers: the greedy action for a state (plan F2).
    answer = bundle.infer({"state": 0})
    assert answer["action"] in range(4)

    # A continuous environment is refused clearly (plan F2).
    with pytest.raises(ValueError, match="FrozenLake"):
        rl.train_q_learning("CartPole-v1", {"training_steps": 100})
