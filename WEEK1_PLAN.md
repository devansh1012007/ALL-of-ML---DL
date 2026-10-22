# WEEK1_PLAN — honest, demo-ready, and actually tunable

- Status: **APPROVED / IN PROGRESS** — written 2026-10-22
- Tier: **L** (public API contract change, security posture, persistence, concurrency)
- Repo state: branch `feature/week1-honest-demo`, base commit `ad5a6ef`
- Spec: operator conversation of 2026-10-22 (audit + "plan out week one")
- Relation to `FOLLOWUP_PLAN.md`: this file is the **week-1 subset and ordering** of the deferred
  round (phases 6-11) plus two additions the deferred round explicitly left out (dataset upload
  with a real registry, and a real `auto_tune`). `FOLLOWUP_PLAN.md` stays the reference for the
  phases it already specifies in detail; where the two disagree, this file wins for week 1.
- Trace tag convention: each change carries `PLAN:week1:<ID>` in the commit message so any line
  can be traced back to its reason.
- Staleness rule: if the repo moves on the files listed in section F, re-verify sections C and F
  before acting.

---

## A. Problem, goal, success criteria

- **Problem** (measured, not read):
  - A fresh clone can produce **zero** training runs: `data/` holds only a README, and the only
    dataset source is the server-side `data/` directory (`backend/app/main.py:236-238`). There is
    no upload endpoint.
  - 13 of the 38 catalog entries train something other than what they advertise. `LSTM`, `RNN`,
    `SSM_timeseries`, `TCN_timeseries`, `GNN` and `Autoencoder` all reach the same 2-layer MLP
    (`backend/app/model_training.py:1266-1304`); `ViT` trains a ResNet-18 (`:1384`); `Q-Learning`
    is a stub (`:1192-1193`). The artifacts of those runs are **corrupt**: loading
    `models/LSTM_1792491722.joblib` raises `EOFError` because `SimpleNet` is a function-local class
    and cannot be pickled (`:1281`, `:1307-1311`).
  - Training blocks the HTTP request for its whole duration (`backend/app/main.py:263`), so the UI
    hangs and a cancelled request leaves the run row in `running` forever (`except Exception` does
    not catch `CancelledError`, `main.py:292`).
  - The API is open by default: no `Authorization` header falls back to a shared `anonymous` user
    whose password is literally `anonymous` (`main.py:73-82`), the JWT signing key is a published
    constant (`backend/app/auth.py:11`), and CORS is a wildcard with credentials
    (`main.py:33-39`). `dataset_name` accepts absolute paths, so any caller can make the server
    read an arbitrary file (`model_training.py:982-984`) — verified: a training run on
    `/tmp/outside.csv` answered HTTP 200.
  - `auto_tune` is a no-op: `manual` and `auto_tune` produce byte-identical effective parameters
    (`model_training.py:1041-1045`), while the API and the UI promise a grid search
    (`main.py:199`) and a Bayesian optimization (`main.py:202`).
  - Alembic is decorative: `alembic upgrade head` creates `users` and the vestigial `notes` table
    and **never** `training_runs`; the app works only because the startup hook calls
    `create_all` (`main.py:126-129`).
- **Goal**: clone -> trained artifact -> downloaded model in under ten minutes, with every visible
  claim true, and `auto_tune` performing an actual search.
- **Success criteria** (observable):
  1. `python -m pytest backend/tests` is green from the repo root (baseline: 102 passed, 9 skipped,
     the 9 skips being the NLP entries that download checkpoints) plus the new tests of section H.
  2. `cd frontend && npm run build` is green.
  3. A manual demo path works on a fresh clone using only the committed sample CSVs: register,
     log in, pick a dataset, train, watch the run, download the artifact.
  4. No catalog entry advertises a metric its trainer cannot produce; a placeholder model fails
     fast with an actionable message instead of training the wrong thing.
  5. A dataset path outside the configured root cannot be trained — by construction, not by
     filtering.
  6. A long training returns a `run_id` immediately and the row reaches a terminal state.
  7. `auto_tune` reports `best_params` and a search summary, and a client-pinned parameter is
     never overridden.
- **Non-goals (week 1)**: real LSTM/GNN/ViT/seq2seq/UL2/GPT/LLaMA trainers; an inference
  endpoint; the comparison view and charts; the full `readme.md` rewrite (`FOLLOWUP_PLAN.md`
  phase 11); a production job queue; Docker/Postgres hardening beyond "the migrations run";
  CI and `LICENSE` (below the cut line).
