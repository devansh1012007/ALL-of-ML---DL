ALL-of-ML-&-DL

This repository is a curated collection of machine learning (ML), deep learning (DL), and transformer models with a web-based interface to run, compare, and manage training jobs. The project is designed to be highly customizable and extensible — include or remove models, change hyperparameters, and run training in different modes (manual, auto-tune, auto-fine-tune, LLM fine-tune, auto-search).

Repository structure

- `backend/` - FastAPI backend, model training orchestration, dataset utilities, and database migrations
	- `app/` - Main FastAPI app and training logic
	- `migrations/` - Alembic migrations (the only schema owner)
- `frontend/` - React single-page app (Vite) for job submission, catalog browsing, and run history
- `data/` - The CSV files that ship with the repository (built-in datasets)
- `scripts/` - `install.sh` and `download.sh` (resumable installers)
- `models/` - Trained model artifacts (git-ignored, do not commit)
- `readme.md` - This document
- `AGENTS.md` - The mandatory engineering workflow for this repository

Features

- 38 model catalog entries (tabular, vision, NLP, time-series, RL, clustering)
- Training modes: `manual`, `auto_tune`, `auto_fine_tune`, `llm_fine_tune`, `auto_search`
- Training presets: `conservative`, `balanced`, `aggressive` for quick hyperparameter adjustments
- LLM-guided hyperparameter suggestions (Google Gemini integration)
- Model intelligence metadata (expected performance ranges, training time estimates, scalability)
- Dataset registry: one row per usable dataset, addressed by `dataset_id` (the client never sends a file path)
- Asynchronous training: a job answers immediately with a `run_id`, and the client polls its status
- Frontend UI for creating training jobs and visualizing run results
- GitHub Actions CI

Quickstart (local development)

