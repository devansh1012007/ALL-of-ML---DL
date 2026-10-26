from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Header,
    Request,
    UploadFile,
    status,
)
from starlette.datastructures import Headers
from starlette.datastructures import UploadFile as StarletteUploadFile
import asyncio
import functools
import io
import json
import logging
import os
import shutil
import socket
import time
import uuid
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.encoders import jsonable_encoder
from jose import JOSEError, jwt
from pathlib import Path
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_, update, func
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from .base import Base
from .database import get_db, engine, AsyncSessionLocal
from .models import Dataset, User, TrainingRun, Deployment
from .auth import (
    ACCESS_TOKEN_MINUTES,
    ALGORITHM,
    BCRYPT_MAX_BYTES,
    SECRET_KEY,
    create_token,
    decode_token,
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
from . import model_training as model_training_module
from . import admin as admin_module
from . import inference as inference_module
from . import sessions
from . import rate_limit as rate_limit_module
from . import cleanup
from . import observability
from . import progress
from . import executor as executor_module
from .admin import audit as write_audit
from .admin import REGISTRATION_MODE
from .bundles import BundleError
from .inference import PredictRequest, load_bundle_of_run, run_prediction
from .quotas import (
    QuotaRefusal,
    check_predict_rate,
    check_submit_quota,
    check_upload_quota,
    effective_quota,
    seed_quota_profiles,
    user_usage,
)
from .tabular import FeatureInputError
from .model_training import (
    TRAINING_MODES,
    TRAINING_PRESETS,
    get_model_entry,
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
    global _slots_in_use
    # The validated configuration of plan H4: every variable is read and
    # checked once, a nonsense value is refused with a message that names it,
    # and the effective non-secret configuration is printed, so an operator
    # sees what the process actually uses. A secret is never printed.
    from .config import ConfigError, Settings

    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        raise RuntimeError(f"The configuration is not valid: {exc}") from None
    logger.info(
        "The effective configuration (secrets masked): %s",
        json.dumps(settings.effective_non_secret(), default=str),
    )
    await verify_schema()
    await reap_the_interrupted_runs()
    await seed_builtin_datasets()
    # The quota profiles of plan A3 and the first admin of plan A1 (the
    # bootstrap environment pair, when no admin exists). The manual database
    # edit for the first admin is gone.
    try:
        await admin_module.ensure_admin_and_profiles()
    except Exception:
        logger.exception("The startup seeding of the quota profiles failed")
    _slots_in_use = 0
    maintenance = None
    if TRAINING_IN_API:
        # Picks up the runs a restart left queued, and sweeps the dead ones.
        maintenance = asyncio.create_task(maintenance_loop())
    # The hash of the dummy password is computed on the first unknown-user
    # login, which would make that one request twice as slow as the others.
    # It is computed here instead, while the application starts.
    await run_in_threadpool(dummy_password_hash)
    try:
        yield
    finally:
        for task in [maintenance, *_background_tasks]:
            if task is not None:
                task.cancel()
        for task in [maintenance, *_background_tasks]:
            if task is not None:
                try:
                    await task
                except BaseException:
                    # Cancelled (or already finished with an error that was logged).
                    pass
        _background_tasks.clear()


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
                        # The content hash (plan E4) and the kind (plan F1)
                        # of the file: two names for one file are one
                        # dataset, and the kind says which family trains on it.
                        content_sha256=datasets_registry.content_sha256(path),
                        kind=datasets_registry.infer_dataset_kind(path, [c["name"] for c in columns]),
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
        try:
            await session.commit()
        except IntegrityError:
            # Two workers that start at the same time register the same
            # built-in dataset. The second one has to survive it: the rows
            # it wanted are already there.
            await session.rollback()
            logger.info("The built-in datasets were registered by another worker")


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

# --- the refresh cookie and the CORS allow-list (plan A2 / G2) ---------------
# The refresh token of section A2 travels in an httpOnly cookie, and a cookie
# is a credential: a deployment that serves it must name its origins
# explicitly. A wildcard there would make the browser reject every credentialed
# request, and the server would be an open refector anyway, so the ambiguity is
# refused at the startup instead of being discovered in the browser.
REFRESH_COOKIE_ENABLED = os.getenv("REFRESH_COOKIE_ENABLED", "1") != "0"
if REFRESH_COOKIE_ENABLED and _CORS_ALLOWS_ANY:
    raise RuntimeError(
        'CORS_ORIGINS contains "*": a deployment that sends the refresh cookie '
        "must name its allowed origins explicitly. Set CORS_ORIGINS to a "
        "comma-separated list, or set REFRESH_COOKIE_ENABLED=0 to run without "
        "browser sessions (API-key-only deployments)."
    )


# --- security headers (plan G2) ----------------------------------------------
# The headers a browser honours and the API cannot rely on the proxy for. HSTS
# is deliberately absent: it belongs to the TLS-terminating proxy, and sending
# it over plain HTTP from the application would be a lie the browser caches.
class SecurityHeaders:
    """Add the static security headers to every response."""

    HEADERS = (
        (b"x-content-type-options", b"nosniff"),
        (b"referrer-policy", b"no-referrer"),
        # The API serves no frames and is not framed: both directions are
        # closed. The style/script sources are 'self' - the SPA is served by
        # its own origin and calls the API cross-origin, which CSP does not
        # restrict (it restricts what the *response's* origin may load, and
        # the API loads nothing).
        (b"content-security-policy",
         b"default-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
         b"form-action 'self'"),
    )

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}
                for name, value in self.HEADERS:
                    if name not in present:
                        headers.append((name, value))
                message = dict(message, headers=headers)
            await send(message)

        await self.app(scope, receive, send_with_headers)


app.add_middleware(SecurityHeaders)

# The request log (plan H3): one JSON line per request, with the request id
# the client can echo and the run id when the path carries one. It sits
# inside everything else, so a refusal of any middleware is logged too.
app.add_middleware(observability.RequestLogMiddleware)

# The states of a run. The column is a free string, so a new state needs no
# migration, but the names live here: the worker, the reaper and the tests
# have to agree on them.
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

# --- the training queue -----------------------------------------------------
# The rows of ``training_runs`` are the queue. A worker claims the oldest
# queued run with one atomic UPDATE, says that it is alive every few seconds
# while it trains, and a sweeper fails the running runs whose heartbeat
# stopped. Nothing here lives in the memory of one process, so a restart loses
# no queued run and a second process cannot fail the runs of the first.
#
# How many trainings one process runs at the same time.
TRAINING_CONCURRENCY = max(1, int(os.getenv("TRAINING_CONCURRENCY", "1")))
# How often a worker writes ``heartbeat_at``, and how old a heartbeat may be
# before its run is considered dead (several beats may be lost to a slow disk).
TRAINING_HEARTBEAT_SECONDS = float(os.getenv("TRAINING_HEARTBEAT_SECONDS", "5"))
TRAINING_STALE_SECONDS = float(os.getenv("TRAINING_STALE_SECONDS", "30"))
# How often the maintenance loop looks for stale runs and for queued ones that
# no process picked up (the runs another process queued, or left behind).
QUEUE_POLL_SECONDS = float(os.getenv("QUEUE_POLL_SECONDS", "5"))
# "0" makes the web process only enqueue: the trainings then run in separate
# ``python -m backend.app.worker`` processes.
TRAINING_IN_API = os.getenv("TRAINING_IN_API", "1") != "0"
# Who this process is, as written in ``worker_id``.
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"

_slots_in_use = 0
_background_tasks: set = set()


def _now() -> datetime:
    """The time as the columns store it: timezone-aware UTC."""
    return datetime.now(timezone.utc)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# --- rate limiting (plan A8) --------------------------------------------------
# The limiter used to live in the memory of the process, which made it a lie
# the moment a second worker started: every process had its own budget. The
# counts live in the ``rate_events`` table now (one row per counted attempt),
# so every worker of the deployment shares one budget per key. The mechanics
# are in ``rate_limit.py``; the limits themselves are here, next to the
# endpoints they guard.
LOGIN_RATE_LIMIT = int(os.getenv("LOGIN_RATE_LIMIT", "10"))
REGISTER_RATE_LIMIT = int(os.getenv("REGISTER_RATE_LIMIT", "20"))
UPLOAD_RATE_LIMIT = int(os.getenv("UPLOAD_RATE_LIMIT", "20"))
# Re-exported for the tests and the operators that read one place.
RATE_LIMIT_WINDOW_SECONDS = rate_limit_module.RATE_LIMIT_WINDOW_SECONDS

# The addresses of the reverse proxies this deployment sits behind. Only when
# the socket address of the request is one of these is the ``X-Forwarded-For``
# header believed - and even then the walk starts at the right, because a
# client can put anything it likes in the left of that list. Without the
# setting the socket address is used, which is the only value nobody can
# forge.
TRUSTED_PROXIES = {
    entry.strip()
    for entry in os.getenv("TRUSTED_PROXIES", "").split(",")
    if entry.strip()
}


def _client_address(request: Request) -> str:
    """The address of the client that made the request.

    The socket address, unless the request arrived through a proxy this
    deployment declared trusted (``TRUSTED_PROXIES``); in that case the
    forward chain is read from the right, skipping the trusted proxies, and
    the first address nobody vouched for is the client. An attacker can write
    anything into the left of the list, so the left is never the answer.
    """
    socket_address = request.client.host if request.client else "unknown"
    if not TRUSTED_PROXIES or socket_address not in TRUSTED_PROXIES:
        return socket_address
    forwarded = request.headers.get("x-forwarded-for", "")
    if not forwarded:
        return socket_address
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    for hop in reversed(hops):
        if hop not in TRUSTED_PROXIES:
            return hop
    # Every hop is a proxy we vouch for: the client is the leftmost entry.
    return hops[0] if hops else socket_address


async def _check_rate_limit(db: AsyncSession, key: str, limit: int) -> None:
    """Raise 429 when the key made too many attempts in the window."""
    try:
        await rate_limit_module.check_rate_limit(db, key, limit)
    except rate_limit_module.RateLimitExceeded as exceeded:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=exceeded.detail
        ) from None