- **Constraints**: no linter, formatter or type checker exists in this repo — validation is
  `pytest` plus a manual dev-server check (`AGENTS.md`). `scikit-learn` stays pinned `<1.10`
  (the catalog uses `LogisticRegression(penalty="l2")` and `SVC(probability=True)`). The public
  names and signatures of `backend/app/model_training.py` stay stable.
- **Reversibility**: two-way. Every phase is one commit, and the three breaking API changes
  (token required, `dataset_id`, the train response) live in their own commits so any one of them
  can be reverted on its own.

## B. Glossary

- **run** — one row in `training_runs`: a training request plus its outcome (`status`,
  `metrics`, `artifact_path`).
- **catalog entry** — one item of `MODEL_CATALOG`; the promise the product makes about a model.
- **placeholder entry** — a catalog entry whose trainer does not build what the entry advertises.
- **dataset registry** — the `datasets` table: one row per usable dataset, owned by a user.
- **search space** — the per-model hyperparameter distribution that `auto_tune` samples from.

## C. Architecture of the codebase (the part that matters here)

- `backend/app/main.py` (354 lines) — every HTTP route, the request models, the CORS middleware and
  the startup hook. No router module, no service layer.
- `backend/app/model_training.py` (1700 lines) — `MODEL_CATALOG` (38 entries), `ALIASES`,
  `TRAINING_MODES`, `TRAINING_PRESETS`, `train_model()` (the dispatcher) and one trainer per
  category.
- `backend/app/models.py` — the ORM: `users`, `training_runs`. `status` is a free `String`, so the
  async lifecycle of phase 4 needs **no** migration.
- `backend/app/auth.py` — bcrypt hashing and JWT minting; `SECRET_KEY` resolution.
- `backend/app/database.py` — the async engine; `DATABASE_URL` is read at import time.
- `backend/migrations/` — Alembic. `env.py` overrides the URL from `DATABASE_URL`; the first
  revision creates `users` + `notes`, the second is empty.
- `frontend/App.jsx` (1410 lines) — the whole SPA: `AuthProvider`/`apiFetch` (adds the bearer
  token, logs out on 401, `App.jsx:144-152`), `AuthView`, `ModelsCatalog`, `RunsDashboard`,
  `RunDetails`, `NewJob`, and the `MainApp` shell. Navigation is `navigate(view, params)` state
  (`App.jsx:1316-1332`); there is no router.
- **Execution flow today** — `POST /api/v1/ml/train` (`main.py:240-297`): create the run row ->
  commit -> `run_in_threadpool(train_model, ...)` -> write `metrics`/`artifact_path`/`status` ->
  return the metrics inline. The frontend reads only `result.run_id` afterwards (`App.jsx:923`).
  `RunDetails` fetches once, without polling (`App.jsx:523-531`); `RunsDashboard` polls every
  five seconds (`App.jsx:425-435`).
- **Conventions to follow**: the module docstrings that state *why* a decision was taken; the
  explicit `raise ValueError(...)` for a bad request that becomes an HTTP 400; the "the client
  sends it, the server stores it" separation; the `safe_json()` numpy-aware serializer; the
  `conftest.py` isolation of the database and `MODEL_DIR`; the test style of asserting a status
  code and a JSON shape, with a docstring that names the contract.
- **Data flow of a dataset today**: `dataset_name` (a bare string from the client) ->
  `resolve_dataset_path()` (`model_training.py:982-984`) -> absolute path passed through unchanged
  -> `pd.read_csv` (`:1331`). The label column is checked only after the file is parsed (`:1358`).

## D. Proposed design

Seven phases in one dependency chain, each ending in an independent review gate (`AGENTS.md`):

```
W1-1 lifespan ─► W1-2 Alembic owns the schema (+ datasets revision)
                              │
                              ▼
 W1-3 token required ─► W1-4 dataset registry / upload / dataset_id
                              │ │
                              └───────┬──────► W1-5 async training
                                             │
                                             ▼
                                       W1-6 honest catalog
                                             │
                                             ▼
                                   W1-7 real auto_tune (stretch)
                                             │
                                             ▼
                                       W1-8 docs truth pass
```

- **Why this order.** The schema must be owned by the migrations before the `datasets` table
  exists (W1-2 gates W1-4). Authentication must be closed before uploads, or the uploads land on
  an anonymous owner that everybody shares (W1-3 gates W1-4). Async training needs the lifespan
  handler for its reaper and the schema for its status column (W1-1/W1-2 gate W1-5). The catalog
  is edited by both W1-6 (honesty) and W1-7 (search spaces), so W1-6 lands first.
