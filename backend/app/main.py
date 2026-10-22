from fastapi import FastAPI, Depends, File, HTTPException, Header, Request, UploadFile, status
from starlette.datastructures import Headers
import json
import logging
import os
import time
import uuid
from collections import defaultdict, deque
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
from .database import get_db, engine, AsyncSessionLocal
from .models import Dataset, User, TrainingRun
from .auth import (
    ALGORITHM,
    SECRET_KEY,
    create_token,
    dummy_password_hash,
    hash_pass,
    is_reserved_username,
    validate_credentials,
    verify_pass,
)
from . import datasets as datasets_registry
from .datasets import (
    DatasetError,
    dataset_to_dict,
    resolve_storage_path,
    unique_dataset_name,
)
from .model_training import (
    MODEL_DIR,
    TRAINING_MODES,
    TRAINING_PRESETS,
    list_available_models,
    list_model_categories,
    suggest_hyperparameters,
    train_model,
)
from .settings import REPO_ROOT, datasets_root
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Callable, List, Tuple


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
    await seed_builtin_datasets()
    # The hash of the dummy password is computed on the first unknown-user
    # login, which would make that one request twice as slow as the others.
    # It is computed here instead, while the application starts.
    await run_in_threadpool(dummy_password_hash)
    yield


async def seed_builtin_datasets() -> None:
    """Register the datasets that ship with the repository.

    The CSV files of ``data/`` are rows of the registry, so that the frontend
    sees one list of datasets - the built-in ones and the uploaded ones - and
    a training request never carries a path.
    """
    from . import datasets as registry

    async with AsyncSessionLocal() as session:
        for path in registry.builtin_files():
            try:
                storage_path = registry.relative_storage_path(path)
            except registry.DatasetError as exc:
                # A file of the data directory that is not a dataset of this
                # application (a symlink that points somewhere else) is
                # skipped: the startup must not fail because of it.
                logger.warning("The built-in dataset %s is skipped: %s", path.name, exc)
                continue
            try:
                existing = (
                    await session.execute(
                        select(Dataset).where(Dataset.storage_path == storage_path)
                    )
                ).scalars().first()
                columns, rows, label = registry.describe_csv(path)
                size_bytes = path.stat().st_size
            except registry.DatasetError as exc:
                logger.warning("The built-in dataset %s is skipped: %s", path.name, exc)
                continue
            except Exception as exc:  # pragma: no cover - the safety net
                # A file that the application cannot describe must never stop
                # the startup: the server has to come up, and the other
                # datasets have to be usable.
                logger.warning(
                    "The built-in dataset %s is skipped: %s", path.name, exc
                )
                continue
            if existing is None:
                session.add(
                    Dataset(
                        owner_id=None,
                        name=path.name,
                        storage_path=storage_path,
                        source="builtin",
                        size_bytes=size_bytes,
                        row_count=rows,
                        columns=columns,
                        label_column=label,
                    )
                )
            else:
                # The name of an existing row is not overwritten: a symlink
                # that points at another file of the directory would take the
                # name of the dataset it points at.
                existing.size_bytes = size_bytes
                existing.row_count = rows
                existing.columns = columns
                existing.label_column = label
        for path in registry.builtin_folders():
            try:
                storage_path = registry.relative_storage_path(path)
            except registry.DatasetError as exc:
                logger.warning("The built-in dataset %s is skipped: %s", path.name, exc)
                continue
            existing = (
                await session.execute(
                    select(Dataset).where(Dataset.storage_path == storage_path)
                )
            ).scalars().first()
            if existing is None:
                session.add(
                    Dataset(
                        owner_id=None,
                        name=path.name,
                        storage_path=storage_path,
                        source="folder",
                        size_bytes=None,
                        row_count=None,
                        columns=[],
                        label_column=None,
                    )
                )
        await session.commit()


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

# --- CORS -------------------------------------------------------------------
# The browser SPA is served by Vite (frontend/vite.config.js -> port 3000) and
# calls this API cross-origin (3000 -> 8010). The allow-list is therefore
# explicit: ``allow_origins=["*"]`` together with ``allow_credentials=True`` is
# rejected by the Fetch standard (a wildcard is not allowed on a credentialed
# request) and, at runtime, makes the server reflect *any* origin with
# credentials enabled.
#
# CORS_ORIGINS is a comma-separated list of the allowed origins. When it is not
# set the development origins of the SPA are used, so a misconfigured
# environment never silently opens the API to every origin. The special value
# "*" restores the old behaviour and is only valid without credentials.
DEFAULT_CORS_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")


