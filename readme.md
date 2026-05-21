ALL-of-ML-&-DL

This repository is a curated collection of machine learning (ML), deep learning (DL), and transformer models with a web-based interface to run, compare, and manage training jobs. The project is designed to be highly customizable and extensible — include or remove models, change hyperparameters, and run training in different modes (manual, auto-tune, auto-fine-tune, LLM fine-tune, auto-search).

Repository structure

- `backend/` - FastAPI backend, model training orchestration, dataset utilities, and database migrations
	- `app/` - Main FastAPI app and training logic
- `frontend/` - React single-page app (Vite) for job submission, catalog browsing, and run history
- `requirements.txt` - Python dependencies for backend
- `readme.md` - This document

Features

- 32+ model catalog entries (tabular, vision, NLP, time-series, RL, clustering)
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

The frontend (Vite) will default to port 5173 and talk to the backend on port 8010. Adjust CORS settings in `backend/app/main.py` if necessary.

How to Use (step-by-step)

1. Open the frontend in your browser (usually `http://localhost:5173`).
2. Register or log in using the app auth UI (the backend includes JWT authentication endpoints).
3. Navigate to "New Training Job".
	 - Choose data source: a) Local CSV dataset detected in `data/` or b) Hugging Face dataset reference.
	 - Select the model architecture from the catalog.
	 - Choose a training mode:
		 - `manual` — you provide all hyperparameters.
		 - `auto_tune` — grid-search style automated tuning.
		 - `auto_fine_tune` — conservative fine-tuning with reduced learning rate.
		 - `llm_fine_tune` — uses Google Gemini to suggest hyperparameters (requires `GOOGLE_API_KEY`).
		 - `auto_search` — searches across a set of candidate models and returns the best.
	 - Choose a preset: `conservative`, `balanced`, or `aggressive` to quickly adjust common hyperparameters.
4. Fill in target label column, train/test split, and any model-specific fields (e.g., `env_id` for RL agents).
5. Submit the job. The backend will schedule and run training and return metrics and artifact paths when complete.
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

I'll provide a simple `Dockerfile` (backend) and `docker-compose.yml` to run the backend + frontend together.

1. Build and run using Docker Compose

```bash
# From repository root
docker-compose up --build
```

2. Access the app
- Frontend: http://localhost:5173
- Backend API: http://localhost:8010

Docker Compose notes

- The compose file mounts local code into containers for live development by default. For production, remove mounts and build image artifacts.
- To use Google Gemini inside Docker, set `GOOGLE_API_KEY` in the environment section of `docker-compose.yml`.

Example docker-compose snippet

```yaml
version: '3.8'
services:
	backend:
		build: ./backend
		ports:
			- '8010:8010'
		environment:
			- GOOGLE_API_KEY=${GOOGLE_API_KEY}
		volumes:
			- ./backend:/app
		command: uvicorn app.main:app --host 0.0.0.0 --port 8010 --reload

	frontend:
		build: ./frontend
		ports:
			- '5173:5173'
		volumes:
			- ./frontend:/app
		command: sh -c "npm install && npm run dev -- --host 0.0.0.0"
```

Troubleshooting

- If the frontend cannot reach the backend, ensure the backend is running and CORS is enabled for the frontend origin in `backend/app/main.py`.
- If LLM suggestions fail, ensure `google-generativeai` is installed and `GOOGLE_API_KEY` is set and valid.
- For permission issues on Windows with file mounting, run Docker Desktop with sufficient permissions and use absolute paths.

Contributing

Feel free to add new model definitions under `DL_models/` or `ML_models/` and update the `MODEL_CATALOG` in `backend/app/model_training.py`.

When adding new models:
1. Add a model entry in `MODEL_CATALOG` with `params`, `optimization`, and `test_results` metadata.
2. Implement training helper functions if the model requires custom data pipelines (e.g., image loaders for vision models).
3. Add frontend card metadata if you want special UI behavior.

License

This repo is for personal use. Add a license file if you plan to open-source it.

---
If you'd like, I can also commit a `docker-compose.yml` and a minimal `Dockerfile` for backend and frontend — want me to add those now?

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


