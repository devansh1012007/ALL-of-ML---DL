# Changelog

All notable changes to the repository are recorded here, newest first. Versions follow
semantic versioning and the procedure in [`docs/cicd/RELEASING.md`](docs/cicd/RELEASING.md);
a tag is never moved or reused.

## [0.1.0] - unreleased

The first tagged release. What ships:

- The application: the FastAPI backend (datasets, training, inference, quotas, admin), the
  training worker, the Alembic migrations, and the React single-page frontend (dark and light
  themes).
- The deployment stack: `docker-compose.yml` (PostgreSQL, the API, a worker) with the
  `docker-compose.prod.yml` overlay (a pulled, tagged image) and the root `.env.example`.
- CI (`.github/workflows/ci.yml`): backend tests and migration check on SQLite, frontend tests
  and build, a manual-only Postgres job, report-only lint, the image build with compose
  validation, and the container smoke test against `/healthz`.
- Security (`.github/workflows/security.yml`, `.github/dependabot.yml`): CodeQL on both code
  languages, dependency review on pull requests, the gitleaks secret scan, pip-audit and
  npm audit, and Dependabot updates for pip, npm, actions and docker.
- Release automation (`.github/workflows/release.yml`): a `v*.*.*` tag runs the full CI, pushes
  the backend image to GHCR (version, minor and SHA tags, with SBOM and provenance) and attaches
  the frontend archive to a GitHub Release with generated notes.

Configuration for operators: see `docs/OPERATOR_GUIDE.md`; release and rollback steps:
`docs/cicd/RELEASING.md`; the adopted decisions: `docs/cicd/DECISIONS.md`.