def _cors_origins() -> List[str]:
    """The origins that are allowed to call the API from a browser."""
    raw = os.getenv("CORS_ORIGINS", "")
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if not origins:
        return list(DEFAULT_CORS_ORIGINS)
    return origins


_CORS_ORIGINS = _cors_origins()
_CORS_ALLOWS_ANY = "*" in _CORS_ORIGINS

# --- the size of an upload ---------------------------------------------------
# The body of an upload is parsed by the framework before the endpoint runs:
# the file part is written to a temporary file of the operating system as it
# arrives. A limit that is only checked inside the endpoint therefore bounds
# the memory of the process, but not the disk of the server: a request
# without a length could write an arbitrary amount of it. The body is
# therefore read with a cap, before the framework sees it.
UPLOAD_PATH = "/api/v1/ml/datasets/upload"
# The body of a multipart request is a little bigger than the file it carries:
# the boundary and the headers of the part are part of it.
UPLOAD_BODY_OVERHEAD_BYTES = 8 * 1024


class UploadSizeLimit:
    """Refuse an upload whose body is too big, before it is parsed.

    The length of the body is used when the client sends one: the request is
    then refused without reading a byte of it. A request without a length is
    read with a cap, and it is refused as soon as it is bigger than the cap,
    so that the framework never sees a body it would write to the disk.
    """

    def __init__(self, app, path: str, limit: Callable[[], int]):
        self.app = app
        self.path = path
        # The limit is read on every request, and not once at the startup:
        # the limit of an upload is a setting, and a setting that is read
        # once would need a restart to change.
        self.limit = limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") != self.path:
            await self.app(scope, receive, send)
            return

        limit = int(self.limit())
        headers = Headers(scope=scope)
        length = headers.get("content-length")
        if length and length.isdigit():
            if int(length) > limit:
                await self._refuse(send, limit)
                return
            # The length is known and it fits: the body is passed on as it
            # arrives, and the framework writes it to its temporary file.
            # Copying it into the memory of the process would only double
            # what the request already holds.
            await self.app(scope, receive, send)
            return

        # The length is unknown: the body is read with a cap, and it is
        # refused as soon as it is bigger than the cap.
        body = bytearray()
        more = True
        while more:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > limit:
                await self._refuse(send, limit)
                return
            more = message.get("more_body", False)

        # The body was read with the cap and it is small enough: it is
        # replayed to the application, which parses it as usual.
        replayed = False

        async def replay():
            nonlocal replayed
            if replayed:
                return {"type": "http.disconnect"}
            replayed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)

    async def _refuse(self, send, limit: int) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    # The body of the request was not read: the connection
                    # cannot carry another request, so it is closed.
                    (b"connection", b"close"),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": json.dumps(
                    {"detail": f"The upload is bigger than the limit of {limit} bytes."}
                ).encode(),
            }
        )


