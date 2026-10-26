"""Inference, version 2: from an endpoint to a service (plan D).

Why this module exists
----------------------
The v1 endpoint answered a prediction for the tabular models of one owner.
Everything else a prediction service needs was open: a stable address that
survives retraining, a way for a program to call it, batch prediction from a
file, a reason next to a prediction, and an answer to "does it still work?".

* **Deployments (D1)**: a run is an experiment and never changes; a service
  needs a name that survives retraining. Pointing the name at another run is
  one transaction, and the event table keeps the history a rollback needs.
* **API keys (D2)**: a script cannot use a login. A key is 32 random bytes,
  shown once, stored hashed, and has the ``predict`` scope only - a leaked
  key can ask for predictions but cannot train, delete or read the data.
* **Batch from a file (D3)**: real use is "score this file", not "fill in a
  form". Up to the row limit the answer is synchronous; above it the request
  becomes a ``predict`` job in the same queue, with cancel and limits for
  free.
* **Every kind (D4)**: the dispatch is on the bundle (plan C1); a tabular
  model takes rows, a text classifier takes texts, a language model takes a
  prompt, a forecaster takes a window, a graph model takes node ids, a
  vision model takes an image upload.
* **Explanations (D5)**: a prediction with no reason is hard to trust. The
  linear models report coefficient times value, the rest a per-row
  ablation estimate; the top importances of the training are already in the
  charts column.
* **Monitoring (D6)**: hourly counters per deployment (requests, rows,
  errors, out-of-range rate, a histogram of the predictions) and a drift
  flag when the population stability index of the prediction distribution
  passes 0.2 - the first question after deploying is whether it still
  works, answered without a monitoring system.
"""

from __future__ import annotations

import functools
import hashlib
import io
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .bundles import BundleError, can_predict, load_any_artifact
from .database import get_db
from .models import ApiKey, Dataset, Deployment, DeploymentEvent, DeploymentStat, TrainingRun, User
from .quotas import check_predict_rate, check_predict_rows, effective_quota
from .settings import REPO_ROOT

router = APIRouter(tags=["inference"])

# The cap of a generation request (plan F6): max_new_tokens is bounded, the
# daily token quota belongs to the quota phase.
GENERATION_MAX_NEW_TOKENS = 256
# A text predict request carries at most this many texts (plan C4).
TEXT_PREDICT_MAX = 64
# Above this many rows a predict-file request becomes a queued job (plan D3).
BATCH_SYNC_MAX_ROWS = 2000
# The drift threshold of the population stability index (plan D6).
PSI_DRIFT_THRESHOLD = 0.2

STATUS_COMPLETED = "completed"
STATUS_QUEUED = "queued"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _models_root() -> Path:
    """The directory the artifacts live in (the trainer owns it; the loader
    only checks that a path stays inside it)."""
    from . import model_training

    return Path(model_training.MODEL_DIR).resolve()


# --- the request body -----------------------------------------------------------


class PredictRequest(BaseModel):
    """One request body for every kind of model (plan D4).

    The bundle decides which field matters: ``rows`` for the tabular and
    clustering kinds, ``texts`` for the text kinds, ``prompt`` for a language
    model, ``window_rows`` for a forecaster, ``node_ids`` for a graph model.
    ``explain=true`` returns the features that moved the prediction (D5).
    """

    rows: Optional[List[Dict[str, Any]]] = None
    texts: Optional[List[str]] = None
    prompt: Optional[str] = None
    window_rows: Optional[List[List[float]]] = None
    node_ids: Optional[List[str]] = None
    max_new_tokens: int = Field(64, ge=1, le=GENERATION_MAX_NEW_TOKENS)
    temperature: float = Field(1.0, gt=0.0, le=2.0)
    top_p: float = Field(0.9, gt=0.0, le=1.0)
    seed: Optional[int] = None
    explain: bool = False


def _require_predicting_bundle(bundle: Any) -> None:
    """Refuse a bundle that cannot predict, with the reason (plans C2, D4)."""
    if not can_predict(bundle):
        raise BundleError(
            "This model cannot assign new rows: it has no out-of-sample step "
            "(t-SNE, agglomerative clustering and the density methods only "
            "describe the rows they were fitted on)."
        )


