# ALL-of-ML

A web application for training, comparing and querying machine-learning models without writing
code. You choose a dataset, a model and a training mode; the application trains it, checks the
result against a baseline (doing nothing), and lets you ask the trained model for predictions.

The catalogue of models, and the rules for describing what each one can do honestly, are in
[`docs/MODEL_TIERS.md`](docs/MODEL_TIERS.md).

## What is in the repository

- `backend/`: a FastAPI application, a training worker, and Alembic migrations. Python.
- `frontend/`: a React and Vite application that talks to the backend. The interface has a dark
  and a light theme.
- `data/`: sample datasets committed for the built-in examples.
- `scripts/`: installers for the Python and Node dependencies.
- `docs/`: guides, plans and the review records of the work.
- `docs/cicd/`: the specification for continuous integration, delivery and the repository rules.

## Quick start (development)

You need Python, Node.js 22, and `uv` (installed by `scripts/install.sh` if missing).

    scripts/install.sh --backend      # Python dependencies in .venv/ (add --cpu for the CPU build of torch)
    cd backend
    ../.venv/bin/python -m alembic upgrade head
    ../.venv/bin/python -m uvicorn app.main:app --port 8010 --reload

In a second terminal:

    cd frontend
    npm install
    npm run dev          # http://localhost:3000

The frontend calls the API at `http://localhost:8010`. That address is set in the code for now;
see [`docs/cicd/SPEC.md`](docs/cicd/SPEC.md), blocker B1.

Create the first administrator with `python -m backend.app.admin create-admin <username>` (see
[`docs/OPERATOR_GUIDE.md`](docs/OPERATOR_GUIDE.md)).

## Tests and checks

    .venv/bin/python -m pytest backend/tests      # backend (after scripts/install.sh --backend --dev)
    cd frontend && npm test                       # frontend unit and component tests
    cd frontend && npm run build                  # production build

Continuous integration runs the backend tests, the migration check, and the frontend build. The
frontend tests are being added to CI; see the specification.

## Deployment

The stack is described by `docker-compose.yml` (PostgreSQL, the API, a worker). It is not yet
deployable as written; the blockers are listed in [`docs/cicd/SPEC.md`](docs/cicd/SPEC.md),
section 2. The operator's procedure is in [`docs/OPERATOR_GUIDE.md`](docs/OPERATOR_GUIDE.md).

## Documentation

| Document | For |
|---|---|
| [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) | people who use the interface |
| [`docs/OPERATOR_GUIDE.md`](docs/OPERATOR_GUIDE.md) | people who run a deployment |
| [`docs/MODEL_TIERS.md`](docs/MODEL_TIERS.md) | what each model in the catalogue can honestly do |
| [`docs/cicd/SPEC.md`](docs/cicd/SPEC.md) | continuous integration, delivery and repository rules |
| [`docs/cicd/RELEASING.md`](docs/cicd/RELEASING.md) | how a version is released and rolled back |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | how to propose a change |
| [`SECURITY.md`](SECURITY.md) | how to report a vulnerability |

## Licence

See [`LICENSE`](LICENSE).
