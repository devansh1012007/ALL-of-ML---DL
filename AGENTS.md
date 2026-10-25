# AGENTS.md

Two independent apps in one repo: `backend/` (FastAPI + async SQLAlchemy + Alembic) and `frontend/` (Vite + React 18 + Tailwind). No root manifest, no CI, no lint/format/typecheck config, no pre-commit hooks. Nothing to run "the linter" — validation is `pytest` plus a manual dev-server check.

## Mandatory Engineering Workflow

This workflow is binding for all work in this repo.

### 1. Understand Before Changing (ALWAYS)

- Before making any code change, spawn subagent(s) to investigate the relevant code and its surrounding system. This step is mandatory, regardless of change size.
- Read relevant documentation, `AGENTS.md` files, ADRs, and existing tests.
- Trace execution flows, dependencies, interfaces, invariants, and downstream effects.
- Identify the root cause, not just the visible symptom.
- Return a concise context report identifying affected files, risks, expected behavior, and required tests.
- Do not modify code until sufficient context has been gathered. Never invent APIs, assume behavior, or guess at undocumented contracts.

### 2. Implement in Atomic Phases

- Break work into small, independently verifiable phases. Make minimal, focused changes that preserve existing contracts unless a change is explicitly required.
- Follow established conventions, keep abstractions justified, handle errors explicitly, validate inputs, and avoid duplication, dead code, unnecessary dependencies, and unrelated refactoring. Update documentation when behavior or interfaces change.
- Use tests and actual source evidence to resolve uncertainty. Never fabricate implementation details, claim unverified behavior works, or weaken tests merely to achieve a passing suite.

### 3. Mandatory Independent Review (EVERY PHASE)

- After each atomic phase, spawn a separate reviewer subagent to audit the changes before declaring the phase complete.
- The reviewer must independently inspect the diff, surrounding code, original requirements, and tests. Check for:
  - Bugs, regressions, flawed assumptions, and integration issues.
  - Security, error handling, edge cases, and violated invariants.
  - Maintainability, unnecessary complexity, and inconsistent conventions.
  - Tests that are missing, incorrect, superficial, or pass without testing the intended behavior.
  - Whether tests would detect the actual bug or failure they claim to prevent.
- Run relevant tests and verify their results. The reviewer must report concrete findings with evidence and severity. Fix valid findings and repeat review and testing until critical issues are resolved or explicitly documented as blockers. Never approve changes merely because tests pass.

### 4. Mandatory Final Review (BEFORE COMPLETION OR COMMIT)

- After all phases are implemented, spawn a fresh reviewer subagent for a full-task review. Re-evaluate the complete diff against the original requirements and system architecture, including cross-phase interactions, regressions, test coverage, and whether the tests genuinely prove correctness.
- Run the appropriate test suite, inspect the final diff, and report verified results separately from unverified assumptions. Do not declare the task complete, commit, or open a PR until this review passes. If issues are found, fix them and repeat the review.

### 5. Git Discipline

- Commits and PRs are permitted. Create focused commits and a PR when appropriate, but only after the mandatory reviews pass. Never commit known unresolved critical issues, claim tests passed without executing them, or bypass review gates to save time.

**Non-negotiable rule:** Context-gathering subagents must run before every change; an independent review subagent must run after every atomic phase and once again at the end. If subagents or required verification are unavailable, stop and report the blocker instead of pretending the workflow was completed.

Repo-specific anchors for this workflow: backend tests are `.venv/bin/python -m pytest backend/tests` from the **repo root** (see Commands); there is no linter, so "run the linter" means run pytest plus a manual dev-server check; the "existing tests" to read are `backend/tests/conftest.py`, `backend/tests/test_main.py`, `backend/tests/test_model_training.py`, `backend/tests/test_catalog_params.py` (the catalog/param/routing contract), `backend/tests/test_auth_and_runs.py` (the auth contract) and `backend/tests/test_datasets.py` (the dataset registry contract).

## Layout / entrypoints