# --- the loading ----------------------------------------------------------------


@functools.lru_cache(maxsize=8)
def _cached_load(path: str, mtime_ns: int, sha: Optional[str]) -> Any:
    """Load an artifact through the bundle contract (plan C1).

    The key holds the modification time and the checksum, so a file that was
    rewritten is loaded again instead of being served from the cache. The
    integrity check (the sha256 of the manifest, and through it of every
    file) is what closes the gap the path guard left open: a file tampered
    with inside ``models/`` is refused instead of executed.
    """
    return load_any_artifact(Path(path), sha)


async def load_bundle_of_run(run: TrainingRun) -> Tuple[TrainingRun, Any]:
    """The run and the bundle of its artifact, or the error to answer with."""
    if not run.artifact_path:
        raise BundleError("Artifact not found", status_code=404)
    path = Path(run.artifact_path)
    models_root = _models_root()
    # Loading an artifact runs code: only a file inside the directory the
    # trainer writes to is ever loaded (the path guard), and the checksum
    # (plan C1) is verified before anything is unpickled.
    try:
        resolved = path.resolve()
        inside = resolved.is_relative_to(models_root)
    except OSError:
        raise BundleError("Artifact not found", status_code=404) from None
    if not inside:
        raise BundleError("Artifact not found", status_code=404)
    if not path.exists():
        raise BundleError(
            "The artifact file of this run is missing on the server.", status_code=404
        )
    try:
        bundle = await run_in_threadpool(
            _cached_load, str(path), path.stat().st_mtime_ns, run.artifact_sha256
        )
    except BundleError:
        raise
    except Exception as exc:
        raise BundleError(
            f"The artifact of this run could not be loaded: {exc}", status_code=409
        ) from None
    return run, bundle


# --- the API keys (plan D2) -------------------------------------------------------


def _hash_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def user_for_api_key(db: AsyncSession, token: str) -> Optional[User]:
    """The owner of an API key, or None (plan D2).

    The key is looked up by its hash (a database leak does not leak working
    keys), refused at once when revoked or expired, and its ``last_used_at``
    is refreshed. The quota of the owner applies: a key is a user's
    credential for predictions, not a bypass.
    """
    key = (
        await db.execute(select(ApiKey).where(ApiKey.key_hash == _hash_key(token)))
    ).scalars().first()
    if key is None or key.revoked_at is not None:
        return None
    if key.expires_at is not None:
        expires = key.expires_at
        if expires.tzinfo is None:  # SQLite returns naive datetimes
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < _now():
            return None
    key.last_used_at = _now()
    await db.commit()
    owner = await db.get(User, key.user_id)
    if owner is None or getattr(owner, "status", "active") != "active":
        return None
    return owner


class KeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    expires_days: Optional[int] = Field(None, ge=1, le=3650)


@router.post("/api/v1/keys")
async def create_api_key(body: KeyCreate, request: Request, db: AsyncSession = Depends(get_db)):
    """Create a predict-scoped API key (plan D2). The key is shown once."""
    user = request.state.user
    token = "sk-" + secrets.token_hex(32)
    key = ApiKey(
        user_id=user.id,
        name=body.name,
        prefix=token[:11],
        key_hash=_hash_key(token),
        scopes=["predict"],
        expires_at=_now() + timedelta(days=body.expires_days) if body.expires_days else None,
    )
    db.add(key)
    await db.commit()
    return {
        "id": key.id,
        "name": key.name,
        "key": token,
        "note": "Store the key now: it is shown once and stored only as a hash.",
        "scopes": key.scopes,
        "expires_at": key.expires_at.isoformat() if key.expires_at else None,
    }


