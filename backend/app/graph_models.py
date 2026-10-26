"""The graph models: semi-supervised node classification (plan F4).

Why this module exists
----------------------
The GNN entry was a placeholder that trained a plain MLP on the node
features and called itself a graph model. The graph is the signal, and the
honest test of whether the model uses it is a second baseline: an MLP with
the same budget on the features alone.

The implementation is deliberately **plain torch** (about 40 lines per
layer): PyTorch Geometric has fragile wheels across CUDA versions and a
heavy install; a GCN over a sparse, symmetrically normalised adjacency with
self-loops is all the entry advertises. Adopt PyG later only if scale
demands it.

* the dataset is a zip of ``nodes.csv`` (a node id, feature columns, a
  label) and ``edges.csv`` (source, target, optional weight), with an option
  to symmetrise;
* the split is stratified over the nodes (60/20/20 train/validation/test
  masks); the loss uses the labels of the training nodes only;
* the metrics are the test accuracy and macro F1, the majority baseline,
  and the **feature-only MLP baseline** - the honest test of whether the
  graph helps;
* the artifact is a ``GraphBundle`` with the weights, the configuration and
  the graph tensors; predict takes node ids and returns the class
  probabilities (transductive: the new node has to be in the graph).
* the catalog's ``batch_size`` is gone: this is full-batch, and advertising
  a batch size would be false until neighbour sampling exists.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .bundles import register_loader
from .charts import cap_charts

try:
    import torch
    import torch.nn as nn
except ImportError:  # pragma: no cover - torch is optional for the tabular models
    torch = None
    nn = None

# The limits of a graph dataset (plan F4): enforced before anything is built.
MAX_NODES = 50000
MAX_EDGES = 500000

# The limits of a zip *archive* (plan G3): a zip is the one upload format whose
# declared size says nothing about what it unpacks to. The caps are checked on
# the archive's own metadata, before a single member is read, so a decompression
# bomb costs the server a stat and not its memory.
MAX_ZIP_MEMBERS = 64
MAX_ZIP_UNCOMPRESSED_BYTES = 256 * 1024 * 1024  # 256 MiB unpacked


def _safe_zip_members(dataset_path: Path) -> List[str]:
    """Validate a zip's members and return their names, or raise ``ValueError``.

    Three things are refused before anything is read (plan G3):

    * a member whose name leaves the archive - an absolute path or a ``..``
      segment (zip-slip). This loader reads members through ``archive.open``
      and never extracts to disk, but the check makes the archive safe for any
      future caller that extracts, and refuses a name that was not honest.
    * a symlink member: its target is outside the archive by definition, and
      extracting one would place a link that climbs out.
    * an archive of too many members or too many unpacked bytes: the counts
      come from the central directory, which is read either way, so the
      refusal happens before the memory is spent.
    """
    import stat as stat_module

    try:
        archive = zipfile.ZipFile(dataset_path)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"'{dataset_path.name}' is not a readable zip archive.") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ZIP_MEMBERS:
            raise ValueError(
                f"The archive holds {len(infos)} files; the limit is {MAX_ZIP_MEMBERS}."
            )
        total = 0
        for info in infos:
            name = info.filename
            if name.startswith("/") or name.startswith("\\") or ":" in name.split("/")[0]:
                raise ValueError(
                    f"The archive holds a member with an absolute path ({name!r}); "
                    "archives with absolute member paths are refused."
                )
            parts = [part for part in name.replace("\\", "/").split("/") if part]
            if ".." in parts:
                raise ValueError(
                    f"The archive holds a member whose path climbs out of it "
                    f"({name!r}); such archives are refused."
                )
            mode = info.external_attr >> 16
            if stat_module.S_ISLNK(mode):
                raise ValueError(
                    f"The archive holds a symlink member ({name!r}); archives "
                    "with symlink members are refused."
                )
            total += info.file_size
            if total > MAX_ZIP_UNCOMPRESSED_BYTES:
                raise ValueError(
                    "The archive unpacks to more than "
                    f"{MAX_ZIP_UNCOMPRESSED_BYTES // (1024 * 1024)} MiB, which is "
                    "more than a dataset may hold."
                )
        return [info.filename for info in infos]


def _load_graph(dataset_path: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Read nodes.csv and edges.csv out of the dataset zip (plan F1/F4)."""
    dataset_path = Path(dataset_path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"The graph dataset '{dataset_path.name}' was not found.")
    if dataset_path.suffix != ".zip":
        raise ValueError("A graph dataset is a zip with nodes.csv and edges.csv.")
    names = set(_safe_zip_members(dataset_path))
    if "nodes.csv" not in names or "edges.csv" not in names:
        raise ValueError(
            "A graph dataset is a zip with nodes.csv and edges.csv; "
            f"this one holds {sorted(names)}."
        )
    with zipfile.ZipFile(dataset_path) as archive:
        nodes = pd.read_csv(archive.open("nodes.csv"))
        edges = pd.read_csv(archive.open("edges.csv"))
    if "node_id" not in nodes.columns:
        raise ValueError("nodes.csv needs a 'node_id' column.")
    if "label" not in nodes.columns:
        raise ValueError("nodes.csv needs a 'label' column (the class of the node).")
    if not {"source", "target"}.issubset(edges.columns):
        raise ValueError("edges.csv needs 'source' and 'target' columns.")
    if len(nodes) > MAX_NODES:
        raise ValueError(f"The graph has {len(nodes)} nodes; the limit is {MAX_NODES}.")
    if len(edges) > MAX_EDGES:
        raise ValueError(f"The graph has {len(edges)} edges; the limit is {MAX_EDGES}.")
    return nodes, edges


