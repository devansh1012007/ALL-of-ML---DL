"""The text models: classifiers and the generation family (plans C4 and F6).

Why this module exists
----------------------
The text classifiers reported only a training loss - no accuracy, no
baseline, nothing measured on rows the model never saw - and the entry the
interface called "GPT" trained a *classifier* while advertising generation.
Every checkpoint name came from a client-overridable parameter, which meant
a client could make the server download any repository from the Hugging
Face hub.

The new contract:

* **the classifiers (C4)**: a stratified held-out split; accuracy, macro F1
  and the majority baseline; ``max_length`` exposed with the truncation
  rate; prediction accepts a list of at most 64 texts;
* **GPT (F6)**: causal language-model fine-tuning of distilgpt2 (gpt2 is
  also allow-listed) - the text is packed into blocks of ``block_size``
  tokens; the report has the held-out cross-entropy and perplexity, the
  perplexity of the pretrained model *before* the fine-tuning (so the gain
  is visible), a unigram baseline, and a token cap on the training;
* **seq2seq (F6)**: t5-small (and BERT2BERT warm-started from two BERT
  checkpoints) on source and target columns; held-out loss, ROUGE-1/2/L and
  exact match against the copy-the-source and first-sentence baselines;
  generation uses beam search;
* **LLaMA (F6)**: LoRA fine-tuning of an allow-listed Llama-architecture
  checkpoint; the artifact is the adapter plus the base model id; a GPU
  worker is required and the catalog says so;
* **the checkpoint allow-list (F1/G)**: only the names the catalog declares
  are ever downloaded, anything else is refused, and ``trust_remote_code``
  is never enabled - the best single security action of the plan.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .bundles import register_loader
from .charts import cap_charts

try:
    import torch
    import torch.nn as nn
except ImportError:  # pragma: no cover
    torch = None
    nn = None

try:
    import transformers
    from transformers import (
        AutoConfig,
        AutoModelForCausalLM,
        AutoModelForSeq2SeqLM,
        AutoTokenizer,
        EncoderDecoderModel,
    )
except ImportError:  # pragma: no cover
    transformers = None

# The tests may force tiny offline configurations (plan F1): an environment
# variable, never a request parameter, so a client cannot shrink a model.
TINY_CONFIG_ENV = "TEXT_MODELS_TINY"

# The truncation report and the caps.
DEFAULT_MAX_LENGTH = 128
DEFAULT_BLOCK_SIZE = 128
MAX_PREDICT_TEXTS = 64
MAX_GENERATION_TOKENS = 256
# The token cap of a language-model training (plan F6): the corpus is cut,
# so a training is bounded whatever the dataset size.
DEFAULT_MAX_TRAIN_TOKENS = 200000


def _tiny_enabled() -> bool:
    return os.getenv(TINY_CONFIG_ENV, "").strip() not in ("", "0", "false")


def _require_transformers():
    if transformers is None:
        raise RuntimeError(
            "transformers is not installed: the text models need transformers and torch."
        )


def _resolve_checkpoint(params: Dict[str, Any], model_def: Dict[str, Any]) -> str:
    """The checkpoint of a text run, from the allow-list only (plan F1/G).

    A client can suggest a checkpoint through the catalog parameters; the
    suggestion is only honoured when the catalog allow-lists it. Anything
    else is refused, so nobody can make the server download an arbitrary
    repository from the hub. ``trust_remote_code`` is never enabled.
    """
    allowed = list(model_def.get("allowed_checkpoints") or [])
    if not allowed:
        raise ValueError(
            f"The model '{model_def.get('name', '')}' declares no checkpoint."
        )
    requested = str(params.get("model_name", allowed[0]))
    if requested not in allowed:
        raise ValueError(
            f"The checkpoint '{requested}' is not allowed for this model. "
            f"The allow-list is: {allowed}."
        )
    return requested


def _text_columns(dataset: pd.DataFrame, label_column: str) -> Tuple[str, Optional[str]]:
    """The text column (and the target column of a pairs dataset).

    A text dataset holds one text column named 'text' or the first
    non-numeric, non-label column; a pairs dataset holds 'source' and
    'target' columns.
    """
    columns = [c for c in dataset.columns if c != label_column]
    if "source" in dataset.columns and "target" in dataset.columns:
        return "source", "target"
    if "text" in dataset.columns:
        return "text", None
    for column in columns:
        if not pd.api.types.is_numeric_dtype(dataset[column]):
            return column, None
    raise ValueError(
        "The dataset has no text column: a text dataset needs a 'text' column "
        "(or 'source' and 'target' for the seq2seq models)."
    )


def _stratified_split(frame: pd.DataFrame, test_size: float, seed: int):
    from sklearn.model_selection import train_test_split

    stratify = frame["label"] if frame["label"].nunique() > 1 else None
    return train_test_split(frame, test_size=test_size, random_state=seed, stratify=stratify)


def _rouge(candidate: str, reference: str) -> Dict[str, float]:
    """ROUGE-1/2/L F1 between two texts, computed inline (plan F6).

    No extra dependency: the scores are n-gram overlap F1 and the longest
    common subsequence F1, the definitions of the ROUGE report.
    """
    def tokens(text: str) -> List[str]:
        return text.lower().split()

    def ngrams(values: List[str], n: int) -> set:
        return {tuple(values[i : i + n]) for i in range(len(values) - n + 1)}

    def f1(overlap: int, candidate_size: int, reference_size: int) -> float:
        if candidate_size == 0 or reference_size == 0 or overlap == 0:
            return 0.0
        precision = overlap / candidate_size
        recall = overlap / reference_size
        return 2 * precision * recall / (precision + recall)

    candidate_tokens, reference_tokens = tokens(candidate), tokens(reference)
    scores: Dict[str, float] = {}
    for n, name in ((1, "rouge1"), (2, "rouge2")):
        candidate_ngrams = ngrams(candidate_tokens, n)
        reference_ngrams = ngrams(reference_tokens, n)
        overlap = len(candidate_ngrams & reference_ngrams)
        scores[name] = round(
            f1(overlap, len(candidate_ngrams), len(reference_ngrams)), 4
        )
    # ROUGE-L: the longest common subsequence.
    if not candidate_tokens or not reference_tokens:
        scores["rougeL"] = 0.0
        return scores
    lengths = np.zeros((len(candidate_tokens) + 1, len(reference_tokens) + 1), dtype=int)
    for i, first in enumerate(candidate_tokens, start=1):
        for j, second in enumerate(reference_tokens, start=1):
            lengths[i, j] = lengths[i - 1, j - 1] + 1 if first == second else max(lengths[i - 1, j], lengths[i, j - 1])
    scores["rougeL"] = round(f1(int(lengths[-1, -1]), len(candidate_tokens), len(reference_tokens)), 4)
    return scores


# --- the bundles ---------------------------------------------------------------------


class TextClassifierBundle:
    """The artifact of a text classifier (plans C1, C4)."""

    kind = "text_classifier"
    request_kind = "texts"

    def __init__(self, directory: Path, class_names: List[str], max_length: int):
        self.directory = Path(directory)
        self.class_names = list(class_names)
        self.max_length = max_length
        self._model = None
        self._tokenizer = None

    def _load(self):
        if self._model is None:
            self._model = AutoModelForSequenceClassification.from_pretrained(self.directory)
            self._model.eval()
            self._tokenizer = AutoTokenizer.from_pretrained(self.directory)
        return self._model, self._tokenizer

    def schema(self) -> Dict[str, Any]:
        return {
            "request_kind": self.request_kind,
            "kind": self.kind,
            "classes": [str(c) for c in self.class_names],
            "max_length": self.max_length,
            "max_texts": MAX_PREDICT_TEXTS,
            "output": "the class of each text, with the probabilities",
        }

    def infer(self, request: Dict[str, Any]) -> Dict[str, Any]:
        texts = request.get("texts") or []
        if not texts:
            raise ValueError("The request has no text.")
        if len(texts) > MAX_PREDICT_TEXTS:
            raise ValueError(f"A request may carry at most {MAX_PREDICT_TEXTS} texts.")
        model, tokenizer = self._load()
        tokenized = tokenizer(
            list(texts), truncation=True, max_length=self.max_length, return_tensors="pt"
        )
        with torch.no_grad():
            logits = model(**tokenized).logits
            probabilities = torch.softmax(logits, dim=1).numpy()
        predictions = [str(self.class_names[int(i)]) for i in probabilities.argmax(axis=1)]
        return {
            "predictions": predictions,
            "probabilities": [
                {str(self.class_names[c]): round(float(row[c]), 4) for c in range(len(self.class_names))}
                for row in probabilities
            ],
        }

    # The save side is a directory the trainer filled with save_pretrained;
    # the bundle only records where it is, so ``save`` copies nothing and the
    # manifest covers the files the trainer wrote.
    def save(self, directory: Path) -> None:
        import shutil

        shutil.copytree(self.directory, Path(directory) / "pretrained")
        shutil.rmtree(self.directory, ignore_errors=True)  # the scratch of the trainer

    @classmethod
    def load(cls, directory: Path, manifest: Optional[Dict[str, Any]] = None) -> "TextClassifierBundle":
        payload = json.loads((Path(directory) / "config.json").read_text())
        return cls(
            Path(directory) / "pretrained",
            class_names=payload["class_names"],
            max_length=payload["max_length"],
        )


register_loader("text_classifier", TextClassifierBundle.load)


class TextGenerationBundle:
    """The artifact of a language model (GPT, LLaMA - plans C1, F6)."""

    kind = "text_generation"
    request_kind = "prompt"

    def __init__(self, directory: Path, block_size: int, lora: bool = False, base_model: Optional[str] = None):
        self.directory = Path(directory)
        self.block_size = block_size
        self.lora = lora
        self.base_model = base_model
        self._model = None
        self._tokenizer = None

    def _load(self):
        if self._model is None:
            if self.lora:
                try:
                    from peft import PeftModel
                except ImportError:
                    raise RuntimeError("peft is not installed: this adapter needs it.") from None
                base = AutoModelForCausalLM.from_pretrained(self.base_model)
                self._model = PeftModel.from_pretrained(base, self.directory / "adapter")
            else:
                self._model = AutoModelForCausalLM.from_pretrained(self.directory)
            self._model.eval()
            self._tokenizer = AutoTokenizer.from_pretrained(self.directory)
        return self._model, self._tokenizer

    def schema(self) -> Dict[str, Any]:
        return {
            "request_kind": self.request_kind,
            "kind": self.kind,
            "block_size": self.block_size,
            "max_new_tokens": MAX_GENERATION_TOKENS,
            "lora": self.lora,
            "base_model": self.base_model,
            "output": "the continuation of the prompt, with the token counts",
        }

    def infer(self, request: Dict[str, Any]) -> Dict[str, Any]:
        prompt = request.get("prompt")
        if not prompt:
            raise ValueError("The request has no prompt.")
        max_new_tokens = min(int(request.get("max_new_tokens", 64)), MAX_GENERATION_TOKENS)
        model, tokenizer = self._load()
        tokenized = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=self.block_size)
        prompt_tokens = int(tokenized["input_ids"].shape[1])
        seed = request.get("seed")
        if seed is not None:
            torch.manual_seed(int(seed))
        generation_kwargs = {
            "max_new_tokens": max_new_tokens,
            "do_sample": float(request.get("temperature", 1.0)) > 0,
            "temperature": max(0.05, float(request.get("temperature", 1.0))),
            "top_p": min(1.0, max(0.05, float(request.get("top_p", 0.9)))),
            "pad_token_id": tokenizer.eos_token_id,
        }
        with torch.no_grad():
            output = model.generate(**tokenized, **generation_kwargs)
        text = tokenizer.decode(output[0][prompt_tokens:], skip_special_tokens=True)
        return {
            "text": text,
            "prompt_tokens": prompt_tokens,
            "new_tokens": int(output.shape[1]) - prompt_tokens,
        }

    def save(self, directory: Path) -> None:
        import shutil

        if self.lora:
            shutil.copytree(self.directory, Path(directory) / "adapter")
        else:
            shutil.copytree(self.directory, Path(directory) / "pretrained")
        shutil.rmtree(self.directory, ignore_errors=True)  # the scratch of the trainer

    @classmethod
    def load(cls, directory: Path, manifest: Optional[Dict[str, Any]] = None) -> "TextGenerationBundle":
        payload = json.loads((Path(directory) / "config.json").read_text())
        directory = Path(directory)
        return cls(
            directory / "adapter" if payload.get("lora") else directory / "pretrained",
            block_size=payload["block_size"],
            lora=bool(payload.get("lora")),
            base_model=payload.get("base_model"),
        )


register_loader("text_generation", TextGenerationBundle.load)


class TextSeq2SeqBundle:
    """The artifact of a seq2seq model (t5, BERT2BERT - plans C1, F6)."""

    kind = "text_seq2seq"
    request_kind = "texts"

    def __init__(self, directory: Path, max_length: int, beam_search: int = 4):
        self.directory = Path(directory)
        self.max_length = max_length
        self.beam_search = beam_search
        self._model = None
        self._tokenizer = None

    def _load(self):
        if self._model is None:
            from transformers import AutoModelForSeq2SeqLM

            self._model = AutoModelForSeq2SeqLM.from_pretrained(self.directory)
            self._model.eval()
            self._tokenizer = AutoTokenizer.from_pretrained(self.directory)
        return self._model, self._tokenizer

    def schema(self) -> Dict[str, Any]:
        return {
            "request_kind": self.request_kind,
            "kind": self.kind,
            "max_length": self.max_length,
            "max_texts": MAX_PREDICT_TEXTS,
            "beam_search": self.beam_search,
            "output": "the generated output of each input text",
        }

    def infer(self, request: Dict[str, Any]) -> Dict[str, Any]:
        texts = request.get("texts") or []
        if not texts:
            raise ValueError("The request has no text.")
        if len(texts) > MAX_PREDICT_TEXTS:
            raise ValueError(f"A request may carry at most {MAX_PREDICT_TEXTS} texts.")
        model, tokenizer = self._load()
        tokenized = tokenizer(
            list(texts), truncation=True, max_length=self.max_length, return_tensors="pt", padding=True
        )
        with torch.no_grad():
            output = model.generate(
                **tokenized,
                max_length=self.max_length,
                num_beams=self.beam_search,
            )
        decoded = tokenizer.batch_decode(output, skip_special_tokens=True)
        return {"predictions": decoded}

    def save(self, directory: Path) -> None:
        import shutil

        shutil.copytree(self.directory, Path(directory) / "pretrained")
        shutil.rmtree(self.directory, ignore_errors=True)  # the scratch of the trainer

    @classmethod
    def load(cls, directory: Path, manifest: Optional[Dict[str, Any]] = None) -> "TextSeq2SeqBundle":
        payload = json.loads((Path(directory) / "config.json").read_text())
        return cls(
            Path(directory) / "pretrained",
            max_length=payload["max_length"],
            beam_search=payload.get("beam_search", 4),
        )


register_loader("text_seq2seq", TextSeq2SeqBundle.load)


# --- the shared loaders ----------------------------------------------------------------


def _tiny_classifier(checkpoint: str, n_classes: int):
    """A tiny configuration, built from a config object (plan F1): the tests
    and the offline deployments never download anything."""
    from transformers import (
        AutoConfig,
        AutoModelForSequenceClassification,
        AutoTokenizer,
    )

    base = checkpoint.split("/")[-1]
    if "gpt" in base:
        config = AutoConfig.for_model(
            "gpt2", n_embd=32, n_layer=2, n_head=2, num_labels=n_classes
        )
        model = AutoModelForSequenceClassification.from_config(config)
        tokenizer = AutoTokenizer.from_pretrained("gpt2")
        tokenizer.pad_token = tokenizer.eos_token
        model.config.pad_token_id = tokenizer.pad_token_id
    else:
        config = AutoConfig.for_model(
            "bert" if "bert" in base else "distilbert",
            hidden_size=32,
            num_hidden_layers=2,
            num_attention_heads=2,
            intermediate_size=64,
            num_labels=n_classes,
        )
        model = AutoModelForSequenceClassification.from_config(config)
        tokenizer = AutoTokenizer.from_pretrained(
            "bert-base-uncased" if "bert" in base else "distilbert-base-uncased"
        )
    return model, tokenizer


def _tiny_causal(checkpoint: str):
    from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer

    if "llama" in checkpoint.lower():
        config = AutoConfig.for_model(
            "llama",
            hidden_size=32,
            intermediate_size=64,
            num_hidden_layers=2,
            num_attention_heads=2,
            vocab_size=50257,  # the tiny configuration ships with the gpt2 tokenizer
        )
        model = AutoModelForCausalLM.from_config(config)
        tokenizer = AutoTokenizer.from_pretrained("gpt2")
        tokenizer.pad_token = tokenizer.eos_token
    else:
        config = AutoConfig.for_model("gpt2", n_embd=32, n_layer=2, n_head=2)
        model = AutoModelForCausalLM.from_config(config)
        tokenizer = AutoTokenizer.from_pretrained("gpt2")
        tokenizer.pad_token = tokenizer.eos_token
    return model, tokenizer


def _tiny_seq2seq(checkpoint: str):
    from transformers import AutoConfig, AutoModelForSeq2SeqLM, AutoTokenizer

    if "t5" in checkpoint:
        config = AutoConfig.for_model(
            "t5", d_model=32, d_ff=64, num_layers=2, num_heads=2
        )
        model = AutoModelForSeq2SeqLM.from_config(config)
        tokenizer = AutoTokenizer.from_pretrained("t5-small")
    else:
        # The tiny BERT2BERT: two tiny BERTs warm-started into an
        # EncoderDecoderModel, exactly the construction of the real one.
        from transformers import (
            BertConfig,
            BertLMHeadModel,
            BertModel,
        )

        encoder_config = BertConfig(
            hidden_size=32, num_hidden_layers=2, num_attention_heads=2, intermediate_size=64
        )
        decoder_config = BertConfig(
            hidden_size=32,
            num_hidden_layers=2,
            num_attention_heads=2,
            intermediate_size=64,
            is_decoder=True,
            add_cross_attention=True,
        )
        model = EncoderDecoderModel(
            encoder=BertModel(encoder_config), decoder=BertLMHeadModel(decoder_config)
        )
        tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
    return model, tokenizer


# --- the classifiers (plan C4) -----------------------------------------------------------


def train_text_classifier(
    model_name: str,
    model_def: Dict[str, Any],
    dataset: pd.DataFrame,
    label_column: str,
    params: Dict[str, Any],
) -> Tuple[Dict[str, Any], TextClassifierBundle]:
    """A text classifier measured on a stratified held-out split (plan C4)."""
    _require_transformers()
    checkpoint = _resolve_checkpoint(params, model_def)
    text_column, _ = _text_columns(dataset, label_column)
    if label_column not in dataset.columns:
        raise ValueError(f"The label column '{label_column}' is not in the dataset.")

    frame = pd.DataFrame(
        {"text": dataset[text_column].astype(str), "label": dataset[label_column].astype(str)}
    ).dropna()
    classes = sorted(frame["label"].unique())
    if len(classes) < 2:
        raise ValueError("The label column needs at least two classes.")
    class_index = {name: i for i, name in enumerate(classes)}

    max_length = int(params.get("max_length", DEFAULT_MAX_LENGTH))
    epochs = max(1, int(params.get("epochs", 1)))
    batch_size = max(1, int(params.get("batch_size", 8)))
    learning_rate = float(params.get("learning_rate", 2e-5))
    seed = int(params.get("random_state", 42))
    torch.manual_seed(seed)

    train_frame, test_frame = _stratified_split(frame, 0.2, seed)

    if _tiny_enabled():
        model, tokenizer = _tiny_classifier(checkpoint, len(classes))
        pretrained_loaded = False
    else:
        tokenizer = AutoTokenizer.from_pretrained(checkpoint)
        model = AutoModelForSequenceClassification.from_pretrained(
            checkpoint, num_labels=len(classes)
        )
        pretrained_loaded = True

    def _tokenize(texts):
        return tokenizer(
            list(texts), truncation=True, max_length=max_length, padding=True, return_tensors="pt"
        )

    # The truncation rate of plan C4: how many texts do not fit max_length.
    lengths = [len(tokenizer.encode(text)) for text in train_frame["text"][:500]]
    truncation_rate = float(np.mean([length > max_length for length in lengths])) if lengths else 0.0

    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    loss_curve: List[float] = []
    train_texts = train_frame["text"].tolist()
    train_labels = torch.tensor([class_index[v] for v in train_frame["label"]])
    for epoch in range(epochs):
        model.train()
        order = torch.randperm(len(train_texts))
        total = 0.0
        for start in range(0, len(order), batch_size):
            batch = order[start : start + batch_size]
            tokenized = _tokenize([train_texts[i] for i in batch.tolist()])
            labels = train_labels[batch]
            optimizer.zero_grad()
            logits = model(**tokenized).logits
            loss = nn.functional.cross_entropy(logits, labels)
            loss.backward()
            optimizer.step()
            total += float(loss) * len(batch)
        loss_curve.append(round(total / len(order), 6))

    # The held-out evaluation of plan C4: accuracy, macro F1, the majority
    # baseline - measured on rows the model never trained on.
    model.eval()
    predictions: List[int] = []
    with torch.no_grad():
        texts = test_frame["text"].tolist()
        for start in range(0, len(texts), 32):
            tokenized = _tokenize(texts[start : start + 32])
            predictions.extend(model(**tokenized).logits.argmax(dim=1).tolist())
    truth = [class_index[v] for v in test_frame["label"]]
    accuracy = float(np.mean([p == t for p, t in zip(predictions, truth)]))
    majority = train_frame["label"].value_counts().idxmax()
    baseline = float(np.mean([v == majority for v in test_frame["label"]]))

    from sklearn.metrics import f1_score

    metrics: Dict[str, Any] = {
        "task_type": "classification",
        "model_name": model_name,
        "checkpoint": checkpoint if pretrained_loaded else f"tiny configuration ({checkpoint} family)",
        "classes": len(classes),
        "train_size": int(len(train_frame)),
        "test_size": int(len(test_frame)),
        "accuracy": round(accuracy, 4),
        "f1_macro": round(float(f1_score(truth, predictions, average="macro")), 4),
        "baseline_accuracy": round(baseline, 4),
        "max_length": max_length,
        "truncation_rate": round(truncation_rate, 4),
        "pretrained_weights_used": pretrained_loaded,
        "artifact_kind": TextClassifierBundle.kind,
        "_charts": cap_charts({"loss_curve": loss_curve}),
    }

    import tempfile

    scratch = Path(tempfile.mkdtemp(prefix=f"text_{model_name}_"))
    model.save_pretrained(scratch)
    tokenizer.save_pretrained(scratch)
    bundle = TextClassifierBundle(scratch, class_names=classes, max_length=max_length)
    return metrics, bundle


# --- the language models (plan F6) ---------------------------------------------------------


def _unigram_perplexity(texts: List[str]) -> Optional[float]:
    """The unigram baseline of plan F6: the perplexity of a model that only
    knows the word frequencies of the training corpus."""
    from collections import Counter

    words = [word for text in texts for word in text.split()]
    if len(words) < 20:
        return None
    counts = Counter(words)
    total = len(words)
    log_likelihood = -sum(np.log(counts[word] / total) for word in words)
    return round(float(np.exp(log_likelihood / total)), 4)


def train_language_model(
    model_name: str,
    dataset: pd.DataFrame,
    label_column: str,
    params: Dict[str, Any],
    model_def: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], TextGenerationBundle]:
    """Causal language-model fine-tuning (GPT, plan F6)."""
    _require_transformers()
    model_def = model_def or {"allowed_checkpoints": ["distilgpt2", "gpt2"]}
    checkpoint = _resolve_checkpoint(params, model_def)
    text_column, _ = _text_columns(dataset, label_column)

    block_size = int(params.get("block_size", DEFAULT_BLOCK_SIZE))
    epochs = max(1, int(params.get("epochs", 1)))
    batch_size = max(1, int(params.get("batch_size", 4)))
    learning_rate = float(params.get("learning_rate", 2e-5))
    max_train_tokens = int(params.get("max_train_tokens", DEFAULT_MAX_TRAIN_TOKENS))
    seed = int(params.get("random_state", 42))
    torch.manual_seed(seed)

    texts = dataset[text_column].dropna().astype(str).tolist()
    if len(texts) < 4:
        raise ValueError("The corpus needs at least four texts.")

    if _tiny_enabled():
        model, tokenizer = _tiny_causal(checkpoint)
        pretrained_loaded = False
    else:
        tokenizer = AutoTokenizer.from_pretrained(checkpoint)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        model = AutoModelForCausalLM.from_pretrained(checkpoint)
        pretrained_loaded = True

    # The held-out split (90/10 by example, plan F6), then the packing of
    # the training texts into blocks of block_size tokens.
    split = max(1, int(len(texts) * 0.9))
    train_texts, held_out_texts = texts[:split], texts[split:]

    def _pack(sample_texts):
        ids: List[int] = []
        for text in sample_texts:
            ids.extend(tokenizer.encode(text))
            ids.extend([tokenizer.eos_token_id])
            if len(ids) >= max_train_tokens:
                break  # the token cap of plan F6 bounds the training
        blocks = []
        for start in range(0, len(ids) - block_size, block_size):
            blocks.append(ids[start : start + block_size])
        return blocks

    blocks = _pack(train_texts)
    if not blocks:
        raise ValueError(
            f"The corpus is too short for block_size={block_size}: no complete "
            "block of tokens fits."
        )

    def _held_out_perplexity(eval_model) -> Optional[float]:
        if not held_out_texts:
            return None
        eval_model.eval()
        total_loss, total_tokens = 0.0, 0
        with torch.no_grad():
            for text in held_out_texts:
                ids = tokenizer.encode(text)
                for start in range(0, max(1, len(ids) - 1), block_size):
                    window = ids[start : start + block_size]
                    if len(window) < 2:
                        continue
                    input_ids = torch.tensor([window])
                    loss = eval_model(input_ids, labels=input_ids).loss
                    total_loss += float(loss) * (len(window) - 1)
                    total_tokens += len(window) - 1
        if total_tokens == 0:
            return None
        return round(float(np.exp(total_loss / total_tokens)), 4)

    # The pretrained perplexity before the fine-tuning (plan F6): the gain
    # is what the number means.
    pretrained_perplexity = _held_out_perplexity(model)

    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    loss_curve: List[float] = []
    tensors = torch.tensor(blocks, dtype=torch.long)
    for epoch in range(epochs):
        model.train()
        order = torch.randperm(len(tensors))
        total = 0.0
        for start in range(0, len(order), batch_size):
            batch = tensors[order[start : start + batch_size]]
            optimizer.zero_grad()
            loss = model(batch, labels=batch).loss
            loss.backward()
            optimizer.step()
            total += float(loss) * len(batch)
        loss_curve.append(round(total / len(order), 6))

    held_out_perplexity = _held_out_perplexity(model)
    unigram = _unigram_perplexity(train_texts)

    metrics: Dict[str, Any] = {
        "task_type": "generation",
        "model_name": model_name,
        "checkpoint": checkpoint if pretrained_loaded else f"tiny configuration ({checkpoint} family)",
        "train_blocks": len(blocks),
        "train_tokens": int(len(blocks) * block_size),
        "held_out_perplexity": held_out_perplexity,
        "pretrained_perplexity": pretrained_perplexity,
        "unigram_perplexity": unigram,
        "improved_over_pretrained": (
            None
            if held_out_perplexity is None or pretrained_perplexity is None
            else bool(held_out_perplexity <= pretrained_perplexity)
        ),
        "pretrained_weights_used": pretrained_loaded,
        "artifact_kind": TextGenerationBundle.kind,
        "_charts": cap_charts({"loss_curve": loss_curve}),
    }

    import tempfile

    scratch = Path(tempfile.mkdtemp(prefix=f"text_lm_{model_name}_"))
    model.save_pretrained(scratch)
    tokenizer.save_pretrained(scratch)
    bundle = TextGenerationBundle(scratch, block_size=block_size)
    return metrics, bundle


# --- the seq2seq family (plan F6) -----------------------------------------------------------


def train_seq2seq(
    model_name: str,
    dataset: pd.DataFrame,
    label_column: str,
    params: Dict[str, Any],
    model_def: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], TextSeq2SeqBundle]:
    """Sequence-to-sequence fine-tuning (t5, BERT2BERT - plan F6)."""
    _require_transformers()
    model_def = model_def or {"allowed_checkpoints": ["t5-small"]}
    checkpoint = _resolve_checkpoint(params, model_def)
    source_column, target_column = _text_columns(dataset, label_column)
    if target_column is None:
        raise ValueError(
            "The seq2seq models need a pairs dataset: a 'source' and a 'target' column."
        )

    max_length = int(params.get("max_length", DEFAULT_MAX_LENGTH))
    epochs = max(1, int(params.get("epochs", 1)))
    batch_size = max(1, int(params.get("batch_size", 8)))
    learning_rate = float(params.get("learning_rate", 2e-5))
    task_prefix = str(params.get("task_prefix", ""))
    seed = int(params.get("random_state", 42))
    torch.manual_seed(seed)

    frame = pd.DataFrame(
        {
            "source": dataset[source_column].astype(str),
            "target": dataset[target_column].astype(str),
        }
    ).dropna()
    train_frame, test_frame = frame.iloc[: max(3, int(len(frame) * 0.9))], frame.iloc[
        max(3, int(len(frame) * 0.9)) :
    ]

    if _tiny_enabled():
        model, tokenizer = _tiny_seq2seq(checkpoint)
        pretrained_loaded = False
    else:
        tokenizer = AutoTokenizer.from_pretrained(checkpoint)
        if model_name == "BERT2BERT":
            # Two BERT checkpoints warm-started into an encoder-decoder
            # (plan F6): the special tokens have to be set, a well-known
            # source of silent failure.
            model = EncoderDecoderModel.from_encoder_decoder_pretrained(
                checkpoint, checkpoint
            )
            model.config.decoder_start_token_id = tokenizer.cls_token_id
            model.config.eos_token_id = tokenizer.sep_token_id
            model.config.pad_token_id = tokenizer.pad_token_id
            model.config.vocab_size = model.config.encoder.vocab_size
        else:
            model = AutoModelForSeq2SeqLM.from_pretrained(checkpoint)
        pretrained_loaded = True

    def _encode(sources, targets):
        inputs = tokenizer(
            [task_prefix + str(s) for s in sources],
            truncation=True,
            max_length=max_length,
            padding=True,
            return_tensors="pt",
        )
        labels = tokenizer(
            [str(t) for t in targets],
            truncation=True,
            max_length=max_length,
            padding=True,
            return_tensors="pt",
        )
        return inputs, labels

    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    loss_curve: List[float] = []
    sources = train_frame["source"].tolist()
    targets = train_frame["target"].tolist()
    for epoch in range(epochs):
        model.train()
        order = np.random.default_rng(seed + epoch).permutation(len(sources))
        total = 0.0
        for start in range(0, len(order), batch_size):
            batch = order[start : start + batch_size]
            inputs, labels = _encode(
                [sources[i] for i in batch], [targets[i] for i in batch]
            )
            optimizer.zero_grad()
            # The labels of the padding positions are masked out.
            label_ids = labels["input_ids"].clone()
            label_ids[label_ids == tokenizer.pad_token_id] = -100
            loss = model(**inputs, labels=label_ids).loss
            loss.backward()
            optimizer.step()
            total += float(loss) * len(batch)
        loss_curve.append(round(total / max(1, len(order)), 6))

    # The held-out evaluation of plan F6: ROUGE-1/2/L and exact match,
    # against the copy-the-source and first-sentence baselines.
    model.eval()
    predicted: List[str] = []
    test_sources = test_frame["source"].tolist()
    test_targets = test_frame["target"].tolist()
    with torch.no_grad():
        for start in range(0, len(test_sources), 16):
            batch_sources = test_sources[start : start + 16]
            tokenized = tokenizer(
                [task_prefix + str(s) for s in batch_sources],
                truncation=True,
                max_length=max_length,
                padding=True,
                return_tensors="pt",
            )
            output = model.generate(**tokenized, max_length=max_length, num_beams=4)
            predicted.extend(tokenizer.batch_decode(output, skip_special_tokens=True))

    if predicted:
        rouge_scores = [
            _rouge(candidate, reference) for candidate, reference in zip(predicted, test_targets)
        ]
        mean_rouge = {
            key: round(float(np.mean([score[key] for score in rouge_scores])), 4)
            for key in ("rouge1", "rouge2", "rougeL")
        }
        copy_scores = [
            _rouge(source, reference) for source, reference in zip(test_sources, test_targets)
        ]
        copy_baseline = {
            key: round(float(np.mean([score[key] for score in copy_scores])), 4)
            for key in ("rouge1", "rouge2", "rougeL")
        }
        exact_match = round(
            float(np.mean([p.strip() == str(t).strip() for p, t in zip(predicted, test_targets)])), 4
        )
    else:
        mean_rouge = {"rouge1": None, "rouge2": None, "rougeL": None}
        copy_baseline = {"rouge1": None, "rouge2": None, "rougeL": None}
        exact_match = None

    metrics: Dict[str, Any] = {
        "task_type": "seq2seq",
        "model_name": model_name,
        "checkpoint": checkpoint if pretrained_loaded else f"tiny configuration ({checkpoint} family)",
        "train_size": int(len(train_frame)),
        "test_size": int(len(test_frame)),
        **mean_rouge,
        "exact_match": exact_match,
        "baseline_copy_rouge1": copy_baseline["rouge1"],
        "loss_curve_last": loss_curve[-1] if loss_curve else None,
        "pretrained_weights_used": pretrained_loaded,
        "artifact_kind": TextSeq2SeqBundle.kind,
        "_charts": cap_charts({"loss_curve": loss_curve}),
    }

    import tempfile

    scratch = Path(tempfile.mkdtemp(prefix=f"text_seq2seq_{model_name}_"))
    model.save_pretrained(scratch)
    tokenizer.save_pretrained(scratch)
    bundle = TextSeq2SeqBundle(scratch, max_length=max_length)
    return metrics, bundle


# --- LLaMA (plan F6) --------------------------------------------------------------------------


def train_llama_lora(
    model_name: str,
    dataset: pd.DataFrame,
    label_column: str,
    params: Dict[str, Any],
    model_def: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], TextGenerationBundle]:
    """LoRA fine-tuning of a Llama-architecture checkpoint (plan F6).

    Requires a GPU worker; on a CPU-only deployment the catalog marks the
    entry unavailable. The tests use a tiny Llama configuration with LoRA
    on CPU (without 4-bit), which checks that the adapter saves, loads and
    merges.
    """
    _require_transformers()
    model_def = model_def or {
        "allowed_checkpoints": ["TinyLlama/TinyLlama-1.1B-Chat-v1.0"]
    }
    checkpoint = _resolve_checkpoint(params, model_def)
    text_column, _ = _text_columns(dataset, label_column)

    if not _tiny_enabled():
        if not torch.cuda.is_available():
            raise RuntimeError(
                "LLaMA fine-tuning needs a GPU worker; this deployment has none. "
                "The entry is unavailable on CPU-only deployments by design."
            )

    try:
        from peft import LoraConfig, get_peft_model
    except ImportError:
        raise RuntimeError("peft is not installed: the LoRA fine-tuning needs it.") from None

    r = int(params.get("r", 8))
    alpha = int(params.get("alpha", 16))
    lora_dropout = float(params.get("lora_dropout", 0.05))
    block_size = int(params.get("block_size", DEFAULT_BLOCK_SIZE))
    epochs = max(1, int(params.get("epochs", 1)))
    learning_rate = float(params.get("learning_rate", 2e-4))
    max_train_tokens = int(params.get("max_train_tokens", 100000))
    seed = int(params.get("random_state", 42))
    torch.manual_seed(seed)

    texts = dataset[text_column].dropna().astype(str).tolist()
    if len(texts) < 4:
        raise ValueError("The corpus needs at least four texts.")

    if _tiny_enabled():
        model, tokenizer = _tiny_causal("llama")
    else:
        tokenizer = AutoTokenizer.from_pretrained(checkpoint)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        # 4-bit loading exists only on CUDA (plan F6).
        if torch.cuda.is_available():
            try:
                from transformers import BitsAndBytesConfig

                model = AutoModelForCausalLM.from_pretrained(
                    checkpoint,
                    quantization_config=BitsAndBytesConfig(load_in_4bit=True),
                    device_map="auto",
                )
            except Exception:
                model = AutoModelForCausalLM.from_pretrained(checkpoint, device_map="auto")
        else:
            model = AutoModelForCausalLM.from_pretrained(checkpoint)

    lora_config = LoraConfig(
        r=r,
        lora_alpha=alpha,
        lora_dropout=lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "v_proj"],
    )
    model = get_peft_model(model, lora_config)

    # The packing of plan F6, capped by max_train_tokens.
    ids: List[int] = []
    for text in texts:
        ids.extend(tokenizer.encode(text))
        if len(ids) >= max_train_tokens:
            break
    blocks = [ids[start : start + block_size] for start in range(0, len(ids) - block_size, block_size)]
    if not blocks:
        raise ValueError(f"The corpus is too short for block_size={block_size}.")

    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=learning_rate
    )
    loss_curve: List[float] = []
    tensors = torch.tensor(blocks, dtype=torch.long)
    for epoch in range(epochs):
        order = torch.randperm(len(tensors))
        total = 0.0
        for start in range(0, len(order), max(1, int(params.get("batch_size", 2)))):
            batch = tensors[order[start : start + max(1, int(params.get("batch_size", 2)))]]
            optimizer.zero_grad()
            loss = model(batch, labels=batch).loss
            loss.backward()
            optimizer.step()
            total += float(loss) * len(batch)
        loss_curve.append(round(total / len(order), 6))

    # The artifact is the adapter plus the base model id (plan F6): a few
    # megabytes instead of gigabytes, which also keeps the storage quota
    # small.
    import tempfile

    adapter_dir = Path(tempfile.mkdtemp(prefix="text_lora_"))
    model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)

    metrics: Dict[str, Any] = {
        "task_type": "generation",
        "model_name": model_name,
        "checkpoint": checkpoint,
        "lora_r": r,
        "lora_alpha": alpha,
        "train_blocks": len(blocks),
        "train_tokens": int(len(blocks) * block_size),
        "loss_curve_last": loss_curve[-1] if loss_curve else None,
        "adapter_parameters": int(
            sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
        ),
        "artifact_kind": TextGenerationBundle.kind,
        "_charts": cap_charts({"loss_curve": loss_curve}),
    }
    bundle = TextGenerationBundle(
        adapter_dir, block_size=block_size, lora=True, base_model=checkpoint
    )
    return metrics, bundle