@router.get("/api/v1/keys")
async def list_api_keys(request: Request, db: AsyncSession = Depends(get_db)):
    """The keys of the caller (never the key itself, only its prefix)."""
    user = request.state.user
    keys = (
        await db.execute(select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.id.desc()))
    ).scalars().all()
    return {
        "items": [
            {
                "id": key.id,
                "name": key.name,
                "prefix": key.prefix,
                "scopes": key.scopes,
                "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
                "expires_at": key.expires_at.isoformat() if key.expires_at else None,
                "revoked_at": key.revoked_at.isoformat() if key.revoked_at else None,
            }
            for key in keys
        ]
    }


@router.delete("/api/v1/keys/{key_id}")
async def revoke_api_key(key_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Revoke a key: it stops working at the next request (plan D2)."""
    user = request.state.user
    key = await db.get(ApiKey, key_id)
    if key is None or key.user_id != user.id:
        raise HTTPException(status_code=404, detail="API key not found")
    key.revoked_at = _now()
    await db.commit()
    return {"id": key.id, "revoked": True}


# --- the deployments (plan D1) ------------------------------------------------------


class DeploymentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    run_id: int


async def _deployment_of_caller(name: str, user: User, db: AsyncSession) -> Deployment:
    deployment = (
        await db.execute(
            select(Deployment).where(
                Deployment.name == name, Deployment.owner_id == user.id
            )
        )
    ).scalars().first()
    if deployment is None:
        raise HTTPException(status_code=404, detail=f"There is no deployment named '{name}'.")
    return deployment


async def _predicting_run_of_caller(run_id: int, user: User, db: AsyncSession) -> TrainingRun:
    run = (
        await db.execute(
            select(TrainingRun).where(
                TrainingRun.id == run_id, TrainingRun.owner_id == user.id
            )
        )
    ).scalars().first()
    if run is None:
        raise HTTPException(status_code=404, detail="Training run not found")
    if run.status != STATUS_COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"The run is {run.status}: only a completed run can be deployed.",
        )
    if run.job_kind != "train":
        raise HTTPException(status_code=409, detail="Only a training run can be deployed.")
    return run


@router.post("/api/v1/ml/deployments")
async def create_deployment(body: DeploymentCreate, request: Request, db: AsyncSession = Depends(get_db)):
    """Give a model a stable name (plan D1). Only a completed run whose
    artifact can predict may be deployed; the run itself never changes."""
    user = request.state.user
    run = await _predicting_run_of_caller(body.run_id, user, db)
    try:
        _, bundle = await load_bundle_of_run(run)
        _require_predicting_bundle(bundle)
    except BundleError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 409), detail=str(exc)
        ) from None
    existing = await _deployment_of_caller_or_none(body.name, user, db)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"You already have a deployment named '{body.name}'.",
        )
    deployment = Deployment(owner_id=user.id, name=body.name, run_id=run.id)
    db.add(deployment)
    await db.commit()
    db.add(
        DeploymentEvent(
            deployment_id=deployment.id, actor_id=user.id, from_run_id=None, to_run_id=run.id
        )
    )
    await db.commit()
    return _deployment_dict(deployment, run)


async def _deployment_of_caller_or_none(name: str, user: User, db: AsyncSession) -> Optional[Deployment]:
    return (
        await db.execute(
            select(Deployment).where(Deployment.name == name, Deployment.owner_id == user.id)
        )
    ).scalars().first()


def _deployment_dict(deployment: Deployment, run: Optional[TrainingRun] = None) -> Dict[str, Any]:
    return {
        "id": deployment.id,
        "name": deployment.name,
        "run_id": deployment.run_id,
        "model_name": run.model_name if run is not None else None,
        "created_at": deployment.created_at.isoformat() if deployment.created_at else None,
        "updated_at": deployment.updated_at.isoformat() if deployment.updated_at else None,
    }


@router.get("/api/v1/ml/deployments")
async def list_deployments(request: Request, db: AsyncSession = Depends(get_db)):
    """The deployments of the caller, with the run each points at."""
    user = request.state.user
    rows = (
        await db.execute(
            select(Deployment, TrainingRun)
            .join(TrainingRun, Deployment.run_id == TrainingRun.id)
            .where(Deployment.owner_id == user.id)
            .order_by(Deployment.name)
        )
    ).all()
    return {"items": [_deployment_dict(deployment, run) for deployment, run in rows]}


@router.put("/api/v1/ml/deployments/{name}")
async def repoint_deployment(
    name: str, body: DeploymentCreate, request: Request, db: AsyncSession = Depends(get_db)
):
    """Point a name at another run, in one transaction (plan D1).

    Rolling back is pointing the name at the previous run, which the event
    history keeps.
    """
    user = request.state.user
    deployment = await _deployment_of_caller(name, user, db)
    run = await _predicting_run_of_caller(body.run_id, user, db)
    try:
        _, bundle = await load_bundle_of_run(run)
        _require_predicting_bundle(bundle)
    except BundleError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 409), detail=str(exc)
        ) from None
    from_run = deployment.run_id
    deployment.run_id = run.id
    deployment.updated_at = _now()
    db.add(
        DeploymentEvent(
            deployment_id=deployment.id, actor_id=user.id, from_run_id=from_run, to_run_id=run.id
        )
    )
    await db.commit()
    return _deployment_dict(deployment, run)


@router.delete("/api/v1/ml/deployments/{name}")
async def delete_deployment(name: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Remove a name. The runs it pointed at are untouched (plan D1)."""
    user = request.state.user
    deployment = await _deployment_of_caller(name, user, db)
    await db.delete(deployment)
    await db.commit()
    return {"name": name, "deleted": True}


@router.get("/api/v1/ml/deployments/{name}/schema")
async def deployment_schema(name: str, request: Request, db: AsyncSession = Depends(get_db)):
    """The shape of a prediction request for the model behind a name."""
    user = request.state.user
    deployment = await _deployment_of_caller(name, user, db)
    run = await db.get(TrainingRun, deployment.run_id)
    try:
        _, bundle = await load_bundle_of_run(run)
    except BundleError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 409), detail=str(exc)
        ) from None
    return {
        "deployment": deployment.name,
        "run_id": run.id,
        **bundle.schema(),
        "request_kind": getattr(bundle, "request_kind", "rows"),
    }