app.add_middleware(
    # The guard on the size of an upload is added before the CORS, so that it
    # is inside it: a refusal that has no CORS headers is an opaque error in
    # the browser.
    UploadSizeLimit,
    path=UPLOAD_PATH,
    limit=lambda: datasets_registry.MAX_UPLOAD_BYTES + UPLOAD_BODY_OVERHEAD_BYTES,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    # A wildcard origin cannot be combined with credentials: the browser
    # rejects such a response, and the server would otherwise reflect the
    # requesting origin with the credentials enabled.
    allow_credentials=not _CORS_ALLOWS_ANY,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# --- rate limiting ----------------------------------------------------------
# A login endpoint that is not limited can be used to try passwords, and an
# un-limited registration endpoint can be used to fill the database. The
# limiter counts the attempts of every client in a sliding window. It lives in
# the memory of the process, which is enough for the single-process deployment
# this application runs in; a multi-worker deployment would need a shared
# store.
LOGIN_RATE_LIMIT = int(os.getenv("LOGIN_RATE_LIMIT", "10"))
REGISTER_RATE_LIMIT = int(os.getenv("REGISTER_RATE_LIMIT", "20"))
UPLOAD_RATE_LIMIT = int(os.getenv("UPLOAD_RATE_LIMIT", "20"))
RATE_LIMIT_WINDOW_SECONDS = 60.0

# The maximum number of clients the limiter remembers. Without it, an
# unauthenticated client could fill the memory of the process by sending
# requests with a different username every time.
RATE_LIMIT_MAX_CLIENTS = int(os.getenv("RATE_LIMIT_MAX_CLIENTS", "10000"))

# The attempts per key. A failed login is counted twice: under the address
# alone, so that one client cannot spray one password over many accounts, and
# under the address *and* the account, so that one client cannot hammer one
# account. The account is deliberately not a key of its own: a limit that
# counts every attempt on an account, wherever it comes from, lets an
# attacker lock a victim out of their own account.
_login_attempts: Dict[str, deque] = defaultdict(deque)


def _client_address(request: Request) -> str:
    """The address of the client that made the request."""
    return request.client.host if request.client else "unknown"


def _prune_attempts(now: float) -> None:
    """Forget the attempts that fell out of the window.

    The entries of the clients that are not seen any more would otherwise
    stay in the memory of the process forever.
    """
    for key in list(_login_attempts.keys()):
        attempts = _login_attempts[key]
        while attempts and now - attempts[0] > RATE_LIMIT_WINDOW_SECONDS:
            attempts.popleft()
        if not attempts:
            del _login_attempts[key]


def _check_rate_limit(key: str, limit: int) -> None:
    """Raise 429 when the client made too many attempts.

    The window is a sliding one: an attempt that is older than the window is
    forgotten, so a client that stops trying gets its budget back.
    """
    if limit <= 0:
        return
    now = time.monotonic()
    attempts = _login_attempts[key]
    while attempts and now - attempts[0] > RATE_LIMIT_WINDOW_SECONDS:
        attempts.popleft()
    if len(attempts) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again in a minute.",
        )


def _record_rate_limit(key: str) -> None:
    """Count an attempt against the client's budget."""
    now = time.monotonic()
    _login_attempts[key].append(now)
    if len(_login_attempts) > RATE_LIMIT_MAX_CLIENTS:
        _prune_attempts(now)
        if len(_login_attempts) > RATE_LIMIT_MAX_CLIENTS:
            # The window did not free anything: the oldest entry is dropped.
            oldest = min(
                _login_attempts,
                key=lambda name: _login_attempts[name][0] if _login_attempts[name] else now,
            )
            _login_attempts.pop(oldest, None)


def _forget_rate_limit(key: str) -> None:
    """Give the client its budget back after a successful attempt."""
    _login_attempts.pop(key, None)


def reset_rate_limits() -> None:
    """Forget every recorded attempt.

    The test suite uses it so that every test starts with a clean budget.
    """
    _login_attempts.clear()


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    """The user of the request, or 401.

    Every ML endpoint requires a valid token. The previous behaviour - a
    request without a header fell back to a shared ``anonymous`` account -
    meant that all the unauthenticated callers shared one history, that the
    account could be logged into with the password ``anonymous``, and that a
    dataset uploaded by one of them belonged to all of them.

    The dependency is the OAuth2 bearer scheme, so the OpenAPI document
    describes the endpoints as protected and the Swagger UI offers an
    "Authorize" button. The scheme answers 401 by itself when the header is
    missing or malformed.
    """
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

class UserCreate(BaseModel):
    username: str
    password: str
    # Accepted for backwards compatibility but ignored: a client may never choose its
    # own role. Admin promotion is a manual database operation.
    role: Optional[str] = Field(default="user", description="Ignored: new accounts are always created with role 'user'.")

class TrainRequest(BaseModel):
    model_name: str
    # The dataset of the training, as a row of the registry. The client never
    # sends a path: the server resolves the row to a file inside the datasets
    # root, which is what makes it impossible to read a file outside of it.
    dataset_id: Optional[int] = None
    # The name of a dataset. It is resolved through the registry as well, so
    # it cannot be used to reach a file either; it exists for the clients that
    # do not know the ids yet.
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

async def get_current_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user