async def _record_rate_limit(db: AsyncSession, key: str) -> None:
    """Count an attempt against the key's budget."""
    await rate_limit_module.record_rate_limit(db, key)


async def _forget_rate_limit(db: AsyncSession, key: str) -> None:
    """Give the key its budget back after a successful attempt."""
    await rate_limit_module.forget_rate_limit(db, key)


async def reset_rate_limits(db: AsyncSession) -> None:
    """Forget every recorded attempt (the test suite and the admin tooling)."""
    await rate_limit_module.reset_rate_limits(db)


def reset_rate_limits_sync() -> None:
    """The test-suite bridge: a synchronous reset against the configured
    database, on its own engine, on its own loop.

    The application engine belongs to the event loop of the process; the
    fixture that clears the budget runs outside it. A throwaway engine,
    created and disposed inside one ``asyncio.run``, is the dialect-neutral
    way to do that (a plain ``DELETE FROM rate_events``).
    """
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from .settings import DATABASE_URL

    async def _reset():
        engine = create_async_engine(DATABASE_URL)
        try:
            async with engine.begin() as connection:
                await connection.execute(text("DELETE FROM rate_events"))
        finally:
            await engine.dispose()

    asyncio.run(_reset())


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
        payload = decode_token(token)
    except JOSEError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token", headers={"WWW-Authenticate": "Bearer"}) from None
    username: str = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    # The lifecycle state of the account (plan A1): a suspended or unapproved
    # account stops working at the next request, because the row is read from
    # the database every time - the token itself never has to expire.
    if getattr(user, "status", "active") != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    # The revocation of a session (plan A2): the token carries the
    # ``token_version`` it was issued with, and any change that must end
    # sessions (password change, suspension, role change) increments the
    # column. A token from before the change is then an old token, and an old
    # token is rejected here. A token that predates the claim at all is
    # treated as version 0, so it survives until the first bump - a
    # deployment that adopts the check does not log everyone out at once.
    issued_version = int(payload.get("token_version") or 0)
    if issued_version < int(getattr(user, "token_version", 0) or 0):
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
    # Overrides the guess made from the label column ("classification" or
    # "regression"); None keeps the guess.
    task_type: Optional[str] = None
    # The user-steerable preprocessing options of plan C6 (scale,
    # numeric_impute, categorical, max_categories, drop_columns, class_weight).
    # Every default equals the behaviour before the option existed.
    preprocessing: Optional[Dict[str, Any]] = None
    # The split and leakage guards of plan C7: method (auto | stratified |
    # random | chronological | group), time_column, group_column, dedupe.
    split: Optional[Dict[str, Any]] = None
    # The time column of a chronological split or a forecast (plan F3).
    time_column: Optional[str] = None
    # Folds of the cross-validation of the tabular models; 0 turns it off.
    cv_folds: int = Field(5, ge=0, le=20)

async def get_current_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user

