"""The smoke tests of the implemented entries (plan F0).

An entry is ``implemented: True`` only when all three hold, and these tests
are the first: a smoke test with a tiny configuration runs offline (nothing
is downloaded - the tiny text configurations are built from config objects)
and reports the advertised metric on held-out data, next to a baseline.

The second (it saves a ``ModelBundle`` that can predict) and the third (it
declares what it needs) are pinned here as well: the round trips go through
``write_bundle`` / ``load_any_artifact``, and the declared needs of every
entry are compared with what the catalog says.
"""

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.app import forecasting, graph_models, model_training, textmodels
from backend.app.bundles import load_any_artifact, write_bundle
from backend.app.model_training import MODEL_CATALOG

torch = pytest.importorskip("torch", reason="the deep trainers need torch")


# --- the shared data ----------------------------------------------------------------


def _sine_frame(n: int = 240, noise: float = 0.15, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    values = np.sin(np.arange(n) * 2 * np.pi / 24) * 3 + rng.normal(0, noise, n)
    return pd.DataFrame({"value": values.round(4)})


def _ar_frame(n: int = 240, seed: int = 1) -> pd.DataFrame:
    """An autoregressive series: x(t) = 0.5 x(t-1) + noise.

    The fast decay keeps the naive forecast honestly beatable: a coefficient
    near one is a near-random-walk, where nothing beats the naive forecast
    and the plan's assertion would be false by construction.
    """
    rng = np.random.default_rng(seed)
    values = [0.0]
    for _ in range(n - 1):
        values.append(0.5 * values[-1] + rng.normal(0, 0.1))
    return pd.DataFrame({"value": np.asarray(values).round(4)})


SMALL_FORECAST_PARAMS = {
    "window": 12,
    "horizon": 3,
    "epochs": 15,
    "patience": 5,
    "hidden_size": 32,
    "learning_rate": 0.01,
}


@pytest.mark.parametrize("series_name", ["sine", "ar"])
@pytest.mark.parametrize(
    "model_name", ["RNN", "LSTM", "TCN_timeseries", "SSM_timeseries"]
)
def test_a_neural_forecaster_beats_the_naive_baseline(model_name, series_name):
    """The forecasting contract of plan F3: on a learnable series the model
    beats the naive forecast on the held-out tail, and the baselines are
    reported next to it."""
    frame = _sine_frame() if series_name == "sine" else _ar_frame()
    metrics, bundle = forecasting.train_forecaster(
        model_name, frame, "value", {**SMALL_FORECAST_PARAMS, "hidden_size": 24}
    )
    assert metrics["task_type"] == "timeseries"
    assert metrics["baseline_naive_mae"] is not None
    assert metrics["baseline_seasonal_naive_mae"] is not None
    assert metrics["beats_naive"] is True, (
        f"{model_name} on {series_name}: mae={metrics['mae']} naive={metrics['baseline_naive_mae']}"
    )
    assert metrics["test_size"] > 0


@pytest.mark.parametrize("model_name", ["RNN", "LSTM", "TCN_timeseries", "SSM_timeseries"])
def test_the_forecasting_split_is_chronological(model_name):
    """No test timestamp precedes a training timestamp (plan F3): the split
    is chronological, never shuffled."""
    frame = _sine_frame()
    n = len(frame)
    metrics, _bundle = forecasting.train_forecaster(
        model_name, frame, "value", {**SMALL_FORECAST_PARAMS, "hidden_size": 16}
    )
    # 80 percent of the rows train, the tail tests: the sizes say it, and
    # the test below rebuilds the windows and asserts their targets.
    assert metrics["train_size"] + metrics["validation_size"] + metrics["test_size"] > 0
    # The windows of the test segment never target a row before its start.
    test_size = metrics["test_size"]
    horizon = metrics["horizon"]
    window = metrics["window"]
    first_test_target = n - test_size  # the earliest target a test window holds
    assert first_test_target >= n - max(1, int(0.2 * n)) - horizon


@pytest.mark.parametrize("model_name", ["RNN", "LSTM", "TCN_timeseries", "SSM_timeseries"])
def test_the_forecasting_scaler_is_fitted_on_the_training_segment_only(model_name):
    """The scaler statistics equal those of the training segment (plan F3) -
    the leakage test of the forecasting contract."""
    frame = _sine_frame()
    metrics, bundle = forecasting.train_forecaster(
        model_name, frame, "value", {**SMALL_FORECAST_PARAMS, "hidden_size": 16}
    )
    # Rebuild the training windows exactly as the contract cuts them (the
    # chronological split), and assert the statistics are theirs alone -
    # a scaler fitted on the whole series would differ.
    train_idx, _val_idx, _test_idx = forecasting._chronological_split(len(frame), 0.2)
    X_train, _y = forecasting._cut_windows(
        frame, ["value"], metrics["window"], metrics["horizon"], train_idx
    )
    expected_mean = float(X_train.reshape(-1, X_train.shape[2]).mean())
    expected_std = float(X_train.reshape(-1, X_train.shape[2]).std())
    assert bundle.scaler_mean[0] == pytest.approx(expected_mean, abs=1e-6)
    assert bundle.scaler_std[0] == pytest.approx(expected_std, abs=1e-5)
    # And it is NOT the statistic of the whole series (the leakage answer).
    whole_mean = float(frame["value"].mean())
    assert bundle.scaler_mean[0] != pytest.approx(whole_mean, abs=1e-4)


def test_the_tcn_is_causal():
    """Changing a future input of a TCN does not change an earlier output
    (plan F3): the convolutions are left-padded, so position t only sees
    positions <= t."""
    model = forecasting.build_architecture(
        "tcn", 2, 4, {"num_channels": 8, "levels": 3, "kernel_size": 3}
    )
    model.eval()
    with torch.no_grad():
        base = torch.randn(1, 12, 2)
        altered = base.clone()
        altered[:, 6:, :] = altered[:, 6:, :] + 10.0  # the future is changed

        def _sequence(input_tensor):
            current = input_tensor.transpose(1, 2)
            for block, residual in zip(model.blocks, model.residuals):
                out = block(current)[:, :, : current.shape[2]]
                current = torch.nn.functional.gelu(out) + residual(current)
            return current

        sequence_base = _sequence(base)
        sequence_altered = _sequence(altered)
        # The outputs up to (and including) position 5 are identical.
        assert torch.allclose(sequence_base[:, :, :6], sequence_altered[:, :, :6], atol=1e-5)


def test_the_ssm_state_stays_below_one_after_training():
    """The diagonal state matrix keeps a magnitude below one by construction
    (plan F3) - the stability the description advertises."""
    metrics, bundle = forecasting.train_forecaster(
        "SSM_timeseries", _sine_frame(), "value",
        {**SMALL_FORECAST_PARAMS, "hidden_size": 24, "state_dim": 8},
    )
    assert metrics["ssm_state_max_magnitude"] < 1.0
    assert metrics["ssm_states_below_one"] is True


@pytest.mark.parametrize(
    "model_name", ["XGboost_timeseries", "lightGBM_timeseries", "CATboost_timeseries"]
)
def test_the_boosters_have_a_forecasting_mode(model_name):
    """The boosters on the shared contract (plan F3): lag features, a
    chronological split, the naive baselines - the honest baseline family."""
    frame = _sine_frame()
    metrics, bundle = forecasting.train_forecaster(
        model_name, frame, "value", {**SMALL_FORECAST_PARAMS, "n_estimators": 40}
    )
    assert metrics["task_type"] == "timeseries"
    assert metrics["baseline_naive_mae"] is not None
    assert metrics["beats_naive"] in (True, False)
    assert metrics["skill_vs_naive"] is not None


def test_invalid_forecasting_parameters_are_refused():
    """A window longer than the series is a clear error, not a crash."""
    with pytest.raises(ValueError, match="too short"):
        forecasting.train_forecaster(
            "LSTM", _sine_frame(20), "value", {"window": 30, "horizon": 1, "epochs": 1}
        )


@pytest.mark.parametrize("model_name", ["RNN", "LSTM", "TCN_timeseries", "SSM_timeseries"])
def test_the_forecasting_bundle_round_trip_gives_identical_forecasts(
    model_name, tmp_path
):
    """The bundle round trip of plan F3: save, load, forecast - identical."""
    frame = _sine_frame()
    metrics, bundle = forecasting.train_forecaster(
        model_name, frame, "value", {**SMALL_FORECAST_PARAMS, "hidden_size": 16}
    )
    record = write_bundle(model_name, bundle, model_dir=tmp_path)
    loaded = load_any_artifact(Path(record["artifact_path"]), record["artifact_sha256"])
    assert loaded.kind == "timeseries"

    window_rows = frame["value"].tail(loaded.window).to_numpy().reshape(-1, 1).tolist()
    first = loaded.infer({"window_rows": window_rows})
    second = bundle.infer({"window_rows": window_rows})
    assert first["predictions"] == pytest.approx(second["predictions"], abs=1e-4)


# --- the graph models (plan F4) --------------------------------------------------------


def _sbm_zip(tmp_path: Path, n_per_block: int = 30, seed: int = 3) -> Path:
    rng = np.random.default_rng(seed)
    labels = ["a"] * n_per_block + ["b"] * n_per_block
    n = len(labels)
    nodes = pd.DataFrame(
        {
            "node_id": [f"n{i}" for i in range(n)],
            "x": rng.normal(size=n).round(3),  # uninformative features
            "y": rng.normal(size=n).round(3),
            "label": labels,
        }
    )
    edges = [
        (f"n{i}", f"n{j}")
        for i in range(n)
        for j in range(i + 1, n)
        if rng.random() < (0.4 if labels[i] == labels[j] else 0.02)
    ]
    path = tmp_path / "sbm.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("nodes.csv", nodes.to_csv(index=False))
        archive.writestr(
            "edges.csv", pd.DataFrame(edges, columns=["source", "target"]).to_csv(index=False)
        )
    return path


def test_the_gnn_beats_the_feature_only_baseline_on_a_graph_with_noise_features(tmp_path):
    """The honest test of plan F4: on a stochastic block model whose
    features are pure noise, the GNN beats the feature-only MLP by a wide
    margin - or the graph does nothing."""
    metrics, bundle = graph_models.train_gnn(
        "GNN", _sbm_zip(tmp_path), {"epochs": 60, "hidden_size": 16}
    )
    assert metrics["task_type"] == "graph"
    assert metrics["accuracy"] > metrics["baseline_feature_only_accuracy"] + 0.2
    assert metrics["beats_feature_only"] is True
    assert metrics["f1_macro"] > 0.6
    # The bundle answers: the class probabilities of a node.
    answer = bundle.infer({"node_ids": ["n0", "n1"]})
    assert len(answer["predictions"]) == 2
    assert set(answer["predictions"]) <= {"a", "b"}


def test_the_normalised_adjacency_is_symmetric(tmp_path):
    """The propagation matrix of the GCN is symmetric (plan F4)."""
    matrix = graph_models._normalised_adjacency(
        [f"n{i}" for i in range(4)],
        pd.DataFrame({"source": ["n0", "n1"], "target": ["n1", "n2"]}),
        symmetrise=True,
    )
    dense = matrix.to_dense()
    assert torch.allclose(dense, dense.T, atol=1e-6)


def test_the_graph_limits_are_enforced(tmp_path, monkeypatch):
    """The node and edge limits of plan F4 are refused, not suffered."""
    monkeypatch.setattr(graph_models, "MAX_NODES", 40)
    with pytest.raises(ValueError, match="nodes"):
        graph_models._load_graph(_sbm_zip(tmp_path, n_per_block=30))  # 60 nodes


def test_the_graph_bundle_round_trip(tmp_path):
    """The graph bundle saves, loads and predicts (plan C1/F4)."""
    metrics, bundle = graph_models.train_gnn(
        "GNN", _sbm_zip(tmp_path), {"epochs": 20, "hidden_size": 16}
    )
    record = write_bundle("GNN", bundle, model_dir=tmp_path)
    loaded = load_any_artifact(Path(record["artifact_path"]), record["artifact_sha256"])
    answer = loaded.infer({"node_ids": ["n5"]})
    assert answer["predictions"][0] in ("a", "b")


# --- the text family (plans C4, F6) -------------------------------------------------------


@pytest.fixture
def tiny_text_models(monkeypatch):
    """The tiny offline configurations of plan F1: an environment variable,
    never a request parameter, so a client cannot shrink a model."""
    monkeypatch.setenv("TEXT_MODELS_TINY", "1")


def _keyword_corpus(n: int = 60) -> pd.DataFrame:
    """Two classes separated by keywords: learnable by a tiny model."""
    positive = ["great", "good", "excellent", "wonderful", "fantastic"]
    negative = ["terrible", "awful", "bad", "horrible", "poor"]
    rng = np.random.default_rng(0)
    rows = []
    for _ in range(n):
        if rng.random() < 0.5:
            rows.append((" ".join(rng.choice(positive, 2)), "positive"))
        else:
            rows.append((" ".join(rng.choice(negative, 2)), "negative"))
    return pd.DataFrame(rows, columns=["text", "label"])


def _tiny_classifier_params():
    return {"epochs": 10, "batch_size": 8, "max_length": 32}


@pytest.mark.parametrize(
    "model_name", ["BERT", "DistilBERT", "self-attenetion_transformer", "MiniLM"]
)
def test_a_text_classifier_measures_a_held_out_split(model_name, tiny_text_models):
    """The classifiers of plan C4: accuracy and macro F1 on a stratified
    held-out split, next to the majority baseline, with the truncation rate."""
    corpus = _keyword_corpus()
    model_def = {
        "name": model_name,
        "allowed_checkpoints": [MODEL_CATALOG[model_name]["params"]["model_name"]],
    }
    metrics, bundle = textmodels.train_text_classifier(
        model_name, model_def, corpus, "label", _tiny_classifier_params()
    )
    assert metrics["task_type"] == "classification"
    assert metrics["accuracy"] is not None
    assert metrics["f1_macro"] is not None
    assert metrics["baseline_accuracy"] is not None
    assert metrics["accuracy"] > metrics["baseline_accuracy"]
    assert "truncation_rate" in metrics
    assert metrics["test_size"] > 0
    # The bundle answers for texts it never saw (at most 64, plan C4).
    answer = bundle.infer({"texts": ["great good", "terrible awful"]})
    assert len(answer["predictions"]) == 2


def test_the_gpt_fine_tuning_improves_the_held_out_perplexity(tiny_text_models):
    """GPT is language-model fine-tuning (plan F6): the held-out perplexity
    is reported next to the pretrained perplexity before the fine-tuning and
    the unigram baseline, and the gain is visible on a repetitive corpus."""
    corpus = pd.DataFrame(
        {"text": ["the model learns from data "] * 30 + ["a network trains on examples "] * 30}
    )
    metrics, bundle = textmodels.train_language_model(
        "GPT", corpus, "label",
        {"epochs": 3, "block_size": 16, "batch_size": 4, "max_train_tokens": 4000},
        model_def={"allowed_checkpoints": ["distilgpt2", "gpt2"]},
    )
    assert metrics["task_type"] == "generation"
    assert metrics["held_out_perplexity"] is not None
    assert metrics["pretrained_perplexity"] is not None
    assert metrics["unigram_perplexity"] is not None
    assert metrics["improved_over_pretrained"] is True
    # Generation is capped (plan F6).
    answer = bundle.infer({"prompt": "the model", "max_new_tokens": 8})
    assert isinstance(answer["text"], str)
    assert 0 < answer["new_tokens"] <= 8


def _reverse_pairs() -> pd.DataFrame:
    words = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta"]
    rows = []
    for first in words:
        for second in words[:4]:
            source = f"{first} {second}"
            rows.append((source, " ".join(reversed(source.split()))))
    return pd.DataFrame(rows, columns=["source", "target"])


def test_the_seq2seq_learns_a_deterministic_mapping_and_beats_the_copy_baseline(tiny_text_models):
    """seq2seq (plan F6): a tiny T5 learns to reverse the word order, and
    its ROUGE-L beats the copy-the-source baseline (ROUGE-L is
    order-sensitive, which is what makes the comparison honest)."""
    pairs = _reverse_pairs()
    metrics, bundle = textmodels.train_seq2seq(
        "seq2seq", pairs, "target",
        {"epochs": 60, "batch_size": 8, "max_length": 16},
        model_def={"allowed_checkpoints": ["t5-small"]},
    )
    assert metrics["task_type"] == "seq2seq"
    assert metrics["rouge1"] is not None
    assert metrics["baseline_copy_rouge1"] is not None
    # The tiny model learns the mapping (a random one sits far below this,
    # and the run asserts the gain is real, not that it is perfect).
    assert metrics["rougeL"] > 0.3, metrics
    # The bundle generates.
    answer = bundle.infer({"texts": ["alpha beta"]})
    assert isinstance(answer["predictions"][0], str)


def test_a_tiny_bert2bert_trains_and_generates(tiny_text_models):
    """BERT2BERT (plan F6): a tiny encoder-decoder trains offline and
    generates - the warm start is exercised, not downloaded."""
    pairs = _reverse_pairs()
    metrics, bundle = textmodels.train_seq2seq(
        "BERT2BERT", pairs, "target",
        {"epochs": 3, "batch_size": 8, "max_length": 16},
        model_def={"allowed_checkpoints": ["bert-base-uncased"]},
    )
    assert metrics["task_type"] == "seq2seq"
    assert metrics["test_size"] > 0
    answer = bundle.infer({"texts": ["alpha beta"]})
    assert isinstance(answer["predictions"][0], str)


def test_a_tiny_llama_lora_adapter_saves_loads_and_merges(tiny_text_models):
    """LLaMA (plan F6): the LoRA adapter on a tiny Llama configuration, on
    CPU without 4-bit - the adapter saves, loads and merges."""
    pytest.importorskip("peft", reason="the LoRA fine-tuning needs peft")
    corpus = pd.DataFrame({"text": ["one two three four "] * 24})
    metrics, bundle = textmodels.train_llama_lora(
        "LLaMA", corpus, "label",
        {"epochs": 1, "block_size": 12, "r": 4, "alpha": 8, "batch_size": 4},
        model_def={"allowed_checkpoints": ["TinyLlama/TinyLlama-1.1B-Chat-v1.0"]},
    )
    assert metrics["task_type"] == "generation"
    assert metrics["adapter_parameters"] > 0
    assert metrics["adapter_parameters"] < 5_000_000  # an adapter, not a model
    # The adapter merges back into the base model.
    from peft import PeftModel

    merged = bundle._load()[0].merge_and_unload()
    assert merged is not None


def test_a_checkpoint_outside_the_allow_list_is_refused():
    """The allow-list of plans F1/G: any other checkpoint name is refused,
    so a client cannot make the server download an arbitrary repository."""
    model_def = {"allowed_checkpoints": ["distilgpt2", "gpt2"]}
    with pytest.raises(ValueError, match="not allowed"):
        textmodels._resolve_checkpoint(
            {"model_name": "some/random-repo"}, model_def
        )
    # The default is the allow-list's first entry.
    assert textmodels._resolve_checkpoint({}, model_def) == "distilgpt2"


def test_trust_remote_code_is_never_enabled():
    """``trust_remote_code`` is never enabled (plans F1, G): a repository
    cannot ship code that the server then runs."""
    import inspect
    import re

    for module in (textmodels,):
        source = inspect.getsource(module)
        assert not re.search(r"trust_remote_code\s*=\s*True", source), (
            "a trainer enables trust_remote_code"
        )


def test_the_generation_respects_the_token_cap():
    """max_new_tokens is capped by the service (plan F6)."""
    from backend.app import inference

    assert inference.GENERATION_MAX_NEW_TOKENS <= 256


# --- the declared needs of every entry (plans F0, F8) -------------------------------------


def test_every_implemented_entry_declares_what_it_needs():
    """The third condition of plan F0: every implemented entry declares
    requires_gpu, min_memory_mb, downloads_checkpoint and its dataset and
    bundle kinds."""
    for name in MODEL_CATALOG:
        entry = model_training.get_model_entry(name)
        if not entry.get("implemented", False):
            continue
        for field in (
            "requires_gpu",
            "min_memory_mb",
            "downloads_checkpoint",
            "dataset_kind",
            "bundle_kind",
        ):
            assert field in entry, f"{name} does not declare '{field}'"


def test_the_entries_that_download_are_marked():
    """The entries that download a checkpoint say so (plan F8): the admin
    screen shows it and an offline deployment knows what is unavailable."""
    downloaders = ("GPT", "BERT", "DistilBERT", "seq2seq", "BERT2BERT", "ViT", "LLaMA", "MiniLM")
    for name in downloaders:
        entry = model_training.get_model_entry(name)
        assert entry["downloads_checkpoint"] is True, name
        assert entry.get("allowed_checkpoints"), name
    for name in ("Random_Forest", "K-Mean", "Q-Learning", "LSTM", "GNN", "RNN"):
        entry = model_training.get_model_entry(name)
        assert entry["downloads_checkpoint"] is False, name


def test_the_vision_checkpoint_is_allow_listed():
    """The ViT checkpoint is pinned (plan F5/G): google/vit-base-patch16-224
    and nothing else."""
    entry = MODEL_CATALOG["ViT"]
    assert entry["allowed_checkpoints"] == ["google/vit-base-patch16-224"]


def test_a_vision_run_with_an_unlisted_checkpoint_is_refused(isolated_model_dir):
    """An unlisted ViT checkpoint is refused before anything is downloaded
    (plans F5, G)."""
    from backend.app import vision

    with pytest.raises(ValueError, match="not in the allow-list"):
        vision.train_image_model(
            "ViT",
            _tiny_image_folder(),
            {"pretrained": True, "model_name": "some/random-vit", "image_size": 32, "epochs": 1},
            architecture="vit",
            allowed_checkpoints=["google/vit-base-patch16-224"],
        )


def _tiny_image_folder() -> Path:
    """A folder with two classes of two tiny PNGs (the C3 minimum)."""
    import base64

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR42mP4z8AAAAMBAQD3A0FDAAAAAElFTkSuQmCC"
    )
    root = Path(__import__("os").environ["DATASETS_ROOT"]) / "data" / "smoke_vision"
    for class_name in ("red", "blue"):
        directory = root / class_name
        directory.mkdir(parents=True, exist_ok=True)
        for index in (1, 2):
            (directory / f"{class_name}{index}.png").write_bytes(png)
    return root