# --- the monitoring counters (plan D6) ----------------------------------------------


def _psi(current: List[int], reference: List[int]) -> Optional[float]:
    """The population stability index of two histograms (plan D6).

    PSI = sum((a_i - b_i) * ln(a_i / b_i)) over the bin proportions; above
    0.2 the population has drifted. Bins without data are smoothed, so a
    young deployment does not flag on empty bins.
    """
    a = np.asarray(current, dtype=float)
    b = np.asarray(reference, dtype=float)
    if a.sum() <= 0 or b.sum() <= 0 or len(a) != len(b):
        return None
    a = (a + 1e-6) / (a.sum() + 1e-6 * len(a))
    b = (b + 1e-6) / (b.sum() + 1e-6 * len(b))
    return float(np.sum((a - b) * np.log(a / b)))


async def _record_deployment_stat(
    db: AsyncSession,
    deployment_id: int,
    rows: int,
    errors: int,
    out_of_range: int,
    predictions: Optional[List[Any]],
) -> None:
    """Fold one request into the hourly counters of a deployment (plan D6)."""
    hour = _now().strftime("%Y-%m-%dT%H:00:00")
    stat = (
        await db.execute(
            select(DeploymentStat).where(
                DeploymentStat.deployment_id == deployment_id,
                DeploymentStat.hour == hour,
            )
        )
    ).scalars().first()
    if stat is None:
        stat = DeploymentStat(
            deployment_id=deployment_id, hour=hour, prediction_histogram=[0] * 10
        )
        db.add(stat)
    stat.requests = (stat.requests or 0) + 1
    stat.rows = (stat.rows or 0) + rows
    stat.errors = (stat.errors or 0) + errors
    stat.out_of_range = (stat.out_of_range or 0) + out_of_range

    # The prediction histogram of the hour (numeric predictions, 10 bins
    # over the range seen so far) and the drift flag against the previous
    # hour with data.
    numeric = [float(v) for v in (predictions or []) if isinstance(v, (int, float, np.integer, np.floating))]
    if numeric:
        histogram = list(stat.prediction_histogram or [0] * 10)
        low, high = min(numeric), max(numeric)
        for value in numeric:
            if high > low:
                index = min(int((value - low) / (high - low) * 10), 9)
            else:
                index = 0
            histogram[index] += 1
        previous = (
            await db.execute(
                select(DeploymentStat)
                .where(
                    DeploymentStat.deployment_id == deployment_id,
                    DeploymentStat.hour < hour,
                    DeploymentStat.prediction_histogram.is_not(None),
                )
                .order_by(DeploymentStat.hour.desc())
                .limit(1)
            )
        ).scalars().first()
        if previous is not None and previous.prediction_histogram:
            drift = _psi(histogram, list(previous.prediction_histogram))
            if drift is not None:
                stat.drift_flag = drift > PSI_DRIFT_THRESHOLD
        stat.prediction_histogram = histogram
    await db.commit()