@app.post("/api/v1/register")
async def register(
    user: UserCreate,
    request: Request,
    invite_code: Optional[str] = None,
    db=Depends(get_db),
):
    """The registration, under the mode of the deployment (plan A1).

    "open" is today's behaviour; "approval" creates the account as ``pending``
    until an admin approves it; "invite" needs a one-time code an admin
    created. The status of an account is never an oracle: a pending or
    suspended login gets the same generic message as a wrong password.
    """
    address = _client_address(request)
    await _check_rate_limit(db, f"register:{address}", REGISTER_RATE_LIMIT)
    reason = validate_credentials(user.username, user.password)
    if reason:
        logger.warning(f"Registration rejected for '{user.username}': {reason}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)
    logger.info(f"Registration attempt for new user: '{user.username}'")

    initial_status = "active"
    if REGISTRATION_MODE == "approval":
        initial_status = "pending"
    elif REGISTRATION_MODE == "invite":
        if not invite_code:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Registration is invitation-only: an invite code is required.",
            )
        consumed = await _consume_invite(db, invite_code)
        if not consumed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The invite code is invalid, expired or already used.",
            )

    safe_password = user.password[:72]
    # bcrypt is a CPU-bound hash: running it in the event loop blocks every
    # other request for the duration of the hash.
    hashed = await run_in_threadpool(hash_pass, safe_password)
    # The role is always 'user': a client-supplied role is never trusted; an
    # admin is created by an admin (plan A1), never by a signup.
    new_user = User(
        username=user.username, hashed_password=hashed, role="user", status=initial_status
    )
    db.add(new_user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.warning(f"Registration rejected: username '{user.username}' is already taken")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Username '{user.username}' is already taken")
    logger.info(f"Success: User '{user.username}' registered with status '{initial_status}'.")
    if initial_status != "active":
        await write_audit(db, new_user.id, "user.registered_pending", "user", new_user.id, {})
    await _record_rate_limit(db, f"register:{address}")
    await db.commit()
    return {
        "message": "User registered successfully",
        "status": initial_status,
        "note": (
            "The account waits for an approval before it can log in."
            if initial_status == "pending"
            else None
        ),
    }


async def _consume_invite(db, code: str) -> bool:
    """Use a one-time registration code (plan A1): hashed, expiring, counted."""
    import hashlib
    from .models import Invite

    code_hash = hashlib.sha256(code.strip().encode()).hexdigest()
    invite = (
        await db.execute(select(Invite).where(Invite.code_hash == code_hash))
    ).scalars().first()
    if invite is None or invite.expires_at < _now() or invite.use_count >= invite.max_uses:
        return False
    invite.use_count += 1
    await db.commit()
    return True

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
    await _check_rate_limit(db, address_key, LOGIN_RATE_LIMIT * 3)
    await _check_rate_limit(db, account_key, LOGIN_RATE_LIMIT)
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
        await _record_rate_limit(db, account_key)
        await _record_rate_limit(db, address_key)
        await db.commit()
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    # The same generic message for a pending or suspended account, so the
    # status of an account is not an oracle (plan A1).
    if getattr(user, "status", "active") != "active":
        await _record_rate_limit(db, account_key)
        await _record_rate_limit(db, address_key)
        await db.commit()
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    logger.info(f"Success: User '{user.username}' logged in successfully.")
    user.last_login_at = _now()
    # The session of the browser (plan A2): a refresh token is issued with the
    # access token, in the same transaction as the login stamp.
    refresh_raw, _refresh_row = await sessions.issue_refresh_token(db, user.id)
    await db.commit()
    # The role lives in the database and is read on every request; the claim
    # was removed (plan G1) so that no client can ever trust a stale one.
    access_token = create_token(data={"sub": user.username, "token_version": getattr(user, "token_version", 0)})
    await rate_limit_module.forget_rate_limit(db, account_key)
    await db.commit()
    response = JSONResponse({
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "registration_mode": REGISTRATION_MODE,
        # Programmatic clients (a script, a test) take the refresh token from
        # the body. A browser ignores it: the credential it uses is the
        # httpOnly cookie set below, which no script on the page can read.
        "refresh_token": refresh_raw,
        "expires_in": ACCESS_TOKEN_MINUTES * 60,
    })
    _set_refresh_cookie(response, refresh_raw)
    return response


# --- the session endpoints (plan A2) ------------------------------------------

def _set_refresh_cookie(response, raw: str) -> None:
    """Put the refresh token in an httpOnly, SameSite=Strict cookie.

    The cookie is the *only* credential a browser page needs and the one it
    can never read itself. The path is narrowed to the endpoints that consume
    it, ``Secure`` is set when the deployment says it runs behind TLS, and
    ``SameSite=Strict`` keeps it off every cross-site request.
    """
    if not REFRESH_COOKIE_ENABLED:
        return
    response.set_cookie(
        sessions.REFRESH_COOKIE_NAME,
        raw,
        max_age=sessions.REFRESH_TOKEN_DAYS * 86400,
        httponly=True,
        samesite="strict",
        secure=os.getenv("COOKIE_SECURE", "0") == "1",
        path=sessions.REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response) -> None:
    if not REFRESH_COOKIE_ENABLED:
        return
    response.delete_cookie(
        sessions.REFRESH_COOKIE_NAME, path=sessions.REFRESH_COOKIE_PATH
    )


class _RefreshBody(BaseModel):
    refresh_token: Optional[str] = None


def _presented_refresh_token(request: Request, body: Optional[_RefreshBody]) -> Optional[str]:
    """The refresh token of the request: the cookie first, the body second."""
    from_cookie = request.cookies.get(sessions.REFRESH_COOKIE_NAME)
    if from_cookie:
        return from_cookie
    if body is not None and body.refresh_token:
        return body.refresh_token
    return None


@app.post("/api/v1/auth/refresh")
async def refresh_session(
    request: Request,
    body: Optional[_RefreshBody] = None,
    db: AsyncSession = Depends(get_db),
):
    """Exchange a refresh token for a fresh access token (plan A2).

    The presented token is rotated: a new row is issued in the same family
    and the old one is marked revoked. Presenting a token that was already
    rotated means the family leaked - every token of the family is revoked
    before the 401 is answered.
    """
    raw = _presented_refresh_token(request, body)
    if not raw:
        raise HTTPException(status_code=401, detail="No session to refresh.")
    try:
        new_raw, _new_row, _old_row = await sessions.rotate_refresh_token(db, raw)
    except sessions.SessionError:
        await db.commit()
        response = JSONResponse({"detail": "The session is no longer valid."}, status_code=401)
        _clear_refresh_cookie(response)
        return response
    user = (
        await db.execute(select(User).where(User.id == _new_row.user_id))
    ).scalars().first()
    if user is None or getattr(user, "status", "active") != "active":
        await db.commit()
        response = JSONResponse({"detail": "The session is no longer valid."}, status_code=401)
        _clear_refresh_cookie(response)
        return response
    await db.commit()
    access_token = create_token(data={"sub": user.username, "token_version": getattr(user, "token_version", 0)})
    response = JSONResponse({
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "refresh_token": new_raw,
        "expires_in": ACCESS_TOKEN_MINUTES * 60,
    })
    _set_refresh_cookie(response, new_raw)
    return response


@app.post("/api/v1/auth/logout")
async def logout_session(
    request: Request,
    body: Optional[_RefreshBody] = None,
    db: AsyncSession = Depends(get_db),
):
    """End the presented session (plan A2): the token is revoked, the cookie
    is cleared. The access token dies at its own expiry - which is minutes."""
    raw = _presented_refresh_token(request, body)
    if raw:
        await sessions.revoke_refresh_token(db, raw)
        await db.commit()
    response = JSONResponse({"detail": "Logged out."})
    _clear_refresh_cookie(response)
    return response


class _PasswordChange(BaseModel):
    current_password: str
    new_password: str


@app.post("/api/v1/auth/change-password")
async def change_password(
    body: _PasswordChange,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the password (plan A2): the current one is required, the new
    one follows the credential policy, every session of the account ends,
    and a fresh access token (with the new ``token_version``) is returned."""
    stored_hash = current_user.hashed_password
    matches = await run_in_threadpool(verify_pass, body.current_password, stored_hash)
    if not matches:
        raise HTTPException(status_code=400, detail="The current password is not correct.")
    reason = validate_credentials(current_user.username, body.new_password)
    if reason:
        # Only the password part of the policy can bite here; the message is
        # readable either way.
        raise HTTPException(status_code=400, detail=reason)
    # The same 72-byte truncation the login verification applies.
    safe_new = body.new_password[:BCRYPT_MAX_BYTES]
    current_user.hashed_password = await run_in_threadpool(hash_pass, safe_new)
    current_user.token_version = (current_user.token_version or 0) + 1
    revoked = await sessions.revoke_all_for_user(db, current_user.id)
    await write_audit(
        db, current_user.id, "user.password_changed", "user", current_user.id,
        {"sessions_revoked": revoked},
    )
    await db.commit()
    logger.info(f"User '{current_user.username}' changed their password ({revoked} session(s) ended).")
    access_token = create_token(data={"sub": current_user.username, "token_version": current_user.token_version})
    response = JSONResponse({
        "access_token": access_token,
        "token_type": "bearer",
        "detail": "The password was changed; the other sessions have ended.",
    })
    return response

@app.get("/api/v1/admin/all-users")
async def get_all_users(admin_user: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    users = result.scalars().all()
    return [{"id": u.id, "username": u.username, "role": u.role} for u in users]

@app.get("/api/v1/me")
async def who_am_i(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Who the caller is, with the usage panel of plan A7.

    A quota the user cannot see is experienced as a bug: showing the limit
    and the reset time turns a refusal into information.
    """
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "status": current_user.status,
        "registration_mode": REGISTRATION_MODE,
        "usage": await user_usage(db, current_user),
    }


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
        "auto_tune": "Randomized hyperparameter search over a curated per-model space",
        "auto_fine_tune": "Local hyperparameter search around the current configuration",
        "llm_fine_tune": "AI-guided parameters via Google Gemini (requires GOOGLE_API_KEY and the google-generativeai package)",
        "auto_search": "Model selection over multiple candidates - not Bayesian optimization",
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
    if hf_dataset_url:
        # The same hub-identifier rule as the train endpoint (plan G3): the
        # suggestion path reaches the same loader, so it gets the same guard.
        try:
            model_training_module.validate_hf_dataset_reference(hf_dataset_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
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
    for root in (
        str(REPO_ROOT),
        str(datasets_root()),
        str(model_training_module.MODEL_DIR),
    ):
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


@app.get("/api/v1/ml/datasets/{dataset_id}/profile")
async def get_dataset_profile(
    dataset_id: int,
    label_column: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Look at the data before training (plan C6): per-column statistics,
    the label distribution, the duplicate fraction, the correlated pairs, a
    time-order hint, and the leakage suspects. Cached by the file hash."""
    dataset = await _dataset_for_user(dataset_id, current_user, db)
    path = resolve_storage_path(dataset.storage_path)
    if not path.exists() or path.is_dir():
        raise HTTPException(status_code=422, detail="The profile needs a tabular CSV dataset.")
    from .dataset_profile import compute_profile

    label = label_column or dataset.label_column
    try:
        profile = await run_in_threadpool(compute_profile, path, label)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=_public_error(exc)) from None
    return {"dataset_id": dataset.id, "name": dataset.name, **profile}


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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Store a CSV file as a dataset of the caller.

    The file is written under the uploads directory of the user with a
    generated name, and it is registered as a row: a training request refers
    to it by its id.

    The body is read here and not by the framework: a request that is not
    authenticated has to be refused before its file is written to the disk.
    """
    # The values of the session are read before the first commit: a rollback
    # expires them, and reading them afterwards is an error.
    owner_id = current_user.id
    username = current_user.username

    # The upload budget of plan A8 is keyed on the *authenticated user* (an
    # address can be shared by a whole office; an account is one tenant) with
    # a wider address budget as the second line against a rented machine.
    address = _client_address(request)
    await _check_rate_limit(db, f"upload:user:{owner_id}", UPLOAD_RATE_LIMIT)
    await _check_rate_limit(db, f"upload:addr:{address}", UPLOAD_RATE_LIMIT * 3)
    # The ledger is written through a session of its own: an upload that is
    # refused later (a quota, a bad file) has still *used* its attempt, and
    # the event must survive the rollback of the request's transaction - while
    # the request session itself is left exactly as it is. A failure of the
    # ledger is not the request's business: it is advisory, and a database
    # that refuses it will fail the request soon enough anyway.
    try:
        async with AsyncSessionLocal() as ledger:
            await rate_limit_module.record_rate_limit(ledger, f"upload:user:{owner_id}")
            await rate_limit_module.record_rate_limit(ledger, f"upload:addr:{address}")
            await ledger.commit()
    except Exception:  # noqa: BLE001 - the ledger must not break the request
        logger.warning("The upload rate ledger could not be written", exc_info=True)

    # The upload checks of plan A4 (bytes, dataset count, storage headroom)
    # run before the body is parsed: the refusal answers immediately.

    async with request.form() as form:
        upload = form.get("file")
        if not isinstance(upload, StarletteUploadFile):
            raise HTTPException(
                status_code=400, detail="The request has no file."
            )
        # The per-user upload quota of plan A4: the size of the body that
        # arrived, against the limits of the caller's profile.
        upload.file.seek(0, os.SEEK_END)
        upload_size = upload.file.tell()
        upload.file.seek(0)
        try:
            await check_upload_quota(db, current_user, upload_size)
        except QuotaRefusal as refusal:
            raise HTTPException(
                status_code=refusal.status_code, detail=refusal.detail
            ) from None
        filename = upload.filename or ""

        # The file is inspected and written in a thread: a file of fifty
        # megabytes takes a second to read, and the event loop serves the
        # other requests while it does. The file of the framework is a file
        # on the disk, and it is copied instead of being read into the
        # memory of the process.
        try:
            columns, rows, label = await run_in_threadpool(
                datasets_registry.validate_upload, filename, upload.file
            )
            name, storage_path = await run_in_threadpool(
                datasets_registry.write_upload, owner_id, filename, upload.file
            )
        except DatasetError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

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
                size_bytes=datasets_registry.size_of(upload.file),
                row_count=rows,
                columns=columns,
                label_column=label,
                content_sha256=datasets_registry.content_sha256(
                    datasets_registry.resolve_storage_path(storage_path)
                ),
                kind=datasets_registry.infer_dataset_kind(
                    datasets_registry.resolve_storage_path(storage_path),
                    [c["name"] for c in columns],
                ),
            )
            db.add(dataset)
            try:
                await db.commit()
            except IntegrityError:
                # Two uploads of the same name arrived at the same time and
                # the database refused the second one. The name is the only
                # thing that collided: the file of this upload is fine, so
                # it is registered with the next free name.
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
                    size_bytes=datasets_registry.size_of(upload.file),
                    row_count=rows,
                    columns=columns,
                    label_column=label,
                )
                db.add(dataset)
                await db.commit()
        except HTTPException:
            raise
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=400,
                detail="The dataset could not be registered, please try again.",
            ) from None
        finally:
            # The file is removed only when no row points at it. The check is
            # made in a new session: the session of the request may be
            # broken, and a row that was written has to keep its file.
            await _remove_the_file_if_no_dataset_points_at_it(storage_path)

    await db.refresh(dataset)
    logger.info(
        "User '%s' uploaded the dataset '%s' (%s rows)",
        username,
        name,
        rows,
    )
    return dataset_to_dict(dataset)