- **Before flow.** `POST /train` -> row created -> the request blocks for the whole training ->
  the metrics are returned inline -> a failure is an HTTP 400 and the row carries the error.
  Datasets are files in `data/`, named by the client, resolved to an absolute path.
- **After flow.** `POST /train` -> row created (`status="running"`) -> the response returns
  `run_id` -> the training runs in the background -> the row becomes `completed` or `failed` ->
  the client polls `GET /runs/{id}`. Datasets are rows in `datasets`; the client sends a
  `dataset_id`; the server resolves the path from the row, so no client string ever reaches the
  filesystem. Every ML endpoint needs a token.
- **Why this approach.** It is the smallest set of changes that makes the product honest
  (W1-5/W1-6/W1-7) and usable end to end (W1-3/W1-4) while keeping the deployment story simple
  (W1-1/W1-2): one process, one database, no new runtime dependency except
  `google-generativeai` for the LLM mode.

## E. Change list

Every entry is independently reviewable, verifiable and revertable. `Depends on` uses the W1
numbers; the "test ID" refers to section H.

### W1-1 — the lifespan handler replaces the deprecated startup hook

| | |
|---|---|
| What | `@app.on_event("startup")` becomes a `lifespan` context manager; the schema verification and the run reaper live in it. |
| How | `@asynccontextmanager async def lifespan(app: FastAPI)`; `app = FastAPI(..., lifespan=lifespan)`. |
| Why | `on_event` is deprecated and warns on every import and every test run; the reaper and the schema check need exactly one home. |
| Depends on | — · **Test** T01 · **Risk** low · **Revert** revert the commit |

### W1-2 — Alembic is the only schema owner

| | |
|---|---|
| What | A new revision creates `training_runs` and drops the vestigial `notes` table; `create_all` leaves the application; the startup hook *verifies* the schema and fails with an actionable message; the test suite builds its schema by running the migrations; `alembic.ini` loses the stale DSN; `migrations/env.py` escapes `%` in the URL; compose runs the migrations. The first revision becomes idempotent as well, so a database that `create_all` created without an `alembic_version` row upgrades too. |
| How | Revision `c4a9e2b17d3f` (guarded by `_existing_tables()` so all three real-world database states upgrade); revision 1 guarded the same way; `env.py` builds the engine directly from the resolved URL; `conftest.py` gains a session fixture that runs `command.upgrade(config, "head")`; the lifespan inspects the live schema and raises `RuntimeError` naming the missing tables. The `datasets` table is **not** part of this phase: its revision lands with its ORM model and its endpoints in W1-4, so the schema and the ORM never disagree. |
| Why | `alembic upgrade head` today produces a schema the application cannot use, and `create_all` hides that. This is the decision already recorded in `FOLLOWUP_PLAN.md` §1.2 (D2); it moves into week 1 only because the `datasets` table needs a real owner for the schema. |
| Depends on | W1-1 · **Test** T02 · **Risk** medium (existing developer databases are in three different states; the idempotent guards are the mitigation) · **Revert** revert the commit, `create_all` returns |

### W1-3 — a token is required everywhere, the secret is real, CORS is explicit

| | |
|---|---|
| What | The `anonymous` fallback is removed: every ML endpoint requires a valid token and answers 401 otherwise. `SECRET_KEY` comes from the environment; in production a missing key is a hard startup error; in development a random key is generated once and persisted in a git-ignored `.secret_key`. CORS uses an explicit allow-list from `CORS_ORIGINS`. Registration rejects the reserved name `anonymous` and applies a password policy. Login and registration are rate limited per IP. |
| How | The `get_active_user` dependency becomes "token required" on every ML route; `auth.py` resolves the key through `_load_secret_key()`; `main.py` builds the allow-list from the environment; a small in-memory limiter guards `/token` and `/api/v1/register`; bcrypt runs in a threadpool so it does not block the event loop. |
| Why | The published default key lets anyone mint a token for any user (`auth.py:11`); `anonymous/anonymous` is a working credential for the shared bucket (`main.py:78`); a wildcard origin with credentials reflects any origin (`main.py:33-39`). This is `FOLLOWUP_PLAN.md` D4, moved into week 1 by the operator's decision. |
| Depends on | W1-2 · **Test** T03 · **Risk** medium (**breaking**: token-less `curl` stops working, and the pinned test `test_requests_without_authorization_header_stay_available` (`backend/tests/test_auth_and_runs.py:94-102`) must be **inverted**, not deleted) · **Revert** revert the commit; the key change forces one re-login |