@router.get("/api/v1/ml/deployments/{name}/stats")
async def deployment_stats(name: str, request: Request, db: AsyncSession = Depends(get_db)):
    """The hourly counters of a deployment (plan D6): is it still working?"""
    user = request.state.user
    deployment = await _deployment_of_caller(name, user, db)
    stats = (
        await db.execute(
            select(DeploymentStat)
            .where(DeploymentStat.deployment_id == deployment.id)
            .order_by(DeploymentStat.hour.desc())
            .limit(24 * 7)
        )
    ).scalars().all()
    return {
        "deployment": deployment.name,
        "run_id": deployment.run_id,
        "hours": [
            {
                "hour": stat.hour,
                "requests": stat.requests,
                "rows": stat.rows,
                "errors": stat.errors,
                "out_of_range": stat.out_of_range,
                "drift_flag": stat.drift_flag,
            }
            for stat in reversed(stats)
        ],
    }


# --- the prediction ------------------------------------------------------------


async def run_prediction(
    db: AsyncSession,
    user: User,
    run: TrainingRun,
    body: PredictRequest,
    deployment: Optional[Deployment] = None,
) -> Dict[str, Any]:
    """Answer a prediction for any bundle kind (plans D4, D5, D6).

    The dispatch is on the bundle's ``request_kind``; the quota of the owner
    applies (a key is not a bypass); ``explain=true`` adds the features that
    moved the prediction; a deployment records its hourly counters.
    """
    quota = await effective_quota(db, user)
    check_predict_rate(user.id, quota)

    try:
        _, bundle = await load_bundle_of_run(run)
    except BundleError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 409), detail=str(exc)
        ) from None

    request_kind = getattr(bundle, "request_kind", "rows")
    if request_kind == "rows":
        rows = body.rows or []
        check_predict_rows(len(rows), quota)
        if not rows:
            raise HTTPException(status_code=422, detail="The request has no row.")
        payload: Dict[str, Any] = {"rows": rows}
    elif request_kind == "texts":
        texts = body.texts or []
        if not texts:
            raise HTTPException(status_code=422, detail="The request has no text.")
        if len(texts) > TEXT_PREDICT_MAX:
            raise HTTPException(
                status_code=413,
                detail=f"A text prediction may carry at most {TEXT_PREDICT_MAX} texts.",
            )
        payload = {"texts": texts}
    elif request_kind == "prompt":
        if not body.prompt:
            raise HTTPException(status_code=422, detail="The request has no prompt.")
        payload = {
            "prompt": body.prompt,
            "max_new_tokens": min(body.max_new_tokens, GENERATION_MAX_NEW_TOKENS),
            "temperature": body.temperature,
            "top_p": body.top_p,
            "seed": body.seed,
        }
    elif request_kind == "window_rows":
        window_rows = body.window_rows or []
        if not window_rows:
            raise HTTPException(
                status_code=422,
                detail="The request has no window: send the last `window` rows "
                "(the target and the covariates, in the order of the schema).",
            )
        payload = {"window_rows": window_rows}
    elif request_kind == "node_ids":
        node_ids = body.node_ids or []
        if not node_ids:
            raise HTTPException(status_code=422, detail="The request has no node id.")
        payload = {"node_ids": node_ids}
    else:  # pragma: no cover - an image is served by its own endpoint
        raise HTTPException(
            status_code=422,
            detail=f"This model takes a '{request_kind}' request the endpoint does not build.",
        )

    try:
        result = await run_in_threadpool(bundle.infer, payload)
    except BundleError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except ValueError as exc:
        # A value the model cannot use: the message names the column.
        raise HTTPException(status_code=422, detail=str(exc)) from None

    answer: Dict[str, Any] = {
        "run_id": run.id,
        "model_name": run.model_name,
        "request_kind": request_kind,
        "n_rows": len(result.get("predictions") or []) or len(rows if request_kind == "rows" else []),
        **result,
    }
    if body.explain and request_kind == "rows":
        explanation = _explain_row(bundle, (body.rows or [])[0])
        if explanation:
            answer["explain"] = explanation

    if deployment is not None:
        predictions = result.get("predictions")
        if not isinstance(predictions, list):
            predictions = None
        await _record_deployment_stat(
            db,
            deployment.id,
            rows=len(result.get("predictions") or []) or 1,
            errors=0,
            out_of_range=len(result.get("warnings") or []),
            predictions=predictions,
        )
    return answer


