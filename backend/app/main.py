from fastapi import FastAPI, Depends, HTTPException, Header, status
import logging
from contextlib import asynccontextmanager
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.encoders import jsonable_encoder
from jose import JOSEError, jwt
from pathlib import Path
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from .base import Base
from .database import get_db, engine
from .models import User, TrainingRun
from .auth import ALGORITHM, SECRET_KEY, verify_pass, create_token, hash_pass
from .model_training import list_available_models, list_local_datasets, list_model_categories, suggest_hyperparameters, train_model, TRAINING_MODES, TRAINING_PRESETS
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan.

    ``@app.on_event("startup")`` is deprecated: it warns on every import and
    on every test run. The lifespan handler is the modern replacement and is
    the single place where the startup work lives (the reaper of the runs that
    a restart interrupted joins it in the phase that introduces it).

    The schema is owned by the Alembic migrations (``alembic upgrade head``).
    The application must never create the tables itself, because that hides a
    migration that was never applied: the app would then run against a schema
    that no longer matches the migrations. Instead the startup check below
    fails fast with an actionable message.
    """
    await verify_schema()
    yield


async def verify_schema() -> None:
    """Fail fast when the database schema is behind the migrations.

    Three things are checked, because each of them breaks the application in
    a different way:

    * every table the ORM knows about must exist;
    * every column the ORM declares must exist in its table - a table that was
      created by an older version of the application has the right name but
      the wrong columns, and the application would fail on the first query
      that touches the missing column;
    * the database must be under the control of Alembic, i.e. it must carry
      the ``alembic_version`` table. A database that was only ever touched by
      the application itself has the right tables but no migration history,
      so the next ``alembic upgrade head`` would try to create them again.
    """
    async with engine.connect() as conn:
        inspector = await conn.run_sync(lambda sync_conn: sa.inspect(sync_conn))
        names = await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_table_names()
        )
        columns = {
            table.name: await conn.run_sync(
                lambda sync_conn, name=table.name: {
                    column["name"] for column in sa.inspect(sync_conn).get_columns(name)
                }
            )
            for table in Base.metadata.sorted_tables
            if table.name in names
        }

    problems: List[str] = []

    missing_tables = [
        table.name for table in Base.metadata.sorted_tables if table.name not in names
    ]
    if missing_tables:
        problems.append(f"missing table(s) {missing_tables}")

    for table in Base.metadata.sorted_tables:
        if table.name not in columns:
            continue
        declared = {column.name for column in table.columns}
        present = columns[table.name]
        missing_columns = sorted(declared - present)
        extra_columns = sorted(present - declared)
        if missing_columns:
            problems.append(
                f"table '{table.name}' is missing the column(s) {missing_columns}"
            )
        if extra_columns:
            problems.append(
                f"table '{table.name}' has the unexpected column(s) {extra_columns}"
            )

    if "alembic_version" not in names:
        problems.append(
            "the database has no alembic_version table, so it was never migrated"
        )

    if problems:
        raise RuntimeError(
            "The database schema does not match the migrations: "
            + "; ".join(problems)
            + ". Run `alembic upgrade head` in the backend/ directory first. "
            "If the database is already at the latest revision, the schema "
            "itself has drifted: `alembic check` shows the difference."
        )


app = FastAPI(title="PrimeTrade AutoML API", lifespan=lifespan)

# log
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("PrimeTradeAPI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_active_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    if authorization is not None:
        # A credential was supplied, so it has to be valid: an invalid, malformed or
        # expired token is rejected with 401 instead of being silently downgraded to
        # the shared anonymous user. That keeps the frontend's 401 -> logout path
        # working and stops a user's runs from disappearing after token expiry.
        # The check is `is not None` (not truthiness) on purpose: a present but empty
        # Authorization header is a broken credential, not a missing one, so it must
        # be rejected instead of falling through to the anonymous fallback.
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except JOSEError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token", headers={"WWW-Authenticate": "Bearer"}) from None
        username: str = payload.get("sub")
        if not username:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalars().first()
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
        return user

    # No Authorization header: the API stays usable without authentication by falling
    # back to a shared anonymous user, which is created on first use.
    result = await db.execute(select(User).where(User.username == "anonymous"))
    user = result.scalars().first()
    if user:
        return user

    anonymous = User(username="anonymous", hashed_password=hash_pass("anonymous"), role="user")
    db.add(anonymous)
    await db.commit()
    await db.refresh(anonymous)
    return anonymous

class UserCreate(BaseModel):
    username: str
    password: str
    # Accepted for backwards compatibility but ignored: a client may never choose its
    # own role. Admin promotion is a manual database operation.
    role: Optional[str] = Field(default="user", description="Ignored: new accounts are always created with role 'user'.")

class TrainRequest(BaseModel):
    model_name: str
    dataset_name: Optional[str] = None
    hf_dataset_url: Optional[str] = None
    label_column: str = "label"
    test_size: float = Field(0.2, gt=0.0, lt=1.0)
    random_state: int = 42
    hyperparameters: Optional[Dict[str, Any]] = {}
    mode: str = "manual"
    preset: str = "balanced"
    optimize_metric: str = "accuracy"
    env_id: Optional[str] = None
    model_candidates: Optional[List[str]] = None
    sep: Optional[str] = ","
    usecols: Optional[List[str]] = None

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JOSEError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token", headers={"WWW-Authenticate": "Bearer"}) from None
    username: str = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    return user

async def get_current_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user

@app.post("/api/v1/register")
async def register(user: UserCreate, db=Depends(get_db)):
    logger.info(f"Registration attempt for new user: '{user.username}'")
    safe_password = user.password[:72]
    hashed = hash_pass(safe_password)
    # The role is always 'user': a client-supplied role is never trusted, promoting
    # an account to admin is a manual database operation.
    new_user = User(username=user.username, hashed_password=hashed, role="user")
    db.add(new_user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.warning(f"Registration rejected: username '{user.username}' is already taken")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Username '{user.username}' is already taken")
    logger.info(f"Success: User '{user.username}' registered with role 'user'.")
    return {"message": "User registered successfully"}

@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    logger.info(f"Login attempt for user: '{form_data.username}'")
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalars().first()
    if not user or not verify_pass(form_data.password, user.hashed_password):
        logger.warning(f"Failed login: Incorrect credentials for '{form_data.username}'")
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    logger.info(f"Success: User '{user.username}' logged in successfully.")
    access_token = create_token(data={"sub": user.username, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/v1/admin/all-users")
async def get_all_users(admin_user: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    users = result.scalars().all()
    return [{"id": u.id, "username": u.username, "role": u.role} for u in users]

@app.get("/api/v1/ml/models")
async def get_ml_models(current_user: User = Depends(get_active_user)):
    return list_available_models()

@app.get("/api/v1/ml/model-categories")
async def get_ml_categories(current_user: User = Depends(get_active_user)):
    return {"categories": list_model_categories()}

@app.get("/api/v1/ml/model-details")
async def get_model_details(model_name: Optional[str] = None, current_user: User = Depends(get_active_user)):
    """Returns full model metadata including test results for frontend display.
    
    If model_name is provided, returns details for that single model.
    Otherwise returns list of all available models with full metadata.
    """
    models = list_available_models()
    
    if model_name:
        # Find single model by name
        matching = [m for m in models if m["name"] == model_name]
        if matching:
            return matching[0]
        raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")
    
    # Return all models
    return {"models": models}

@app.get("/api/v1/ml/training-modes")
async def get_training_modes(current_user: User = Depends(get_active_user)):
    """Returns available training modes and their descriptions."""
    modes_desc = {
        "manual": "User-defined hyperparameters - full control over training settings",
        "auto_tune": "Grid search optimization - automatically searches for optimal parameters",
        "auto_fine_tune": "Adaptive tuning - fine-tuning with reduced learning rates for stability",
        "llm_fine_tune": "AI-guided parameters - uses Google Gemini to suggest optimal hyperparameters",
        "auto_search": "Bayesian optimization - searches across multiple model candidates",
    }
    return {
        "modes": TRAINING_MODES,
        "descriptions": modes_desc,
    }

@app.get("/api/v1/ml/training-presets")
async def get_training_presets(current_user: User = Depends(get_active_user)):
    """Returns available training presets for quick configuration."""
    presets_info = []
    for preset_name, preset_config in TRAINING_PRESETS.items():
        presets_info.append({
            "name": preset_name,
            "description": preset_config.get("description", ""),
        })
    return {
        "presets": presets_info,
    }

@app.post("/api/v1/ml/suggest")
async def suggest_hyperparameters_endpoint(
    model_name: str,
    task_type: str = "classification",
    optimize_metric: str = "accuracy",
    dataset_name: Optional[str] = None,
    hf_dataset_url: Optional[str] = None,
    current_user: User = Depends(get_active_user),
):
    try:
        return {"suggested_hyperparameters": suggest_hyperparameters(model_name, task_type, optimize_metric, dataset_name, hf_dataset_url)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/api/v1/ml/datasets")
async def get_datasets(current_user: User = Depends(get_active_user)):
    return {"datasets": list_local_datasets()}

@app.post("/api/v1/ml/train")
async def train_model_endpoint(payload: TrainRequest, current_user: User = Depends(get_active_user), db: AsyncSession = Depends(get_db)):
    # The requested optimisation metric is passed through untouched: resolving or
    # remapping it here would hide the training internals from the HTTP layer and
    # would silently optimise for a different metric than the one requested.
    training_run = TrainingRun(
        owner_id=current_user.id,
        model_name=payload.model_name,
        dataset_source="local" if payload.dataset_name else "huggingface",
        dataset_tag=payload.dataset_name or payload.hf_dataset_url or "unknown",
        hf_dataset_url=payload.hf_dataset_url,
        hyperparameters=payload.hyperparameters or {},
        mode=payload.mode,
        env_id=payload.env_id,
        optimize_metric=payload.optimize_metric,
        model_candidates=payload.model_candidates,
        status="running",
    )
    db.add(training_run)
    await db.commit()
    await db.refresh(training_run)

    try:
        metrics, dataset_source, dataset_tag, artifact_path = await run_in_threadpool(
            train_model,
            payload.model_name,
            payload.dataset_name,
            payload.hf_dataset_url,
            payload.label_column,
            payload.test_size,
            payload.random_state,
            payload.hyperparameters or {},
            payload.sep,
            payload.usecols,
            payload.mode,
            payload.optimize_metric,
            payload.env_id,
            payload.model_candidates,
            payload.preset,
        )
        training_run.metrics = metrics
        training_run.artifact_path = artifact_path
        training_run.dataset_source = dataset_source
        training_run.dataset_tag = dataset_tag
        training_run.status = "completed"
        await db.commit()
        return {
            "run_id": training_run.id,
            "status": training_run.status,
            "artifact_path": artifact_path,
            "metrics": jsonable_encoder(metrics),
        }
    except Exception as exc:
        training_run.status = "failed"
        training_run.metrics = {"error": str(exc)}
        await db.commit()
        logger.exception("Model training failed")
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/api/v1/ml/runs")
async def list_training_runs(current_user: User = Depends(get_active_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TrainingRun).where(TrainingRun.owner_id == current_user.id).order_by(TrainingRun.created_at.desc()))
    runs = result.scalars().all()
    return [
        {
            "id": run.id,
            "model_name": run.model_name,
            "dataset_source": run.dataset_source,
            "dataset_tag": run.dataset_tag,
            "mode": run.mode,
            "env_id": run.env_id,
            "optimize_metric": run.optimize_metric,
            "model_candidates": run.model_candidates,
            "status": run.status,
            "artifact_path": run.artifact_path,
            "metrics": run.metrics,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        }
        for run in runs
    ]

@app.get("/api/v1/ml/runs/{run_id}")
async def get_training_run(run_id: int, current_user: User = Depends(get_active_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TrainingRun).where(TrainingRun.id == run_id, TrainingRun.owner_id == current_user.id))
    run = result.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="Training run not found")
    return {
        "id": run.id,
        "model_name": run.model_name,
        "dataset_source": run.dataset_source,
        "dataset_tag": run.dataset_tag,
        "hf_dataset_url": run.hf_dataset_url,
        "hyperparameters": run.hyperparameters,
        "metrics": run.metrics,
        "artifact_path": run.artifact_path,
        "status": run.status,
        "mode": run.mode,
        "env_id": run.env_id,
        "optimize_metric": run.optimize_metric,
        "model_candidates": run.model_candidates,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
    }

@app.get("/api/v1/ml/runs/{run_id}/artifact")
async def download_artifact(run_id: int, current_user: User = Depends(get_active_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TrainingRun).where(TrainingRun.id == run_id, TrainingRun.owner_id == current_user.id))
    run = result.scalars().first()
    if not run or not run.artifact_path:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if not Path(run.artifact_path).exists():
        raise HTTPException(status_code=404, detail="Artifact file missing")
    return FileResponse(run.artifact_path, filename=Path(run.artifact_path).name)
