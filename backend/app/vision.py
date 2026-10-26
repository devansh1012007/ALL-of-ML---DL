"""The vision models with an honest evaluation (plans C3 and F5).

Why this module exists
----------------------
The old ResNet trainer reported an accuracy accumulated over its own
training batches - the number a memorising model maximises - had no
validation split, used the deprecated ``pretrained=`` argument, and its
artifact could not predict (the transform the training used travelled
nowhere with the weights).

The new contract:

* a **stratified train/validation split** built from the ``ImageFolder``
  sample list; the training transform has flips and crops, the validation
  transform has none - augmentation on the validation rows would be a leak;
* the reported numbers are the **validation** accuracy, per-class precision
  and recall, the confusion matrix, the majority-class baseline, and the
  top-3 accuracy when there are more than five classes; early stopping on
  the validation loss; optional class-weighted loss;
* the ``weights=`` API replaces the deprecated ``pretrained=``, and when the
  checkpoint cannot be downloaded the trainer falls back to random weights
  and **says so in the report**;
* the artifact is a bundle: the weights, the class names and the exact
  transform configuration - the transform must travel with the weights or a
  prediction would silently use a different preprocessing than the training;
* predict is an image upload of at most 5 MB, decoded with Pillow's
  decompression-bomb guard on (plan C3);
* ViT (plan F5) reuses this contract: the allow-listed checkpoint
  ``google/vit-base-patch16-224`` with a new head, a linear probe by
  default (``freeze_backbone``), and a tiny offline configuration when the
  weights are not asked for.
"""

from __future__ import annotations

import json
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
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

# The caps of plan C3: the upload size, and the default image size.
MAX_IMAGE_BYTES = 5 * 1024 * 1024
DEFAULT_IMAGE_SIZE = 224
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]
# The patience of the early stopping on the validation loss (plan C3).
PATIENCE = 3


def _torchvision():
    try:
        from torchvision import transforms
        from torchvision.datasets import ImageFolder
        from torchvision.models import resnet18, resnet50

        return transforms, ImageFolder, resnet18, resnet50
    except ImportError:
        return None, None, None, None


def _build_model(architecture: str, n_classes: int, pretrained: bool, image_size: int):
    """The network of a vision run: a ResNet or a ViT, with the ``weights=``
    API (plan C3) and a random-weights fallback that says so."""
    download_note = None
    if architecture in ("resnet18", "resnet50"):
        _, _, resnet18, resnet50 = _torchvision()
        factory = resnet18 if architecture == "resnet18" else resnet50
        if pretrained:
            try:
                from torchvision.models import ResNet18_Weights, ResNet50_Weights

                weights = ResNet18_Weights.IMAGENET1K_V1 if architecture == "resnet18" else ResNet50_Weights.IMAGENET1K_V1
                model = factory(weights=weights)
                pretrained_loaded = True
            except Exception:
                # The checkpoint cannot be downloaded: random weights, and
                # the report says so instead of pretending (plan C3).
                model = factory(weights=None)
                pretrained_loaded = False
                download_note = (
                    "The pretrained checkpoint could not be downloaded; the "
                    "network was trained from random weights."
                )
        else:
            model = factory(weights=None)
            pretrained_loaded = False
        model.fc = nn.Linear(model.fc.in_features, n_classes)
        return model, pretrained_loaded, download_note

    # The ViT (plan F5): the allow-listed checkpoint with a new head, or a
    # tiny configuration when the weights are not asked for (the tests and
    # the offline deployments).
    from transformers import ViTConfig, ViTForImageClassification

    if pretrained:
        checkpoint = "google/vit-base-patch16-224"
        try:
            model = ViTForImageClassification.from_pretrained(checkpoint, num_labels=n_classes, ignore_mismatched_sizes=True)
            pretrained_loaded = True
        except Exception:
            model = ViTForImageClassification(_tiny_vit_config(n_classes, image_size))
            pretrained_loaded = False
            download_note = (
                "The ViT checkpoint could not be downloaded; a tiny "
                "configuration was trained from random weights."
            )
        return model, pretrained_loaded, download_note
    model = ViTForImageClassification(_tiny_vit_config(n_classes, image_size))
    return model, False, None


