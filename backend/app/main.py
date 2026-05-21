from fastapi import FastAPI, Depends, HTTPException, Header, status
import logging
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.encoders import jsonable_encoder
from jose import JWTError, jwt
from pathlib import Path
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from .database import get_db, engine, Base
from .models import User, TrainingRun
from .auth import ALGORITHM, SECRET_KEY, verify_pass, create_token, hash_pass
from .model_training import list_available_models, list_local_datasets, list_model_categories, suggest_hyperparameters, train_model, TRAINING_MODES, TRAINING_PRESETS
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

app = FastAPI(title="PrimeTrade AutoML API")

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
    if authorization:
        try:
            scheme, _, token = authorization.partition(" ")
            if scheme.lower() == "bearer" and token:
                payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                username: str = payload.get("sub")
                if username:
                    result = await db.execute(select(User).where(User.username == username))
                    user = result.scalars().first()
                    if user:
                        return user
        except JWTError:
            pass

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
    role: Optional[str] = "user"

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
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401)
    except JWTError:
        raise HTTPException(status_code=401)

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if user is None:
        raise HTTPException(status_code=401)
    return user

async def get_current_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user

@app.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.post("/api/v1/register")
async def register(user: UserCreate, db=Depends(get_db)):
    logger.info(f"Registration attempt for new user: '{user.username}'")
    safe_password = user.password[:72]
    hashed = hash_pass(safe_password)
    new_user = User(username=user.username, hashed_password=hashed, role=user.role)
    db.add(new_user)
    await db.commit()
    logger.info(f"Success: User '{user.username}' registered with role '{user.role}'.")
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
        "llm_fine_tune": "AI-guided parameters - uses OpenAI to suggest optimal hyperparameters",
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