async def _remove_the_file_if_no_dataset_points_at_it(storage_path: str) -> None:
    """Remove the file of an upload that was not registered.

    A file that no row points at is a file that nobody can reach: it would
    stay on the disk of the server until somebody deletes it by hand. The
    check is made in a new session, because the session of the request may
    be in a failed state - and because a row that was written before a
    cancellation has to keep its file.
    """
    try:
        async with AsyncSessionLocal() as session:
            found = await session.execute(
                select(Dataset.id).where(Dataset.storage_path == storage_path)
            )
            if found.scalar() is not None:
                return
    except Exception:  # pragma: no cover - the safety net
        logger.warning(
            "The file of the upload %s could not be checked", storage_path
        )
        return
    _remove_stored_upload(storage_path)


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
async def train_model_endpoint(
    payload: TrainRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Queue a training and answer immediately.

    The training runs in the background: the request answers with the id of
    the run, and the client reads the result from the run itself. A training
    that takes a minute must not hold a request open for a minute.
    """
    # The requested optimisation metric is passed through untouched: resolving or
    # remapping it here would hide the training internals from the HTTP layer and
    # would silently optimise for a different metric than the one requested.
    if payload.hf_dataset_url and (
        payload.dataset_id is not None or payload.dataset_name
    ):
        # A request carries either a dataset of the registry or a Hugging Face
        # dataset, not both: one of them would be ignored silently.
        raise HTTPException(
            status_code=400,
            detail=(
                "A request carries either a dataset of the registry or a "
                "Hugging Face dataset, not both."
            ),
        )
    if payload.hf_dataset_url:
        # A Hugging Face reference is accepted as a hub identifier only
        # (plan G3): an arbitrary URL would make the server fetch whatever
        # the string points at, which is a server-side request forgery with
        # extra steps. The check runs before the run exists, so the refusal
        # is immediate and the reason is in the answer.
        try:
            model_training_module.validate_hf_dataset_reference(payload.hf_dataset_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
    if _needs_a_dataset(payload.model_name):
        dataset, storage_path = await _dataset_for_training(payload, current_user, db)
    else:
        # A reinforcement learning model trains in an environment, so it needs
        # no data.
        dataset, storage_path = None, None

    # The submit-time quota checks of plan A4: refusing here gives the user
    # the answer immediately, before a run exists. The error body carries the
    # quota object (name, limit, used, resets_at), so the interface can show
    # the reason and the reset time instead of an opaque refusal.
    entry = get_model_entry(payload.model_name)
    if not entry.get("implemented", True):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Model '{payload.model_name}' is not implemented: it does not train "
                "what the catalog advertises."
            ),
        )
    availability = model_training_module.model_availability(entry)
    if not availability["available"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=availability["reason"])
    try:
        await check_submit_quota(
            db, current_user, entry.get("category", "custom"),
            dataset.row_count if dataset is not None else None,
        )
    except QuotaRefusal as refusal:
        raise HTTPException(
            status_code=refusal.status_code, detail=refusal.detail
        ) from None

    if dataset is not None:
        dataset_source, dataset_tag = "local", dataset.name
    elif payload.hf_dataset_url:
        dataset_source, dataset_tag = "huggingface", payload.hf_dataset_url
    else:
        dataset_source, dataset_tag = "rl", payload.env_id or "unknown"

    # The capability routing of plan B7: the run records what its model
    # needs, and the submit answers 409 when no online worker could ever
    # run it - a request that would wait forever is refused, not queued.
    requirements = {
        "requires_gpu": bool(entry.get("requires_gpu", False)),
        "min_memory_mb": entry.get("min_memory_mb"),
    }
    if not await _some_worker_satisfies(requirements):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"No worker online can run '{payload.model_name}': it needs "
                + ("a GPU" if requirements["requires_gpu"] else "more memory than any worker has")
                + ". The catalog entry says so; ask an operator to add a capable worker."
            ),
        )

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
        status=STATUS_QUEUED,
        requirements=requirements,
        # The dataset of the run (plan E4): the comparability guard of the
        # comparison view compares runs by dataset id and content hash.
        dataset_id=dataset.id if dataset is not None else None,
        # Everything a worker needs: the run no longer depends on the memory
        # of this request, so it survives a restart.
        request_payload={
            "request": payload.model_dump(),
            "storage_path": storage_path,
            "dataset_name": dataset.name if dataset is not None else None,
        },
    )
    db.add(training_run)
    # The row is written before the answer: the client polls it, and a run
    # that does not exist yet would be a 404.
    await db.commit()
    await db.refresh(training_run)

    if TRAINING_IN_API:
        # Starts the queue now: the worker takes the oldest queued run (this
        # one, unless the process is busy - then it waits its turn). A task
        # of the event loop, not a Starlette background task: the response
        # must not be tied to a training that may run for an hour - a client
        # (and the test suite's client) waits for the answer, not for the
        # model (plan B1).
        drain = asyncio.create_task(drain_training_queue())
        _background_tasks.add(drain)
        drain.add_done_callback(_background_tasks.discard)

    return {
        "run_id": training_run.id,
        "status": training_run.status,
        "artifact_path": None,
        "metrics": None,
    }


async def drain_training_queue() -> None:
    """Run queued runs while this process has a free slot.

    A slot is taken *before* the claim is awaited: two drains that both saw a
    free slot would otherwise both claim a run, and the process would train
    more runs at once than ``TRAINING_CONCURRENCY`` allows.
    """
    global _slots_in_use
    while _slots_in_use < TRAINING_CONCURRENCY:
        _slots_in_use += 1
        try:
            run_id = await _claim_next_run()
            if run_id is None:
                return
            await _run_claimed(run_id)
        finally:
            _slots_in_use -= 1


async def _claim_next_run() -> Optional[int]:
    """Claim the next run this worker may run, with one atomic UPDATE.

    Two rules sit on top of "oldest first" (plans B5 and B7):

    * the fair share - among the queued runs, the owner with the fewest
      running runs goes first, then the highest priority, then the oldest.
      A user with a thousand queued runs cannot starve a newcomer;
    * the capability routing - a run whose requirements this worker cannot
      satisfy (a GPU model on a CPU worker) is left for a worker that can.
    """
    capabilities = _worker_capabilities()
    # The alias is what makes the count a *correlated* one: the running runs
    # of the same owner the outer row belongs to.
    running = sa.orm.aliased(TrainingRun, name="running")
    running_of_owner = (
        sa.select(sa.func.count())
        .select_from(running)
        .where(
            running.owner_id == TrainingRun.owner_id,
            running.status == STATUS_RUNNING,
        )
        .correlate(TrainingRun)
        .scalar_subquery()
    )
    for _ in range(5):
        async with AsyncSessionLocal() as session:
            candidate = (
                await session.execute(
                    select(TrainingRun.id)
                    .where(
                        TrainingRun.status == STATUS_QUEUED,
                        TrainingRun.request_payload.is_not(None),
                    )
                    .order_by(
                        # The owner with the least running work has the turn.
                        running_of_owner,
                        TrainingRun.priority.desc(),
                        TrainingRun.id,
                    )
                    .limit(20)
                )
            ).scalars().all()
            # The first candidate this worker can satisfy (the ordering above
            # decides whose turn it is; the capability check decides whether
            # this is the machine for it).
            chosen = None
            for candidate_id in candidate:
                requirements = (
                    await session.execute(
                        sa.select(TrainingRun.requirements).where(TrainingRun.id == candidate_id)
                    )
                ).scalar_one_or_none()
                if _worker_satisfies(requirements or {}, capabilities):
                    chosen = candidate_id
                    break
            if chosen is None:
                return None
            now = _now()
            claimed = await session.execute(
                update(TrainingRun)
                .where(TrainingRun.id == chosen, TrainingRun.status == STATUS_QUEUED)
                .values(
                    status=STATUS_RUNNING,
                    worker_id=WORKER_ID,
                    started_at=now,
                    heartbeat_at=now,
                )
            )
            await session.commit()
            if claimed.rowcount == 1:
                return chosen
        # Another worker took it between the SELECT and the UPDATE: try the next one.
    return None


_WORKER_CAPABILITIES_CACHE: Optional[Dict[str, Any]] = None


def _worker_capabilities() -> Dict[str, Any]:
    """What this process can run (plan B7): computed once, cheaply."""
    global _WORKER_CAPABILITIES_CACHE
    if _WORKER_CAPABILITIES_CACHE is None:
        gpu = False
        try:
            import torch

            gpu = bool(torch.cuda.is_available())
        except Exception:  # noqa: BLE001 - no torch: no GPU, no drama
            gpu = False
        memory_mb = None
        try:
            import psutil

            memory_mb = int(psutil.virtual_memory().total / (1024 * 1024))
        except Exception:  # noqa: BLE001
            memory_mb = None
        _WORKER_CAPABILITIES_CACHE = {"gpu": gpu, "cpu": True}
        if memory_mb is not None:
            _WORKER_CAPABILITIES_CACHE["memory_mb"] = memory_mb
    return _WORKER_CAPABILITIES_CACHE


def _worker_satisfies(requirements: Dict[str, Any], capabilities: Dict[str, Any]) -> bool:
    """Whether this worker can run a run with these requirements."""
    if requirements.get("requires_gpu") and not capabilities.get("gpu"):
        return False
    needed = requirements.get("min_memory_mb")
    available = capabilities.get("memory_mb")
    if needed and available and available < int(needed):
        return False
    return True


async def _some_worker_satisfies(requirements: Dict[str, Any]) -> bool:
    """Whether any worker that could take this run exists (plan B7).

    This process counts when it trains in-process (TRAINING_IN_API=1);
    otherwise the online workers of the table are asked, a fresh heartbeat
    being the definition of online.
    """
    if TRAINING_IN_API and _worker_satisfies(requirements, _worker_capabilities()):
        return True
    from .models import Worker

    cutoff = _now() - timedelta(seconds=TRAINING_STALE_SECONDS)
    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(Worker).where(Worker.last_seen > cutoff)
        )
        for worker in rows.scalars():
            if _worker_satisfies(requirements, worker.capabilities or {}):
                return True
    return False


async def register_this_worker() -> None:
    """Write this worker's capabilities and heartbeat (plan B7)."""
    from .models import Worker

    capabilities = _worker_capabilities()
    async with AsyncSessionLocal() as session:
        existing = await session.get(Worker, WORKER_ID)
        if existing is None:
            session.add(
                Worker(
                    id=WORKER_ID,
                    capabilities=capabilities,
                    memory_mb=capabilities.get("memory_mb"),
                    last_seen=_now(),
                )
            )
        else:
            existing.capabilities = capabilities
            existing.memory_mb = capabilities.get("memory_mb")
            existing.last_seen = _now()
        await session.commit()


async def _run_claimed(run_id: int) -> None:
    """Train a claimed run and write the result in it.

    The worker has its own sessions: the request that queued the run was
    answered long ago.
    """
    async with AsyncSessionLocal() as session:
        run = await session.get(TrainingRun, run_id)
        stored = run.request_payload if run is not None else None
    if not stored:
        await _finish_run(
            run_id, STATUS_FAILED, metrics={"error": "The run has no stored request."}
        )
        return
    try:
        payload = TrainRequest(**stored["request"])
    except Exception:
        logger.exception("The stored request of the run %s is invalid", run_id)
        await _finish_run(
            run_id,
            STATUS_FAILED,
            metrics={"error": "The stored request of the run is not valid any more."},
        )
        return
    storage_path = stored.get("storage_path")
    dataset_name = stored.get("dataset_name")

    # A batch prediction above the synchronous limit is a job in this same
    # queue (plan D3): it reuses the queue, so it gets cancel, limits and
    # quotas for free.
    if (stored.get("predict")) is not None:
        await _run_predict_job(run_id, stored["predict"])
        return

    heartbeat = asyncio.create_task(_heartbeat(run_id))
    started = time.monotonic()
    try:
        # The executor interface of plan B1: the queue decided *what* runs;
        # the executor decides *how*. The events of plan B4 flow through the
        # sink: the phases of the executor, the metrics of the trainer.
        sink = progress.DatabaseSink(run_id)
        limits = await _limits_for_run(run_id)
        executor = executor_module.choose_executor()
        try:
            result = await executor.execute(
                run_id, payload, storage_path, limits, sink
            )
        except Exception as exc:
            logger.exception("The executor of the run %s failed", run_id)
            result = executor_module.ExecResult(
                status=STATUS_FAILED, metrics={"error": _public_error(exc)},
                wall_seconds=time.monotonic() - started,
            )
        if result.status == STATUS_CANCELLED:
            # The cancel of plan B3 already marked the row; the result of the
            # work is discarded and the slot is free at once.
            sink.append("phase", {"phase": "cancelled"})
            await sink.flush()
            return
        if result.status == STATUS_FAILED:
            sink.append("phase", {"phase": "failed"})
            await sink.flush()
            await _finish_run(
                run_id, STATUS_FAILED, metrics=result.metrics or {"error": result.error or "failed"},
                wall_seconds=result.wall_seconds,
            )
            return
        sink.append("phase", {"phase": "writing result"})
        await sink.flush()
        await _finish_run(
            run_id,
            STATUS_COMPLETED,
            metrics=result.metrics,
            artifact=result.artifact,
            charts=result.charts,
            wall_seconds=result.wall_seconds,
            dataset_source=result.dataset_source,
            dataset_tag=dataset_name if dataset_name is not None else result.dataset_tag,
        )
        sink.append("phase", {"phase": "completed"})
        await sink.flush()
    finally:
        heartbeat.cancel()
        try:
            await heartbeat
        except BaseException:
            pass


async def _limits_for_run(run_id: int) -> "executor_module.Limits":
    """What this run may consume: the owner's quota, the numbers of plan A3."""
    from sqlalchemy import select as _select

    from .quotas import effective_quota

    async with AsyncSessionLocal() as session:
        owner_id = (
            await session.execute(
                _select(TrainingRun.owner_id).where(TrainingRun.id == run_id)
            )
        ).scalar_one_or_none()
        if owner_id is None:
            return executor_module.Limits()
        user = await session.get(User, owner_id)
        quota = await effective_quota(session, user)
    return executor_module.Limits(
        max_run_seconds=quota.get("max_run_seconds"),
        max_run_memory_mb=quota.get("max_run_memory_mb"),
    )


async def _run_predict_job(run_id: int, spec: dict) -> None:
    """A queued batch prediction (plan D3): the artifact is the result CSV."""
    import csv as _csv

    from .inference import _require_predicting_bundle, load_bundle_of_run

    input_path = Path(spec.get("input_path", ""))
    source_run_id = spec.get("source_run_id")
    try:
        run = None
        async with AsyncSessionLocal() as session:
            source = await session.get(TrainingRun, source_run_id)
            if source is None:
                raise ValueError("The source run of the batch prediction does not exist.")
            run, bundle = await load_bundle_of_run(source)
            _require_predicting_bundle(bundle)
            if bundle.request_kind != "rows":
                raise ValueError("This model cannot score a table of rows.")
        if not input_path.exists():
            raise ValueError("The input file of the batch prediction is gone.")
        import pandas as _pd

        frame = _pd.read_csv(input_path)
        rows = frame.to_dict(orient="records")
        _, bundle = await load_bundle_of_run(run)
        result = await run_in_threadpool(bundle.infer, {"rows": rows})
        predictions = result.get("predictions") or []
        output = input_path.with_name(input_path.stem + "_result.csv")
        frame["prediction"] = list(predictions) + [None] * (len(frame) - len(predictions))
        frame.to_csv(output, index=False)
        await _finish_run(
            run_id,
            STATUS_COMPLETED,
            metrics={
                "job_kind": "predict",
                "source_run_id": source_run_id,
                "rows": len(frame),
                "warnings": result.get("warnings", []),
            },
            artifact={
                "artifact_path": str(output),
                "artifact_sha256": None,
                "artifact_bytes": output.stat().st_size,
            },
        )
    except Exception as exc:
        logger.exception("The batch prediction %s failed", run_id)
        await _finish_run(
            run_id, STATUS_FAILED, metrics={"error": _public_error(exc), "job_kind": "predict"}
        )


async def _heartbeat(run_id: int) -> None:
    """Say, every few seconds, that the worker of the run is alive."""
    while True:
        await asyncio.sleep(TRAINING_HEARTBEAT_SECONDS)
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(TrainingRun)
                    .where(
                        TrainingRun.id == run_id,
                        TrainingRun.status == STATUS_RUNNING,
                        TrainingRun.worker_id == WORKER_ID,
                    )
                    .values(heartbeat_at=_now())
                )
                await session.commit()
        except Exception:
            # A missed beat is not an error: the run is only considered dead
            # after several of them.
            logger.warning("Could not write the heartbeat of the run %s", run_id)