@app.post("/api/v1/register")
async def register(user: UserCreate, request: Request, db=Depends(get_db)):
    address = _client_address(request)
    _check_rate_limit(f"register:{address}", REGISTER_RATE_LIMIT)
    reason = validate_credentials(user.username, user.password)
    if reason:
        logger.warning(f"Registration rejected for '{user.username}': {reason}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)
    logger.info(f"Registration attempt for new user: '{user.username}'")
    safe_password = user.password[:72]
    # bcrypt is a CPU-bound hash: running it in the event loop blocks every
    # other request for the duration of the hash.
    hashed = await run_in_threadpool(hash_pass, safe_password)
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
    _record_rate_limit(f"register:{address}")
    return {"message": "User registered successfully"}

@app.post("/token")
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    # Only a *failed* login counts against the budget: a user who signs in
    # repeatedly is not an attacker, and locking them out would be a denial of
    # service they did not deserve.
    address = _client_address(request)
    account_key = f"login:{address}:{form_data.username.strip().lower()}"
    address_key = f"login-address:{address}"
    # The address budget stops one client from spraying one password over
    # many accounts; the account budget stops one client from hammering one
    # account. Neither is a budget of the account alone, so a victim can
    # always log in from another address.
    _check_rate_limit(address_key, LOGIN_RATE_LIMIT * 3)
    _check_rate_limit(account_key, LOGIN_RATE_LIMIT)
    if is_reserved_username(form_data.username):
        # The reserved names are refused at the login as well as at the
        # registration: a row with that name may still exist in a database
        # that predates the removal of the shared account.
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    logger.info(f"Login attempt for user: '{form_data.username}'")
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalars().first()
    # The password is verified even when the user does not exist, against a
    # dummy hash: otherwise the answer arrives measurably faster for an
    # unknown user, which turns the endpoint into an oracle for the existence
    # of an account.
    stored_hash = user.hashed_password if user else dummy_password_hash()
    password_matches = await run_in_threadpool(verify_pass, form_data.password, stored_hash)
    if not user or not password_matches:
        logger.warning(f"Failed login: Incorrect credentials for '{form_data.username}'")
        _record_rate_limit(account_key)
        _record_rate_limit(address_key)
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    logger.info(f"Success: User '{user.username}' logged in successfully.")
    access_token = create_token(data={"sub": user.username, "role": user.role})
    _forget_rate_limit(account_key)
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/v1/admin/all-users")
async def get_all_users(admin_user: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    users = result.scalars().all()
    return [{"id": u.id, "username": u.username, "role": u.role} for u in users]

@app.get("/api/v1/ml/models")
async def get_ml_models(current_user: User = Depends(get_current_user)):
    return list_available_models()

@app.get("/api/v1/ml/model-categories")
async def get_ml_categories(current_user: User = Depends(get_current_user)):
    return {"categories": list_model_categories()}

@app.get("/api/v1/ml/model-details")
async def get_model_details(model_name: Optional[str] = None, current_user: User = Depends(get_current_user)):
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
async def get_training_modes(current_user: User = Depends(get_current_user)):
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
async def get_training_presets(current_user: User = Depends(get_current_user)):
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
    current_user: User = Depends(get_current_user),
):
    try:
        return {"suggested_hyperparameters": suggest_hyperparameters(model_name, task_type, optimize_metric, dataset_name, hf_dataset_url)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

def _public_error(exc: Exception) -> str:
    """The message of a failure that is safe to show to the client.

    The text of an exception carries the internals of the server: the
    absolute path of a file, the name of a class, the traceback of a library.
    The client gets the reason of the failure, without the paths.
    """
    message = str(exc)
    for root in (str(REPO_ROOT), str(datasets_root()), str(MODEL_DIR)):
        if root and root in message:
            message = message.replace(root, "<server>")
    return message


@app.get("/api/v1/ml/datasets")
async def get_datasets(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The datasets the caller can train on.

    The built-in ones belong to everybody, the uploaded ones to the user who
    uploaded them. A dataset is a row, so the client never sees a path.
    """
    result = await db.execute(
        select(Dataset).where(
            (Dataset.owner_id == current_user.id) | (Dataset.owner_id.is_(None))
        ).order_by(Dataset.name)
    )
    datasets = result.scalars().all()
    return {"datasets": [dataset_to_dict(dataset) for dataset in datasets]}


@app.get("/api/v1/ml/datasets/{dataset_id}")
async def get_dataset(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """One dataset, with its columns and the label column that is suggested."""
    dataset = await _dataset_for_user(dataset_id, current_user, db)
    return dataset_to_dict(dataset)


def _remove_stored_upload(storage_path: str) -> None:
    """Remove the file of an upload that could not be registered.

    A file that no row points at is a file that nobody can reach: it would
    stay on the disk of the server until somebody deletes it by hand.
    """
    try:
        path = resolve_storage_path(storage_path)
    except DatasetError:
        return
    try:
        path.unlink()
    except OSError:
        logger.warning("The file of the upload %s could not be removed", storage_path)


@app.post("/api/v1/ml/datasets/upload")
async def upload_dataset(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Store a CSV file as a dataset of the caller.

    The file is written under the uploads directory of the user with a
    generated name, and it is registered as a row: a training request refers
    to it by its id.
    """
    _check_rate_limit(f"upload:{_client_address(request)}", UPLOAD_RATE_LIMIT)
    _record_rate_limit(f"upload:{_client_address(request)}")

    # The values of the session are read before the first commit: a rollback
    # expires them, and reading them afterwards is an error.
    owner_id = current_user.id
    username = current_user.username

    # The body is read with a limit: reading it completely first would let a
    # single request fill the memory of the process, whatever the size limit
    # says afterwards.
    content = await file.read(datasets_registry.MAX_UPLOAD_BYTES + 1)
    filename = file.filename or ""

    # The file is inspected and written in a thread: a file of fifty megabytes
    # takes a second to read, and the event loop serves the other requests
    # while it does.
    try:
        columns, rows, label = await run_in_threadpool(
            datasets_registry.validate_upload, filename, content
        )
        name, storage_path = await run_in_threadpool(
            datasets_registry.write_upload, owner_id, filename, content
        )
    except DatasetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    registered = False
    try:
        # The name of a dataset has to be unambiguous for the display: a
        # built-in dataset and an upload may have the same name.
        taken = await db.execute(
            select(Dataset.name).where(
                (Dataset.owner_id == owner_id) | (Dataset.owner_id.is_(None))
            )
        )
        name = unique_dataset_name(name, [row[0] for row in taken.all()])

        dataset = Dataset(
            owner_id=owner_id,
            name=name,
            storage_path=storage_path,
            source="upload",
            size_bytes=len(content),
            row_count=rows,
            columns=columns,
            label_column=label,
        )
        db.add(dataset)
        try:
            await db.commit()
        except IntegrityError:
            # Two uploads of the same name arrived at the same time and the
            # database refused the second one. The name is the only thing that
            # collided: the file of this upload is fine, so it is registered
            # with the next free name.
            await db.rollback()
            taken = await db.execute(
                select(Dataset.name).where(
                    (Dataset.owner_id == owner_id) | (Dataset.owner_id.is_(None))
                )
            )
            name = unique_dataset_name(
                f"{name} ({uuid.uuid4().hex[:8]})", [row[0] for row in taken.all()]
            )
            dataset = Dataset(
                owner_id=owner_id,
                name=name,
                storage_path=storage_path,
                source="upload",
                size_bytes=len(content),
                row_count=rows,
                columns=columns,
                label_column=label,
            )
            db.add(dataset)
            await db.commit()
        registered = True
    except HTTPException:
        raise
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=400,
            detail="The dataset could not be registered, please try again.",
        ) from None
    finally:
        if not registered:
            # No row points at the file: it would stay on the disk of the
            # server until somebody deletes it by hand.
            _remove_stored_upload(storage_path)

    await db.refresh(dataset)
    logger.info(
        "User '%s' uploaded the dataset '%s' (%s rows)",
        username,
        name,
        rows,
    )
    return dataset_to_dict(dataset)


async def _dataset_for_user(
    dataset_id: int, current_user: User, db: AsyncSession
) -> Dataset:
    """The dataset with that id, if the caller may use it.

    A dataset that belongs to another user is not found: the answer must not
    tell a caller that an id exists but is not theirs.
    """
    result = await db.execute(
        select(Dataset).where(
            Dataset.id == dataset_id,
            (Dataset.owner_id == current_user.id) | (Dataset.owner_id.is_(None)),
        )
    )
    dataset = result.scalars().first()
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


async def _dataset_for_training(
    payload: TrainRequest, current_user: User, db: AsyncSession
) -> Tuple[Optional[Dataset], Optional[str]]:
    """The dataset of a training request, and the path the trainer reads.

    The path comes from the registry, never from the client. A request that
    carries a name instead of an id is resolved through the registry as well,
    so there is exactly one way from a request to a file.

    ``(None, None)`` means that the request has no local dataset: either it
    names a Hugging Face dataset, or the model is a reinforcement learning
    model, which trains in an environment and needs no data.
    """
    if payload.hf_dataset_url and (payload.dataset_id is not None or payload.dataset_name):
        raise HTTPException(
            status_code=400,
            detail=(
                "A request carries either a dataset of the registry or a "
                "Hugging Face dataset, not both."
            ),
        )
    if payload.hf_dataset_url:
        return None, None

    if payload.dataset_id is not None:
        dataset = await _dataset_for_user(payload.dataset_id, current_user, db)
    elif payload.dataset_name:
        result = await db.execute(
            select(Dataset).where(
                Dataset.name == payload.dataset_name,
                (Dataset.owner_id == current_user.id) | (Dataset.owner_id.is_(None)),
            ).order_by(Dataset.owner_id.is_(None), Dataset.id)
        )
        dataset = result.scalars().first()
        if dataset is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"There is no dataset named '{payload.dataset_name}'. "
                    f"Use the id of a dataset of the list."
                ),
            )
    else:
        raise HTTPException(
            status_code=400,
            detail="Either dataset_id or hf_dataset_url must be provided.",
        )

    try:
        path = resolve_storage_path(dataset.storage_path)
    except DatasetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    if not path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"The file of the dataset '{dataset.name}' is missing on the server.",
        )
    return dataset, dataset.storage_path