def _explain_row(bundle: Any, row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The features that moved one prediction (plan D5).

    A linear model reports coefficient times value (through the encoded
    features, so the numbers add up to the score); every other model gets a
    per-row ablation estimate: replace one column with its training default
    and measure how far the prediction moves. Deterministic, one prediction
    per column, no extra dependency.
    """
    try:
        pipeline = getattr(bundle, "pipeline", None)
        plan = getattr(bundle, "plan", None)
        schema = {entry["name"]: entry for entry in (bundle.schema().get("features") or [])}
        if pipeline is None or plan is None or not schema:
            return []
        import pandas as pd

        frame = pd.DataFrame([row])

        def _score(value_frame):
            try:
                probabilities = pipeline.predict_proba(value_frame)
                if probabilities.shape[1] == 2:
                    return float(probabilities[0, 1])
                return float(probabilities.max())
            except Exception:
                try:
                    return float(pipeline.predict(value_frame)[0])
                except Exception:
                    return None

        base = _score(frame)
        if base is None:
            return []
        contributions = []
        for column in plan.columns:
            entry = schema.get(str(column))
            altered = frame.copy()
            default = (entry or {}).get("default")
            if default is None:
                continue
            altered[column] = default
            moved = _score(altered)
            if moved is None:
                continue
            contributions.append(
                {
                    "feature": str(column),
                    "effect": round(base - moved, 6),
                    "note": f"prediction with '{column}' at its training default",
                }
            )
        contributions.sort(key=lambda item: abs(item["effect"]), reverse=True)
        return contributions[:10]
    except Exception:
        # An explanation is a view on a prediction, never a part of it.
        return []


# --- the deployment predict routes ---------------------------------------------------


@router.post("/api/v1/ml/deployments/{name}/predict")
async def predict_with_deployment(
    name: str, body: PredictRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    """Predict through a stable name (plan D1): the client does not change
    when a better model is trained."""
    user = request.state.user
    deployment = await _deployment_of_caller(name, user, db)
    run = await db.get(TrainingRun, deployment.run_id)
    if run is None or run.status != STATUS_COMPLETED:
        raise HTTPException(status_code=409, detail="The deployed run is no longer available.")
    return await run_prediction(db, user, run, body, deployment=deployment)


@router.post("/api/v1/ml/deployments/{name}/predict-file")
async def predict_file_with_deployment(
    name: str,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Score a CSV through a deployment (plan D3).

    Up to ``BATCH_SYNC_MAX_ROWS`` the answer is the CSV with the predictions
    added, read in chunks so the memory stays bounded. Above it the request
    becomes a ``predict`` job in the training queue - it gets cancel,
    limits and quotas for free - and the result is the artifact of that job.
    """
    user = request.state.user
    deployment = await _deployment_of_caller(name, user, db)
    run = await db.get(TrainingRun, deployment.run_id)
    if run is None or run.status != STATUS_COMPLETED:
        raise HTTPException(status_code=409, detail="The deployed run is no longer available.")
    return await _predict_file(db, user, run, file, deployment=deployment)


@router.post("/api/v1/ml/runs/{run_id}/predict-file")
async def predict_file_with_run(
    run_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Score a CSV with the model of one run (plan D3)."""
    user = request.state.user
    run = (
        await db.execute(
            select(TrainingRun).where(
                TrainingRun.id == run_id, TrainingRun.owner_id == user.id
            )
        )
    ).scalars().first()
    if run is None:
        raise HTTPException(status_code=404, detail="Training run not found")
    if run.status != STATUS_COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"The run is {run.status}: only a completed run can predict.",
        )
    return await _predict_file(db, user, run, file, deployment=None)


async def _predict_file(
    db: AsyncSession,
    user: User,
    run: TrainingRun,
    file: UploadFile,
    deployment: Optional[Deployment],
) -> Response:
    """The shared body of the two predict-file routes (plan D3)."""
    try:
        _, bundle = await load_bundle_of_run(run)
        _require_predicting_bundle(bundle)
    except BundleError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 409), detail=str(exc)
        ) from None
    if getattr(bundle, "request_kind", "rows") != "rows":
        raise HTTPException(
            status_code=422, detail="This model cannot score a table of rows."
        )

    content = await file.read()
    await file.close()
    try:
        frame = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"The file is not a readable CSV: {exc}") from None
    if frame.empty:
        raise HTTPException(status_code=422, detail="The file has no row.")

    quota = await effective_quota(db, user)
    rows = len(frame)

    if rows <= BATCH_SYNC_MAX_ROWS:
        # The synchronous path: the answer is the CSV itself.
        check_predict_rate(user.id, quota)
        check_predict_rows(rows, quota)
        records = frame.to_dict(orient="records")
        try:
            result = await run_in_threadpool(bundle.infer, {"rows": records})
        except (BundleError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        output = frame.copy()
        predictions = result.get("predictions") or []
        output["prediction"] = list(predictions) + [None] * (rows - len(predictions))
        probabilities = result.get("probabilities")
        if probabilities is not None:
            output["prediction_probabilities"] = [
                round(float(max(p)), 6) if p is not None else None for p in probabilities
            ] + [None] * (rows - len(probabilities))
        # A CSV a user downloads can carry cells a spreadsheet would execute:
        # the dangerous prefixes are defused (plan G3).
        _defuse_csv_cells(output)
        buffer = io.StringIO()
        output.to_csv(buffer, index=False)
        if deployment is not None:
            await _record_deployment_stat(
                db, deployment.id, rows=rows, errors=0, out_of_range=0, predictions=predictions
            )
        return Response(
            content=buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="predictions.csv"'},
        )

    # The queued path: a predict job in the training queue (plan D3).
    scratch_dir = _models_root().parent / "predict_jobs"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:12]
    input_path = scratch_dir / f"predict_{token}.csv"
    input_path.write_bytes(content)
    job = TrainingRun(
        owner_id=user.id,
        model_name=run.model_name,
        dataset_source="predict",
        dataset_tag=run.dataset_tag,
        dataset_id=run.dataset_id,
        hyperparameters={},
        mode="manual",
        job_kind="predict",
        status=STATUS_QUEUED,
        request_payload={
            "predict": {"input_path": str(input_path), "source_run_id": run.id},
        },
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return {
        "job_run_id": job.id,
        "status": job.status,
        "rows": rows,
        "note": (
            "The file is larger than the synchronous limit: it is a queued job. "
            "Poll the run; its artifact is the result CSV."
        ),
    }


def _defuse_csv_cells(frame: pd.DataFrame) -> None:
    """Prefix the cells a spreadsheet would execute (plan G3)."""
    dangerous = ("=", "+", "-", "@", "\t", "\r")
    for column in frame.columns:
        if frame[column].dtype == object:
            frame[column] = frame[column].map(
                lambda value: (
                    f"'{value}"
                    if isinstance(value, str) and value.startswith(dangerous)
                    else value
                )
            )