def _normalised_adjacency(
    node_ids: List[str],
    edges: pd.DataFrame,
    symmetrise: bool,
):
    """The sparse, symmetrically normalised adjacency with self-loops.

    A - 1/2 D^-1/2 (A + I) D^-1/2 - is the propagation of the GCN (plan F4).
    A test asserts the result is symmetric.
    """
    if torch is None:
        raise RuntimeError("torch is not installed: the graph models need it")
    index = {node_id: i for i, node_id in enumerate(node_ids)}
    n = len(node_ids)

    source = edges["source"].map(index)
    target = edges["target"].map(index)
    known = source.notna() & target.notna()
    rows = [int(v) for v in source[known]]
    cols = [int(v) for v in target[known]]

    if symmetrise:
        rows, cols = rows + cols + list(range(n)), cols + rows + list(range(n))
    else:
        rows, cols = rows + list(range(n)), cols + list(range(n))
    values = [1.0] * len(rows)

    indices = torch.tensor([rows, cols], dtype=torch.long)
    values = torch.tensor(values, dtype=torch.float32)
    A = torch.sparse_coo_tensor(indices, values, (n, n)).coalesce()

    # D^-1/2 (A + I) D^-1/2, computed on the degree of the sparse matrix.
    degree = torch.sparse.sum(A, dim=1).to_dense()
    degree = torch.where(degree > 0, degree, torch.ones_like(degree))
    d_inv_sqrt = 1.0 / torch.sqrt(degree)
    rows, cols = A.indices()
    scaled_values = A.values() * d_inv_sqrt[rows] * d_inv_sqrt[cols]
    return torch.sparse_coo_tensor(
        torch.stack([rows, cols]), scaled_values, (n, n)
    ).coalesce()


class GCNLayer(nn.Module):
    """One graph-convolution layer over a precomputed normalised adjacency."""

    def __init__(self, in_features: int, out_features: int):
        super().__init__()
        self.linear = nn.Linear(in_features, out_features)

    def forward(self, x, adjacency):
        return torch.sparse.mm(adjacency, self.linear(x))


class SAGELayer(nn.Module):
    """A GraphSAGE-style mean-aggregate layer (the ``layer`` option)."""

    def __init__(self, in_features: int, out_features: int):
        super().__init__()
        self.linear = nn.Linear(in_features, out_features)

    def forward(self, x, adjacency):
        aggregated = torch.sparse.mm(adjacency, x)
        return self.linear(aggregated + x)


class GCN(nn.Module):
    """Two layers, hidden size, dropout - the full-batch GCN of plan F4."""

    def __init__(self, in_features: int, hidden_size: int, n_classes: int, layer: str = "gcn", dropout: float = 0.5):
        super().__init__()
        layer_class = GCNLayer if layer == "gcn" else SAGELayer
        first_out = hidden_size
        self.first = layer_class(in_features, first_out)
        # SAGE concatenates the aggregation with the node features.
        second_in = first_out if layer == "gcn" else first_out
        self.second = layer_class(second_in, n_classes)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, adjacency):
        x = self.first(x, adjacency)
        x = torch.relu(x)
        x = self.dropout(x)
        return self.second(x, adjacency)


class FeatureOnlyMLP(nn.Module):
    """The honest baseline of plan F4: the same budget on the features alone.

    If the GNN does not beat it by a wide margin on a graph whose features
    are noise, the graph does nothing and the entry is an MLP in disguise.
    """

    def __init__(self, in_features: int, hidden_size: int, n_classes: int, dropout: float = 0.5):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(in_features, hidden_size),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size, n_classes),
        )

    def forward(self, x, adjacency=None):
        return self.network(x)


# --- the bundle ------------------------------------------------------------------


