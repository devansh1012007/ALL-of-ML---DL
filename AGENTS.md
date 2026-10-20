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

Repo-specific anchors for this workflow: backend tests are `python -m pytest backend/tests` from the **repo root** (see Commands); there is no linter, so "run the linter" means run pytest plus a manual dev-server check; the "existing tests" to read are `backend/tests/conftest.py`, `backend/tests/test_main.py`, `backend/tests/test_model_training.py`, `backend/tests/test_catalog_params.py` and `backend/tests/test_auth_and_runs.py` (the last two were added by the bug-fix round; they pin the catalog/param/routing and auth contracts).

## Layout / entrypoints

- `backend/app/main.py` — FastAPI app (`uvicorn app.main:app`), all HTTP routes, request models.
- `backend/app/model_training.py` (~1.7k lines) — the ML core: `MODEL_CATALOG`, `ALIASES`, `TRAINING_MODES`, `TRAINING_PRESETS`, `train_model()`, `build_model()`, per-category trainers.
- `backend/app/models.py` — ORM (`users`, `training_runs`); `backend/app/database.py` — engine/session; `backend/app/auth.py` — bcrypt + JWT.
- `backend/migrations/` — Alembic; `backend/tests/` — pytest.
- `frontend/App.jsx` (~1.4k lines) — the whole SPA. `frontend/main.jsx` is the entry; **there is no `src/` dir** — `index.html`, `main.jsx`, `App.jsx`, `styles.css` all sit at the `frontend/` root.
- `data/` — local CSV datasets are read from here at runtime. Only `data/README.md` is committed, so a fresh clone has **zero datasets**; the local-dataset dropdown will be empty until you add a CSV.

## Commands

Backend (from repo root, venv at repo root):
- install: `pip install -r backend/requirements.txt`
- run: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload` (port 8010 is what the frontend hardcodes; logs go to `backend/app.log`, relative to CWD)
- tests: `python -m pytest backend/tests` — **run from the repo root**: test modules import `backend.app.*` and neither `backend/` nor `backend/app/` has `__init__.py`, so the repo root must be on `sys.path`. `backend/tests/conftest.py` puts it there (and pins an isolated sqlite `DATABASE_URL` + a temporary `MODEL_DIR`), so bare `pytest backend/tests` works from the repo root too.
- single test: `python -m pytest backend/tests/test_model_training.py::test_train_model_auto_fine_tune_tabular`
- migrations: `cd backend && alembic upgrade head` (needs `DATABASE_URL`); new revision: `cd backend && alembic revision --autogenerate -m "..."` (see `backend/commands.txt`, which uses `docker-compose run --rm web ...`)

Frontend:
- `cd frontend && npm install && npm run dev` → **http://localhost:3000** (`frontend/vite.config.js` sets `server.port: 3000`; the root `readme.md` says 5173 — it is wrong).
- `npm run build` → `frontend/dist/`

Docker:
- The compose file is `backend/docker-compose.yml`, **not** the repo root. `cd backend && docker-compose up --build`.
- Needs `backend/.env` (gitignored) with `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST_PORT`, `POSTGRES_PORT`, `DATABASE_URL` (in compose, `DATABASE_URL` must point at the `db` service, not localhost).
- The `web` service's `command:` overrides the Dockerfile `CMD`, so **`alembic upgrade head` does not run automatically in compose** — run it manually.

## Environment gotchas

- `DATABASE_URL` must be set before the app is importable. The default in `backend/app/database.py` is `sqlite+aiosqlite:///./backend.db`; `aiosqlite` **is** in `requirements.txt` now, so the sqlite fallback works out of the box (it creates `./backend.db` in the CWD). Use `postgresql+asyncpg://user:pass@host:5432/db` for anything real.
- `python-dotenv` is in `requirements.txt` but nothing calls `load_dotenv` — export env vars yourself (or rely on compose `env_file`).
- Still missing from `requirements.txt`: `google-generativeai` (`llm_fine_tune` mode), `umap` / `hdbscan` (catalog models `UMAP`/`HDBSCAN` raise "not installed" at train time), `gymnasium` / `stable-baselines3` / `torch` are declared but huge. Optional imports in `model_training.py` are guarded, so the module still imports.
- `scikit-learn` is pinned to `<1.10` because the catalog uses `LogisticRegression(penalty="l2")` (removed in 1.10) and `SVC(probability=True)` (removed in 1.11). Relax the pin only after removing those params.
- `openai` is in `requirements.txt` but unused by the code; `llm_fine_tune` uses **Google Gemini** (`GOOGLE_API_KEY`, optional `GOOGLE_MODEL`) — the backend's mode description says so too.
- `alembic.ini` has a stale `sqlalchemy.url` (`admin/password123@localhost:5433/notes_db`); `migrations/env.py` overrides it from `DATABASE_URL`.
- `POST /api/v1/ml/train` trains **synchronously** inside the request (`run_in_threadpool`) and only returns when training finishes.