def _remove_artifact_files(artifact_path: str) -> None:
    """Remove an artifact of either format: a directory or a single file."""
    path = Path(artifact_path)
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink()
    except OSError:
        pass


async def _finish_run(
    run_id: int,
    status: str,
    metrics: Optional[Dict[str, Any]] = None,
    artifact: Optional[Dict[str, Any]] = None,
    charts: Optional[Dict[str, Any]] = None,
    wall_seconds: Optional[float] = None,
    dataset_source: Optional[str] = None,
    dataset_tag: Optional[str] = None,
) -> bool:
    """Write the result of a training in its run, if the run is still running.

    The write is conditional (``WHERE status = 'running'``): a run that was
    cancelled while it trained must stay cancelled, so its result is dropped,
    and the artifact it wrote is removed instead of being left orphaned.

    ``artifact`` is the record of ``write_bundle`` (path, sha256, bytes - plan
    C1/A5); ``charts`` is the chart data of plan E1; ``wall_seconds`` feeds
    the usage accounting of plan A5.
    """
    values: Dict[str, Any] = {"status": status, "finished_at": _now()}
    if metrics is not None:
        values["metrics"] = metrics
    if artifact is not None:
        values["artifact_path"] = artifact.get("artifact_path")
        if artifact.get("artifact_sha256") is not None:
            values["artifact_sha256"] = artifact["artifact_sha256"]
        if artifact.get("artifact_bytes") is not None:
            values["artifact_bytes"] = artifact["artifact_bytes"]
    if charts is not None:
        values["charts"] = charts
    if wall_seconds is not None:
        values["wall_seconds"] = wall_seconds
    if dataset_source is not None:
        values["dataset_source"] = dataset_source
    if dataset_tag is not None:
        values["dataset_tag"] = dataset_tag
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(TrainingRun)
            .where(TrainingRun.id == run_id, TrainingRun.status == STATUS_RUNNING)
            .values(**values)
        )
        await session.commit()
        written = result.rowcount == 1
    if not written and artifact is not None:
        logger.info("The run %s is no longer running: its result is discarded", run_id)
        _remove_artifact_files(artifact.get("artifact_path") or "")
    return written