class GraphBundle:
    """The artifact of a graph run (plans C1, F4).

    The graph tensors travel with the weights: prediction is transductive
    (the node has to be in the graph), so the propagation needs the graph.
    """

    kind = "graph"
    request_kind = "node_ids"

    def __init__(
        self,
        model: Any,
        layer: str,
        hidden_size: int,
        node_ids: List[str],
        features: Any,
        adjacency: Any,
        class_names: List[str],
    ):
        self.model = model
        self.layer = layer
        self.hidden_size = hidden_size
        self.node_ids = list(node_ids)
        self.features = features
        self.adjacency = adjacency
        self.class_names = list(class_names)

    def schema(self) -> Dict[str, Any]:
        return {
            "request_kind": self.request_kind,
            "kind": self.kind,
            "nodes": len(self.node_ids),
            "classes": [str(c) for c in self.class_names],
            "output": "the class probabilities of each node (transductive)",
        }

    def infer(self, request: Dict[str, Any]) -> Dict[str, Any]:
        node_ids = request.get("node_ids") or []
        if not node_ids:
            raise ValueError("The request has no node id.")
        unknown = [node for node in node_ids if node not in self.node_ids]
        if unknown:
            raise ValueError(
                f"The node(s) {unknown[:5]} are not in the graph: prediction is "
                "transductive (only the nodes of the training graph)."
            )
        if torch is None:
            raise RuntimeError("torch is not installed")
        self.model.eval()
        with torch.no_grad():
            logits = self.model(self.features, self.adjacency)
            probabilities = torch.softmax(logits, dim=1).numpy()
        indices = [self.node_ids.index(node) for node in node_ids]
        selected = probabilities[indices]
        return {
            "predictions": [str(self.class_names[int(i)]) for i in selected.argmax(axis=1)],
            "probabilities": [
                {str(self.class_names[c]): round(float(row[c]), 4) for c in range(len(self.class_names))}
                for row in selected
            ],
        }

    def save(self, directory: Path) -> None:
        directory = Path(directory)
        torch.save(
            {
                "state_dict": self.model.state_dict(),
                "features": self.features,
                "adjacency_indices": self.adjacency.indices(),
                "adjacency_values": self.adjacency.values(),
                "adjacency_size": self.adjacency.shape,
            },
            directory / "model.pt",
        )
        (directory / "config.json").write_text(
            json.dumps(
                {
                    "kind": self.kind,
                    "layer": self.layer,
                    "hidden_size": self.hidden_size,
                    "node_ids": self.node_ids,
                    "class_names": [str(c) for c in self.class_names],
                }
            )
        )

    @classmethod
    def load(cls, directory: Path, manifest: Optional[Dict[str, Any]] = None) -> "GraphBundle":
        directory = Path(directory)
        if torch is None:
            raise RuntimeError("torch is not installed")
        payload = torch.load(directory / "model.pt", map_location="cpu")
        config = json.loads((directory / "config.json").read_text())
        in_features = payload["features"].shape[1]
        n_classes = len(config["class_names"])
        model = GCN(in_features, config["hidden_size"], n_classes, layer=config["layer"])
        model.load_state_dict(payload["state_dict"])
        model.eval()
        adjacency = torch.sparse_coo_tensor(
            payload["adjacency_indices"],
            payload["adjacency_values"],
            tuple(payload["adjacency_size"]),
        ).coalesce()
        return cls(
            model=model,
            layer=config["layer"],
            hidden_size=config["hidden_size"],
            node_ids=config["node_ids"],
            features=payload["features"],
            adjacency=adjacency,
            class_names=config["class_names"],
        )


register_loader("graph", GraphBundle.load)


# --- the trainer --------------------------------------------------------------------