## Model catalog (the real extension point)

- `MODEL_CATALOG` (`backend/app/model_training.py:137`) is the source of truth (38 entries). `ALIASES` maps alternate spellings to canonical keys. `list_available_models()` scans `ROOT/{ML_models,DL_models,Encoder_Decoder}` — those dirs were **deleted** in commit `d4b397c` — so it always falls back to the catalog.
- Adding a model: catalog entry (`category`, `description`, `params`, `optimization`, `test_results`) + optional `ALIASES` entry + a `build_model()` branch (sklearn-like) or a category trainer routed from `train_model()`.
- `category` selects the code path in `train_model()`: `reinforcement-learning` → `_train_rl_model` (requires `env_id`), `vision` → `_train_resnet_image_model` (requires a local dir with class subfolders, not a CSV), `clustering` → `_train_clustering`, `nlp` → `_train_transformer_text_classifier`, `timeseries`/`graph`/`autoencoder` → `_train_torch_regression_or_classification` (a plain MLP — the "time-series"/GNN/autoencoder models are not real implementations), everything else → the sklearn tabular flow.
- Category strings are inconsistent: `"time-series"` (XGBoost/LightGBM/CatBoost — these train as **tabular** models) vs `"timeseries"` (LSTM/RNN/SSM/TCN → the torch MLP branch). `HMM_timeseries` was moved to `category: "clustering"` so it reaches the trainer that implements it.
- Catalog `params` are splatted into the estimator constructor (`build_model()`), so they must only contain keys that estimator accepts. Trainer-owned keys (notably `test_size`) are stripped centrally in `train_model()` and in `build_model()`/`_train_clustering()`; an **unknown/typo'd** key still raises `TypeError` on purpose — do not add a blanket signature filter.
- The preset is applied **once**, to the merged base: final params = `{**preset(catalog + mode_suggestions), **preset(client_values)}`. The client's explicit values still win, and a preset is effective in every mode (even with an empty `hyperparameters` dict). `metrics["model_parameters"]` reports the effective set for the tabular flow (the other trainers don't emit it).
- Artifacts land in `<repo>/models/<Model>_<unix_ts>.joblib` (`MODEL_DIR` is created at import time). `models/` is now gitignored — don't commit artifacts.

## Frontend conventions

- Single-file SPA, no router, no react-router: navigation is `navigate(view, params)` state in `MainApp` (`frontend/App.jsx`). Views live in `frontend/App.jsx` (`AuthView`, `ModelsCatalog`, `RunsDashboard`, `RunDetails`, `NewJob`).
- The API base is hardcoded: `const API_BASE = 'http://localhost:8010'` at `frontend/App.jsx:8`. There is no Vite proxy and no env var — change it there.
- Token is kept in `localStorage` under `prime_token`; `apiFetch` in `AuthProvider` adds the `Authorization` header and auto-logs-out on 401.
- `frontend/tailwind.config.js` `content` lists only `./index.html`, `./App.jsx`, `./main.jsx` — add any new file there or its Tailwind classes won't be generated.
- CORS is wide open (`allow_origins=["*"]`) in `backend/app/main.py`.

## Auth reality

- Most ML endpoints use `get_active_user`: **no** `Authorization` header → an auto-created `anonymous` user (so they work unauthenticated); a header that is present but invalid/expired → **401** (the SPA logs out and shows "Session expired"). Only `GET /api/v1/admin/all-users` requires a real admin token (`get_current_admin`).
- `SECRET_KEY` is hardcoded as the default in `backend/app/auth.py` but overridable by the `SECRET_KEY` env var. Login is OAuth2 form POST `/token`; registration is JSON POST `/api/v1/register` (a client-supplied `role` is ignored; a duplicate username → 409).

## Existing docs (read before changing ML code)

- `backend/app/README.md` — detailed "how to add a model" guide. Mostly accurate; trust `model_training.py` over it where they disagree.
- `readme.md` — partially stale: frontend port 5173, compose at repo root, models under `ML_models/`/`DL_models/`, and it ends with a stray "If you'd like, I can also commit a docker-compose.yml…" paragraph.
- `TODO.MD` — single open item: auto fine-tuning with and without the LLM.