async def reap_the_interrupted_runs() -> None:
    """Fail the runs whose worker is gone.

    A running run is dead when its heartbeat stopped (or was never written:
    the runs of an older version). A run with a fresh heartbeat belongs to a
    live worker - possibly another process - and is left alone: that is what
    the previous version got wrong, when it failed every queued or running
    row at startup. A queued run without a stored request cannot be resumed
    either (it was queued by an older version), and is failed with a message.

    Both updates are conditional, so a run that finishes while the sweeper
    looks at it is never overwritten.
    """
    now = _now()
    cutoff = now - timedelta(seconds=TRAINING_STALE_SECONDS)
    async with AsyncSessionLocal() as session:
        # The retries of plan B6: a run whose worker died is requeued while
        # it has attempts left - an infrastructure failure costs the user
        # nothing and fails the same way never twice. A run that *raised*
        # (the executor's failure path) is never retried: only a dead worker
        # gets another chance.
        requeued = await session.execute(
            update(TrainingRun)
            .where(
                TrainingRun.status == STATUS_RUNNING,
                or_(TrainingRun.heartbeat_at.is_(None), TrainingRun.heartbeat_at < cutoff),
                TrainingRun.attempts < TrainingRun.max_attempts,
            )
            .values(
                status=STATUS_QUEUED,
                worker_id=None,
                started_at=None,
                heartbeat_at=None,
                attempts=TrainingRun.attempts + 1,
                metrics=None,
            )
        )
        stopped = await session.execute(
            update(TrainingRun)
            .where(
                TrainingRun.status == STATUS_RUNNING,
                or_(TrainingRun.heartbeat_at.is_(None), TrainingRun.heartbeat_at < cutoff),
                TrainingRun.attempts >= TrainingRun.max_attempts,
            )
            .values(
                status=STATUS_FAILED,
                finished_at=now,
                metrics={
                    "error": (
                        "The worker stopped before the training finished (the server "
                        "restarted or crashed), and the run had no attempts left. "
                        "Please run it again."
                    )
                },
            )
        )
        orphaned = await session.execute(
            update(TrainingRun)
            .where(
                TrainingRun.status == STATUS_QUEUED,
                TrainingRun.request_payload.is_(None),
            )
            .values(
                status=STATUS_FAILED,
                finished_at=now,
                metrics={
                    "error": (
                        "This run was queued by an older version of the server and "
                        "cannot be resumed. Please run it again."
                    )
                },
            )
        )
        await session.commit()
    if stopped.rowcount or orphaned.rowcount or requeued.rowcount:
        logger.info(
            "%s stopped runs were failed, %s were requeued, %s unresumable queued runs were failed",
            stopped.rowcount,
            requeued.rowcount,
            orphaned.rowcount,
        )


async def maintenance_loop() -> None:
    """Sweep the dead runs and pick up the queued ones, forever.

    The training itself runs in a task of its own, so a long training never
    stops the sweeper.
    """
    while True:
        try:
            await reap_the_interrupted_runs()
            # The worker says what it is and that it is alive (plan B7).
            await register_this_worker()
            # The rate events that fell out of every window: one indexed
            # DELETE over a small range on every tick keeps the ledger from
            # growing without bound (plan A8).
            async with AsyncSessionLocal() as session:
                await rate_limit_module.purge_rate_events(session)
                # The retention of the artifacts and the janitor of plan H1:
                # the files that no row refers to are removed, the rows whose
                # file is gone are marked, and the profiles' retention rules
                # retire the artifacts that fell out of them.
                try:
                    await cleanup.apply_retention(session)
                    await cleanup.janitor_sweep(session)
                    await session.commit()
                except Exception:
                    await session.rollback()
                    logger.exception("The retention or the janitor sweep failed")
            if _slots_in_use < TRAINING_CONCURRENCY:
                task = asyncio.create_task(drain_training_queue())
                _background_tasks.add(task)
                task.add_done_callback(_background_tasks.discard)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("The maintenance of the training queue failed")
        await asyncio.sleep(QUEUE_POLL_SECONDS)


async def cancel_run_row(db: AsyncSession, run: TrainingRun) -> bool:
    """Mark a run cancelled (the owner endpoint and the admin queue share it).

    The claim is conditional: a run that already finished stays what it is.
    """
    if run.status not in (STATUS_QUEUED, STATUS_RUNNING):
        return False
    await db.execute(
        update(TrainingRun)
        .where(
            TrainingRun.id == run.id,
            TrainingRun.status.in_([STATUS_QUEUED, STATUS_RUNNING]),
        )
        .values(status=STATUS_CANCELLED, finished_at=_now())
    )
    await db.commit()
    return True