def train_gnn(
    model_name: str,
    dataset_path: Path,
    params: Dict[str, Any],
) -> Tuple[Dict[str, Any], GraphBundle]:
    """Train the two-layer GCN (or SAGE) on a graph (plan F4)."""
    if torch is None:
        raise RuntimeError("torch is not installed: the graph models need it")
    nodes, edges = _load_graph(Path(dataset_path))

    symmetrise = bool(params.get("symmetrise", True))
    layer = str(params.get("layer", "gcn"))
    if layer not in ("gcn", "sage"):
        raise ValueError("layer must be 'gcn' or 'sage'.")
    hidden_size = int(params.get("hidden_size", 32))
    epochs = int(params.get("epochs", 200))
    learning_rate = float(params.get("learning_rate", 0.01))
    weight_decay = float(params.get("weight_decay", 5e-4))
    dropout = float(params.get("dropout", 0.5))
    random_state = int(params.get("random_state", 42))
    torch.manual_seed(random_state)

    node_ids = [str(v) for v in nodes["node_id"].tolist()]
    feature_columns = [
        column
        for column in nodes.columns
        if column not in ("node_id", "label")
        and pd.api.types.is_numeric_dtype(nodes[column])
    ]
    if not feature_columns:
        # Every non-id, non-label column is categorical: one number per
        # distinct value is the cheapest encoding that keeps going.
        for column in nodes.columns:
            if column in ("node_id", "label"):
                continue
            codes, _ = pd.factorize(nodes[column])
            nodes[column] = codes.astype(float)
            feature_columns.append(column)
    features = torch.tensor(
        nodes[feature_columns].to_numpy(dtype=float), dtype=torch.float32
    )

    classes = sorted(str(v) for v in nodes["label"].unique())
    class_index = {name: i for i, name in enumerate(classes)}
    y = torch.tensor(
        [class_index[str(v)] for v in nodes["label"]], dtype=torch.long
    )
    n = len(node_ids)

    # The stratified node split of plan F4: 60/20/20 train/validation/test.
    from sklearn.model_selection import train_test_split

    all_indices = np.arange(n)
    train_part, temp_part = train_test_split(
        all_indices, test_size=0.4, stratify=y.numpy(), random_state=random_state
    )
    val_part, test_part = train_test_split(
        temp_part, test_size=0.5, stratify=y.numpy()[temp_part], random_state=random_state
    )
    train_mask = torch.zeros(n, dtype=torch.bool)
    val_mask = torch.zeros(n, dtype=torch.bool)
    test_mask = torch.zeros(n, dtype=torch.bool)
    train_mask[torch.tensor(train_part)] = True
    val_mask[torch.tensor(val_part)] = True
    test_mask[torch.tensor(test_part)] = True

    adjacency = _normalised_adjacency(node_ids, edges, symmetrise)
    model = GCN(features.shape[1], hidden_size, len(classes), layer=layer, dropout=dropout)

    def _train_eval(builder):
        """The shared training loop of the GNN and the feature-only baseline."""
        trained = builder()
        optimizer = torch.optim.Adam(
            trained.parameters(), lr=learning_rate, weight_decay=weight_decay
        )
        best_val, best_state, stale = -1.0, None, 0
        for _epoch in range(max(1, epochs)):
            trained.train()
            optimizer.zero_grad()
            logits = trained(features, adjacency)
            # The loss uses the labels of the training nodes only (plan F4):
            # a test that the labels of the test nodes never enter the loss
            # is what keeps the number honest.
            loss = nn.functional.cross_entropy(logits[train_mask], y[train_mask])
            loss.backward()
            optimizer.step()
            trained.eval()
            with torch.no_grad():
                val_logits = trained(features, adjacency)
                val_accuracy = float(
                    (val_logits[val_mask].argmax(dim=1) == y[val_mask]).float().mean()
                )
            if val_accuracy > best_val:
                best_val = val_accuracy
                best_state = {k: v.clone() for k, v in trained.state_dict().items()}
                stale = 0
            else:
                stale += 1
                if stale >= 20:
                    break
        if best_state is not None:
            trained.load_state_dict(best_state)
        trained.eval()
        return trained

    trained_model = _train_eval(lambda: model)
    # The feature-only baseline with the same budget (plan F4): the honest
    # test of whether the graph helps at all.
    baseline_model = _train_eval(
        lambda: FeatureOnlyMLP(features.shape[1], hidden_size, len(classes), dropout=dropout)
    )

    with torch.no_grad():
        logits = trained_model(features, adjacency)
        test_predictions = logits[test_mask].argmax(dim=1).numpy()
        test_truth = y[test_mask].numpy()
        accuracy = float((test_predictions == test_truth).mean())

        baseline_logits = baseline_model(features, adjacency)
        baseline_predictions = baseline_logits[test_mask].argmax(dim=1).numpy()

    from sklearn.metrics import f1_score

    majority = pd.Series(y[train_mask].numpy()).value_counts().idxmax()
    metrics: Dict[str, Any] = {
        "task_type": "graph",
        "model_name": model_name,
        "layer": layer,
        "nodes": n,
        "edges": int(len(edges)),
        "feature_columns": feature_columns,
        "classes": len(classes),
        "train_size": int(train_mask.sum()),
        "validation_size": int(val_mask.sum()),
        "test_size": int(test_mask.sum()),
        "accuracy": round(accuracy, 4),
        "f1_macro": round(float(f1_score(test_truth, test_predictions, average="macro")), 4),
        "baseline_majority_accuracy": round(
            float((test_truth == majority).mean()), 4
        ),
        "baseline_feature_only_accuracy": round(
            float((baseline_predictions == test_truth).mean()), 4
        ),
        "beats_feature_only": bool(
            accuracy > float((baseline_predictions == test_truth).mean())
        ),
        "artifact_kind": GraphBundle.kind,
    }

    bundle = GraphBundle(
        model=trained_model,
        layer=layer,
        hidden_size=hidden_size,
        node_ids=node_ids,
        features=features,
        adjacency=adjacency,
        class_names=classes,
    )
    return metrics, bundle