Prerequisites
- Python 3.12 (3.11+ minimum; `pandas 3` needs 3.11+, `numpy 2` needs 3.12+)
- Node.js 18+ (`vite ^5.4.1` requires `^18 || >=20`)
- `uv` (https://docs.astral.sh/uv/getting-started/installation/) for the Python side
- `npm` for the frontend
- Docker & Docker Compose (optional — recommended for isolated setup)

1. Clone the repo

```bash
git clone "<your-repo-url>"
cd "ALL-of-ML-&-DL"
```

2. Install the dependencies

The repository ships `scripts/install.sh`, a resumable installer whose downloads continue where they stopped and whose cache lives in `.cache/`:

```bash
# Everything: the Python backend and the Node frontend
scripts/install.sh --backend --frontend

# Only the Python backend (with the small CPU build of torch)
scripts/install.sh --backend --cpu

# Only the Node frontend
scripts/install.sh --frontend
```

`--backend` creates the virtual environment `.venv` at the repository root (Python 3.12) and installs `backend/requirements.txt`. `--dev` additionally installs `pytest`, `pytest-asyncio`, `httpx` and `ruff`; `--optional` installs `google-generativeai` (the LLM fine-tuning mode fails with an explicit message when it is missing). The installer retries generously and resumes interrupted downloads.

3. Migrate the database first

The schema is owned by Alembic, and the application refuses to start on an unmigrated database:

```bash
cd backend && ../.venv/bin/python -m alembic upgrade head
```

4. Run the backend API

```bash
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

The backend listens on **http://localhost:8010**. Every ML endpoint requires a valid token; there is no anonymous access.

5. Run the frontend

```bash
cd frontend && npm run dev
```

The frontend listens on **http://localhost:3000** (`frontend/vite.config.js` sets `server.port: 3000`) and talks to the backend on port 8010. Add your origin to `CORS_ORIGINS` if you serve the SPA elsewhere.

Environment variables

The application is configured through environment variables (read before the app is importable; `python-dotenv` is declared but nothing calls `load_dotenv`, so export them yourself):

| Variable | Meaning | Default |
|---|---|---|
| `DATABASE_URL` | Database URL, also used by Alembic | `sqlite+aiosqlite:///./backend.db` |
| `SECRET_KEY` | JWT signing key. Required in production (`APP_ENV=production`); in development a random key is generated once into `.secret_key` (git-ignored) | random per process |
| `SECRET_KEY_FILE` | Path of the development key file | current directory / `.secret_key` |
| `CORS_ORIGINS` | Comma-separated allow-list of origins the SPA may call from a browser | `http://localhost:3000`, `http://127.0.0.1:3000` |
| `APP_ENV` / `ENVIRONMENT` | `production` makes a missing `SECRET_KEY` a hard startup error | `development` |
| `DATASETS_ROOT` | Directory every dataset is read from; `data/` holds the built-ins, `uploads/` the user uploads | repository root |
| `GOOGLE_API_KEY` | Key for LLM-guided hyperparameter suggestions (Google Gemini) | unset |
| `GOOGLE_MODEL` | Gemini model used by `llm_fine_tune` | `gemini-pro` |

The upload limits (`MAX_UPLOAD_BYTES` 50 MiB, `MAX_UPLOAD_ROWS` 2 000 000, `MAX_UPLOAD_COLUMNS` 1000, `MAX_REPORTED_COLUMNS` 200, `MAX_FILE_NAME_BYTES` 200) and `UPLOAD_RATE_LIMIT` (20 uploads per minute and per client address) are declared in `backend/app/datasets.py` and `backend/app/main.py`.

How to Use (step-by-step)

1. Open the frontend in your browser (usually `http://localhost:3000`).
2. Register or log in using the app auth UI (the backend includes JWT authentication endpoints). Every ML endpoint requires a token; there is no anonymous access.
3. Navigate to "New Training Job".
   - Pick a dataset from the dropdown (`GET /api/v1/ml/datasets`). Datasets are rows of the server-side registry: the built-in sample CSVs plus the CSVs you uploaded through `POST /api/v1/ml/datasets/upload` (comma-separated CSV only, size / row / column limits apply). Send the dataset as `dataset_id` (or `dataset_name`, a lookup in the same registry); the server resolves the row to a path under `DATASETS_ROOT` — the client never sends a file path.
   - Select the model architecture from the catalog. Entries flagged "Not implemented" cannot be trained (they advertise a model no trainer builds yet).
   - Choose a training mode:
     - `manual` — you provide all hyperparameters.
     - `auto_tune` — randomized hyperparameter search over a curated per-model space; reports `best_params` and a search summary.
     - `auto_fine_tune` — local hyperparameter search around the current configuration.
     - `llm_fine_tune` — uses Google Gemini to suggest hyperparameters (requires `GOOGLE_API_KEY` and the `google-generativeai` package).
     - `auto_search` — model selection over multiple candidates (not Bayesian optimization).
   - Choose a preset: `conservative`, `balanced`, or `aggressive` to quickly adjust common hyperparameters.
4. Fill in target label column, train/test split, and any model-specific fields (e.g., `env_id` for RL agents).
5. Submit the job. Training runs in the background: the backend answers immediately with a `run_id` and the run status (`queued` → `running` → `completed`/`failed`). Poll `GET /api/v1/ml/runs/{run_id}` for the metrics and the trained artifact.
6. Check run history under "Runs" to download trained model artifacts or review logs and metrics.

Dataset registry and upload

A dataset is a **row of the `datasets` table**, not a path:
- The built-in `data/*.csv` files are seeded as rows at startup (they belong to everybody).
- `POST /api/v1/ml/datasets/upload` stores a user upload under `DATASETS_ROOT/uploads/<user id>/<uuid>_<name>.csv` and gives it an owner.
- `GET /api/v1/ml/datasets` lists the datasets the caller can train on (columns, row count, suggested label column); `GET /api/v1/ml/datasets/{id}` is the detail.
- An upload is a comma-separated CSV file: a non-CSV, a file with less than two columns, or a file without rows is refused with a 400. The body is read and confined by the `UploadSizeLimit` ASGI middleware **before** it reaches the framework, so an oversized file is refused with a 413 before a byte is written to disk, and the read happens only after the token was checked.
- `resolve_storage_path()` refuses an absolute path, a `..`, and a symlink that points out of the datasets root — a dataset path outside the configured root cannot be trained, by construction.

Training modes

- `manual`: the client's hyperparameters are applied exactly as sent (the preset still scales them once).
- `auto_tune`: a randomized hyperparameter search (`RandomizedSearchCV`, `n_iter = min(12, combinations)`, `cv = 3` with a `cv = 2` fallback on small folds, scoring accuracy for classification and `r2` for regression) over the model's curated `search_space`; reports `best_params` as `metrics["model_parameters"]` and `metrics["search_results"]`. Client-pinned keys are sampled out of the space and still win.
- `auto_fine_tune`: the same search engine restricted to a neighbourhood of the base configuration.
- `llm_fine_tune`: Google Gemini proposes values, each validated against the model's space; requires `google-generativeai` and `GOOGLE_API_KEY`, and fails fast with an actionable message when either is missing.
- `auto_search`: trains every candidate the client sends and keeps the best one (model selection, not Bayesian optimization).

Configuring LLM (Google Gemini) for hyperparameter suggestions

To use LLM-guided tuning you must set the `GOOGLE_API_KEY` environment variable. Install the `google-generativeai` package in the backend venv:

```bash
pip install google-generativeai
```

Then set the key in your shell or Docker environment:

```bash
export GOOGLE_API_KEY="YOUR_KEY"     # Linux / macOS
setx GOOGLE_API_KEY "YOUR_KEY"       # Windows (PowerShell: setx)
```

Optionally set `GOOGLE_MODEL` to an available Gemini model (defaults to `gemini-pro`).

CI

The repository is tested on GitHub Actions (`.github/workflows/ci.yml`) on every push and pull request: it installs the Python and Node dependencies with `scripts/install.sh`, migrates the database (`alembic upgrade head`), verifies there is no migration drift (`alembic check`), runs `pytest backend/tests`, and builds the frontend (`npm run build`).

Docker setup (recommended)

The compose file lives at `backend/docker-compose.yml` (not at the repository root). Run it from the `backend/` directory:

```bash
cd backend
docker-compose up --build
```

The compose file mounts local code into containers for live development by default, runs the migrations (`alembic upgrade head`) before the server, and needs `backend/.env` (git-ignored; `backend/.env.example` documents every variable) with `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_HOST_PORT`, `POSTGRES_PORT`, `DATABASE_URL` (in compose, `DATABASE_URL` must point at the `db` service, not localhost) plus `SECRET_KEY` and `CORS_ORIGINS`.

Access the app:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8010

Troubleshooting

- If the frontend cannot reach the backend, ensure the backend is running and your origin is in `CORS_ORIGINS`.
- If the backend refuses to start, run `cd backend && ../.venv/bin/python -m alembic upgrade head` first: the schema is owned by Alembic and the app verifies it at startup.
- If LLM suggestions fail, ensure `google-generativeai` is installed and `GOOGLE_API_KEY` is set and valid.
- For permission issues on Windows with file mounting, run Docker Desktop with sufficient permissions and use absolute paths.

Contributing

Feel free to add new model entries to `MODEL_CATALOG` in `backend/app/model_training.py` and update this document when behaviour or interfaces change. Every change carries `PLAN:week1:<ID>` in its commit message so any line can be traced back to its reason; see `AGENTS.md` for the mandatory engineering workflow.

When adding new models:
1. Add a model entry in `MODEL_CATALOG` with `category`, `description`, `params`, `optimization`, `test_results` (or `planned_test_results` for a placeholder), and an `implemented` flag.
2. If the model needs custom training logic, add a branch to the category router in `train_model()` (`backend/app/model_training.py`) and register its category.
3. Run `python -m pytest backend/tests` and `cd frontend && npm run build`.

License

This repository is released under the [MIT License](LICENSE).

## Available Models

The repository includes the following 38 models in the `MODEL_CATALOG` (25 implemented, 13 placeholders marked "Not implemented" in the UI):

- K-Mean
- HMM_timeseries
- GMM
- Hierarchical_Clustering
- PCA
- t-SNE
- UMAP
- DBSCAN
- HDBSCAN
- Random_Forest
- Logistic_Regression
- MLR
- KNN
- SVM
- XGboost_timeseries
- lightGBM_timeseries
- CATboost_timeseries
- PPO
- DQN
- Q-Learning (not implemented)
- Autoencoder (not implemented)
- BERT2BERT (not implemented)
- self-attenetion_transformer
- seq2seq (not implemented)
- UL2 (not implemented)
- GNN (not implemented)
- BERT
- DistilBERT
- GPT (not implemented)
- LLaMA (not implemented)
- LSTM (not implemented)
- MiniLM
- ResNet
- ResNet50
- RNN (not implemented)
- SSM_timeseries (not implemented)
- TCN_timeseries (not implemented)
- ViT (not implemented)