@app.post("/api/v1/ml/runs/{run_id}/cancel")
async def cancel_training_run(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a queued or running run.

    A queued run never starts. A running run cannot be interrupted - the
    estimators have no hook to stop a ``fit`` - so it is marked cancelled at
    once and its result is discarded when the training ends. Its slot is
    freed then, not now; the answer says so instead of pretending otherwise.
    """
    result = await db.execute(
        select(TrainingRun).where(
            TrainingRun.id == run_id, TrainingRun.owner_id == current_user.id
        )
    )
    run = result.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="Training run not found")
    if run.status not in (STATUS_QUEUED, STATUS_RUNNING):
        raise HTTPException(status_code=409, detail=f"The run is already {run.status}.")
    was = run.status
    updated = await db.execute(
        update(TrainingRun)
        .where(
            TrainingRun.id == run_id,
            TrainingRun.status.in_([STATUS_QUEUED, STATUS_RUNNING]),
        )
        .values(
            status=STATUS_CANCELLED,
            finished_at=_now(),
            metrics={"cancelled": True, "message": "The run was cancelled by its owner."},
        )
    )
    await db.commit()
    if updated.rowcount != 1:
        # It finished between the read and the write.
        raise HTTPException(status_code=409, detail="The run has just finished.")
    response: Dict[str, Any] = {"id": run_id, "status": STATUS_CANCELLED, "was": was}
    if was == STATUS_RUNNING:
        response["note"] = (
            "The training cannot be interrupted once it started: its result is "
            "discarded when it ends."
        )
    return response


# How many runs one page of the list may carry (plan E5). The old endpoint
# returned every run with its full metrics, which slows down in proportion to
# usage; the list is now paginated, filterable and searchable, and returns
# {items, total}.
RUNS_PAGE_DEFAULT = 20
RUNS_PAGE_MAX = 100


def _run_summary(run: TrainingRun) -> Dict[str, Any]:
    """The list view of a run: everything except the chart data (plan E1).

    The metrics stay (the list sorts by them); the ``charts`` column never
    leaves the database through this endpoint.
    """
    return {
        "id": run.id,
        "model_name": run.model_name,
        "dataset_source": run.dataset_source,
        "dataset_tag": run.dataset_tag,
        "dataset_id": run.dataset_id,
        "mode": run.mode,
        "env_id": run.env_id,
        "optimize_metric": run.optimize_metric,
        "model_candidates": run.model_candidates,
        "status": run.status,
        "job_kind": run.job_kind,
        "artifact_path": run.artifact_path,
        "artifact_removed": run.artifact_removed_at is not None,
        "metrics": run.metrics,
        "tags": run.tags,
        "note": run.note,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "wall_seconds": run.wall_seconds,
    }


@app.get("/api/v1/ml/runs")
async def list_training_runs(
    limit: int = 20,
    offset: int = 0,
    status_filter: Optional[str] = None,
    model: Optional[str] = None,
    dataset_id: Optional[int] = None,
    q: Optional[str] = None,
    tag: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The runs of the caller, paginated, filtered and searched (plan E5)."""
    limit = max(1, min(int(limit), RUNS_PAGE_MAX))
    offset = max(0, int(offset))
    query = select(TrainingRun).where(TrainingRun.owner_id == current_user.id)
    count_query = select(TrainingRun.id).where(TrainingRun.owner_id == current_user.id)
    if status_filter:
        query = query.where(TrainingRun.status == status_filter)
        count_query = count_query.where(TrainingRun.status == status_filter)
    if model:
        query = query.where(TrainingRun.model_name == model)
        count_query = count_query.where(TrainingRun.model_name == model)
    if dataset_id is not None:
        query = query.where(TrainingRun.dataset_id == dataset_id)
        count_query = count_query.where(TrainingRun.dataset_id == dataset_id)
    if q:
        needle = f"%{q}%"
        query = query.where(
            or_(TrainingRun.model_name.ilike(needle), TrainingRun.dataset_tag.ilike(needle))
        )
        count_query = count_query.where(
            or_(TrainingRun.model_name.ilike(needle), TrainingRun.dataset_tag.ilike(needle))
        )
    if tag:
        # The tags are a JSON array; the filter matches the array as a string,
        # which is enough for a tag word and needs no dialect-specific JSON path.
        query = query.where(TrainingRun.tags.cast(sa.String).ilike(f'%"{tag}"%'))
        count_query = count_query.where(TrainingRun.tags.cast(sa.String).ilike(f'%"{tag}"%'))
    query = query.order_by(TrainingRun.created_at.desc()).limit(limit).offset(offset)
    runs = (await db.execute(query)).scalars().all()
    total = len((await db.execute(count_query)).all())
    return {"items": [_run_summary(run) for run in runs], "total": total, "limit": limit, "offset": offset}

@app.get("/api/v1/ml/runs/compare")
async def compare_runs(
    ids: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The comparability guard and the shared facts of the runs (plan E4).

    A comparison of runs on different data is the most common way to fool
    yourself, so the guard comes before the charts: the answer lists every
    difference (dataset, label, task type, split seed, test fraction) and why
    the numbers may not be comparable. The user can still proceed.
    """
    try:
        run_ids = [int(part) for part in ids.split(",") if part.strip()]
    except ValueError:
        raise HTTPException(status_code=422, detail="ids must be a comma-separated list of run ids.") from None
    if not 2 <= len(run_ids) <= 6:
        raise HTTPException(status_code=422, detail="Compare between 2 and 6 runs.")
    runs = []
    for run_id in run_ids:
        run = (
            await db.execute(
                select(TrainingRun).where(TrainingRun.id == run_id, TrainingRun.owner_id == current_user.id)
            )
        ).scalars().first()
        if run is None:
            raise HTTPException(status_code=404, detail=f"Training run {run_id} not found")
        runs.append(run)
    facts = []
    for run in runs:
        request = (run.request_payload or {}).get("request") or {}
        dataset_hash = None
        if run.dataset_id is not None:
            dataset = await db.get(Dataset, run.dataset_id)
            if dataset is not None:
                dataset_hash = dataset.content_sha256
        facts.append(
            {
                "id": run.id,
                "model_name": run.model_name,
                "dataset_id": run.dataset_id,
                "dataset_hash": dataset_hash,
                "label_column": request.get("label_column"),
                "random_state": request.get("random_state"),
                "test_size": request.get("test_size"),
                "task_type": (run.metrics or {}).get("task_type"),
                "metrics": run.metrics,
                "hyperparameters": run.hyperparameters,
                "parameters": (run.metrics or {}).get("model_parameters"),
                "preprocessing": (run.metrics or {}).get("preprocessing"),
                "cv": (run.metrics or {}).get("cv"),
            }
        )
    # The differences against the first run.
    differences = []
    reference = facts[0]
    for field_name, label in (
        ("dataset_id", "dataset"),
        ("dataset_hash", "dataset content"),
        ("label_column", "label column"),
        ("task_type", "task type"),
        ("random_state", "split seed"),
        ("test_size", "test fraction"),
    ):
        values = [fact[field_name] for fact in facts]
        if len(set(map(str, values))) > 1:
            differences.append({"field": label, "values": values})
    return {
        "runs": facts,
        "differences": differences,
        "comparable": not differences,
        "note": (
            None
            if not differences
            else "These runs differ in " + ", ".join(d["field"] for d in differences)
            + ": the numbers may not be comparable. You can still look at them."
        ),
    }

@app.get("/api/v1/ml/runs/{run_id}")
async def get_training_run(run_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TrainingRun).where(TrainingRun.id == run_id, TrainingRun.owner_id == current_user.id))
    run = result.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="Training run not found")
    # The comparability facts of the run (plan E4): what the comparison guard
    # compares. The dataset content hash comes from the dataset row.
    dataset_hash = None
    label_column = None
    split_seed = None
    test_size = None
    task_type = None
    if run.request_payload:
        request = run.request_payload.get("request") or {}
        label_column = request.get("label_column")
        split_seed = request.get("random_state")
        test_size = request.get("test_size")
        task_type = (run.metrics or {}).get("task_type")
    if run.dataset_id is not None:
        dataset = await db.get(Dataset, run.dataset_id)
        if dataset is not None:
            dataset_hash = dataset.content_sha256
    return {
        "id": run.id,
        "model_name": run.model_name,
        "dataset_source": run.dataset_source,
        "dataset_tag": run.dataset_tag,
        "dataset_id": run.dataset_id,
        "dataset_hash": dataset_hash,
        "label_column": label_column,
        "random_state": split_seed,
        "test_size": test_size,
        "task_type": task_type,
        "hf_dataset_url": run.hf_dataset_url,
        "hyperparameters": run.hyperparameters,
        "metrics": run.metrics,
        "artifact_path": run.artifact_path,
        "artifact_sha256": run.artifact_sha256,
        "artifact_removed": run.artifact_removed_at is not None,
        "status": run.status,
        "job_kind": run.job_kind,
        "mode": run.mode,
        "env_id": run.env_id,
        "optimize_metric": run.optimize_metric,
        "model_candidates": run.model_candidates,
        "tags": run.tags,
        "note": run.note,
        "has_charts": bool(run.charts),
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "heartbeat_at": run.heartbeat_at.isoformat() if run.heartbeat_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


@app.get("/api/v1/ml/runs/{run_id}/charts")
async def get_run_charts(run_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The chart data of a run (plan E1): the heavy series, outside the list."""
    result = await db.execute(select(TrainingRun).where(TrainingRun.id == run_id, TrainingRun.owner_id == current_user.id))
    run = result.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="Training run not found")
    return {"run_id": run.id, "charts": run.charts or {}}


@app.patch("/api/v1/ml/runs/{run_id}")
async def patch_run(
    run_id: int,
    body: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The editable memory of a run (plan E5): tags and a note."""
    result = await db.execute(select(TrainingRun).where(TrainingRun.id == run_id, TrainingRun.owner_id == current_user.id))
    run = result.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="Training run not found")
    unknown = sorted(set(body) - {"tags", "note"})
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown field(s): {unknown}; only tags and note are editable.")
    if "tags" in body:
        tags = body["tags"]
        if not isinstance(tags, list) or not all(isinstance(t, str) and len(t) <= 40 for t in tags):
            raise HTTPException(status_code=422, detail="tags must be a list of short strings.")
        run.tags = tags[:20]
    if "note" in body:
        note = body["note"]
        if not isinstance(note, str) or len(note) > 4000:
            raise HTTPException(status_code=422, detail="note must be a string of at most 4000 characters.")
        run.note = note
    await db.commit()
    return {"id": run.id, "tags": run.tags, "note": run.note}


# --- the progress events (plan B4) ---------------------------------------------


@app.get("/api/v1/ml/runs/{run_id}/events")
async def run_events_endpoint(
    run_id: int,
    after: int = 0,
    limit: int = 500,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """What the run has been doing since the event ``after`` (plan B4).

    The answer is ordered by seq and carries the highest seq it contains, so
    the client polls with ``?after=<last seen>`` and never misses one.
    """
    run = (
        await db.execute(
            select(TrainingRun).where(
                TrainingRun.id == run_id, TrainingRun.owner_id == current_user.id
            )
        )
    ).scalars().first()
    if run is None:
        raise HTTPException(status_code=404, detail="Training run not found")
    events = await progress.events_after(db, run_id, after, limit)
    last_seq = max([event.seq for event in events], default=after)
    return {
        "run_id": run_id,
        "last_seq": last_seq,
        "events": [
            {
                "seq": event.seq,
                "kind": event.kind,
                "payload": event.payload,
                "ts": event.ts.isoformat() if event.ts else None,
            }
            for event in events
        ],
    }


@app.get("/api/v1/ml/runs/{run_id}/stream")
async def run_events_stream(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The events of the run, streamed (plan B4, the optional SSE form).

    The stream ends when the run reaches a state it does not leave. A client
    that only wants the final answer can just poll the run itself; this is
    for the page that shows the loss curve moving.
    """
    run = (
        await db.execute(
            select(TrainingRun).where(
                TrainingRun.id == run_id, TrainingRun.owner_id == current_user.id
            )
        )
    ).scalars().first()
    if run is None:
        raise HTTPException(status_code=404, detail="Training run not found")

    async def event_source():
        last_seq = 0
        while True:
            fresh = await progress.events_after(db, run_id, last_seq, limit=200)
            for event in fresh:
                last_seq = max(last_seq, event.seq)
                payload = json.dumps({
                    "seq": event.seq,
                    "kind": event.kind,
                    "payload": event.payload,
                }, default=str)
                yield f"id: {event.seq}\ndata: {payload}\n\n"
            await db.commit()  # the read transaction must not sit open
            current = (
                await db.execute(
                    select(TrainingRun.status).where(TrainingRun.id == run_id)
                )
            ).scalar_one_or_none()
            if current in (STATUS_COMPLETED, STATUS_FAILED, STATUS_CANCELLED) and not fresh:
                yield "event: done\ndata: {}\n\n"
                return
            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- deletion and retention (plan H1) -----------------------------------------


async def _deleteable_run(run: TrainingRun, current_user: User, db: AsyncSession) -> Optional[str]:
    """The reason a run cannot be deleted right now, or None when it can."""
    if run.status in (STATUS_QUEUED, STATUS_RUNNING):
        return "The run is queued or running; cancel it first."
    deployment = await cleanup.run_is_served_by_deployment(db, run.id)
    if deployment is not None:
        return f"The run is served by the deployment '{deployment}'; delete the deployment first."
    return None


async def _delete_run_checked(db: AsyncSession, run: TrainingRun) -> Dict[str, Any]:
    result = await cleanup.delete_run(db, run)
    await write_audit(
        db, run.owner_id, "run.deleted", "run", run.id,
        {"model_name": run.model_name, "artifact_removed": result["artifact_removed"]},
    )
    return result


@app.delete("/api/v1/ml/runs/{run_id}")
async def delete_run(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a run of the caller (plan H1): the row, its artifact directory
    and its charts. A run that is queued or running is refused (cancel it
    first), and so is a run that a deployment still serves."""
    result = await db.execute(
        select(TrainingRun).where(
            TrainingRun.id == run_id, TrainingRun.owner_id == current_user.id
        )
    )
    run = result.scalars().first()
    if run is None:
        raise HTTPException(status_code=404, detail="Training run not found")
    reason = await _deleteable_run(run, current_user, db)
    if reason:
        raise HTTPException(status_code=409, detail=reason)
    summary = await _delete_run_checked(db, run)
    await db.commit()
    return {"deleted": [summary]}


class _BulkDelete(BaseModel):
    ids: List[int]


@app.post("/api/v1/ml/runs/delete-bulk")
async def delete_runs_bulk(
    body: _BulkDelete,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete several runs at once (plan H1).

    The answer says what happened to every id: the ones that went, and the
    ones that were refused with the reason - a bulk action must not die on
    the first exception, and it must not pretend the refused ones went.
    """
    if not body.ids:
        return {"deleted": [], "refused": []}
    if len(body.ids) > 100:
        raise HTTPException(status_code=422, detail="Delete at most 100 runs at a time.")
    runs = (
        await db.execute(
            select(TrainingRun).where(
                TrainingRun.id.in_(body.ids), TrainingRun.owner_id == current_user.id
            )
        )
    ).scalars().all()
    found = {run.id: run for run in runs}
    deleted: List[Dict[str, Any]] = []
    refused: List[Dict[str, Any]] = []
    for requested in body.ids:
        run = found.get(requested)
        if run is None:
            refused.append({"id": requested, "reason": "No such run."})
            continue
        reason = await _deleteable_run(run, current_user, db)
        if reason:
            refused.append({"id": requested, "reason": reason})
            continue
        deleted.append(await _delete_run_checked(db, run))
    await db.commit()
    return {"deleted": deleted, "refused": refused}


@app.delete("/api/v1/ml/datasets/{dataset_id}")
async def delete_dataset(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an uploaded dataset (plan H1): the file and the row.

    The datasets that ship with the repository are refused (they are not the
    caller's to delete), and so is a dataset an active run is reading right
    now - the training holds the path, and pulling it would fail the run.
    """
    dataset = await db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if dataset.owner_id is None:
        raise HTTPException(
            status_code=403,
            detail="The datasets that ship with the repository cannot be deleted.",
        )
    if dataset.owner_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=404, detail="Dataset not found")
    active = (
        await db.execute(
            select(TrainingRun.id)
            .where(
                TrainingRun.dataset_id == dataset.id,
                TrainingRun.status.in_((STATUS_QUEUED, STATUS_RUNNING)),
            )
            .limit(1)
        )
    ).scalar()
    if active is not None:
        raise HTTPException(
            status_code=409,
            detail="The dataset is used by a queued or running training; cancel that run first.",
        )
    try:
        path = resolve_storage_path(dataset.storage_path)
    except DatasetError:
        path = None
    if path is not None and path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path is not None and path.exists():
        try:
            path.unlink()
        except OSError:
            logger.warning("The file of the dataset %s could not be removed", dataset.id)
    await write_audit(
        db, current_user.id, "dataset.deleted", "dataset", dataset.id,
        {"name": dataset.name},
    )
    await db.delete(dataset)
    await db.commit()
    return {"deleted": dataset_id}


class _SelfDelete(BaseModel):
    password: str


@app.post("/api/v1/users/me/delete")
async def delete_own_account(
    body: _SelfDelete,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete the caller's own account (plan H1): the password is required,
    the runs, the datasets, the files, the sessions and the API keys go with
    it. A POST with the password in the body, not a DELETE: a password is a
    payload, and several HTTP clients refuse to carry a body on DELETE. The
    deployments of the account are refused if any is live - an endpoint other
    callers may be using must not vanish silently."""
    matches = await run_in_threadpool(
        verify_pass, body.password, current_user.hashed_password
    )
    if not matches:
        raise HTTPException(status_code=400, detail="The password is not correct.")
    if current_user.role == "admin":
        admins = (
            await db.execute(select(func.count(User.id)).where(User.role == "admin"))
        ).scalar() or 0
        if admins <= 1:
            raise HTTPException(status_code=409, detail="The last admin cannot be deleted.")
    live_deployments = (
        await db.execute(
            select(func.count(Deployment.id)).where(
                Deployment.owner_id == current_user.id,
            )
        )
    ).scalar() or 0
    if live_deployments:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{live_deployments} deployment(s) still serve this account; delete "
                "them before deleting the account."
            ),
        )
    await admin_module.purge_user(db, current_user)
    await write_audit(
        db, current_user.id, "user.deleted_self", "user", current_user.id, {}
    )
    await db.commit()
    response = JSONResponse({"detail": "The account and its data are deleted."})
    _clear_refresh_cookie(response)
    return response


@app.get("/api/v1/ml/runs/{run_id}/artifact")
async def download_artifact(run_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The artifact of a run: a zip when it is a bundle directory (plan C1)."""
    result = await db.execute(select(TrainingRun).where(TrainingRun.id == run_id, TrainingRun.owner_id == current_user.id))
    run = result.scalars().first()
    if not run or not run.artifact_path:
        raise HTTPException(status_code=404, detail="Artifact not found")
    path = Path(run.artifact_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact file missing")
    if path.is_file():
        return FileResponse(str(path), filename=path.name)
    if not path.is_dir():
        raise HTTPException(status_code=404, detail="Artifact file missing")

    import zipfile

    from fastapi.responses import Response

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(path.rglob("*")):
            if file.is_file():
                archive.write(file, file.relative_to(path))
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="artifact_{run.id}.zip"'},
    )


# --- inference, version 2 (plan D) --------------------------------------------
# A saved artifact is only useful if it can be used. The schema route says
# what a request must contain (the UI builds its form from it), and the
# predict route answers for data the model has never seen. Both dispatch on
# the bundle: a tabular model takes rows, a text classifier takes texts, a
# language model takes a prompt, a forecaster takes a window, a graph model
# takes node ids, a vision model takes an image upload, and a reinforcement
# learner takes a state.

# The most rows one tabular prediction request may carry. The rows are held
# in memory and predicted in one call, so the limit is what keeps one request
# cheap.
PREDICT_MAX_ROWS = int(os.getenv("PREDICT_MAX_ROWS", "1000"))


async def get_predict_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    """The user of a predict request: an API key or the login (plan D2).

    A key is accepted on the predict endpoints only (its scope is
    ``predict``), is rate-limited per key, and counts against the owner's
    quota. Everything else needs the login.
    """
    if token.startswith("sk-"):
        user = await inference_module.user_for_api_key(db, token)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or revoked API key",
                headers={"WWW-Authenticate": "Bearer"},
            )
        request.state.user = user
        return user
    user = await get_current_user(token=token, db=db)
    request.state.user = user
    return user


async def _run_of_caller(run_id: int, current_user: User, db: AsyncSession) -> TrainingRun:
    result = await db.execute(
        select(TrainingRun).where(TrainingRun.id == run_id, TrainingRun.owner_id == current_user.id)
    )
    run = result.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="Training run not found")
    if run.status != STATUS_COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"The run is {run.status}: only a completed run can predict.",
        )
    return run


@app.get("/api/v1/ml/runs/{run_id}/schema")
async def get_run_schema(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The shape of a prediction request for the model of a completed run."""
    run = await _run_of_caller(run_id, current_user, db)
    try:
        _, bundle = await load_bundle_of_run(run)
    except BundleError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 409), detail=str(exc)
        ) from None
    return {
        "run_id": run.id,
        **bundle.schema(),
        "max_rows": PREDICT_MAX_ROWS,
        "request_kind": bundle.request_kind,
    }


@app.post("/api/v1/ml/runs/{run_id}/predict")
async def predict_with_run(
    run_id: int,
    body: PredictRequest,
    current_user: User = Depends(get_predict_user),
    db: AsyncSession = Depends(get_db),
):
    """Predict with the model of a completed run (any bundle kind, plan D4).

    ``explain=true`` returns the features that moved the prediction
    (plan D5): coefficient times value for the linear models, a per-row
    permutation estimate for the rest.
    """
    run = await _run_of_caller(run_id, current_user, db)
    if len(body.rows or []) > PREDICT_MAX_ROWS:
        raise HTTPException(
            status_code=413,
            detail=f"A request may carry at most {PREDICT_MAX_ROWS} rows, got {len(body.rows)}.",
        )
    try:
        return await run_prediction(db, current_user, run, body)
    except BundleError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 409), detail=str(exc)
        ) from None