def _needs_a_dataset(model_name: str) -> bool:
    """Whether the model of a request trains on a dataset.

    A reinforcement learning model trains in an environment (the ``env_id`` of
    the request), so it needs no data.
    """
    from .model_training import get_model_entry

    return get_model_entry(model_name).get("category") != "reinforcement-learning"


@app.post("/api/v1/ml/train")
async def train_model_endpoint(payload: TrainRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # The requested optimisation metric is passed through untouched: resolving or
    # remapping it here would hide the training internals from the HTTP layer and
    # would silently optimise for a different metric than the one requested.
    if _needs_a_dataset(payload.model_name):
        dataset, storage_path = await _dataset_for_training(payload, current_user, db)
    else:
        # A reinforcement learning model trains in an environment, so it needs
        # no data.
        dataset, storage_path = None, None

    if dataset is not None:
        dataset_source, dataset_tag = "local", dataset.name
    elif payload.hf_dataset_url:
        dataset_source, dataset_tag = "huggingface", payload.hf_dataset_url
    else:
        dataset_source, dataset_tag = "rl", payload.env_id or "unknown"

    training_run = TrainingRun(
        owner_id=current_user.id,
        model_name=payload.model_name,
        dataset_source=dataset_source,
        dataset_tag=dataset_tag,
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
            storage_path,
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
        # The tag of a local dataset is its name: the path the registry
        # resolved it to is an internal detail of the server.
        training_run.dataset_tag = dataset.name if dataset is not None else dataset_tag
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
        training_run.metrics = {"error": _public_error(exc)}
        await db.commit()
        logger.exception("Model training failed")
        raise HTTPException(status_code=400, detail=_public_error(exc))

@app.get("/api/v1/ml/runs")
async def list_training_runs(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
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
async def get_training_run(run_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
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
async def download_artifact(run_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TrainingRun).where(TrainingRun.id == run_id, TrainingRun.owner_id == current_user.id))
    run = result.scalars().first()
    if not run or not run.artifact_path:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if not Path(run.artifact_path).exists():
        raise HTTPException(status_code=404, detail="Artifact file missing")
    return FileResponse(run.artifact_path, filename=Path(run.artifact_path).name)
