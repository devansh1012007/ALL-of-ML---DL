# FOLLOWUP_PLAN — the deferred round for ALL-of-ML---DL

> **Superseded: executed under WEEK1_PLAN, see commits.** Phases 6-11 were carried out as
> W1-1 ... W1-8 (`git log --grep "PLAN:week1"`), with these deviations: training rows start as
> `queued` (not `running`), the dataset registry and a real `auto_tune` were added, and the
> catalog round finished with 13 placeholder entries (the five NLP ones - BERT2BERT, seq2seq, UL2,
> GPT, LLaMA - were flagged in a later commit) instead of a real `Autoencoder`.
> The still-open items of section 11 moved to `TODO.MD`. Do not read this file as a description
> of the current code.

Status: ~~ready to execute~~ **superseded** · Written 2026-10-20, after the bug-fix round (commits `36ad1dc`, `a21e4d2`, `e70a650`).

This document plans the six items that `FIX_PLAN.md` deliberately deferred. It is written to be
executable by someone who has not read the investigation: every phase states **why** the change is
needed (with the measured evidence), **exactly what** to change, **which tests** prove it, and
**what could go wrong**. Phases continue the numbering of `FIX_PLAN.md` (which covered phases 1-5).

---

## 1. Context

### 1.1 Where the repo stands

| | |
|---|---|
| Backend | FastAPI + async SQLAlchemy + Alembic, `backend/app/main.py` (all routes), `backend/app/model_training.py` (~1700 lines, the ML core) |
| Frontend | Vite + React 18 SPA in a single file, `frontend/App.jsx` (~1410 lines), dev server on port **3000**, API base hardcoded to `http://localhost:8010` |
| Tests | `python -m pytest backend/tests` from the repo root → **102 passed, 9 skipped** (the 9 skips are the `nlp` catalog entries, which need checkpoint downloads) |
| Frontend checks | `cd frontend && npm run build` — there is no frontend test suite and no linter anywhere |
| Toolchain | `fastapi 0.152`, `starlette 1.9`, `sqlalchemy 2.1.5`, `scikit-learn 1.9.1`, `pandas 3.0.6`, `pytest 9.1.1`. **Optional and absent**: `torch`, `transformers`, `torchvision`, `gymnasium`, `stable-baselines3`, `hmmlearn`, `umap`, `hdbscan`, `google-generativeai` |

### 1.2 The six deferred items and their decisions

| # | Item | Decision taken | Phase |
|---|---|---|---|
| D1 | The `on_event("startup")` deprecation | Migrate to a `lifespan` handler | 6 |
| D2 | Alembic drift (`notes` created, `training_runs` never) | **Drop `notes`**, **Alembic is the only schema owner** (remove `create_all`) | 7 |
| D3 | Async training | `BackgroundTasks` + a `running` → `completed`/`failed` row lifecycle + frontend polling | 8 |
| D4 | CORS / secret posture | **Require a token everywhere**; env-driven CORS allow-list; `SECRET_KEY` never published | 9 |
| D5 | `readme.md` staleness | Full rewrite, executed last so it describes the final state | 11 |
| D6 | The fake `timeseries`/`graph`/`autoencoder` (and friends) implementations | **Honest metadata + fail fast** (+ a real autoencoder, + a silhouette metric) | 10 |

The four decisions marked **bold** were taken by the repository owner. They are binding; the
alternatives are recorded in the "Rejected alternatives" section of each phase for future reference.

### 1.3 Phase order and why it is sequential

```
Phase 6  lifespan  ──► Phase 7  Alembic  ──► Phase 8  async training
                                              └──► Phase 9  security  ──► Phase 10  model honesty
                                                                                      │
                                                                            Phase 11  docs
```

The phases **cannot** be parallelised: `backend/app/main.py` is touched by phases 6, 7, 8 and 9;
`backend/app/model_training.py` by phases 9 and 10; `frontend/App.jsx` by phases 8 and 10. Phases 6-9
also build on each other structurally (the schema check and the stuck-run reaper both live in the
lifespan handler that phase 6 introduces).

Each phase must go through the mandatory review gate in `AGENTS.md`: an independent reviewer
subagent audits the phase's diff, the findings are fixed, the review is repeated, and only then is
the next phase started.

---

## 2. Phase 6 — Replace `@app.on_event("startup")` with a `lifespan` handler

### 2.1 Why

`backend/app/main.py:126-129` uses the deprecated startup hook:

```python
@app.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

FastAPI 0.152 emits `DeprecationWarning: on_event is deprecated, use lifespan event handlers
instead` on every import and every test run. The hook is also the place where phases 7 (the schema
check) and 8 (the stuck-run reaper) must live, so it has to be the modern one before they land.

A subtlety worth knowing: `create_all` only creates the tables of the models that were **imported**
at the moment it runs. It works today only because `main.py:14` imports `.models`. Any refactor that
moves the call into a module that does not import the ORM silently creates **nothing** — a trap that
phase 7 removes entirely.

### 2.2 What changes

**File: `backend/app/main.py`**

1. Add the import:
   ```python
   from contextlib import asynccontextmanager
   ```
2. Insert the lifespan handler **before** `app = FastAPI(...)` (currently line 20):
   ```python
   @asynccontextmanager
   async def lifespan(app: FastAPI):
       """Application lifespan: prepare the database before the first request.

       Phase 7 replaces the table creation with a schema check and phase 8 adds
       the reaper for runs that were interrupted by a restart; both belong here.
       """
       async with engine.begin() as conn:
           await conn.run_sync(Base.metadata.create_all)
       yield
   ```
3. Change the app construction to pass it:
   ```python
   app = FastAPI(title="PrimeTrade AutoML API", lifespan=lifespan)
   ```
4. **Delete** the old `@app.on_event("startup")` block (lines 126-129).

> **Do not keep both.** FastAPI uses its default lifespan only when `lifespan is None`; passing a
> custom `lifespan` **replaces** it, so a leftover `@app.on_event("startup")` would silently stop
> running — the app would start with no tables and no error.

### 2.3 Tests

No new test is required, but the existing ones are the proof:

- `backend/tests/test_main.py:7,14,23` and `backend/tests/test_auth_and_runs.py:51-55` all use
  `with TestClient(app) as client:` — `TestClient.__enter__` starts the lifespan task, so the schema
  is still created. The suite staying green is the acceptance criterion.
- A `TestClient(app)` **without** the context manager runs no lifespan and creates no tables. That
  was the root cause R4 of the previous round; the suite must keep using the `with` form. The plan
  adds an explicit note in `backend/tests/conftest.py` so nobody reintroduces the trap.

### 2.4 Acceptance criteria

- `python -m pytest backend/tests` → still **102 passed, 9 skipped**.
- The `DeprecationWarning: on_event is deprecated` no longer appears in the test output.
- `backend/app/main.py` contains no `on_event`.

### 2.5 Risks

| Risk | Mitigation |
|---|---|
| A leftover `on_event` silently stops running | the acceptance criteria above (the suite would fail with "no such table: users") |
| The `lifespan` function is defined after `FastAPI(...)` → `NameError` | define it before line 20 |

### 2.6 Docs to update in this phase

`AGENTS.md` — the "Environment gotchas" section does not mention the startup hook, so nothing
changes yet. Phase 7 rewrites the migration story.

---

## 3. Phase 7 — Make Alembic the only schema owner

### 3.1 Why

**Measured**: `alembic upgrade head` on an empty database produces `alembic_version, users, notes` —
**`training_runs` is never created**. The app only works because `create_all` creates it behind
Alembic's back. The consequences are severe:

1. `alembic upgrade head` produces a schema the application **cannot use**.
2. The `notes` table is a vestige of the previous "PrimeTrade Secure Notes API" project. It is
   referenced by **no** ORM model, **no** route and **no** frontend view — only by the migration and
   by the stale `alembic.ini` URL (`admin:password123@localhost:5433/**notes_db**`). The committed
   `backend/app.log` still contains its log lines from 2026-03-25.
3. `create_all` **poisons the migration path**: a database that the app has started against has
   `training_runs` without Alembic knowing, so a later `alembic upgrade head` fails with
   `DuplicateTableError: relation "training_runs" already exists` and `alembic_version` stays
   behind. Every existing developer database is already in that state.
4. `backend/alembic.ini:89` still hardcodes the previous project's URL. When `DATABASE_URL` is
   unset, `migrations/env.py:74-76` leaves it in place and Alembic tries to connect to
   `127.0.0.1:5433/notes_db` — a misleading "connection refused" that looks like "Postgres is not
   up" rather than "the URL is wrong".
5. `migrations/env.py` calls `config.set_main_option("sqlalchemy.url", db_url)` without escaping
   `%`, so a password containing `%` crashes ConfigParser with
   `ValueError: invalid interpolation syntax`.

### 3.2 Decision

Alembic owns the schema. `create_all` is removed. The startup hook becomes a **verification** that
fails fast with an actionable message, and the test suite builds its schema by **running the
migrations** — which means the suite itself now proves that the migration chain matches the ORM.

### 3.3 What changes

#### 3.3.1 A new revision

**New file: `backend/migrations/versions/c4a9e2b17d3f_add_training_runs_drop_notes.py`**

```python
"""add training_runs table, drop the vestigial notes table

Revision ID: c4a9e2b17d3f
Revises: 7f9590585a2a
Create Date: 2026-10-20 21:15:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4a9e2b17d3f'
down_revision: Union[str, Sequence[str], None] = '7f9590585a2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    """Upgrade schema."""
    tables = _existing_tables()

    if 'training_runs' not in tables:
        op.create_table('training_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('model_name', sa.String(), nullable=False),
        sa.Column('dataset_source', sa.String(), nullable=False),
        sa.Column('dataset_tag', sa.String(), nullable=False),
        sa.Column('hf_dataset_url', sa.String(), nullable=True),
        sa.Column('mode', sa.String(), nullable=False),
        sa.Column('env_id', sa.String(), nullable=True),
        sa.Column('optimize_metric', sa.String(), nullable=True),
        sa.Column('model_candidates', sa.JSON(), nullable=True),
        sa.Column('hyperparameters', sa.JSON(), nullable=False),
        sa.Column('metrics', sa.JSON(), nullable=True),
        sa.Column('artifact_path', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_training_runs_id'), 'training_runs', ['id'], unique=False)

    if 'notes' in tables:
        op.drop_index(op.f('ix_notes_id'), table_name='notes')
        op.drop_table('notes')


def downgrade() -> None:
    """Downgrade schema."""
    tables = _existing_tables()

    if 'notes' not in tables:
        op.create_table('notes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('content', sa.String(), nullable=True),
        sa.Column('owner_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_notes_id'), 'notes', ['id'], unique=False)

    if 'training_runs' in tables:
        op.drop_index(op.f('ix_training_runs_id'), table_name='training_runs')
        op.drop_table('training_runs')
```

Four decisions inside this file are deliberate and must not be "simplified":

- **The DDL is idempotent** (guarded by `_existing_tables()`). Real databases are in one of three
  states — migrated to `7f9590585a2a` (`users` + `notes`), touched only by `create_all`
  (`users` + `training_runs`), or both. A plain revision fails on two of the three with
  `DuplicateTableError`. The guards make `alembic upgrade head` succeed from any of them.
- **`sa.func.now()`, not `sa.text('now()')`.** Autogenerate emits `sa.text('now()')`, which renders
  as `DEFAULT (now())` on SQLite and fails with `OperationalError: unknown function: now()` on
  INSERT. `sa.func.now()` renders as `CURRENT_TIMESTAMP` on SQLite and `now()` on Postgres — and it
  is byte-identical to what `create_all` produces.
- **`sa.JSON()`, not `postgresql.JSONB()`.** The ORM declares plain `sa.JSON`; `alembic check`
  reports three `modify_type` diffs for JSONB, and `JSONB` also renders with the wrong affinity
  on SQLite.
- **The ORM-only concerns are deliberately not in the DDL**: `role="user"`, `mode="manual"` and
  `status="pending"` are Python-side defaults, `onupdate=func.now()` is SQLAlchemy-level (a raw
  SQL `UPDATE` does not refresh `updated_at`), and `relationship`/`cascade` never appear in DDL.

`down_revision` is `'7f9590585a2a'`: the no-op revision `7f9590585a2a` is **kept** (removing it
would break the `alembic_version` of every existing database).

#### 3.3.2 The URL is never read from the ini file

**File: `backend/alembic.ini`** — replace line 89 (`sqlalchemy.url = postgresql+asyncpg://admin:password123@localhost:5433/notes_db`) with:

```ini
# The database URL comes from the DATABASE_URL environment variable
# (migrations/env.py resolves it) and is intentionally left empty here: a
# hard-coded URL in this file silently points Alembic at the wrong database.
sqlalchemy.url =
```

**File: `backend/migrations/env.py`** — resolve the URL once, at module level, so the online *and*
the offline (`--sql`) paths agree, and fall back to the application's own default so Alembic and the
app can never disagree:

```python
from app.database import DATABASE_URL
from app.models import Base
...
config = context.config

# The URL is never taken from alembic.ini: it comes from the DATABASE_URL
# environment variable, or -- when that is not set -- from the application's own
# default, so Alembic and the app always talk to the same database.
# "%%" is required because ConfigParser treats a bare "%" as interpolation syntax.
db_url = os.getenv("DATABASE_URL") or DATABASE_URL
config.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
```

and in `run_async_migrations()` replace the config-driven engine with a direct one:

```python
    connectable = create_async_engine(db_url, poolclass=pool.NullPool)
```

(`from sqlalchemy.ext.asyncio import create_async_engine`; `async_engine_from_config` and the
`prefix="sqlalchemy."` indirection are no longer needed.)

#### 3.3.3 The app verifies the schema instead of creating it

**File: `backend/app/main.py`** — replace the body of the lifespan handler (phase 6) with:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Fail fast when the schema has not been migrated.

    The schema is owned by Alembic (``alembic upgrade head``); the app must
    never create tables itself, because that hides a migration that was never
    applied.
    """
    async with engine.connect() as conn:
        names = await conn.run_sync(
            lambda sync_conn: sa.inspect(sync_conn).get_table_names()
        )
    missing = [table.name for table in Base.metadata.sorted_tables if table.name not in names]
    if missing:
        raise RuntimeError(
            "The database schema is not up to date: missing table(s) "
            f"{missing}. Run `alembic upgrade head` in the backend/ directory first."
        )
    yield
```

(`import sqlalchemy as sa` is needed; `engine` and `Base` are already imported at `main.py:13`.)

#### 3.3.4 The test suite builds its schema with the migrations

**File: `backend/tests/conftest.py`** — add a session fixture:

```python
@pytest.fixture(scope="session", autouse=True)
def _migrated_test_database():
    """Create the schema with Alembic -- the same path production uses.

    The application deliberately does not call ``Base.metadata.create_all`` any
    more, so the schema has to come from the migrations. Running them here also
    means the test suite fails if the migration chain ever drifts away from
    ``backend/app/models.py`` again.
    """
    from alembic import command
    from alembic.config import Config

    backend_dir = os.path.join(REPO_ROOT, "backend")
    config = Config(os.path.join(backend_dir, "alembic.ini"))
    config.set_main_option("script_location", os.path.join(backend_dir, "migrations"))
    command.upgrade(config, "head")
    yield
```

The conftest already sets `DATABASE_URL` to an isolated temp sqlite file **before** the app is
imported, and the `atexit` hook removes that directory — the migration therefore runs against the
throwaway database.

> **Note**: `alembic` is already in `backend/requirements.txt:15`, but it is **not** installed in the
> verification venv used during development. Install it with
> `uv pip install --python /tmp/opencode/verify-venv/bin/python alembic` before running the suite.

#### 3.3.5 Compose runs the migrations

**File: `backend/docker-compose.yml`** — line 18 overrides the image `CMD`, so the migrations never
run in compose. Change it to mirror the Dockerfile:

```yaml
    command: sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload"
```

### 3.4 Tests

- The existing suite keeps passing, but now it **proves** the migration chain: the schema comes from
  `alembic upgrade head`, so a drift between `backend/app/models.py` and the migrations fails the
  suite instead of being papered over.
- **New test** (in `backend/tests/test_catalog_params.py` or a new `backend/tests/test_migrations.py`):
  a test that the migrated schema matches the ORM — e.g. run `alembic check` (needs alembic ≥ 1.9)
  and assert it reports no operations, or compare the table/column names of the migrated database
  with `Base.metadata.sorted_tables`.
- **New test**: the startup hook fails with the actionable message when a table is missing. It can
  be triggered by pointing `DATABASE_URL` at an empty database and importing the app — the
  `RuntimeError` must mention `alembic upgrade head`.

### 3.5 Acceptance criteria

- `alembic upgrade head` on an **empty** database produces exactly `users` + `training_runs`
  (+ `alembic_version`) and `alembic check` reports no drift.
- `alembic upgrade head` on a database that was previously touched by `create_all` (i.e. has
  `training_runs` but no `notes`) succeeds and is idempotent.
- `python -m pytest backend/tests` → still **102 passed, 9 skipped**.
- `Base.metadata.create_all` no longer appears anywhere in `backend/app/`.
- `backend/alembic.ini` contains no database URL.

### 3.6 Risks and rollback

| Risk | Severity | Mitigation |
|---|---|---|
| **`notes` rows are destroyed** (the table may hold real notes from the previous project in someone's dev database) | data loss | the owner accepted this. Recommend a `pg_dump -t notes` before upgrading; the `downgrade()` path recreates an **empty** table, it does not restore rows |
| The test suite now needs `alembic` installed | medium | it is already in `requirements.txt`; note it in `AGENTS.md` |
| A developer's database is in state 2 or 3 (see above) | high | the revision is idempotent by design |
| `create_all` removal breaks the compose deployment | high | phase 7 also changes `docker-compose.yml` (3.3.5) — the two must land together |
| `create_all` removal breaks the documented quickstart | medium | `readme.md` is rewritten in phase 11 with `alembic upgrade head` in the setup steps |
| A `%` in the database password | low | the `%%` escaping in `env.py` fixes it |

**Rollback**: `cd backend && alembic downgrade 7f9590585a2a` (drops `training_runs`, recreates an
empty `notes`) or `alembic downgrade base` (full teardown). Reverting the code in git additionally
requires `alembic stamp 7f9590585a2a` on any database already stamped with the new revision.

### 3.7 Rejected alternatives

- **Keep `create_all` and make the revision idempotent** — the drift stays masked and the
  `DuplicateTableError` trap stays open for future revisions.
- **Drop `notes` in a separate later revision** — two migrations instead of one, and the orphan
  table lives longer.
- **Rewrite the migration history** (a fresh root revision) — breaks every existing `alembic_version`.

### 3.8 Docs to update in this phase

- `AGENTS.md` — the "Commands" section says `cd backend && alembic upgrade head`; add that the
  migrations are now the **only** schema owner, that the app refuses to start on an unmigrated
  database, and that `alembic` must be installed for the test suite.
- `backend/app/README.md` — add an "Operational notes" line that the schema is owned by Alembic.

---

## 4. Phase 8 — Asynchronous training

### 4.1 Why

`backend/app/main.py:241-297` trains **inside the request**:

```python
    try:
        metrics, dataset_source, dataset_tag, artifact_path = await run_in_threadpool(
            train_model, payload.model_name, ...
        )
        ...
        return {"run_id": ..., "status": ..., "artifact_path": ..., "metrics": ...}
    except Exception as exc:
        training_run.status = "failed"
        training_run.metrics = {"error": str(exc)}
        await db.commit()
        logger.exception("Model training failed")
        raise HTTPException(status_code=400, detail=str(exc))
```

Consequences, all measured:

1. **The HTTP response waits for the whole training.** The catalog advertises up to 60 s for the
   neural entries and the RL entries default to 10 000 timesteps — a request can hang for minutes.
2. **A cancelled request leaves the run stuck in `running` forever.** `except Exception` does not
   catch `asyncio.CancelledError`, and Starlette's `run_in_threadpool` (anyio
   `to_thread.run_sync`, `abandon_on_cancel=False`) lets the thread **finish** and then raises the
   `CancelledError` at the `await` — so the `except` block is skipped entirely. Reproduced with a
   direct ASGI cancellation probe: the training completed, the row stayed `status="running"`.
   Nothing else in the codebase ever writes `"failed"` outside that handler.
3. The frontend's "New Job" form blocks for the duration and shows "Initializing Run…" the whole
   time.

### 4.2 Decision

`BackgroundTasks` — no new dependency, keeps the existing `run_in_threadpool` offload, and the
background task is a thin wrapper around `train_model` so it can later be swapped for a Celery/RQ
task in one place.

### 4.3 What changes

#### 4.3.1 The worker (`backend/app/main.py`)

Add the imports (`from fastapi import BackgroundTasks`; `AsyncSessionLocal` from `.database`) and two
module-level functions **above** the endpoint:

```python
async def _finish_run(run_id: int, **fields) -> None:
    """Write the outcome of a run with its own session.

    The request-scoped session (get_db) belongs to the request; the background
    task outlives it, so it must not share it.
    """
    async with AsyncSessionLocal() as session:
        run = await session.get(TrainingRun, run_id)
        if run is None:
            return
        for name, value in fields.items():
            setattr(run, name, value)
        await session.commit()


async def _execute_training(run_id: int, request: TrainRequest) -> None:
    """Train in the background and record the outcome in the run row.

    This coroutine never raises: the response has already been sent, so an
    exception here could only be logged by the server - the row has to carry
    the error instead.
    """
    try:
        metrics, dataset_source, dataset_tag, artifact_path = await run_in_threadpool(
            train_model,
            request.model_name, request.dataset_name, request.hf_dataset_url,
            request.label_column, request.test_size, request.random_state,
            request.hyperparameters or {}, request.sep, request.usecols,
            request.mode, request.optimize_metric, request.env_id,
            request.model_candidates, request.preset,
        )
    except Exception as exc:
        logger.exception("Model training failed for run %s", run_id)
        await _finish_run(run_id, status="failed", metrics={"error": str(exc)})
        return

    await _finish_run(run_id, status="completed", metrics=metrics,
                      artifact_path=artifact_path,
                      dataset_source=dataset_source, dataset_tag=dataset_tag)
```

#### 4.3.2 The endpoint

```python
@app.post("/api/v1/ml/train")
async def train_model_endpoint(payload: TrainRequest, background_tasks: BackgroundTasks,
                               current_user: User = Depends(get_active_user),
                               db: AsyncSession = Depends(get_db)):
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
    run_id = training_run.id

    # The row is committed before the response, so the client can poll it.
    background_tasks.add_task(_execute_training, run_id, payload)

    return {"run_id": run_id, "status": "running", "artifact_path": None, "metrics": None}
```

The `try/except` and the 400 disappear from the endpoint: **the row becomes the error channel**.

#### 4.3.3 Reaping runs interrupted by a restart

A training thread dies with the process, so its row stays `running`. Add to the lifespan handler
(phase 7's):

```python
        # A training that was interrupted by a restart leaves its row in
        # "running" forever: the thread died with the process. Those rows are
        # failed at startup. This is exact for the single-worker deployment the
        # compose file runs; a multi-worker deployment would need a heartbeat
        # and a staleness rule instead.
        async with engine.begin() as conn:
            await conn.execute(
                TrainingRun.__table__.update()
                .where(TrainingRun.status == "running")
                .values(status="failed",
                        metrics={"error": "The training process restarted before the run finished."})
            )
```

#### 4.3.4 The frontend polls (`frontend/App.jsx`)

`RunDetails` currently fetches once (`App.jsx:523-531`). Replace that effect with a
self-rescheduling poll that stops as soon as the status leaves `running`:

```jsx
  useEffect(() => {
    let active = true;
    let timer = null;
    const poll = async () => {
      try {
        const data = await apiFetch(`/api/v1/ml/runs/${runId}`);
        if (!active) return;
        setRun(data);
        setError(null);
        if (data.status === 'running') timer = setTimeout(poll, 2000);
      } catch (err) {
        if (active) setError(err);
      }
    };
    setRun(null);
    setError(null);
    poll();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [apiFetch, runId]);
```

- **Exit condition**: `status !== 'running'`.
- **Interval**: 2000 ms, using chained `setTimeout` (not `setInterval`) so requests cannot overlap.
  `RunsDashboard` already polls every 5 s, so this is consistent with the app.
- `NewJob.handleSubmit` needs **no** change: it only reads `result.run_id`.
- The `running` badge should get the existing `Activity`/`animate-pulse` icon so the user sees that
  the run is live.

### 4.4 The API contract change

The response keeps the same four keys but with `status="running"`, `artifact_path=None` and
`metrics=None`; the client polls `GET /api/v1/ml/runs/{id}`, which **already** returns `status`,
`metrics`, `artifact_path` and `updated_at` — no backend change is needed for polling.

The HTTP status stays **200** (not 202) to avoid churn in the frontend and the existing assertions.

### 4.5 Tests

Two existing tests depend on the synchronous behaviour and must be rewritten:

| Test | Today | After |
|---|---|---|
| `backend/tests/test_main.py::test_train_invalid_dataset` | asserts **400** and `"not found"` in `detail` | POST → 200 + `run_id` + `status == "running"`; then `GET /api/v1/ml/runs/{run_id}` → `status == "failed"` and `"not found"` in `metrics["error"].lower()` |
| `backend/tests/test_auth_and_runs.py::test_auto_search_picks_the_better_candidate_on_a_regression_dataset` | reads `response.json()["metrics"]` | POST → `run_id`; then read the metrics from the run detail |
| `backend/tests/test_auth_and_runs.py::test_run_history_exposes_the_mode_and_the_environment` | does a raw SQL `UPDATE` on the row right after the POST | the raw UPDATE now **races** the background worker (and can hit `database is locked` on SQLite) → wait for a terminal status before the UPDATE, or assert `mode`/`env_id` without the raw UPDATE |

**New tests**:

1. A failed training ends with the row in `status="failed"` and the error in `metrics["error"]`.
2. A successful training ends with `status="completed"`, the metrics, the artifact path, and
   `dataset_source`/`dataset_tag` from `train_model`.
3. The background task never raises: a training failure must not surface as a 500.

> **Testing caveat**: `TestClient` awaits the whole ASGI call, so the background task has already
> finished when `client.post(...)` returns. A test that asserts "the POST returns before the training
> finishes" therefore **fails** under `TestClient` — such a test needs a real server. Tests that
> assert the final row state immediately after the POST work fine.

### 4.6 Acceptance criteria

- `POST /api/v1/ml/train` returns `{"run_id": N, "status": "running", ...}` immediately.
- The run row reaches `completed` or `failed`; a failed run carries the error in `metrics["error"]`.
- The frontend's run detail page shows the live status and then the metrics.
- The suite passes (102 passed, 9 skipped, plus the new tests).

### 4.7 Risks

| Risk | Mitigation |
|---|---|
| A background task that raises is re-raised into `TestClient` (`RuntimeError: Caught handled exception, but response already started.`) | the task catches everything and returns; it never raises |
| The event loop is blocked by the training | `run_in_threadpool` **inside** the async task; a direct `train_model(...)` call would block every other request |
| The request-scoped session is reused in the task | the task opens its own `AsyncSessionLocal()` session; the request session is closed when the request ends |
| The startup reaper kills a live run in a multi-worker deployment | documented; the compose file runs a single worker. A multi-worker deployment needs a heartbeat — that is a follow-up, not this phase |
| `updated_at` is not refreshed during a long training (1 s resolution, ORM-level `onupdate`) | it is not used as a progress signal; the status is |

### 4.8 Rejected alternatives

- **`threading.Thread` + an in-process queue** — a detached thread needs its own event loop for the
  async SQLAlchemy writes, and `asyncpg` (the production driver) binds connections to the creating
  loop.
- **Celery / RQ / arq** — the right long-term answer, but it needs a broker, a worker service, worker
  DB credentials and a test harness. The chosen design keeps the swap local to `_execute_training`.
- **A polling job table** — over-engineering; `training_runs` already *is* the job table.

### 4.9 Docs to update in this phase

- `AGENTS.md` — the "Environment gotchas" line "`POST /api/v1/ml/train` trains **synchronously**" must
  change to describe the background task and the polling contract.
- `backend/app/README.md` — the "limitations" section says "Synchronous execution: … consider a job
  queue"; update it to describe the background task, the row lifecycle and the reaper.
- `readme.md` — phase 11 (the rewrite covers it).

---

## 5. Phase 9 — Auth and security posture

### 5.1 Why

Six real defects, all measured:

| # | Defect | Evidence |
|---|---|---|
| S1 | **The JWT secret is published in the source.** `backend/app/auth.py:11` falls back to the literal `"SUPER_SECRET_KEY_FOR_ASSIGNMENT"`. The token's only verified claim is `sub`, so anyone who reads the repo can mint a valid token for **any** username — full impersonation, no password. Measured: a token forged with the published key for a user `victim` was accepted (200). | `auth.py:11`, `main.py:59,109` |
| S2 | **CORS reflects any origin with credentials.** `allow_origins=["*"]` + `allow_credentials=True` is invalid per the Fetch standard; Starlette "fixes" it by echoing the request origin. Measured: `Origin: http://evil.example` → `access-control-allow-origin: http://evil.example` + `access-control-allow-credentials: true`. Combined with S3, any website can drive and read this API from a visitor's browser. | `main.py:33-39` |
| S3 | **The shared `anonymous` owner leaks runs across clients.** Every unauthenticated request resolves to the same `User(username="anonymous")` row, so the run listing (`main.py:301`) and the artifact download (`main.py:348`) expose every anonymous client's runs and artifacts. Measured: client B (no token) saw client A's run. | `main.py:43-82` |
| S4 | **Anyone can register the username `anonymous`** on a fresh database and thereby own the shared bucket. Measured: `POST /api/v1/register {"username":"anonymous"}` → 200. | `main.py:132-147` |
| S5 | **`dataset_name` accepts absolute paths** → the server can be made to read any local file and return aggregates. `resolve_dataset_path` uses an absolute path verbatim. | `model_training.py:982-984` |
| S6 | **No credential policy, no rate limiting, a 46× timing oracle on `/token`, and internals leaked in the 400 `detail`.** `POST /api/v1/register {"username":"","password":""}` → 200. An unknown user answers in ~6.7 ms, an existing user with a wrong password in ~312 ms (bcrypt is skipped for unknown users). The training 400 leaks the estimator class and the absolute server path. | `main.py:132-159`, `main.py:292-297` |

The `role` escalation hole was already closed in the previous round (registration ignores a
client-supplied role), and there is **no** SQL injection (every query is ORM-bound) and **no** path
traversal in the artifact route (the path is server-generated).

### 5.2 Decisions

- **S3/S4 — require a token everywhere.** The `anonymous` fallback is removed; every ML endpoint
  requires a valid token. The SPA is unaffected (it renders `MainApp` only when a token exists),
  but unauthenticated API clients (`curl`) stop working and the pinned test
  `test_requests_without_authorization_header_stay_available`
  (`backend/tests/test_auth_and_runs.py:94-102`) must be **inverted** into
  "requests without an authorization header are rejected".
- **S1 — the secret is never published.** `SECRET_KEY` from the environment wins; in production
  (`APP_ENV=production`) a missing `SECRET_KEY` is a hard error; in development a random key is
  generated once and persisted in `<repo>/.secret_key` (git-ignored) so restarts and multiple workers
  agree on it.
- **S2 — an explicit CORS allow-list.**
- **S5 — the dataset path is confined to a configurable root.**
- **S6 — a credential policy, a per-IP limiter, a constant-time login and curated error details.**

### 5.3 What changes

#### 5.3.1 `SECRET_KEY` resolution (`backend/app/auth.py`)

```python
from datetime import datetime, timedelta
from jose import jwt
import bcrypt
import os
import secrets
import warnings
from pathlib import Path

ALGORITHM = "HS256"

# The signing key of the JWTs. It must never be a value that is published in the
# source: the token's "sub" is the only claim that is verified, so anyone who
# knows the key can mint a valid token for any existing user (a full
# impersonation) and for an admin account as soon as one exists.
#
#   * SECRET_KEY from the environment always wins.
#   * APP_ENV=production (or ENVIRONMENT=production) without SECRET_KEY is a
#     hard error: the app must not start with a guessable key.
#   * In development a random key is generated once and persisted in
#     <repo>/.secret_key (git-ignored) so that restarts and multiple workers
#     agree on it. If the file cannot be written, the key is random per
#     process: every restart then invalidates the tokens issued before.
_SECRET_KEY_FILE = Path(__file__).resolve().parents[2] / ".secret_key"
_IS_PRODUCTION = os.getenv(
    "APP_ENV", os.getenv("ENVIRONMENT", "development")
).strip().lower() in {"production", "prod"}


def _load_secret_key() -> str:
    """Resolve the JWT signing key (env > production hard fail > dev file)."""
    key = os.getenv("SECRET_KEY")
    if key:
        return key
    if _IS_PRODUCTION:
        raise RuntimeError(
            "SECRET_KEY must be set when the app runs in production. Generate one with: "
            "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    try:
        if _SECRET_KEY_FILE.exists():
            stored = _SECRET_KEY_FILE.read_text(encoding="utf-8").strip()
            if stored:
                return stored
        key = secrets.token_urlsafe(48)
        _SECRET_KEY_FILE.write_text(key, encoding="utf-8")
        _SECRET_KEY_FILE.chmod(0o600)
        warnings.warn(
            f"SECRET_KEY is not set: a random development key was generated in "
            f"{_SECRET_KEY_FILE}. Set SECRET_KEY explicitly in any shared or "
            f"production environment.",
            RuntimeWarning,
            stacklevel=2,
        )
        return key
    except OSError:
        key = secrets.token_urlsafe(48)
        warnings.warn(
            "SECRET_KEY is not set and the development key file could not be written: "
            "a random per-process key is used, so every restart invalidates the "
            "existing tokens.",
            RuntimeWarning,
            stacklevel=2,
        )
        return key


SECRET_KEY = _load_secret_key()
```

Add `.secret_key` to the repository-root `.gitignore`.

**Rollout**: provision `SECRET_KEY` in `backend/.env` before deploying; expect **one** forced
re-login after the change (the key changes).

#### 5.3.2 CORS (`backend/app/main.py:33-39`)

```python
# --- CORS -------------------------------------------------------------------
# The browser SPA is served by Vite (frontend/vite.config.js -> port 3000) and
# calls this API cross-origin (3000 -> 8010). The allow-list is therefore
# explicit: `allow_origins=["*"]` together with `allow_credentials=True` is
# rejected by the Fetch standard (a wildcard is not allowed on a credentialed
# request) and, at runtime, makes the server reflect *any* origin with
# credentials enabled.
#
# CORS_ORIGINS is a comma-separated list of the allowed origins. When it is not
# set the development origins of the SPA are used. The special value "*" restores
# the old wildcard behaviour and is only valid together with
# allow_credentials=False.
DEFAULT_CORS_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")


def _cors_origins() -> List[str]:
    """The origins that are allowed to call the API from a browser.

    An empty or unset CORS_ORIGINS falls back to the development default, so a
    misconfigured environment never silently opens the API to every origin.
    """
    raw = os.getenv("CORS_ORIGINS", "")
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or list(DEFAULT_CORS_ORIGINS)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    # The SPA authenticates with a bearer token in localStorage and never sends
    # cookies, so credentials are not needed. A wildcard origin together with
    # credentials is invalid per the Fetch standard.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`import os` is needed. A request **without** an `Origin` header is unaffected (the middleware is a
no-op), so `curl` and the OpenAPI docs keep working.

**Rollout**: a developer whose SPA runs on another origin (a LAN IP, a tunnel) must set
`CORS_ORIGINS`; the failure is a visible browser CORS error.

#### 5.3.3 A token is required everywhere (`backend/app/main.py:43-82`)

Replace `get_active_user` with a strict dependency (the existing `get_current_user` at
`main.py:107` already does this) and use it on every ML route:

```python
async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    """Resolve the authenticated user.

    Every ML endpoint requires a valid token: there is no anonymous fallback,
    so two unauthenticated clients can never share an owner (and therefore a
    run history).
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Bearer"})
    except JOSEError:
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Bearer"})

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if user is None:
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Bearer"})
    return user
```

Then replace every `current_user: User = Depends(get_active_user)` with
`current_user: User = Depends(get_current_user)` and delete `get_active_user`. The `anonymous` user
is never created any more, so S4 disappears with it.

> **Note**: the `oauth2_scheme` is `OAuth2PasswordBearer(tokenUrl="token")`, which already returns
> **401** with a `WWW-Authenticate` header when the header is missing — so the "no header" case needs
> no extra work; the manual `authorization` header parsing (and its empty-header handling) goes away
> with `get_active_user`.

#### 5.3.4 The dataset path is confined (`backend/app/model_training.py:982-984`)

```python
def resolve_dataset_path(dataset_name: str) -> Path:
    """Resolve a dataset reference inside the configured dataset root.

    An absolute path is only accepted when it lies inside DATASET_ROOT (the
    ``data/`` directory by default), so a client cannot make the server read
    arbitrary files. ALLOW_ARBITRARY_DATASET_PATHS=1 restores the old
    behaviour for trusted environments.
    """
    root = Path(os.getenv("DATASET_ROOT") or DATA_DIR).resolve()
    candidate = Path(dataset_name)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if os.getenv("ALLOW_ARBITRARY_DATASET_PATHS") == "1":
        return resolved
    if resolved != root and root not in resolved.parents:
        raise ValueError(
            f"Dataset '{dataset_name}' is outside the dataset root '{root}'. "
            "Only files inside the dataset directory can be used."
        )
    return resolved
```

The test fixtures use absolute paths under a temp directory, so `backend/tests/conftest.py` must set
`DATASET_ROOT` to that directory (and the vision error message, which advertises absolute paths,
needs a look in phase 11).

**Rollout**: an existing deployment that points at datasets outside `data/` must set
`DATASET_ROOT` or `ALLOW_ARBITRARY_DATASET_PATHS=1`.

#### 5.3.5 Credential policy, rate limiting and a constant-time login

- `UserCreate` (`main.py:84-89`): add `Field(min_length=3, max_length=64)` to `username` and
  `Field(min_length=8, max_length=128)` to `password`.
- `POST /token`: always run a bcrypt comparison, even for an unknown user, so the response time no
  longer reveals whether the account exists:
  ```python
  DUMMY_HASH = hash_pass("not-a-real-password")   # module level, computed once

  async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
      logger.info(f"Login attempt for user: '{form_data.username}'")
      result = await db.execute(select(User).where(User.username == form_data.username))
      user = result.scalars().first()
      # Compare against a dummy hash for an unknown user so the response time
      # does not reveal whether the account exists.
      password_ok = verify_pass(form_data.password, user.hashed_password if user else DUMMY_HASH)
      if not user or not password_ok:
          logger.warning(f"Failed login: Incorrect credentials for '{form_data.username}'")
          raise HTTPException(status_code=400, detail="Incorrect username or password")
      ...
  ```
- A small **in-process** per-IP limiter (no new dependency) for `POST /token` and
  `POST /api/v1/register`: after N failures from one IP within a window, reject with 429 and a
  growing backoff. Per-**IP** (not per-username) — a per-username lockout is a denial-of-service
  vector.
- The training 400 must not leak internals: catch `ValueError`/`FileNotFoundError` explicitly and
  pass their message through (they are the curated, user-facing errors), and genericise everything
  else to `"Training failed, see the server log."` while the detail goes to the log.

### 5.4 Tests

- **Invert** `backend/tests/test_auth_and_runs.py::test_requests_without_authorization_header_stay_available`
  into `test_requests_without_an_authorization_header_are_rejected` (401 on `/api/v1/ml/models` and
  `/api/v1/ml/runs`).
- **New**: the `anonymous` user is never created; two different tokens see different runs (already
  covered by `test_run_history_exposes_the_mode_and_the_environment`).
- **New**: a forged token signed with the old published constant is rejected — **skipped if** the
  key is the development one; better: assert that `SECRET_KEY` is not the published literal when
  `APP_ENV=production` (the app must refuse to start).
- **New**: the CORS middleware echoes an allowed origin, does **not** echo a foreign one, and does
  not add `Access-Control-Allow-Credentials`.
- **New**: `resolve_dataset_path` rejects a path outside `DATASET_ROOT` and accepts one inside.
- **New**: registration rejects an empty/short username or password.

### 5.5 Acceptance criteria

- Every `/api/v1/ml/*` route answers **401** without a valid token.
- The app **refuses to start** with `APP_ENV=production` and no `SECRET_KEY`.
- A foreign `Origin` receives no `Access-Control-Allow-Origin`.
- `resolve_dataset_path` refuses a path outside the dataset root.
- The suite passes.

### 5.6 Risks

| Risk | Mitigation |
|---|---|
| Unauthenticated API clients break | this is the accepted decision; the change is announced in `readme.md` |
| One forced re-login after the secret change | expected and documented |
| A developer on another origin gets a CORS error | `CORS_ORIGINS` is documented in `readme.md` and `backend/.env` |
| The dataset confinement breaks the test fixtures / the vision workflow | `DATASET_ROOT` is configurable; the fixtures set it |
| The per-IP limiter penalises a shared NAT | the backoff is gradual and the window is short |

### 5.7 Rejected alternatives

- **Per-client anonymous owner** (`anon-<hash of IP+UA>`) — keeps the API usable without a login
  without cross-client leakage. Rejected in favour of "require a token everywhere".
- **Keep the wildcard CORS but set `allow_credentials=False`** — spec-valid, but it still lets any
  website call and read the API.
- **A random per-process secret in development** (no file) — every restart invalidates all sessions.

---

## 6. Phase 10 — Honest model metadata, placeholders that fail fast, a real autoencoder

### 6.1 Why

13 of the 38 catalog entries advertise metrics their trainer cannot produce, and 20 entries have
catalog parameters that are silently ignored. The full audit (measured, not read):

| Entry | What actually happens | What the catalog advertises |
|---|---|---|
| `LSTM`, `RNN`, `SSM_timeseries`, `TCN_timeseries` (category `timeseries`) | a plain 2-layer MLP (`Linear→ReLU→Linear`) trained with MSE on the label; `batch_size` is never used (full-batch steps), `X_test`/`y_test` are computed and never used, `hidden_size` is the MLP width; the reported metric is only `final_loss`; **and the run then crashes** — the network is a function-local class, so `joblib.dump` raises `PicklingError: Can't pickle ...SimpleNet` → the API answers 400 and the run is stored `failed` | `expected_accuracy: (0.70, 0.90)`, `typical_training_time_sec: 18`, "LSTM for sequential prediction." |
| `GNN` (category `graph`) | the same MLP — no graph, no edges, no message passing | `expected_accuracy: (0.75, 0.92)`, "Graph neural network training." |
| `Autoencoder` | the same MLP on the label; `latent_dim` is never read | `expected_reconstruction_mse: (0.01, 0.1)`, "Autoencoder training for representation learning." |
| `ViT` (category `vision`) | **a ResNet-18** — `architecture = resnet50 if model_name == "ResNet50" else resnet18`; `google/vit-base-patch16-224` is never fetched | "Vision Transformer for image classification.", `expected_accuracy: (0.86, 0.96)` |
| `seq2seq`, `UL2`, `BERT2BERT`, `GPT`, `LLaMA` (nlp) | all become **sequence classifiers** via `AutoModelForSequenceClassification`; `GPT` (`distilgpt2`) fails with `ValueError: Cannot handle batch sizes > 1 if no padding token is defined.`; `LLaMA` is a gated repo → 401; `UL2` downloads a ~2.3 B T5; the trainer reports `train_loss` only — **no accuracy** | `expected_accuracy`, "Sequence-to-sequence training for text generation.", "UL2-based language fine-tuning." |
| `Q-Learning` | a stub: `return {"status": "Q-Learning is supported as a discrete prototype only."}` — that dict is written as the "model artifact" | `expected_reward: (30, 200)`, "Classic Q-learning for discrete environments." |
| `K-Mean`, `GMM`, `Hierarchical_Clustering`, `DBSCAN` | real, but the trainer reports `cluster_count`/`sample_count` — **no silhouette**, although the labels are already in hand | `expected_silhouette` |
| `PCA`, `t-SNE`, `UMAP` | projections, not clustering; `UMAP` needs a dependency that is not in `requirements.txt` | `expected_explained_variance` / `expected_quality` — neither is computed |
| `HDBSCAN` | needs `hdbscan`, which is not in `requirements.txt` | `expected_quality` |
| `PPO`, `DQN` | real SB3 agents, but `gamma` (and `ent_coef` for PPO) are never passed | `optimization` lists only the keys that are read, but the ignored ones are in `params` |
| `ResNet`, `ResNet50` | real, but `trainable_layers` is ignored and the reported `accuracy` is the **training** accuracy (no held-out split) | — |

The frontend renders the advertised numbers as fact (`frontend/App.jsx:349-411` shows
"Est. Performance 70-90%", "Training Time ~18s"), and the "Model Intelligence" panel **silently
disappears** when an entry has no `test_results` — so the UI cannot distinguish "not implemented"
from "no data yet". `score_candidate` also returns `0.0` for every clustering candidate, so
`auto_search` always keeps the first one in that category.

### 6.2 Decision

**Honest metadata + fail fast**, plus the two contained real fixes that are possible with the data
contract that already exists: a **real autoencoder** and a **silhouette metric**.

The real LSTM/GNN/ViT/seq2seq trainers need **new data contracts** (a time axis, an edge list, an
image pipeline) — design decisions that belong to their own round and would make this change
unreviewable. The repository's own contract already demands the honesty fix: *"a silently ignored
parameter is worse than a loud failure"* (`model_training.py:126-128`).

### 6.3 What changes

#### 6.3.1 The catalog (`backend/app/model_training.py`)

Add `"implemented": False` to the entries with no honest implementation — `LSTM`, `RNN`,
`SSM_timeseries`, `TCN_timeseries`, `GNN`, `Q-Learning`, `ViT`, `seq2seq`, `UL2`, `BERT2BERT`, `GPT`,
`LLaMA` — and **move their `test_results` to `planned_test_results`** so the numbers stay available
for reference but are never presented as measured:

```python
"LSTM": {
    "category": "timeseries",
    "implemented": False,
    "description": "Placeholder - no sequence model (LSTM/RNN/SSM/TCN) is implemented in this repository; training it is rejected.",
    "params": {"epochs": 5, "batch_size": 32, "learning_rate": 1e-3, "hidden_size": 64, "dropout": 0.0},
    "optimization": [],
    "planned_test_results": {
        "expected_accuracy": (0.70, 0.90),
        "best_for": ["time_series", "sequence_modeling", "long_dependencies"],
        "typical_training_time_sec": 18,
        "scalability": "medium",
    },
},
```

`BERT`, `DistilBERT`, `self-attenetion_transformer` and `MiniLM` stay `implemented: True` (they
really are sequence classifiers) but their unreachable `expected_accuracy` must be removed from
`test_results` — or the trainer must be extended with a held-out split and an accuracy metric
(recommended: ~20 lines, and it makes the advertised number true).

`ResNet`/`ResNet50` stay implemented; their `trainable_layers` parameter must be removed from
`params` (it is ignored) or implemented.

`PPO`/`DQN`: remove `gamma`/`ent_coef` from `params` (they are ignored) or pass them to the agent.

#### 6.3.2 Fail fast (`train_model`)

Right after `model_def = get_model_entry(model_name)` — **before** the dataset is loaded and before
every branch:

```python
    if not model_def.get("implemented", True):
        raise ValueError(
            f"'{model_name}' is a placeholder in this repository: "
            f"{model_def.get('description', '')} No model is trained and no metrics are produced."
        )
```

The endpoint turns that into the usual 400 and the run row into `status="failed"` with
`metrics={"error": ...}`.

#### 6.3.3 The API surface (`list_available_models`, `model_training.py:837`)

Add `"implemented": info.get("implemented", True)` to **both** returned dicts (the repository-scan
branch and the catalog-fallback branch). `get_model_entry` needs no change (it deep-copies the
entry).

#### 6.3.4 A silhouette metric (`_train_clustering`, `model_training.py:1105`)

```python
    metrics = {"cluster_count": int(pd.Series(labels).nunique()), "sample_count": int(len(labels))}
    try:
        from sklearn.metrics import silhouette_score
        unique = set(labels)
        if 1 < len(unique) < len(X):
            metrics["silhouette"] = float(silhouette_score(X, labels))
    except Exception:
        pass
```

DBSCAN's `-1` noise label should be excluded from the silhouette and reported separately as
`noise_count`. Add `"silhouette"` to `_CANDIDATE_SCORE_KEYS` (`model_training.py:939`) so
`auto_search` can rank clustering candidates. This makes the four `expected_silhouette` blocks true
and closes the `score_candidate` gap.

#### 6.3.5 A real autoencoder

A new `_train_autoencoder(model_name, dataset, label_column, hyperparameters)`:

- encoder `Linear(in, latent_dim) → ReLU`, decoder `Linear(latent_dim, in)`;
- the loss is the **reconstruction** MSE over the features (the label column is optional for this
  path);
- metrics: `{"reconstruction_mse": ..., "latent_dim": ..., "sample_count": ...}`;
- the model is a **module-level** class (not a function-local one) so that `joblib.dump` can pickle
  it — the `PicklingError` that breaks every current `timeseries`/`graph`/`autoencoder` run comes
  from the local class in `_train_torch_regression_or_classification` and must not be repeated.

Route it in `train_model()` before the generic `{"timeseries", "graph", "autoencoder"}` block, so
`Autoencoder` keeps `implemented: True` and its `expected_reconstruction_mse` becomes true.

> **Also fix the pickling bug** in `_train_torch_regression_or_classification`: move `SimpleNet` to
> module level, otherwise any entry that still routes there (none, after this phase — but the code
> stays) cannot be saved.

#### 6.3.6 The frontend (`frontend/App.jsx`)

- `ModelsCatalog` card (`:349`): a "Not implemented" badge when `model.implemented === false`, and
  the `test_results` block hidden (it is empty for those entries now).
- `formatTestResults()` (`:931`): three cases — measured data, **not implemented** (amber panel
  with the reason), and **no benchmark data yet** (neutral panel). Today the panel simply vanishes
  when `test_results` is missing, which is the ambiguity this phase removes.
- The model picker (`:1084`): `{m.name} ({m.category})` → add " — not implemented" for a
  placeholder, and disable the submit button for a selected placeholder with the reason shown.
- `FALLBACK_MODELS` (`:83`) already contains only the 8 genuinely implemented tabular models.

### 6.4 Tests

**New tests (the honesty contract)** in `backend/tests/test_catalog_params.py`:

1. `test_placeholder_models_are_refused_with_an_explicit_message` — for every entry with
   `implemented is False`: `train_model` raises a `ValueError` naming the model, **no trainer is
   dispatched** and **no artifact is written**.
2. `test_no_catalog_entry_advertises_a_metric_its_trainer_cannot_produce` — build a map from the
   advertised key to the metric the trainer reports
   (`expected_accuracy→accuracy`, `expected_r2→r2`, `expected_reward→mean_reward`,
   `expected_silhouette→silhouette`, `expected_reconstruction_mse→reconstruction_mse`) and assert
   that every key of an implemented entry's `test_results` maps to a metric its trainer reports.
   **This test fails today for ~13 entries** — it is the test that pins the fix.
3. `test_placeholder_entries_carry_no_test_results` — an `implemented: False` entry must not expose
   a `test_results` block.
4. `test_every_catalog_parameter_is_read_by_its_trainer` — every key of an implemented entry's
   `params` must be consumed by its trainer (kills `trainable_layers`, `latent_dim`,
   `num_channels`, `warmup_steps`, `dropout*`, the RL `gamma`/`ent_coef`).
5. `test_clustering_reports_a_silhouette` and `test_score_candidate_ranks_two_clustering_candidates`.
6. `test_vision_entry_does_not_train_a_resnet` — the vision trainer must build the architecture the
   catalog names (fails for `ViT` today).

**Existing tests to adjust**: `test_catalog_model_is_routed_to_the_expected_trainer` asserts that
each model reaches a trainer — a placeholder now raises before any trainer is called, so the test
must branch on `implemented` and assert the placeholder error instead. The `nlp` skip must move
**after** the placeholder check, so a placeholder nlp entry still asserts something.

### 6.5 Acceptance criteria

- Every placeholder entry is refused with a clear message, from the API and from the UI.
- No implemented entry advertises a metric its trainer cannot produce (proved by the new test).
- The autoencoder trains, reports `reconstruction_mse` and can be downloaded.
- The clustering trainer reports a silhouette and `auto_search` can rank clustering candidates.
- The suite passes.

### 6.6 Risks

| Risk | Mitigation |
|---|---|
| Users lose models they could "train" (they trained a substitute) | the substitute was not the advertised model; the failure is now honest |
| `test_results` disappears for 13 entries → the catalog looks emptier | the planned values move to `planned_test_results` and the UI shows a badge instead of numbers |
| The `implemented` flag becomes stale | the new test #2 fails whenever a trainer stops reporting an advertised metric |

### 6.7 Rejected alternatives

- **Implementing the real models now** — needs new data contracts (a time axis, an edge list, an
  image pipeline) and per-model design decisions; a much larger change.
- **Honest metadata only** (no autoencoder, no silhouette) — leaves two advertised numbers
  permanently false.

---

## 7. Phase 11 — Documentation

Executed **last**, so the documents describe the final state. The `readme.md` inventory below was
produced by comparing every line against the code.

### 7.1 `readme.md` (root) — full rewrite

**Wrong or stale lines and their corrections**:

| Line | Current | Correction |
|---|---|---|
| 1 | `ALL-of-ML-&-DL` | `ALL-of-ML---DL` |
| 7-10 | the structure lists `requirements.txt` at the root | the structure must be: `backend/` (with `app/`, `migrations/`, `tests/`, `requirements.txt`, `alembic.ini`, `commands.txt`, `dockerfile`, `docker-compose.yml`), `frontend/`, `data/`, `models/` (git-ignored), `readme.md`, `AGENTS.md`, `TODO.MD` |
| 15 | "32+ model catalog entries" | "38 model catalog entries" |
| 25 | "Python 3.9+" | **Python 3.12+** (`pandas 3.0.6` needs ≥3.11, `numpy 2.5.4` needs ≥3.12) |
| 26 | "Node.js 16+" | **Node.js 18+** (`vite ^5.4.1` requires `^18 \|\| >=20`) |
| 29-34 | `git clone "<your-repo-url>"` / `cd "ALL-of-ML-&-DL"` | the real repository URL and folder name |
| 40-45 | the venv steps | correct; add that the venv lives at the repository root |
| 47-58 | the frontend steps | correct; the dev server is **http://localhost:3000**; drop the yarn branch (the repo ships `package-lock.json`) |
| 60-65 | the uvicorn command | correct |
| 67, 71 | "port 5173" (twice) | **port 3000**; and "Adjust CORS settings" → "set `CORS_ORIGINS`" |
| 73-74 | the data source | mention that `data/` also holds the image folders for the vision models |
| 84 | "The backend will schedule and run training and return metrics … when complete" | training is asynchronous: the endpoint returns a `run_id` immediately and the SPA polls the run (phase 8) |
| 89-102 | the Gemini section | correct; state explicitly that `google-generativeai` is **not** in `backend/requirements.txt` |
| 104-146 | the Docker section | the compose file is `backend/docker-compose.yml` and runs **postgres + the backend only** — there is **no frontend service**; the image is `backend/dockerfile` (lowercase); the compose `command:` runs the migrations (phase 7); the required `backend/.env` keys are `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT`, `POSTGRES_HOST_PORT`, `DATABASE_URL` (pointing at the `db` service), plus `SECRET_KEY`, `CORS_ORIGINS` and the optional `GOOGLE_API_KEY` |
| 150 | "ensure CORS is enabled" | "add your origin to `CORS_ORIGINS`" |
| 152 | the Windows file-mounting note | obsolete — the compose stack is backend-only |
| 156 | "add new model definitions under `DL_models/` or `ML_models/`" | those directories were deleted in `d4b397c`; new models go into `MODEL_CATALOG` in `backend/app/model_training.py` (+ an optional `ALIASES` entry + a `build_model()` branch or a category trainer) |
| 159-161 | "Add frontend card metadata if you want special UI behavior" | the frontend renders the catalog generically; there is no per-model card file |
| 167-168 | "If you'd like, I can also commit a `docker-compose.yml` … want me to add those now?" | **delete** (agent-directed text; the files already exist) |
| 170-206 | the model list (33 entries) | the exact 38 catalog keys, in catalog order, and move the section above the license |

**The corrected model list** (38 keys, in `MODEL_CATALOG` order):

```
K-Mean, HMM_timeseries, GMM, Hierarchical_Clustering, PCA, t-SNE, UMAP, DBSCAN, HDBSCAN,
Random_Forest, Logistic_Regression, MLR, KNN, SVM, XGboost_timeseries, lightGBM_timeseries,
CATboost_timeseries, PPO, DQN, Q-Learning, Autoencoder, BERT2BERT, self-attenetion_transformer,
seq2seq, UL2, GNN, BERT, DistilBERT, GPT, LLaMA, LSTM, MiniLM, ResNet, ResNet50, RNN,
SSM_timeseries, TCN_timeseries, ViT
```

The list must also state which entries are **not implemented** (phase 10) — e.g. a "not
implemented" marker per entry — so the documentation matches the API.

**The quickstart** must also contain, in order: create the venv → `pip install -r
backend/requirements.txt` → `cd backend && alembic upgrade head` → `uvicorn app.main:app --port
8010 --reload` → `cd frontend && npm install && npm run dev` → open **http://localhost:3000**. And it
must state that the API now **requires a token** (phase 9) and that the SPA is served locally.

### 7.2 `backend/app/README.md`

- **Delete** line 246 ("If you want, I can also add a template `backend/tests/test_new_model.py` …")
  and rewrite line 251 in a neutral voice.
- Add the missing secrets to "Operational notes" (`:232`): `SECRET_KEY` (required in production),
  `CORS_ORIGINS`, `DATASET_ROOT`, `GOOGLE_API_KEY`.
- The technical content was verified as **accurate** (every claim about the routing, the parameter
  ownership, the preset, `score_candidate` and `list_local_datasets` matches the code) — it only
  needs the phase-8 update (the async contract) and the phase-7 note (Alembic owns the schema).

### 7.3 `TODO.MD`

The single line ("add auto fintuning features with and without using llm") is **partially** satisfied:
both modes exist, but `auto_tune`/`auto_fine_tune` only re-apply the catalog values (there is no
grid/random search anywhere) and `llm_fine_tune` needs `google-generativeai` (not in
`requirements.txt`) plus `GOOGLE_API_KEY`, and it can only propose values for keys the catalog
already declares. Replace it with:

```markdown
- [x] auto fine-tuning modes exist (`auto_tune`, `auto_fine_tune`, `llm_fine_tune`) — but they only re-apply the catalog values
- [ ] implement a real hyperparameter search for `auto_tune` (grid / random search over the catalog's `optimization` keys)
- [ ] make `auto_fine_tune` a genuine fine-tuning strategy (per-category: smaller learning rate, fewer epochs, early stopping)
- [ ] `llm_fine_tune`: add `google-generativeai` to `backend/requirements.txt`, document `GOOGLE_API_KEY`/`GOOGLE_MODEL`, and let the LLM propose values for keys the catalog does not declare
- [ ] implement the placeholder models (LSTM/RNN/SSM/TCN/GNN/ViT/seq2seq/UL2/GPT/LLaMA/Q-Learning) or remove them from the catalog
```

### 7.4 `AGENTS.md`

Update in the same phases (each phase updates the lines it invalidates):

- Phase 7: the schema is owned by Alembic; the app refuses to start on an unmigrated database;
  `alembic` must be installed for the test suite.
- Phase 8: the training endpoint is asynchronous; the run row is the error channel; the frontend
  polls.
- Phase 9: the API requires a token; `SECRET_KEY`/`CORS_ORIGINS`/`DATASET_ROOT` are environment
  variables; the CORS allow-list is no longer `*`.
- Phase 10: the placeholder entries and the `implemented` flag; the silhouette metric; the
  autoencoder.

---

## 8. Cross-cutting invariants

Every phase must preserve these. They are the contract the current code already keeps and that the
tests pin:

1. The run row exists and is committed before the response; the client polls `GET /runs/{id}`.
2. A failed training ends with the row in `status="failed"` and the error in `metrics["error"]`.
3. A successful training ends with `status="completed"`, the metrics, the artifact path and the
   `dataset_source`/`dataset_tag` returned by `train_model`.
4. The training never blocks the event loop (`run_in_threadpool`) and never shares the
   request-scoped session.
5. A background task never raises.
6. The artifact lands in `MODEL_DIR` and `GET /runs/{id}/artifact` keeps working.
7. An unknown/typo'd hyperparameter still raises `TypeError`; the trainer-owned `test_size` is still
   ignored in favour of the request's top-level `test_size`.
8. The preset is applied once, to the merged base; the client's values still win.
9. `score_candidate` ranks by a metric the run actually reports.
10. The public API of `backend/app/model_training.py` keeps its names and signatures; `MODEL_CATALOG`
    keeps exactly 38 entries.
11. Every ML endpoint requires a valid token and answers 401 otherwise.
12. The database schema is created by the migrations, never by the application.

## 9. Consolidated risk register

| # | Risk | Phase | Severity | Mitigation |
|---|---|---|---|---|
| R1 | `notes` rows are destroyed on upgrade | 7 | data loss | accepted; recommend a `pg_dump -t notes` first; the downgrade recreates an empty table |
| R2 | The test suite now needs `alembic` | 7 | medium | it is in `requirements.txt`; documented |
| R3 | `create_all` removal breaks compose / the quickstart | 7 | high | the compose `command:` and the readme change in the same phase |
| R4 | The startup reaper kills a live run under `--workers N` | 8 | medium | documented; single-worker deployment; a heartbeat is a follow-up |
| R5 | A background task that raises leaks into the response | 8 | medium | the task catches everything; a test pins it |
| R6 | Unauthenticated API clients break | 9 | breaking | accepted decision; announced in the readme |
| R7 | One forced re-login after the secret change | 9 | low | documented; the tests import the module constant and are unaffected |
| R8 | A developer on another origin hits a CORS error | 9 | low | `CORS_ORIGINS` is documented |
| R9 | The dataset confinement breaks the fixtures / the vision workflow | 9 | medium | `DATASET_ROOT` is configurable; the fixtures set it |
| R10 | Users lose 13 catalog entries | 10 | breaking | they trained a substitute, not the advertised model; the UI marks them |
| R11 | A phase regresses an earlier phase | all | high | the phases are sequential and each ends with the full suite + an independent review |

## 10. Verification (per phase and at the end)

```bash
# backend suite (from the repo root)
python -m pytest backend/tests -p no:cacheprovider        # expect 102 passed, 9 skipped + new tests

# single test
python -m pytest backend/tests/test_catalog_params.py::test_placeholder_models_are_refused_with_an_explicit_message

# frontend build
cd frontend && npm install && npm run build

# migrations (from backend/, with DATABASE_URL set)
cd backend && alembic upgrade head && alembic check
```

At the end of the round, a **final independent review** of the complete diff against this document,
followed by a focused commit per phase.

## 11. Still out of scope after this round

- A real grid/random search for `auto_tune` (the `TODO.MD` item).
- The real LSTM / GNN / ViT / seq2seq / UL2 / GPT / LLaMA / Q-Learning implementations (they need
  new data contracts).
- A production-grade job queue (Celery/RQ) — the background task is the seam where it would go.
- The `notes` data for anyone who still has the old database (irrecoverable once dropped).
- `updated_at` maintained by a database trigger.
- `postgresql.JSONB` for the JSON columns (would require changing the ORM and breaks SQLite).