@app.post("/api/v1/ml/runs/{run_id}/predict-image")
async def predict_image_with_run(
    run_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_predict_user),
    db: AsyncSession = Depends(get_db),
):
    """Predict an uploaded image with a vision model (plan C3).

    The upload is capped and decoded with Pillow's decompression-bomb guard
    on: the artifact carries the exact transform the training used, so the
    preprocessing of a prediction is the preprocessing of the training.
    """
    run = await _run_of_caller(run_id, current_user, db)
    content = await file.read()
    await file.close()
    try:
        _, bundle = await load_bundle_of_run(run)
    except BundleError as exc:
        raise HTTPException(
            status_code=getattr(exc, "status_code", 409), detail=str(exc)
        ) from None
    if bundle.request_kind != "image":
        raise HTTPException(
            status_code=422,
            detail="This model does not take an image upload; use the predict endpoint.",
        )
    from fastapi.concurrency import run_in_threadpool

    try:
        result = await run_in_threadpool(bundle.infer, {"images": [content]})
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=_public_error(exc)) from None
    return {"run_id": run.id, "model_name": run.model_name, **result}


# --- the routers of the plan: the admin API (A6) and inference v2 (D) ----------


async def _admin_route_guard(request: Request, admin: User = Depends(get_current_admin)):
    """The role check of every admin route (plan A10): attached to the router
    at include time, so an admin route can never be exposed without it."""
    request.state.admin_user = admin
    return admin


async def _user_route_guard(request: Request, user: User = Depends(get_current_user)):
    """The login requirement of the inference routes (plan D)."""
    request.state.user = user
    return user


def _include_inference_router() -> None:
    """Attach the inference routes with the right authentication (plan D2).

    The predict routes accept an API key as well as the login; everything
    else (creating a deployment, listing the keys) needs the login, because a
    key has the predict scope only.
    """
    from fastapi.routing import APIRoute

    for route in inference_module.router.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path.endswith("/predict") or route.path.endswith("/predict-file"):
            route.dependencies.append(Depends(get_predict_user))
        else:
            route.dependencies.append(Depends(_user_route_guard))
    app.include_router(inference_module.router)


def _include_admin_router() -> None:
    """Attach the admin routes behind the role check (plan A10).

    The guard is appended to every route before the router is included, so
    an admin route can never be exposed without it.
    """
    for route in admin_module.router.routes:
        route.dependencies.append(Depends(_admin_route_guard))
    app.include_router(admin_module.router)


_include_admin_router()
_include_inference_router()
# The health, readiness and metrics endpoints of plan H3: deliberately
# outside the user guard, because a monitor holds no account.
app.include_router(observability.router)
