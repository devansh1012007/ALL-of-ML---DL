# Contributing

Thank you for looking at this. The rules below are what the repository's checks enforce or what
the maintainer expects; where a check does not exist yet, the rule says so.

## Set up

    scripts/install.sh --backend --dev     # Python dependencies, including the test tools
    cd frontend && npm install

The proposed CI uses Node.js 22. The Python version is the one `uv` selects; the two Dockerfiles
currently use different versions (SPEC, blocker B3).

## Before you open a pull request

Run what your change touches:

- backend: `.venv/bin/python -m pytest backend/tests`
- schema: `cd backend && ../.venv/bin/python -m alembic check` (see the migrations rules below)
- frontend: `cd frontend && npm test && npm run build`
- workflow files: `actionlint` on the changed files, if you have it installed

CI runs the backend tests, the migration check and the frontend build on every pull request. The
frontend tests join CI when the specification's phase P2 is done.

## Branches and commits

- Branch names: `feature/<short-name>`, `fix/<short-name>`, `docs/<short-name>`.
- Open a pull request into `main`. Do not push to `main` directly once branch protection is on.
- Commit messages: `type(scope): summary`, with types such as `feat`, `fix`, `docs`, `test`,
  `ci`, `chore`. The history contains other styles; new commits should follow this one.

## Migrations

- A model change needs a migration in the same pull request.
- Never edit a migration that has been applied anywhere.
- Prefer additive changes. A removal or a rename is split over two releases (see
  `docs/cicd/RELEASING.md`).

## Secrets and data

- Never commit `.env`, `.secret_key`, anything under `models/`, or user uploads. They are in
  `.gitignore`; The proposed security workflow scans the history for secrets as well.
- Do not put real credentials in examples or tests.

## Pull request contents

Use the pull request template. State what changed, how you tested it, what could go wrong, and how
to roll it back. If the change belongs to a numbered wave in `docs/agent-ops/`, link its report.

## Review

Every change is reviewed before it is merged. The maintainer's review records live in
`docs/agent-ops/`. An approval from a reviewer is required once branch protection is on
(SPEC SET-1).
