"""The artifact contract of every kind of model (plan C1).

Why this module exists
----------------------
Every trainer used to invent its own artifact: a pickled estimator for the
tabular models, a pickled network class for the torch models, whatever
``save_pretrained`` writes for the text models. Three problems follow. A
torch artifact pickles a *class*, which breaks the moment the class moves in
the code. Nothing records which files belong to the artifact, so a file
tampered with inside ``models/`` still runs its code when it is loaded. And
each new trainer re-invents how a prediction is answered, which is how the
old vision trainer ended up unable to predict at all.

The contract in this module fixes the three together:

* every artifact is a **directory** ``models/<name>_<timestamp>_<uuid>/``
  with a ``bundle.json`` manifest (kind, format version, schema, the sha256
  of every file) and the files themselves;
* the sha256 of the manifest is stored in the run row and **verified before
  every load**, so a file altered inside ``models/`` is refused instead of
  executed - the gap the path guard left open;
* a torch artifact is ``model.pt`` (a ``state_dict``) plus ``config.json``
  and the architecture is rebuilt from a registry of architectures, never
  pickled by class reference;
* ``load_any_artifact`` recognises the old single-file ``.joblib`` artifacts
  as well, so a run trained before the contract stays loadable.

The kind of a bundle decides how it is saved and loaded; the loaders of the
torch and transformers kinds register themselves lazily (their modules import
this one), so this module never imports a trainer.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import joblib
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

FORMAT_VERSION = 1
MANIFEST_NAME = "bundle.json"
# The file the sklearn-serialisable bundles are written to.
JOBLIB_FILE = "model.joblib"


class BundleError(Exception):
    """An artifact cannot be loaded: missing, tampered with, or unknown.

    The message is safe to show to a client (no absolute paths). The status
    code says which refusal it is: 404 the artifact is missing, 409 it was
    tampered with, 422 it holds no model that can predict.
    """

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


# --- the bundle protocol ------------------------------------------------------

try:
    # Every bundle the trainers build inherits from this class when it is
    # cheap to do so; duck typing is accepted as well (the tabular bundles of
    # ``tabular.py`` predate the contract and only grew ``save``/``load``).
    class ModelBundle:
        """The protocol every artifact answers: what it is and how to use it.

        ``kind`` names the artifact family (tabular, timeseries, vision, ...);
        ``request_kind`` names what a prediction request carries (rows,
        texts, a prompt, a window of rows, node ids, an image).
        """

        kind: str = "abstract"
        request_kind: str = "rows"

        def schema(self) -> Dict[str, Any]:  # pragma: no cover - abstract
            raise NotImplementedError

        def infer(self, request: Dict[str, Any]) -> Dict[str, Any]:  # pragma: no cover
            raise NotImplementedError

        def save(self, directory: Path) -> None:  # pragma: no cover - abstract
            raise NotImplementedError

        @classmethod
        def load(cls, directory: Path) -> "ModelBundle":  # pragma: no cover
            raise NotImplementedError

except Exception:  # pragma: no cover - defensive
    ModelBundle = object  # type: ignore[assignment]


def can_predict(bundle: Any) -> bool:
    """Whether the bundle answers predictions at all.

    A clustering model without an out-of-sample step is a valid artifact that
    cannot predict; the endpoint says so (422) instead of guessing.
    """
    return bool(getattr(bundle, "predicts", True))


# --- the loader registry ------------------------------------------------------
# kind -> loader(directory, manifest) -> bundle. The kinds whose modules would
# import this one (a cycle) register through ``register_loader`` at import
# time; the map below only names the module, and the import happens on the
# first load of that kind.

_KIND_MODULES: Dict[str, str] = {
    "timeseries": "backend.app.forecasting",
    "graph": "backend.app.graph_models",
    "vision": "backend.app.vision",
    "q_table": "backend.app.rl",
    "rl_policy": "backend.app.rl",
    "text_classifier": "backend.app.textmodels",
    "text_seq2seq": "backend.app.textmodels",
    "text_generation": "backend.app.textmodels",
    "clustering": "backend.app.clustering",
}

_LOADERS: Dict[str, Callable[[Path, Dict[str, Any]], Any]] = {}


def register_loader(kind: str, loader: Callable[[Path, Dict[str, Any]], Any]) -> None:
    """Register the loader of a kind (called by the trainer modules)."""
    _LOADERS[kind] = loader


def _loader_for(kind: str) -> Optional[Callable[[Path, Dict[str, Any]], Any]]:
    if kind in _LOADERS:
        return _LOADERS[kind]
    module_name = _KIND_MODULES.get(kind)
    if module_name:
        try:
            importlib.import_module(module_name)
        except ImportError as exc:  # pragma: no cover - the module is in-repo
            raise BundleError(
                f"the artifact kind '{kind}' needs the module "
                f"'{module_name}', which cannot be imported: {exc}"
            ) from None
        return _LOADERS.get(kind)
    return None


def _joblib_loader(directory: Path, manifest: Dict[str, Any]) -> Any:
    """The loader of the kinds saved as one joblib file (plan C1 backwards)."""
    return joblib.load(directory / JOBLIB_FILE)


for _kind in ("tabular", "autoencoder"):
    register_loader(_kind, _joblib_loader)


# --- hashing ------------------------------------------------------------------


def _sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_files(directory: Path) -> List[Path]:
    """Every file of the artifact directory, relative to it."""
    return sorted(p for p in directory.rglob("*") if p.is_file())


# --- writing ------------------------------------------------------------------


def write_bundle(
    model_name: str,
    bundle: Any,
    model_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Write a bundle as a directory artifact and return its record.

    The record is what the run row stores: the path, the sha256 of the
    manifest (and through it of every file) and the total size in bytes.
    ``MODEL_DIR`` of the trainer is passed in by ``write_artifact``; it is a
    parameter (and not an import) because the tests redirect it.
    """
    from .settings import REPO_ROOT  # local import: settings has no trainer deps

    directory = Path(model_dir) if model_dir is not None else REPO_ROOT / "models"
    artifact_name = (
        f"{model_name}_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_"
        f"{uuid.uuid4().hex[:8]}"
    )
    artifact_dir = directory / artifact_name
    artifact_dir.mkdir(parents=True, exist_ok=True)

    if hasattr(bundle, "save"):
        # The torch and transformers kinds: state_dict + config, or the
        # ``save_pretrained`` directory. The class is never pickled.
        bundle.save(artifact_dir)
    else:
        # The sklearn-serialisable kinds (tabular, autoencoder): the bundle
        # object itself, a module-level class, is the artifact.
        joblib.dump(bundle, artifact_dir / JOBLIB_FILE)

    files = {
        str(path.relative_to(artifact_dir)): _sha256_of_file(path)
        for path in _relative_files(artifact_dir)
    }
    if not files:
        shutil.rmtree(artifact_dir, ignore_errors=True)
        raise BundleError("the bundle wrote no file; there is nothing to save")

    manifest = {
        "kind": getattr(bundle, "kind", "unknown"),
        "request_kind": getattr(bundle, "request_kind", "rows"),
        "format_version": FORMAT_VERSION,
        "model_name": model_name,
        "schema": _plain(bundle.schema()) if hasattr(bundle, "schema") else None,
        "files": files,
    }
    manifest_path = artifact_dir / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))

    total_bytes = sum(p.stat().st_size for p in _relative_files(artifact_dir))
    return {
        "artifact_path": str(artifact_dir),
        "artifact_sha256": _sha256_of_file(manifest_path),
        "artifact_bytes": int(total_bytes),
    }