### W1-4 — the dataset registry: one table, an upload, one resolution root

| | |
|---|---|
| What | (a) a CSV upload endpoint; (b) the built-in `data/*.csv` files are seeded as rows at startup; (c) one listing endpoint that returns the columns, the row count and a suggested label column; (d) a training request references a dataset **by id**, never by a client-supplied path. |
| How | New `backend/app/datasets.py` with the `Dataset` ORM model; `POST /api/v1/ml/datasets/upload` (CSV only, size and row limits) storing the file under `DATASETS_ROOT/uploads/<uuid>_<name>.csv`; `GET /api/v1/ml/datasets` and `GET /api/v1/ml/datasets/{id}` (the row carries the columns, so the schema endpoint of the plan was merged into the detail endpoint); `POST /api/v1/ml/train` takes `dataset_id` **or** `hf_dataset_url`, exactly one; `resolve_dataset_path()` becomes root-relative and rejects absolute paths and `..`; `DATASETS_ROOT` (default: the repository root) holds `data/` for the built-ins and `uploads/` for user files. `train_model()` keeps its signature and receives the resolved relative path. |
| Why | The dropdown is empty on a fresh clone and the only data source is the server's `data/` directory (`main.py:236-238`); `dataset_name` accepts absolute paths, which I turned into a successful training run on `/tmp/outside.csv`. A registry also gives every upload an owner, which the shared anonymous bucket made impossible. |
| Depends on | W1-2, W1-3 · **Test** T04 · **Risk** medium (the dataset-name semantics of `train_model` change, so `backend/tests` moves to relative paths under a patched root — a documented deviation from `FOLLOWUP_PLAN.md` invariant 10 with the same intent as its S5) · **Revert** revert the commit |

### W1-5 — asynchronous training

| | |
|---|---|
| What | `POST /train` creates the row, answers `200` with `{run_id, status: "queued", artifact_path: null, metrics: null}` and trains in the background; the row is the error channel; a restart reaps the rows that were left `queued` or `running`; the frontend polls the run. |
| How | `BackgroundTasks.add_task(_execute_training, run_id, payload)`; the row is created `queued` and the worker sets it `running` when it takes it (the plan said `running` at the moment of the answer: a row that is `running` while nothing trains yet is a claim the server cannot keep, and the four states `queued`/`running`/`completed`/`failed` are the ones the frontend shows); the worker writes the outcome with its **own** `AsyncSessionLocal()` session, never the request-scoped one; any exception writes `status="failed", metrics={"error": ...}`; the lifespan reaper fails the `running` rows at startup; `RunDetails` polls every two seconds with a chained `setTimeout` while the status is `running`; `write_artifact()` gets a unique name (microseconds) because two runs in the same second currently overwrite each other (`model_training.py:1308`). |
| Why | The request blocks for the whole training (`main.py:263`); a cancelled request leaves the row `running` forever (`main.py:292`). |
| Depends on | W1-1, W1-2, W1-4 · **Test** T05 · **Risk** medium (contract change) · **Revert** revert the commit |

### W1-6 — an honest catalog

