# FIX_PLAN — bug fix plan for ALL-of-ML---DL

Status: **implemented** (phases 1-4 done + reviewed; phase 5 reviews done) · Baseline measured on 2026-10-20 (commit `d4b397c` + untracked `AGENTS.md`) · Baseline was `4 failed, 5 passed` → now `102 passed, 9 skipped`.

## Baseline (measured, not assumed)

`python -m pytest backend/tests` from the repo root, using an isolated venv
(`/tmp/opencode/verify-venv`: fastapi 0.152, starlette 1.9, sqlalchemy 2.1.5, scikit-learn 1.9.1,
xgboost 3.4.1, lightgbm 4.7.0, catboost 1.2.10, pandas 3.0.6, httpx 0.28.1, pytest 9.1.1):

```
FAILED backend/tests/test_main.py::test_get_ml_models              - sqlalchemy.exc.OperationalError: no such table: users
FAILED backend/tests/test_main.py::test_get_datasets               - sqlalchemy.exc.OperationalError: no such table: users
FAILED backend/tests/test_main.py::test_train_invalid_dataset       - sqlalchemy.exc.OperationalError: no such table: users
FAILED backend/tests/test_model_training.py::test_train_model_auto_fine_tune_tabular
                                                                       - TypeError: LogisticRegression.__init__() got an unexpected keyword argument 'test_size'
4 failed, 5 passed
```

**Headline bug:** every sklearn tabular model (Random_Forest, Logistic_Regression, MLR, KNN, SVM) is
untrainable — from the UI *and* from the API — because catalog `params` are splatted straight into the
estimator constructor. Only the clustering models and the torch/transformer paths can train today.

## Root causes (evidence-backed)