- `backend/app/main.py` — FastAPI app (`uvicorn app.main:app`), all HTTP routes, request models.
- `backend/app/model_training.py` (~1.7k lines) — the ML core: `MODEL_CATALOG`, `ALIASES`, `TRAINING_MODES`, `TRAINING_PRESETS`, `train_model()`, `build_model()`, per-category trainers.
- `backend/app/models.py` — ORM (`users`, `datasets`, `training_runs`); `backend/app/database.py` — engine/session; `backend/app/auth.py` — bcrypt + JWT.
- `backend/app/datasets.py` — the dataset registry: `resolve_storage_path()`, `relative_storage_path()`, `validate_upload()`, `write_upload()`, `describe_csv()`, `suggest_label()`, `size_of()`, `unique_dataset_name()`, `builtin_files()`, `builtin_folders()`, `dataset_to_dict()`, and the upload limits. An upload is validated and written in two steps (`validate_upload()` then `write_upload()`), so the description of the file is computed once and reused for the row of the registry. `backend/app/settings.py` — `DATABASE_URL`, `datasets_root()`, `builtin_datasets_dir()`, `uploads_dir()`.
- `backend/migrations/` — Alembic; `backend/tests/` — pytest.
- `frontend/App.jsx` (~1.4k lines) — the whole SPA. `frontend/main.jsx` is the entry; **there is no `src/` dir** — `index.html`, `main.jsx`, `App.jsx`, `styles.css` all sit at the `frontend/` root.
- `data/` — the CSV files that ship with the repository. They are registered as rows of the `datasets` table at the startup (`seed_builtin_datasets()` in `backend/app/main.py`), so a fresh clone already has two datasets (`sample_customer_churn.csv`, `sample_house_prices.csv`). A directory of `data/` that holds one subdirectory per class is registered as a `folder` row for the vision models; a directory without such subdirectories is not registered.
- `scripts/install.sh`, `scripts/download.sh` — the installer of the repository.
- A dataset is a **row of the `datasets` table**, not a path: the client sends `dataset_id` (or a `dataset_name`, which is a lookup in the same registry), and the server resolves the row to a path **relative** to the datasets root (`DATASETS_ROOT`, the repository root by default). `resolve_storage_path()` (`backend/app/datasets.py`) refuses an absolute path, a `..` and a symlink that points out of the root. The root holds `data/` (the built-in datasets) and `uploads/` (the files the users upload, under `uploads/<user id>/` with a generated name). The name of a dataset is unique per owner, and the built-in ones (no owner) have a unique name of their own.
- An upload is a **comma separated CSV file**: `validate_upload()` refuses a file with another separator, a file with less than two columns and a file without rows. The name of the client is only the display name — the file is stored as `<32 hex characters>_<name of the client>` under `uploads/<user id>/` — and `POST /api/v1/ml/datasets/upload` reads the body itself, after the token was checked, so an unauthenticated request is refused before its file is written to the disk.

## Commands

