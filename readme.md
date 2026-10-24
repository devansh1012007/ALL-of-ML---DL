ALL-of-ML-&-DL

This repository is a curated collection of machine learning (ML), deep learning (DL), and transformer models with a web-based interface to run, compare, and manage training jobs. The project is designed to be highly customizable and extensible — include or remove models, change hyperparameters, and run training in different modes (manual, auto-tune, auto-fine-tune, LLM fine-tune, auto-search).

Repository structure

- `backend/` - FastAPI backend, model training orchestration, dataset utilities, and database migrations
	- `app/` - Main FastAPI app and training logic
- `frontend/` - React single-page app (Vite) for job submission, catalog browsing, and run history
- `requirements.txt` - Python dependencies for backend
- `readme.md` - This document

Features

- 38 model catalog entries (tabular, vision, NLP, time-series, RL, clustering)
- Training modes: `manual`, `auto_tune`, `auto_fine_tune`, `llm_fine_tune`, `auto_search`
- Training presets: `conservative`, `balanced`, `aggressive` for quick hyperparameter adjustments
- LLM-guided hyperparameter suggestions (Google Gemini integration)
- Model intelligence metadata (expected performance ranges, training time estimates, scalability)
- Frontend UI for creating training jobs and visualizing run results

Quickstart (local development)

Prerequisites
- Python 3.9+ (3.11/3.12 recommended)
- Node.js 16+ (for frontend)
- Docker & Docker Compose (optional — recommended for isolated setup)

1. Clone the repo

```bash
git clone "<your-repo-url>"
cd "ALL-of-ML-&-DL"
```

2. Backend - create virtual environment and install dependencies

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# or cmd
.\.venv\Scripts\activate.bat
pip install -r backend/requirements.txt
```

3. Frontend - install npm dependencies and run

```bash
cd frontend
# using npm
npm install
npm run dev

# or using yarn
yarn
yarn dev
```

4. Run the backend API

```bash
cd ../backend
uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload
```

The frontend (Vite) will default to port 3000 and talk to the backend on port 8010. Adjust CORS settings in `backend/app/main.py` if necessary.

How to Use (step-by-step)

1. Open the frontend in your browser (usually `http://localhost:3000`).
2. Register or log in using the app auth UI (the backend includes JWT authentication endpoints).
   Every ML endpoint requires a token; there is no anonymous access.
3. Navigate to "New Training Job".
   - Pick a dataset from the dropdown (`GET /api/v1/ml/datasets`). Datasets are rows of the
     server-side registry: the built-in sample CSVs plus the CSVs you uploaded through
     `POST /api/v1/ml/datasets/upload` (comma-separated CSV only, size/row/column limits apply).
     Send the dataset as `dataset_id` (or `dataset_name`, a lookup in the same registry); the
     server resolves the row to a path under `DATASETS_ROOT` — the client never sends a file path.
   - Select the model architecture from the catalog. Entries flagged "Not implemented" cannot be
     trained (they advertise a model no trainer builds yet).
   - Choose a training mode:
     - `manual` — you provide all hyperparameters.
     - `auto_tune` — randomized hyperparameter search over a curated per-model space; reports
       `best_params` and a search summary.
     - `auto_fine_tune` — local hyperparameter search around the current configuration.
     - `llm_fine_tune` — uses Google Gemini to suggest hyperparameters (requires `GOOGLE_API_KEY`
       and the `google-generativeai` package).
     - `auto_search` — model selection over multiple candidates (not Bayesian optimization).
   - Choose a preset: `conservative`, `balanced`, or `aggressive` to quickly adjust common hyperparameters.
4. Fill in target label column, train/test split, and any model-specific fields (e.g., `env_id` for RL agents).
5. Submit the job. Training runs in the background: the backend answers immediately with a `run_id`
   and the run status (`queued` → `running` → `completed`/`failed`). Poll `GET /api/v1/ml/runs/{run_id}`
   for the metrics and the trained artifact.
6. Check run history under "Runs" to download trained model artifacts or review logs and metrics.

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

Docker setup (recommended)

The compose file lives at `backend/docker-compose.yml` (not at the repository root). Run it from
the `backend/` directory:

```bash
cd backend
docker-compose up --build
```

The compose file mounts local code into containers for live development by default and runs the
migrations (`alembic upgrade head`) before the server. For production, remove mounts and build
image artifacts. To use Google Gemini inside Docker, set `GOOGLE_API_KEY` in the environment
section of `backend/docker-compose.yml` (or via `env_file`).

Access the app:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8010

The backend must be started and CORS must allow the frontend origin in `backend/app/main.py`.

Troubleshooting

- If the frontend cannot reach the backend, ensure the backend is running and CORS is enabled for the frontend origin in `backend/app/main.py`.
- If LLM suggestions fail, ensure `google-generativeai` is installed and `GOOGLE_API_KEY` is set and valid.
- For permission issues on Windows with file mounting, run Docker Desktop with sufficient permissions and use absolute paths.

Contributing

Feel free to add new model entries to `MODEL_CATALOG` in `backend/app/model_training.py`
and update this document when behaviour or interfaces change.

When adding new models:
1. Add a model entry in `MODEL_CATALOG` with `category`, `description`, `params`, `optimization`,
   `test_results` (or `planned_test_results` for a placeholder), and an `implemented` flag.
2. If the model needs custom training logic, add a branch to the category router in `train_model()`
   (`backend/app/model_training.py`) and register its category in `CATEGORY_TO_TRAINER`.
3. Keep `EXPECTED_CATEGORY_BY_MODEL` in `backend/tests/test_catalog_params.py` in sync with the catalog.

License

This repo is for personal use. Add a license file if you plan to open-source it.


## Available Models

The repository includes the following models in the `MODEL_CATALOG`:

- K-Mean
- HMM_timeseries
- GMM
- Hierarchical_Clustering
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
- Q-Learning
- Autoencoder
- BERT2BERT
- self-attenetion_transformer
- seq2seq
- UL2
- GNN
- BERT
- DistilBERT
- GPT
- LLaMA
- LSTM
- MiniLM
- ResNet
- ResNet50
- RNN
- SSM_timeseries
- TCN_timeseries
- ViT