| | |
|---|---|
| What | The twelve placeholder entries get `implemented: False` and their `test_results` move to `planned_test_results`; training fails fast for them; clustering reports a `silhouette` (and a `noise_count`, DBSCAN's `-1` excluded) and `auto_search` can rank clustering candidates; a **real** autoencoder replaces the MLP in disguise; the generic torch trainer's `SimpleNet` moves to module level so its artifacts are picklable; the vision trainer reports `train_accuracy` instead of `accuracy`; the user interface shows a "Not implemented" badge, disables those options, and distinguishes "not implemented" from "no benchmark data yet". |
| How | As specified in `FOLLOWUP_PLAN.md` §6.3.1-6.3.6: the `implemented` flag in `MODEL_CATALOG`, the `planned_test_results` rename, the fail-fast in `train_model()` right after `get_model_entry()`, `silhouette` in `_train_clustering()` and in `_CANDIDATE_SCORE_KEYS` (`model_training.py:939`), a new `_train_autoencoder()` with a module-level class, `SimpleNet` hoisted to module level, and the frontend badge plus the disabled option. |
| Why | The catalog is the product's credibility surface: thirteen entries advertise metrics their trainers cannot emit, and the timeseries/GNN/autoencoder runs currently produce corrupt artifacts (verified: `EOFError` on load). |
| Depends on | W1-5 · **Test** T06 · **Risk** medium (**the routing test at `backend/tests/test_catalog_params.py:249-330` enumerates all 38 entries and expects each to reach a trainer; it must gain an `IMPLEMENTED` set — updated to the new truth, not weakened**) · **Revert** revert the commit |

### W1-7 — a real `auto_tune` (stretch)

| | |
|---|---|
| What | `auto_tune` performs a randomized hyperparameter search over a curated per-model space and reports `best_params` plus a search summary. `auto_fine_tune` becomes a local search around the current configuration. `llm_fine_tune` works for real: Gemini proposes values, they are validated against the model's space, and a missing key or package fails fast with an actionable message. `auto_search` is relabelled honestly ("model selection over candidates"); it is not Bayesian. |
| How | A new `search_space` key per tabular catalog entry; `RandomizedSearchCV(estimator=build_model(...), param_distributions=space, n_iter=min(12, |space|), cv=3, scoring=accuracy or r2, refit=True)` on the training split; `metrics["model_parameters"]` becomes the best parameters and `metrics["search_results"]` holds the top candidates. Client-supplied values are excluded from the space (the client wins); `test_size` stays trainer-owned. `auto_fine_tune` uses the same engine restricted to a neighborhood of the base parameters. `llm_fine_tune` requires `google-generativeai` and `GOOGLE_API_KEY` and validates every proposed value. The false mode descriptions are replaced (`main.py:199`, `main.py:202`, `App.jsx:64-70`). |
| Why | `auto_tune` is a no-op today (verified: identical effective parameters to `manual`) while the product promises a search; this is also `TODO.MD`'s actual open item. |
| Depends on | W1-6 · **Test** T07 · **Risk** medium (a search is slower; `cv=3` can fail on a small fold, so it falls back to `cv=2` and says so) · **Revert** revert the commit |

### W1-8 — the documentation truth pass

| | |
|---|---|
| What | `readme.md` (port 3000, the real paths, the real model count, the AI-artifact paragraphs removed), `backend/app/README.md:246,251`, `TODO.MD`, `AGENTS.md` (the new endpoints, `dataset_id`, the token requirement, `DATASETS_ROOT`), `.env.example`, `.gitignore` (`data/uploads/`, `.secret_key`), the 14 tracked `.pyc` files and `backend/app.log` untracked, the log to stdout instead of a CWD-relative file (`main.py:27`). |
| How | One pass over the documents after the behaviour is final, so the text describes the shipped system. |
| Why | The documentation currently contradicts the code (port 5173 vs 3000, a root `docker-compose.yml` that does not exist, the deleted `ML_models/` directories, "grid search" and "Bayesian optimization"). |
| Depends on | W1-7 · **Test** — the manual demo path of section A · **Risk** low · **Revert** revert the commit |

**Below the cut line** (dropped first if the week runs short): the CI workflow, `LICENSE`, the full
`readme.md` rewrite, the comparison view, charts.

## F. Files affected

| File | Change | IDs | Why it must change |
|---|---|---|---|
| `backend/app/main.py` | modify | W1-1,2,3,4,5 | every route, the CORS middleware, the startup hook, the train endpoint |
| `backend/app/model_training.py` | modify | W1-4,5,6,7 | the dataset resolution, the catalog, the trainers, the mode suggestions |
| `backend/app/auth.py` | modify | W1-3 | the signing key |
| `backend/app/models.py` | modify | W1-4 | the `datasets` table |
| `backend/app/datasets.py` | new | W1-4 | the registry, the upload, the schema inspection |
| `backend/migrations/versions/c4a9e2b17d3f_*.py` | new | W1-2 | creates `training_runs`, drops `notes` |
| `backend/migrations/versions/<new>_*_datasets.py` | new | W1-4 | creates `datasets` (lands with the ORM model and the endpoints); a second revision makes the name of a dataset unique per owner |
| `backend/migrations/env.py` | modify | W1-2 | the URL, the `%` escaping, the engine |
| `backend/alembic.ini` | modify | W1-2 | the stale DSN |
| `backend/docker-compose.yml` | modify | W1-2 | the migrations must run |
| `backend/tests/conftest.py` | modify | W1-2,3,4 | the schema source, the auth fixtures, the dataset root |
| `backend/tests/test_main.py` | modify | W1-3,4,5 | the pinned contract tests |
| `backend/tests/test_auth_and_runs.py` | modify | W1-3,5 | the pinned contract tests |
| `backend/tests/test_catalog_params.py` | modify | W1-6 | the routing expectation table |
| `backend/tests/test_datasets.py` | new | W1-4 | the registry and the upload |
| `backend/tests/test_search.py` | new | W1-7 | the search |
| `backend/requirements.txt` | modify | W1-7 | `google-generativeai` |
| `frontend/App.jsx` | modify | W1-3,4,5,6,7 | the dataset picker, the polling, the badges, the mode copy |
| `data/sample_*.csv` | new | W1-4 | the demo datasets a fresh clone needs |
| `.gitignore`, `.env.example` | modify | W1-3,4,8 | the uploads, the secret, the environment |
| `readme.md`, `backend/app/README.md`, `TODO.MD`, `AGENTS.md` | modify | W1-8 | the truth pass |

## G. Alternatives and decisions

| ID | Decision | Options | Chosen | Why | Rejected because |
|---|---|---|---|---|---|
| D1 | Week-1 scope | demo only / claims only / both | **both, staged** | operator | — |
| D2 | Authentication | keep the fallback / require a token | **require a token** | operator; closes a verified credential hole | — |
| D3 | Upload storage | disk only / a `datasets` table | **`datasets` table** | operator; gives an upload an owner | the table stores the *metadata*; the bytes stay on disk, so the database does not grow with the data |
| D4 | Train contract | synchronous / asynchronous 200 + `run_id` | **asynchronous** | operator | — |
| D5 | Grid search | defer / implement now | **implement, as the stretch phase** | ~10 h of implementation plus the review gates exceeds the remaining week | squeezing it in means dropping W1-4 (8 h) or W1-5 (6 h), and both break the "clone to artifact" promise |
| D6 | Dataset reference | a client path / a server-side id | **id only** | makes traversal structurally impossible instead of filterable | a client path is exactly the "read any file on the server" primitive that was demonstrated |
| D7 | Cut line | CI, LICENSE, docs | **dropped first** | operator | — |
| D8 | Dataset bytes | a database blob / a file | **a file plus a metadata row** | portability without database bloat | a blob turns every dataset read into a full-table scan on Postgres |
| D9 | Alembic | defer to week 2 / in week 1 | **in week 1** | the `datasets` table needs a real schema owner | — |

## H. Tests and validation

- **What the existing suite guarantees**: the category-to-trainer routing of all 38 entries, the
  estimator construction for the tabular models, the strict rejection of unknown hyperparameters,
  the ownership of `test_size`, the preset semantics, the 401/409/403 auth contracts, the run
  history fields, and the auto-search ranking. **What it does not guarantee**: the migration chain
  (the schema comes from `create_all`), the path confinement, the dataset registry, the async
  lifecycle, the search, and the honesty flags.
- **Baseline**: `python -m pytest backend/tests` from the repo root -> 102 passed, 9 skipped (the
  skips are the NLP entries, which download checkpoints). `cd frontend && npm run build` -> green.

| ID | Level | Scenario | Expected | Proves | New |
|---|---|---|---|---|---|
| T01 | unit | the app imports and starts | no `DeprecationWarning` about `on_event`; the lifespan runs | W1-1 | new |
| T02 | integration | the schema comes from the migrations | the migrated tables equal the ORM metadata; the app refuses to start on an unmigrated database with a message naming `alembic upgrade head` | W1-2 | new |
| T03 | integration | the auth posture | no header -> 401; `anonymous` cannot be registered nor logged in; production without `SECRET_KEY` refuses to start; a foreign origin gets no CORS header | W1-3 | new + the inverted pinned test |
| T04 | integration | the dataset registry | an upload is stored, listed and trainable; a non-CSV and an oversized file are rejected; `..` and absolute paths are rejected; user B cannot train user A's dataset | W1-4 | new |
| T05 | integration | the async lifecycle | the response returns immediately with a `run_id`; the row reaches `completed`; a failing run reaches `failed` with the error; the reaper fails a stale `queued`/`running` row; two runs in the same second get different artifact names | W1-5 | new + four rewritten pinned tests |
| T06 | integration | the honest catalog | every entry declares `implemented`; no entry advertises a metric its trainer cannot produce; a placeholder fails fast and writes no artifact; the silhouette is reported and the DBSCAN noise is excluded; `auto_search` ranks clustering candidates; the autoencoder artifact loads back | W1-6 | new + the routing expectation table |
| T07 | integration | the search | `auto_tune` reports `best_params` that the estimator accepts; a client-pinned parameter is not overridden; `auto_fine_tune` stays in its neighborhood; `llm_fine_tune` without a key answers an actionable 400 | W1-7 | new |
| T14 | build | `npm run build` | green | the frontend | existing |

- **Non-test validation**: the manual demo path of section A, executed against a fresh clone with
  only the committed sample CSVs; the run list showing a `running` row that becomes `completed`
  without a page reload; the artifact downloading and loading in a Python shell.

## I. Edge cases and failure modes (derived from this code)

| Case | Where it bites | Expected behavior | Handled by |
|---|---|---|---|
| DBSCAN's `-1` noise label | `_train_clustering` | excluded from the silhouette, reported as `noise_count` | W1-6, T06 |
| The task type is inferred by cardinality, but `MLR`/`Logistic_Regression` are estimator-fixed | `model_training.py:925-932` | a search space must be task-aware; a regression target with `Logistic_Regression` must fail loudly | W1-7, T07 |
| A headerless, empty or one-gigabyte-per-line CSV | the upload | rejected with a size/parse message | W1-4, T04 |
| Two uploads with the same file name | the registry | the `uuid` prefix keeps the paths unique; the display name is suffixed | W1-4 |
| A built-in CSV deleted after the seeding | the registry | the row stays, the training says the file is missing | W1-4 |
| `cv=3` on a six-row fold | the search | falls back to `cv=2` and reports it in `search_results` | W1-7, T07 |
| An unvalidated `model_candidates` list | `main.py:103` | the server validates the candidates against the catalog | W1-7 |
| A training that outlives the process | the reaper | the row is failed at the next start | W1-5, T05 |
| Two runs in the same second | `write_artifact` | unique names | W1-5, T05 |
| A `%` in the database password | `migrations/env.py` | escaped as `%%` | W1-2 |

## J. Impact, second-order effects, compatibility

- **Blast radius**: every ML endpoint (the token requirement), the train endpoint (the response
  shape), the dataset endpoints (new), the catalog (a new key), the frontend (the dataset picker,
  the polling, the badges), the database (a new table, `notes` dropped).
- **Backward compatibility**: the frontend and the backend must ship together; a token-less client
  breaks; an old `dataset_name` payload is rejected with an actionable message; the `notes` table
  is dropped, and its data is not recoverable (it is referenced by no model, route or view).
- **Concurrency**: the background worker writes with its own session; SQLite's write lock is held
  only for the short status update.
- **Performance**: a search multiplies the training time by `n_iter`; the row-based listing is
  bounded by the user's dataset count.
- **Security**: the traversal primitive is removed by construction; the anonymous bucket is gone;
  the signing key is no longer published; the CORS allow-list is explicit; login is rate limited.
- **Second-order effects**: the catalog visibly shrinks from 38 to 25 trainable entries — that is
  the honest number, and the UI has to say so. A database that was only ever touched by `create_all`
  now needs `alembic upgrade head` before the app starts; that is the point of the change, and the
  error message says exactly what to run.

## K. Rollout, rollback, observability

- **Rollout order**: the phases in section D, each merged separately, with the frontend change of
  a phase in the same commit as its backend change.
- **Rollback**: revert the commit of the phase. The schema change is the one irreversible step
  (the `notes` data); the migration's `downgrade()` restores the table.
- **Point of no return**: the `notes` drop inside the migration, and the key rotation in W1-3
  (one forced re-login).
- **Observability**: `pytest` after every phase; a manual demo path; a run that stays `running`
  for more than five minutes is the signal that the reaper or the worker failed.

## L. Risks and assumptions

| ID | Type | Description | Likelihood x impact | Mitigation / how to verify | Owner | Status |
|---|---|---|---|---|---|---|
| R1 | risk | the chain is serial: a bad day in W1-2 delays everything | M x M | W1-2 is the only genuinely risky item; its idempotent guards are pre-written in `FOLLOWUP_PLAN.md` §3.3.1 | implementer | open |
| R2 | risk | the catalog shrinks from 38 to 25 trainable entries | M x M | W1-6 discloses it in the UI; the honest count is the point | implementer | accepted |
| R3 | risk | uploads on a container-local disk are lost on redeploy | M x M | documented in W1-8; the compose volume is week 2 | implementer | open |
| R4 | risk | a search on a 60-row dataset is noise fitting | M x L | `cv` and `n_iter` are reported in `search_results`; the text calls it a summary, not a promise | implementer | open |
| R5 | assumption | Alembic can run against the async sqlite URL the tests use | M x M | verify first in W1-2 with a 20-minute spike | implementer | open |
| R6 | assumption | the frontend can move to `dataset_id` without a router | L x L | yes: `App.jsx` is one file and the dataset list is one state array | implementer | open |

**Pre-mortem (it shipped and failed anyway):** (1) the migrations do not run cleanly against the
async sqlite URL -> R5, spike first; (2) the worker's SQLite write collides with a concurrent read
-> own session, short writes; (3) a search space does not match the estimator signature -> validate
every space against `inspect.signature` when the space is built; (4) the honesty change breaks the
routing test and someone "fixes" it by deleting assertions -> the expectation table gains an
`IMPLEMENTED` set instead; (5) the chain slips past Friday -> the cut line absorbs it.

## M. Decision log and changelog

- D1-D9 are listed in section G. D5 (the search is the stretch phase) is the recommendation the
  operator has not yet accepted or rejected.
- Round 1 (2026-10-22): the operator chose "both" (demo-ready *and* real claims), a token on
  every endpoint, a `datasets` table, the asynchronous train contract, the cut line
  (CI/LICENSE/docs) and a full week. That re-scoped week 1 from "honest + demo" to the eight
  phases above and pulled `FOLLOWUP_PLAN.md` phases 6, 7, 8, 9 and 10 into the week.
- Rejected ideas, so nobody reopens them blindly: keeping the anonymous fallback "for
  convenience" (it is a working credential for a shared bucket); storing the dataset bytes in the
  database (a full-table scan per read on Postgres); a client-supplied dataset path with a filter
  (the filter is the vulnerability).
- W1-4, round 1 (2026-10-22): the registry shipped with the review of the phase. The review
  found that the contract had broken the Hugging Face mode and the reinforcement learning models
  (every request had to carry a dataset), that the upload left the client with the label column
  of the previous dataset, that the body was read into the memory before the limit was checked,
  that the limit on the rows was never read, that a refused upload left its file on the disk, and
  that the upload had no rate limit. All fixed, with a test for each.
- W1-4, round 2 (2026-10-22): the second review found four ways to make the server answer with
  a 500 (a field the csv parser refuses, a name of multi-byte characters that is too long for
  the file system, a broken file in `data/` that stopped the startup, and an upload whose body
  was spooled to the disk before the limit was checked), and that the uniqueness of the name was
  only checked in the application, so two uploads of the same name that arrived at the same time
  both got it. The name is unique in the database now, the body of an upload is refused before it
  is read, and the startup skips a file it cannot read instead of stopping.
- W1-5 (2026-10-22): the training does not run inside the request any more. The request creates
  the row, answers with the id of the run and queues the training in the background; the worker
  has its own session, writes `running` when it takes the run and `completed`/`failed` at the
  end; a failure is written in the run, because the request was answered long ago and the run is
  the only channel the client has left; the lifespan fails the runs that a restart interrupted,
  so a run cannot stay in a state that never changes; the artifact of a run has a name of its
  own (microseconds and a random suffix), because two runs that start in the same second wrote
  over each other's artifact; the details view of the frontend polls the run every two seconds
  and stops when the run is finished. Four tests that pinned the synchronous contract were
  rewritten (the result is read from the run) and seven tests of the asynchronous lifecycle were
  added. The plan said the row is created `running`; it is created `queued` and the worker sets
  it `running` - the state of the row has to be the state of the work.
- W1-4, round 2, the suite of the documented installation: the installer installs torch, and with
  torch the suite showed nine failures that the review had found before: the network of the torch
  trainer was defined inside the function, so its artifact could not be loaded back, and the test
  of the vision models used empty class directories. Both are fixed, so the numbers of this
  repository are the numbers of a fresh clone.

## N. Approval record

- Readiness checklist: every breaking change is isolated in its own commit; every risk has a
  mitigation; the three pinned tests that change meaning are inverted or rewritten, not deleted;
  the schema check turns a missing migration into a loud, actionable failure.
- Accepted risks: R2 (the honest catalog is smaller).
- Operator approval: 2026-10-22 — "write the plan and other .md files and start coding".