| # | Root cause | Evidence |
|---|---|---|
| R1 | `MODEL_CATALOG[...]["params"]` contains trainer-level keys (`test_size`) and estimator-invalid keys (`random_state` for `LinearRegression`/`KNeighbors*`, `probability` for `SVC`/`SVR`) and they are splatted into the estimator | `model_training.py:242,261,274,292,313,334,355,375` → `build_model()` at `:1000-1035` |
| R2 | `SVC(probability=True, **params)` duplicates `probability` (already in SVM's params) | `model_training.py:1015` + `:310` |
| R3 | `suggest_hyperparameters()` injects `learning_rate` for every classification/regression task — invalid for all 5 sklearn estimators — and it is merged into the estimator params | `model_training.py:985-988` merged at `:1485/:1502/:1514` |
| R4 | `TestClient(app)` used without a `with` block never runs the lifespan → `startup_event` (`create_all`) never fires → `get_active_user` hits a missing `users` table | `backend/tests/test_main.py:7,14,23`; starlette runs lifespan only in `TestClient.__enter__`; `main.py:112-115`, `main.py:60` |
| R5 | Import-time blockers: `sqlalchemy` is not the `[asyncio]` extra (no `greenlet`), `aiosqlite` missing (default `DATABASE_URL` needs it), `httpx` not declared | `requirements.txt:4-5`; `database.py:5,7`; `main.py:11` |
| R6 | Catalog category strings are inconsistent (`"time-series"` vs `"timeseries"`); `train_model` routes only `{"timeseries","graph","autoencoder"}` to the torch path, so `HMM_timeseries` (category `"time-series"`, handled inside `_train_clustering`) falls into the tabular path and dies with `Unsupported model: HMM_timeseries` | `model_training.py:137` vs `:1536`, `:1064-1067`, `:1035` |
| R7 | Auth: `get_active_user` swallows `JWTError` and silently downgrades to the shared `anonymous` user → the frontend's 401→logout path is dead code and a user's runs vanish after token expiry | `main.py:42-69`; `auth.py:18` (2 h expiry) |
| R8 | `POST /api/v1/register` trusts a client-supplied `role` (privilege escalation) and has no `IntegrityError` handling (duplicate username → 500) | `main.py:71-74,117-126` |
| R9 | Frontend contract drift: mode description read from a list, `data.descriptions` discarded, "OpenAI" hardcoded although the backend uses Google Gemini; `modeDescription` is dead code | `App.jsx:539,544,751-761,890`; `main.py:180`; `model_training.py:952-983` |
| R10 | Frontend hyperparameter form cannot express the catalog values it renders: `None` defaults become text inputs submitted as strings, `step="1"` blocks fractional values (e.g. `C=0.5`) | `App.jsx:862-870` |
| R11 | Frontend hides effective parameters and prints literal `"null"` metrics; fetch errors are swallowed with `console.error` | `App.jsx:461,465,209,308,398,537-540` |
| R12 | `list_local_datasets()` globs only `data/*.csv` → vision models (image folders) are unreachable from the UI; the dataset select is `required` even for RL, which needs no dataset | `model_training.py:869-872`; `App.jsx:656-664` |

## Phases

Each phase is atomic, file-isolated (so phases can run in parallel), and independently verifiable.

### Phase 1 — Test & environment infrastructure
**Files:** `backend/requirements.txt`, `backend/tests/conftest.py` (new), `backend/tests/test_main.py`, `backend/tests/test_model_training.py`

1. `requirements.txt`: `sqlalchemy` → `sqlalchemy[asyncio]` (pulls `greenlet`), add `aiosqlite`, add `httpx`.
2. New `backend/tests/conftest.py`: set `DATABASE_URL` to an isolated sqlite file **before** the app is imported, and put the repo root on `sys.path` so both `pytest` and `python -m pytest` work.
3. `test_main.py`: use `with TestClient(app) as client:` so the lifespan runs and tables are created.
4. `test_model_training.py`: the 4-row fixture degenerates to a single-class training fold (`ValueError: This solver needs samples of at least 2 classes`) → use ≥6 rows (3 per class); keep the test's intent.
5. Add regression tests that would have caught the bugs: every `build_model`-routed catalog entry must construct; `train_model` must work for a tabular model in `manual` / `auto_tune` / `auto_fine_tune`; category→trainer routing must be asserted.

**Done when:** `python -m pytest backend/tests` → 0 failures, and the new tests fail on the pre-fix code.

### Phase 2 — Estimator-parameter validity (the headline bug)
**File:** `backend/app/model_training.py`

1. Remove `test_size` from the 8 catalog entries that route through `build_model()`; remove `random_state` from `MLR` and `KNN`; remove `probability` from `SVM`.
2. `build_model()`: drop trainer-owned keys before constructing the estimator, and stop the `SVC(probability=True, **params)` duplicate-keyword error. **Keep strict rejection of unknown keys** so typos still raise (no silent blanket signature filtering).
3. `suggest_hyperparameters()`: stop injecting `learning_rate` into models that do not declare it.
4. `HMM_timeseries` must reach its trainer: give it a category that routes to `_train_clustering`, and document the category→code-path mapping in a comment.
5. Remove the removed-in-xgboost-2.0 `use_label_encoder=False` argument.
6. `list_local_datasets()`: also list directories under `data/` so vision models are selectable.

**Done when:** all 8 tabular/boosting catalog models construct and train; no `TypeError` from catalog params; `HMM_timeseries` no longer raises `Unsupported model`.

### Phase 3 — API correctness & auth
**Files:** `backend/app/main.py`, `backend/app/auth.py`

1. `get_active_user`: an **invalid/expired** bearer token must return 401 (so the frontend logs out); **no** header keeps the current anonymous fallback (keeps the API usable unauthenticated and the existing tests valid).
2. `POST /api/v1/register`: never trust a client-supplied `role` (force `user`); duplicate username → 409 instead of 500.
3. `/api/v1/ml/training-modes`: `llm_fine_tune` description must say Google Gemini, not OpenAI.
4. `/runs` and `/runs/{id}`: return the stored `mode` (and `env_id`) so the UI can show which mode produced a run.
5. `auto_search` scoring: fall back to `r2` when `optimize_metric`/`accuracy` are absent instead of scoring every candidate 0.

**Done when:** expired token → 401; register as `admin` → role `user`; duplicate register → 409; runs expose their mode; auto_search picks the better regression candidate.

### Phase 4 — Frontend contract & UX
**File:** `frontend/App.jsx`

1. Training modes: consume `data.descriptions`; delete the dead `modeDescription`; replace the hardcoded "OpenAI" with "Google Gemini"; drive the mode `<select>` from the fetched modes.
2. Hyperparameter inputs: `None` defaults render as optional numeric inputs and are omitted when blank; `step="any"` for floats; keep values numeric.
3. Dataset select: not `required` for RL / vision models; show the backend list (now including image folders).
4. Run details: show the **effective** parameters (`metrics.model_parameters`), render `null` metrics as "—", `replaceAll` for underscore labels, surface fetch errors (no silent `console.error`), handle 404.
5. Register: friendly 409 message; handle FastAPI's 422 `detail` list.
6. `parseJwt`: base64url-safe decoding.

**Done when:** `npm run build` succeeds and each item above is demonstrably addressed.

### Phase 5 — Independent review (per phase) + final review
A reviewer subagent audits each phase's diff; findings are fixed and re-reviewed. A final reviewer audits the complete diff against this plan. Only then may the work be declared done.

## Deferred (deliberately out of scope this round)

- **Async training** (`POST /api/v1/ml/train` trains synchronously inside the request → the UI blocks for the whole run and a proxy timeout leaves the run stuck in `running`). Fix = `BackgroundTasks` + status polling in the frontend; it changes the API contract and requires rewriting `test_train_invalid_dataset`. Planned as its own phase after Phases 1-4 are green.
- **Alembic drift**: the migrations create `notes` and never `training_runs`, so `alembic upgrade head` yields an unusable schema (the app relies on `create_all`). Needs a new revision.
- **`@app.on_event("startup")` deprecation** → migrate to a `lifespan` handler.
- **Security posture**: hardcoded `SECRET_KEY`, `allow_origins=["*"]` + `allow_credentials=True`, CORS wildcard, anonymous fallback by design.
- **Fake model implementations**: `timeseries`/`graph`/`autoencoder` all route to one plain MLP; `Q-Learning` is a stub; the vision path only implements ResNet.
- **Repo hygiene**: `models/` **done** (added to `.gitignore`); still open — point the `app.log` handler at a fixed path; `readme.md` corrections (port 3000, compose location, `ML_models/` removal, stray LLM paragraph).
- **`write_artifact` filename resolution** is 1 second, so two runs of the same model within a second overwrite each other.
- **Clustering candidates cannot be ranked**: `score_candidate` returns `0.0` for clustering metrics (`cluster_count`/`sample_count`), so `auto_search` keeps the first candidate in that category.

## Verification

- Backend: `python -m pytest backend/tests` from the repo root, in an isolated venv.
- Frontend: `cd frontend && npm install && npm run build`.
- Manual: backend on `:8010`, frontend on `:3000`; train a tabular model end-to-end through the UI.