def _plain(value: Any) -> Any:
    """A schema that survives JSON: numpy and paths become plain values."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


# --- loading ------------------------------------------------------------------


def load_any_artifact(
    path: Path,
    expected_sha256: Optional[str] = None,
) -> Any:
    """Load an artifact of either format, verifying its integrity (plan C1).

    A directory artifact is verified file by file against its manifest, and
    the manifest itself against the sha256 stored in the run row - the
    integrity check that closes the gap the path guard left open. A legacy
    single-file ``.joblib`` artifact is loaded as it is; when the run row
    carries a hash for it (it does not, for old runs), the file is verified.
    """
    path = Path(path)
    if not path.exists():
        raise BundleError(
            "The artifact of this run is missing on the server.", status_code=404
        )

    if path.is_file():
        # The artifact of a run trained before the bundle contract.
        if expected_sha256 and _sha256_of_file(path) != expected_sha256:
            raise BundleError(
                "The artifact of this run does not match the recorded checksum: "
                "it was changed after the training. It is refused.",
                status_code=409,
            )
        bundle = joblib.load(path)
        if not (hasattr(bundle, "infer") and hasattr(bundle, "schema")):
            raise BundleError(
                "The artifact of this run cannot predict: only the supervised "
                "tabular models and the autoencoder save a bundle that knows its "
                "columns. A run trained before that change has to be trained again.",
            )
        return bundle

    if not path.is_dir():
        raise BundleError(
            "The artifact of this run is not a file or a directory.", status_code=404
        )

    manifest_path = path / MANIFEST_NAME
    if not manifest_path.exists():
        raise BundleError(
            "The artifact directory has no manifest; it is refused.", status_code=409
        )
    if expected_sha256 and _sha256_of_file(manifest_path) != expected_sha256:
        raise BundleError(
            "The artifact of this run does not match the recorded checksum: "
            "it was changed after the training. It is refused.",
            status_code=409,
        )
    try:
        manifest = json.loads(manifest_path.read_text())
    except ValueError:
        raise BundleError(
            "The manifest of the artifact is not readable; it is refused.",
            status_code=409,
        ) from None

    for relative, recorded in (manifest.get("files") or {}).items():
        member = path / relative
        if not member.is_file():
            raise BundleError(
                f"The file '{relative}' of the artifact is missing; it is refused.",
                status_code=409,
            )
        if _sha256_of_file(member) != recorded:
            raise BundleError(
                f"The file '{relative}' of the artifact does not match its recorded "
                "checksum: it was changed after the training. It is refused.",
                status_code=409,
            )

    kind = manifest.get("kind")
    loader = _loader_for(kind) if kind else None
    if loader is None:
        raise BundleError(
            f"The artifact kind '{kind}' cannot be loaded here.", status_code=409
        )
    return loader(path, manifest)