Backend (from repo root, venv at repo root):
- install: `scripts/install.sh` — it creates the virtual environment `.venv` (python 3.12) at the repository root and installs the backend and the frontend dependencies. It needs `uv` (https://docs.astral.sh/uv/getting-started/installation/) for the python side and `npm` for the frontend. The flags are `--backend` (the python dependencies only), `--frontend` (the node dependencies only), `--optional` (`google-generativeai`, `umap-learn`, `hdbscan`), `--dev` (`pytest`, `pytest-asyncio`, `httpx`, `ruff`) and `--cpu` (the small build of torch; it only has an effect together with `--backend`). Without a flag it installs the backend and the frontend. A download that fails is retried, and the cache of the installer lives in `.cache/` of the repository, so an interrupted installation resumes instead of starting over.
- run: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload` (port 8010 is what the frontend hardcodes; logs go to `app.log`, relative to the CWD, and to stdout)
- **migrate first**: `cd backend && ../.venv/bin/python -m alembic upgrade head` (the `alembic` executable is not on the PATH: the virtual environment is at the root of the repository) — the app **verifies** the schema at startup and refuses to start when it is behind. The app never creates tables any more.
- tests: `.venv/bin/python -m pytest backend/tests` — **run from the repo root**: test modules import `backend.app.*` and neither `backend/` nor `backend/app/` has `__init__.py`, so the repo root must be on `sys.path`. `backend/tests/conftest.py` puts it there (and pins an isolated sqlite `DATABASE_URL`, a temporary `DATASETS_ROOT` and a temporary `MODEL_DIR`), so bare `pytest backend/tests` works from the repo root too. The suite builds its schema with the migrations and runs `alembic check`, so a drift between the migrations and the ORM fails the suite.
- single test: `.venv/bin/python -m pytest backend/tests/test_model_training.py::test_train_model_auto_fine_tune_tabular`
- migrations: `cd backend && ../.venv/bin/python -m alembic upgrade head` (needs `DATABASE_URL`); the drift check: `cd backend && ../.venv/bin/python -m alembic check`; new revision: `cd backend && ../.venv/bin/python -m alembic revision --autogenerate -m "..."` (see `backend/commands.txt`, which uses `docker-compose run --rm web ...`)

Frontend:
- install: `scripts/install.sh --frontend` — it runs `npm install` in `frontend/` with the cache of the repository.
- `cd frontend && npm run dev` → **http://localhost:3000** (`frontend/vite.config.js` sets `server.port: 3000`; the root `readme.md` says 5173 — it is wrong).
- `npm run build` → `frontend/dist/`

Scripts:
- `scripts/download.sh <url> [target]` — downloads a file and continues where it stopped (`curl --continue-at -`), retrying a transfer that breaks.

Docker:
- The compose file is `backend/docker-compose.yml`, **not** the repo root. `cd backend && docker-compose up --build`.
- Needs `backend/.env` (gitignored; `backend/.env.example` documents every variable) with `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST_PORT`, `POSTGRES_PORT`, `DATABASE_URL` (in compose, `DATABASE_URL` must point at the `db` service, not localhost).
- The `web` service's `command:` runs `alembic upgrade head` before the server, and the `db` service has a healthcheck, so the migrations do not race the start of Postgres.

## Environment gotchas

- `DATABASE_URL` must be set before the app is importable. The default in `backend/app/settings.py` is `sqlite+aiosqlite:///./backend.db`; `aiosqlite` **is** in `requirements.txt` now, so the sqlite fallback works out of the box (it creates `./backend.db` in the CWD). Use `postgresql+asyncpg://user:pass@host:5432/db` for anything real.
- `DATASETS_ROOT` is the directory every dataset is read from; the default is the repository root (`backend/app/settings.py`). `data/` (the datasets that ship with the repository) and `uploads/` (the files the users upload) are resolved against it, and the path of a dataset is relative to it. It is read on **every call** (`datasets_root()`), so a change does not need a restart. An empty value is not the default: the root becomes the current directory of the process.
- The upload limits are read **at import time**, so a change needs a restart: `MAX_UPLOAD_BYTES` (50 MiB), `MAX_UPLOAD_ROWS` (2000000), `MAX_UPLOAD_COLUMNS` (1000), `MAX_REPORTED_COLUMNS` (200) and `MAX_FILE_NAME_BYTES` (200) in `backend/app/datasets.py`, and `UPLOAD_RATE_LIMIT` (20 uploads per minute and per client address) in `backend/app/main.py`. The body of an upload is refused with a **413** before the framework parses it: a request that announces its length is refused without reading a byte of it, and a request without a length is read with the limit in force, so an oversized file never reaches the disk of the server. The `UploadSizeLimit` middleware re-reads `MAX_UPLOAD_BYTES` on every request; the other limits are import-time.
- `python-dotenv` is in `requirements.txt` but nothing calls `load_dotenv` — export env vars yourself (or rely on compose `env_file`).
- Still missing from `requirements.txt`: `google-generativeai` (`llm_fine_tune` mode), `umap` / `hdbscan` (catalog models `UMAP`/`HDBSCAN` raise "not installed" at train time), `gymnasium` / `stable-baselines3` / `torch` are declared but huge. `scripts/install.sh --optional` installs the first three. Optional imports in `model_training.py` are guarded, so the module still imports.
- `scikit-learn` is pinned to `<1.10` because the catalog uses `LogisticRegression(penalty="l2")` (removed in 1.10) and `SVC(probability=True)` (removed in 1.11). Relax the pin only after removing those params.
- `openai` is in `requirements.txt` but unused by the code; `llm_fine_tune` uses **Google Gemini** (`GOOGLE_API_KEY`, optional `GOOGLE_MODEL`) — the backend's mode description says so too.
- The URL of the database comes from `DATABASE_URL` (or the app's default); `alembic.ini` has no URL of its own, and `migrations/env.py` escapes the `%` of a password.
- `POST /api/v1/ml/train` **enqueues**: it creates a `TrainingRun` row with status `queued` and a stored `request_payload` (everything a worker needs), returns the `run_id` immediately and starts `drain_training_queue` as a background task. The rows are the queue: `_claim_next_run` claims the oldest queued run with one atomic `UPDATE ... WHERE status = 'queued'`, `_run_claimed` trains it in a thread while `_heartbeat` writes `heartbeat_at`, and `_finish_run` writes the result **conditionally** (`WHERE status = 'running'`) so a run cancelled meanwhile stays cancelled and its artifact is deleted. `reap_the_interrupted_runs` (at startup and every `QUEUE_POLL_SECONDS` in `maintenance_loop`) fails only running runs whose heartbeat is older than `TRAINING_STALE_SECONDS` and queued rows without a request - never a live worker's run. `POST /api/v1/ml/runs/{id}/cancel` cancels a queued run for good; a running one is marked cancelled and its result discarded (the `fit` cannot be interrupted). Settings: `TRAINING_CONCURRENCY`, `TRAINING_HEARTBEAT_SECONDS`, `TRAINING_STALE_SECONDS`, `QUEUE_POLL_SECONDS`, `TRAINING_IN_API` (`0` = enqueue only, run `python -m backend.app.worker`). The run row is still the error channel.

## Model catalog (the real extension point)

- `MODEL_CATALOG` (`backend/app/model_training.py:137`) is the source of truth (38 entries). `ALIASES` maps alternate spellings to canonical keys. `list_available_models()` scans `ROOT/{ML_models,DL_models,Encoder_Decoder}` — those dirs were **deleted** in commit `d4b397c` — so it always falls back to the catalog.
- Adding a model: catalog entry (`category`, `description`, `params`, `optimization`, `test_results`) + optional `ALIASES` entry + a `build_model()` branch (sklearn-like) or a category trainer routed from `train_model()`.
- `category` selects the code path in `train_model()`: `reinforcement-learning` → `_train_rl_model` (requires `env_id`), `vision` → `_train_resnet_image_model` (requires a dataset of the registry whose source is `folder`: a directory with class subfolders, not a CSV), `clustering` → `_train_clustering`, `nlp` → `_train_transformer_text_classifier`, `timeseries`/`graph`/`autoencoder` → `_train_torch_regression_or_classification` (a plain MLP — the "time-series"/GNN/autoencoder models are not real implementations), everything else → the sklearn tabular flow.
- Category strings are inconsistent: `"time-series"` (XGBoost/LightGBM/CatBoost — these train as **tabular** models) vs `"timeseries"` (LSTM/RNN/SSM/TCN → the torch MLP branch). `HMM_timeseries` was moved to `category: "clustering"` so it reaches the trainer that implements it.
- Catalog `params` are splatted into the estimator constructor (`build_model()`), so they must only contain keys that estimator accepts. Trainer-owned keys (notably `test_size`) are stripped centrally in `train_model()` and in `build_model()`/`_train_clustering()`; an **unknown/typo'd** key still raises `TypeError` on purpose — do not add a blanket signature filter.
- The preset is applied **once**, to the merged base: final params = `{**preset(catalog + mode_suggestions), **preset(client_values)}`. The client's explicit values still win, and a preset is effective in every mode (even with an empty `hyperparameters` dict). `metrics["model_parameters"]` reports the effective set for the tabular flow (the other trainers don't emit it).
- The supervised tabular models save a `TabularModelBundle` (`backend/app/tabular.py`: pipeline + feature schema + label encoder), `Autoencoder` an `AutoencoderBundle`; `GET .../schema` and `POST .../predict` serve them (`_bundle_for_run` loads only a file inside `MODEL_DIR`, since loading unpickles). Preprocessing, the stratified split, the baselines and the cross-validation live in `tabular.py`; `train_model()` only orchestrates them. The heavy modules are `model_training.py` and `tabular.py` - keep `tabular.py` free of any import from `model_training.py` (no cycle).
- Artifacts land in `<repo>/models/<Model>_<unix_ts>.joblib` (`MODEL_DIR` is created at import time). `models/` is now gitignored — don't commit artifacts.

## Frontend conventions

- Single-file SPA, no router, no react-router: navigation is `navigate(view, params)` state in `MainApp` (`frontend/App.jsx`). Views live in `frontend/App.jsx` (`AuthView`, `ModelsCatalog`, `RunsDashboard`, `RunDetails`, `NewJob`).
- The API base is hardcoded: `const API_BASE = 'http://localhost:8010'` at `frontend/App.jsx:8`. There is no Vite proxy and no env var — change it there.
- Token is kept in `localStorage` under `prime_token`; `apiFetch` in `AuthProvider` adds the `Authorization` header and auto-logs-out on 401.
- The dataset of a training job is picked in a dropdown (`GET /api/v1/ml/datasets`) and sent as `dataset_id`; the file input of the form uploads a CSV (`POST /api/v1/ml/datasets/upload`) and the label column is chosen from the columns of the selected dataset.
- `frontend/tailwind.config.js` `content` lists only `./index.html`, `./App.jsx`, `./main.jsx` — add any new file there or its Tailwind classes won't be generated.
- CORS is an explicit allow-list (`CORS_ORIGINS`) in `backend/app/main.py`, not `allow_origins=["*"]`.

## Auth reality

- **Every ML endpoint requires a token.** `get_current_user` uses the OAuth2 bearer scheme: no `Authorization` header → **401**; a header that is present but invalid/expired → **401** (the SPA logs out and shows "Session expired"). There is **no** anonymous fallback any more: the shared `anonymous` account was removed (it had the password `anonymous` and was the owner of every unauthenticated run). `GET /api/v1/admin/all-users` additionally requires an admin token (`get_current_admin`).
- `SECRET_KEY` comes from the environment. In production (`APP_ENV=production`) a missing key is a **hard startup error**; in development a random key is generated once into `<repo>/.secret_key` (git-ignored, `SECRET_KEY_FILE` overrides the path). An empty `SECRET_KEY_FILE` is not the default: the path becomes the current directory of the process, and the key is then not persisted. A token signed with the old published default is rejected.
- Login is OAuth2 form POST `/token`; registration is JSON POST `/api/v1/register` (a client-supplied `role` is ignored; a duplicate username → 409; the reserved names `anonymous`/`admin`/`root`/`system` → 400; a password of at least 8 characters and at most 72 **bytes**).
- Failed logins are rate limited per address **and** per account, registrations per address (`LOGIN_RATE_LIMIT`, `REGISTER_RATE_LIMIT`). CORS uses an explicit allow-list (`CORS_ORIGINS`, the dev origins of the SPA by default) — `allow_origins=["*"]` is gone.
- `backend/.env.example` documents every environment variable of the application, except `RATE_LIMIT_MAX_CLIENTS`, which the rate limiter reads with the default of 10000.

## Existing docs (read before changing ML code)

- `backend/app/README.md` — detailed "how to add a model" guide. Mostly accurate; trust `model_training.py` over it where they disagree.
- `data/README.md` — the datasets that ship with the repository, the two ways to add one and the format a CSV has to have.
- `readme.md` — describes the shipped system (frontend port 3000, compose at `backend/docker-compose.yml`, the dataset as a row of the registry the client addresses by `dataset_id`, the randomized auto_tune search).
- `TODO.MD` — the open item (auto fine-tuning with and without the LLM) is done; it was implemented in W1-7.
- `AUDIT.md`, `FIX_PLAN.md`, `FOLLOWUP_PLAN.md`, `WEEK1_PLAN.md` — the plans of the earlier rounds. They describe the state before the change they plan, on purpose: do not read them as a description of the current code.