def _tiny_vit_config(n_classes: int, image_size: int) -> "ViTConfig":
    """A tiny ViT built from a config object: no download, seconds on CPU
    (the test configuration of plan F5)."""
    from transformers import ViTConfig

    patch = 8 if image_size % 8 == 0 else 4
    return ViTConfig(
        image_size=image_size,
        patch_size=patch,
        num_channels=3,
        hidden_size=32,
        num_hidden_layers=2,
        num_attention_heads=2,
        intermediate_size=64,
        num_labels=n_classes,
    )


def _transforms(image_size: int):
    """The train and validation transforms of plan C3: augmentation on the
    training rows only, never on the validation rows."""
    from torchvision import transforms

    mean, std = IMAGENET_MEAN, IMAGENET_STD
    train = transforms.Compose(
        [
            transforms.Resize((image_size, image_size)),
            transforms.RandomHorizontalFlip(),
            transforms.RandomCrop(image_size, padding=max(2, image_size // 16)),
            transforms.ToTensor(),
            transforms.Normalize(mean, std),
        ]
    )
    validation = transforms.Compose(
        [
            transforms.Resize((image_size, image_size)),
            transforms.ToTensor(),
            transforms.Normalize(mean, std),
        ]
    )
    return train, validation


# --- the bundle -------------------------------------------------------------------


class VisionBundle:
    """The artifact of a vision run (plans C1, C3): the weights, the class
    names and the exact transform configuration."""

    kind = "vision"
    request_kind = "image"

    def __init__(self, model: Any, architecture: str, class_names: List[str], image_size: int):
        self.model = model
        self.architecture = architecture
        self.class_names = list(class_names)
        self.image_size = image_size

    def schema(self) -> Dict[str, Any]:
        return {
            "request_kind": self.request_kind,
            "kind": self.kind,
            "classes": [str(c) for c in self.class_names],
            "image_size": self.image_size,
            "max_upload_bytes": MAX_IMAGE_BYTES,
            "output": "the class of each uploaded image, with the probabilities",
        }

    def _load_image(self, content: bytes):
        if Image is None:
            raise RuntimeError("Pillow is not installed")
        # The decompression-bomb guard of Pillow stays on (plan C3).
        image = Image.open(__import__("io").BytesIO(content))
        image = image.convert("RGB")
        return image

    def infer(self, request: Dict[str, Any]) -> Dict[str, Any]:
        images = request.get("images") or []
        if not images:
            raise ValueError("The request has no image.")
        if len(images) > 16:
            raise ValueError("A request may carry at most 16 images.")
        from torchvision import transforms

        transform = transforms.Compose(
            [
                transforms.Resize((self.image_size, self.image_size)),
                transforms.ToTensor(),
                transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
            ]
        )
        tensors = []
        for content in images:
            if len(content) > MAX_IMAGE_BYTES:
                raise ValueError(
                    f"An image is {len(content)} bytes; the limit is {MAX_IMAGE_BYTES}."
                )
            tensors.append(transform(self._load_image(content)))
        batch = torch.stack(tensors)
        self.model.eval()
        with torch.no_grad():
            logits = self.model(batch)
            if hasattr(logits, "logits"):  # the HF ViT answers an object
                logits = logits.logits
            probabilities = torch.softmax(logits, dim=1).numpy()
        predictions = [self.class_names[int(i)] for i in probabilities.argmax(axis=1)]
        return {
            "predictions": predictions,
            "probabilities": [
                {str(self.class_names[c]): round(float(row[c]), 4) for c in range(len(self.class_names))}
                for row in probabilities
            ],
        }

    def save(self, directory: Path) -> None:
        directory = Path(directory)
        torch.save(self.model.state_dict(), directory / "model.pt")
        (directory / "config.json").write_text(
            json.dumps(
                {
                    "kind": self.kind,
                    "architecture": self.architecture,
                    "class_names": [str(c) for c in self.class_names],
                    "image_size": self.image_size,
                }
            )
        )

    @classmethod
    def load(cls, directory: Path, manifest: Optional[Dict[str, Any]] = None) -> "VisionBundle":
        directory = Path(directory)
        if torch is None:
            raise RuntimeError("torch is not installed")
        config = json.loads((directory / "config.json").read_text())
        model, _, _ = _build_model(
            config["architecture"], len(config["class_names"]), pretrained=False, image_size=config["image_size"]
        )
        model.load_state_dict(torch.load(directory / "model.pt", map_location="cpu"))
        model.eval()
        return cls(
            model=model,
            architecture=config["architecture"],
            class_names=config["class_names"],
            image_size=config["image_size"],
        )


register_loader("vision", VisionBundle.load)


# --- the trainer --------------------------------------------------------------------


def train_image_model(
    model_name: str,
    dataset_path: Path,
    params: Dict[str, Any],
    architecture: str = "resnet18",
    allowed_checkpoints: Optional[List[str]] = None,
) -> Tuple[Dict[str, Any], VisionBundle]:
    """Train an image classifier with the honest evaluation of plan C3."""
    if torch is None:
        raise RuntimeError("torch is not installed: the vision models need torch")
    _, ImageFolder, _, _ = _torchvision()
    if ImageFolder is None:
        raise RuntimeError("torchvision is not installed: the vision models need it")

    dataset_path = Path(dataset_path)
    if not dataset_path.exists() or not dataset_path.is_dir():
        raise FileNotFoundError(f"The image folder '{dataset_path.name}' was not found.")

    image_size = int(params.get("image_size", DEFAULT_IMAGE_SIZE))
    epochs = max(1, int(params.get("epochs", 3)))
    batch_size = max(1, int(params.get("batch_size", 16)))
    learning_rate = float(params.get("learning_rate", 1e-3))
    freeze_backbone = bool(params.get("freeze_backbone", False)) if architecture == "vit" else False
    class_weighted = str(params.get("class_weight", "none"))
    pretrained = bool(params.get("pretrained", False))
    random_state = int(params.get("random_state", 42))
    torch.manual_seed(random_state)

    # The checkpoint allow-list of plans F1/G is enforced BEFORE anything is
    # built or downloaded: a client cannot make the server fetch an
    # arbitrary repository from the hub.
    if architecture == "vit" and allowed_checkpoints:
        checkpoint = str(params.get("model_name", allowed_checkpoints[0]))
        if checkpoint not in allowed_checkpoints:
            raise ValueError(
                f"The checkpoint '{checkpoint}' is not in the allow-list "
                f"{allowed_checkpoints} of this model."
            )

    # The sample list of the ImageFolder drives the stratified split of
    # plan C3: two images per class minimum, or the split cannot stratify.
    from sklearn.model_selection import train_test_split

    full = ImageFolder(str(dataset_path))
    class_names = full.classes
    n_classes = len(class_names)
    if n_classes < 2:
        raise ValueError("The image folder needs at least two classes (one subdirectory each).")
    samples = full.samples
    labels = [target for _, target in samples]
    # A real dataset gets the usual 80/20; a tiny one (the two images per
    # class of the tests) needs half of each class on each side, or the
    # stratified split cannot place every class in both parts.
    validation_fraction = 0.2 if len(samples) >= 20 else 0.5
    train_paths, val_paths = train_test_split(
        samples, test_size=validation_fraction, stratify=labels, random_state=random_state
    )

    model, pretrained_loaded, download_note = _build_model(
        architecture, n_classes, pretrained, image_size
    )

    if freeze_backbone and architecture == "vit":
        for parameter in model.vit.parameters():
            parameter.requires_grad = False
        # The classifier head stays trainable: that is the linear probe.

    train_transform, val_transform = _transforms(image_size)

    class _SplitDataset(torch.utils.data.Dataset):
        def __init__(self, items, transform):
            self.items = items
            self.transform = transform

        def __len__(self):
            return len(self.items)

        def __getitem__(self, index):
            path, target = self.items[index]
            image = Image.open(path).convert("RGB")
            return self.transform(image), target

    train_dataset = _SplitDataset(train_paths, train_transform)
    val_dataset = _SplitDataset(val_paths, val_transform)
    train_loader = torch.utils.data.DataLoader(
        train_dataset, batch_size=min(batch_size, max(1, len(train_dataset))), shuffle=True
    )
    val_loader = torch.utils.data.DataLoader(
        val_dataset, batch_size=min(batch_size, max(1, len(val_dataset))), shuffle=False
    )

    # The class-weighted loss of plan C3: the rare classes stop being
    # invisible to the optimisation.
    weights = None
    if class_weighted == "balanced":
        counts = np.bincount([target for _, target in train_paths], minlength=n_classes)
        weights = torch.tensor(
            counts.sum() / np.maximum(counts, 1) / n_classes, dtype=torch.float32
        )

    optimizer = torch.optim.Adam(
        [p for p in model.parameters() if p.requires_grad], lr=learning_rate
    )
    loss_function = nn.CrossEntropyLoss(weight=weights)

    best_val_loss = float("inf")
    best_state = None
    stale = 0
    loss_curve: List[float] = []
    for epoch in range(epochs):
        model.train()
        for images, targets in train_loader:
            optimizer.zero_grad()
            logits = model(images)
            if hasattr(logits, "logits"):
                logits = logits.logits
            loss = loss_function(logits, targets)
            loss.backward()
            optimizer.step()
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for images, targets in val_loader:
                logits = model(images)
                if hasattr(logits, "logits"):
                    logits = logits.logits
                val_loss += float(loss_function(logits, targets)) * len(targets)
        val_loss /= max(1, len(val_dataset))
        loss_curve.append(round(val_loss, 6))
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            stale = 0
        else:
            stale += 1
            if stale >= PATIENCE:
                break  # early stopping on the validation loss (plan C3)
    if best_state is not None:
        model.load_state_dict(best_state)

    # The validation metrics of plan C3: accuracy, per-class precision and
    # recall, the confusion matrix, the majority baseline, top-3 when there
    # are more than five classes.
    model.eval()
    all_probabilities: List[np.ndarray] = []
    all_targets: List[int] = []
    with torch.no_grad():
        for images, targets in val_loader:
            logits = model(images)
            if hasattr(logits, "logits"):
                logits = logits.logits
            probabilities = torch.softmax(logits, dim=1).numpy()
            all_probabilities.extend(probabilities)
            all_targets.extend(targets.numpy().tolist())
    probabilities = np.asarray(all_probabilities)
    val_targets = np.asarray(all_targets)
    predictions = probabilities.argmax(axis=1)
    accuracy = float((predictions == val_targets).mean()) if len(val_targets) else None

    from sklearn.metrics import confusion_matrix, precision_score, recall_score

    majority = pd.Series([t for _, t in train_paths]).value_counts().idxmax()
    metrics: Dict[str, Any] = {
        "task_type": "classification",
        "model_name": model_name,
        "architecture": architecture,
        "classes": n_classes,
        "train_size": int(len(train_paths)),
        "test_size": int(len(val_paths)),
        "epochs_run": len(loss_curve),
        "val_accuracy": round(accuracy, 4) if accuracy is not None else None,
        "baseline_accuracy": round(float((val_targets == majority).mean()), 4)
        if len(val_targets)
        else None,
        "precision_per_class": {
            str(class_names[c]): round(float(precision_score(val_targets == c, predictions == c, zero_division=0)), 4)
            for c in range(n_classes)
        },
        "recall_per_class": {
            str(class_names[c]): round(float(recall_score(val_targets == c, predictions == c, zero_division=0)), 4)
            for c in range(n_classes)
        },
        "confusion_matrix": confusion_matrix(val_targets, predictions, labels=list(range(n_classes))).tolist(),
        "pretrained_weights_used": bool(pretrained_loaded),
        "artifact_kind": VisionBundle.kind,
    }
    if download_note:
        metrics["pretrained_note"] = download_note
    if n_classes > 5 and len(val_targets):
        top3_classes = np.argsort(probabilities, axis=1)[:, -3:]
        metrics["top3_accuracy"] = round(
            float(np.mean([val_targets[i] in top3_classes[i] for i in range(len(val_targets))])), 4
        )

    metrics["_charts"] = cap_charts(
        {
            "loss_curve": loss_curve,
            "confusion": {
                "labels": [str(c) for c in class_names],
                "matrix": metrics["confusion_matrix"],
            },
        }
    )

    bundle = VisionBundle(
        model=model, architecture=architecture, class_names=class_names, image_size=image_size
    )
    return metrics, bundle

