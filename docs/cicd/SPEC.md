# CI/CD and repository specification

Status: proposal. Nothing in this document is active until a file is moved into place and a
repository setting is changed. The proposed files are in `docs/cicd/proposed/`.

Verified against `origin/main` at `ca3f917` (PR #2 merged). Every statement about the repository
below was checked by reading the files or running the command named next to it. Anything that
was not run is marked **unverified**.

Owner of decisions: the repository owner (section 12 lists them). Process: `docs/agent-ops/` is
the owner's review process; this spec does not replace it (section 11).

---

## 1. What is in place today

| Area | State on `origin/main` | Evidence |
|---|---|---|
| CI | One workflow, `.github/workflows/ci.yml`. One job: install backend and frontend, `alembic upgrade head`, `alembic check`, `pytest backend/tests`, `npm run build`. | the file |
| CI triggers | Pushes to `main` and to `feature/week1-honest-demo`; pull requests to `main`. The named feature branch is no longer in use. | the file, `on:` block |
| Frontend tests in CI | **Not run.** CI builds the frontend and never runs `npm test`. | the file |
| Frontend tests | 170 tests in 11 files, all passing. | run this session: `npm test` in a clean checkout, 170 passed, exit 0 |
| Backend tests | 345 test functions found by grep. **Unverified:** not run this session, because the install pulls torch. | `git grep` count |
| Frontend build | Passes. | run this session: `npm run build`, exit 0 |
| Postgres in CI | None. CI runs the suite on SQLite. | the `ci.yml` comment |
| Images | Root `Dockerfile` (python 3.12-slim, backend only). `backend/dockerfile` (python 3.11-slim, a different image). | both files |
| Compose | Root `docker-compose.yml`: `db` (postgres 16), `api`, `worker`. `backend/docker-compose.yml`: a separate development stack (postgres 15, `--reload`). | both files |
| CD | **None.** No image is published, no release is created, nothing is deployed. | no workflow file for it |
| Security tooling | None: no CodeQL, no secret scanning in CI, no dependency review, no Dependabot config. | absence in `.github/` |
| Repository files | No `README.md`, no `CONTRIBUTING.md`, no `SECURITY.md`, no `CODEOWNERS`, no pull-request template, no `.dockerignore`, no lint or format configuration (`pyproject.toml`, `ruff.toml`, ESLint config). | `git ls-tree` |
| Operator docs | `docs/OPERATOR_GUIDE.md` describes the deployment start and backups. | the file |

## 2. Blockers

Nothing below can be deployed until these are fixed. Items B1 to B5 also make the CI proposal
honest. Each item lists the evidence and the fix.

**B1. The frontend cannot point at any API but localhost.** `frontend/components/shared.jsx:6`
sets `export const API_BASE = 'http://localhost:8010';`. A static build of the frontend therefore
calls the developer's own machine. Fix: read `import.meta.env.VITE_API_BASE`, keep
`http://localhost:8010` as the default, document the variable. On the backend the origin is
already configurable: `CORS_ORIGINS` (read in `backend/app/config.py:131`, default localhost),
so the frontend origin only needs to be added to that variable.

**B2. The root compose stack fails at its first step.** The `api` service runs
`alembic upgrade head` from `/app`. The Dockerfile copies `backend/` to `/app/backend`, so
`alembic.ini` is at `/app/backend/alembic.ini`, not in the working directory. Reproduced in a
directory without `alembic.ini`: `FAILED: No 'script_location' key found in configuration.` The
same command appears in `docs/OPERATOR_GUIDE.md` ("docker compose exec api alembic upgrade
head"), so the documented start fails too. Fix: `alembic -c backend/alembic.ini upgrade head`
(the `script_location` in that file is `%(here)s/migrations`, so it resolves from the file's own
directory). **Unverified** end to end: the reproduction used the alembic CLI, not the container.

**B3. Two images and two compose stacks disagree.** Root `Dockerfile`: python 3.12, no
`libgomp1`. `backend/dockerfile`: python 3.11, installs `libgomp1` and `libssl-dev`, with the comment
"required by ML libraries (LightGBM, XGBoost, etc.)". Root compose uses the first, `backend/docker-compose.yml` uses the second.
Whether the root image needs `libgomp1` at runtime is **unverified**; the wheels may bundle it.
Fix: keep one Dockerfile and one production compose file; keep a development compose file
explicitly named as such; delete or rename the other.

**B4. The documented `.env.example` does not exist at the root.** The root compose header says
"copy .env.example to .env first", and `docs/OPERATOR_GUIDE.md` says `cp .env.example .env`.
Only `backend/.env.example` exists (23 `KEY=` lines). Compose refuses to start without `.env`
(`env_file: .env`). Fix: add a root `.env.example` covering the variables the root compose uses
(`POSTGRES_*`, `DATABASE_URL`, `CORS_ORIGINS`, `TRAINING_*`), and make the operator guide point at
it.

**B5. The Docker build context ships local secrets.** There is no `.dockerignore`. The root
Dockerfile runs `COPY backend backend` and `COPY data data`. Both directories can contain files
that are gitignored but present on a developer's machine: `backend/.env`, `backend/.secret_key`,
`backend/models/`, `data/uploads/`. Those files are copied into the image. Fix: add a
`.dockerignore` (draft: `docs/cicd/proposed/dockerignore.txt`) at the root, and a
`backend/.dockerignore` for the stack that builds from `backend/` (draft:
`docs/cicd/proposed/backend-dockerignore.txt`), because the root file does not apply to a build
whose context is `backend/`.

**B6. The deploy template needs a production compose file.** `docs/cicd/proposed/deploy.yml`
calls `docker-compose.prod.yml`, which does not exist. The root compose builds from source
(`build: .`); production must pull a tagged image (`image: ${ALLML_IMAGE}`) instead. Fix: add
`docker-compose.prod.yml` with that override, and nothing else.

**B7. CI never runs the frontend tests.** Fixed in the proposal (`ci.yml`, job `frontend`).

**B8. The operator guide describes things the repository does not have.** It says Postgres is
"the tested target (see `.github/workflows/ci-postgres.yml`)". That file does not exist, and CI
runs the suite on SQLite. Fix: state what is tested (SQLite in CI; Postgres only in the manual
job until it passes), and remove the reference to the missing file. Done on this branch in
`docs/OPERATOR_GUIDE.md`.

**B9. There is no README.** Draft provided at the root on this branch. It uses only the commands
that are documented in the repository.

**B10. The CI push trigger names a branch that is no longer used.** Fixed in the proposal:
pushes to `main` and pull requests run CI; the stale branch name is removed.

## 3. Constraints

- **Cost.** GitHub-hosted runners are the default. Public repositories receive standard hosted
  runners at no charge. Private repositories have a monthly minutes allowance on the free plan.
  Check the current limits before adopting anything that runs on every push. **Unverified:** the
  visibility of this repository and the plan it runs on.
- **Size.** The backend depends on torch, torchvision, transformers, sentence-transformers,
  stable-baselines3 and others (`backend/requirements.txt`). Installing them is the dominant cost
  of every backend job. `scripts/install.sh --cpu` installs the CPU build of torch; the uv cache
  (`enable-cache: true`) keeps the rest.
- **Torch in the production image.** `torch` is listed without an index. On Linux, the default
  index's torch wheels pull CUDA dependencies, which makes the image large. **Unverified:** the
  size was not measured; no Docker daemon was available.
- **Determinism.** `scikit-learn<1.10` is pinned because the catalog relies on removed
  parameters (`backend/requirements.txt`). Other packages are not pinned. Dependency automation
  (section 4.2) must respect this pin.
- **Data.** Trained models and user uploads are runtime data (`.gitignore`: `models/`,
  `uploads/`, `data/uploads/`). They must never be baked into an image or committed.
- **Secrets.** `SECRET_KEY`, `POSTGRES_PASSWORD` and the host `.env` are not GitHub secrets; they
  live on the host (decision D8).

## 4. The options

Every item below is a candidate. The recommendation column uses four values:

- **Now**: adopt in the first phase that is possible.
- **After Bn**: adopt once blocker n is fixed.
- **Later**: worth doing, not on the critical path.
- **Skip**: not for this repository now, with the reason.

### 4.1 Continuous integration

| ID | Option | What it gives | Recommendation | Notes |
|---|---|---|---|---|
| CI-1 | Backend unit and integration tests (`pytest backend/tests`) | Regressions in the backend | Now (exists) | Already in `ci.yml`. Keep. |
| CI-2 | Migration check (`alembic upgrade head`, `alembic check`) | Schema drift between models and migrations | Now (exists) | Already in `ci.yml`. |
| CI-3 | Frontend unit and component tests (`npm test`) | 170 tests run on every change | Now | Missing today (B7). Proposed in `ci.yml`, job `frontend`. |
| CI-4 | Frontend production build (`npm run build`) | The bundle compiles | Now (exists) | Keep. Upload `frontend/dist` as an artifact (7 days). |
| CI-5 | Postgres job (`alembic` and `pytest` on Postgres 16) | Behaviour on the production database | After the suite is confirmed on Postgres | Proposed as `backend-postgres`, manual trigger only. Needs one manual run first (decision D6). |
| CI-6 | Python lint (`ruff`) | Style and common errors | Now, report only | No configuration exists. Proposed as `lint` with `continue-on-error`, pinned `ruff@0.8.4`. Promote to required after triage. |
| CI-7 | Dockerfile lint (`hadolint`) | Image hygiene | Now, report only | Proposed in `lint`. |
| CI-8 | Docker build without push (`docker/build-push-action`, `push: false`) | The image still builds | Now | Proposed in `docker`. Requires B3 and B5 first. |
| CI-9 | Compose validation (`docker compose config --quiet`) | The compose files parse with the variables they need | Now | Proposed in `docker`; writes a throwaway `.env` (needs B4 for a real one). |
| CI-10 | Container smoke test (start the image with a database, call `/healthz`) | The image runs, not just builds | After B2 | Not in the proposal yet: it needs a database service and the fixed migration command. |
| CI-11 | Type checking (mypy, pyright, `tsc`) | Type errors | Later | No configuration; the Python code has no annotations contract. Start with one module. |
| CI-12 | Browser end-to-end tests (Playwright) | The four main flows work in a real browser | Later | Playwright is planned in the `docs/plans/2026-11-09-playwright-*` documents. Run as a separate job after the unit jobs; one flow first. |
| CI-13 | Accessibility checks in CI (axe) | Regression of WCAG findings | Later | Add to the Playwright job once CI-12 exists. |
| CI-14 | Visual regression screenshots | Unintended visual change | Later | High maintenance; only for the light and dark themes. |
| CI-15 | Frontend bundle size budget | Bundle growth | Later | Measure the current size first, then set a budget. |
| CI-16 | Coverage report with a threshold | Untested code | Later | Report first, no threshold. |
| CI-17 | Path filters (run backend jobs only when `backend/` changes, frontend only when `frontend/` changes) | Faster pull requests | Later | Worth it once the backend job is measured; a filter that skips a needed job is a silent gate failure, so add it carefully. |
| CI-18 | Dependency caching (`enable-cache` for uv, `cache: npm`) | Shorter installs | Now | In the proposal. |
| CI-19 | Concurrency cancellation of superseded runs | Less wasted runner time | Now | In the proposal (`concurrency:`). |
| CI-20 | Job timeouts | No runaway jobs | Now | In the proposal (`timeout-minutes`). |
| CI-21 | Least-privilege token (`permissions: contents: read`) | A compromised step cannot write to the repository | Now | In the proposal, on every workflow. |
| CI-22 | Reusable CI (`workflow_call`) | The release workflow requires the same checks as a merge | Now | In the proposal. Release depends on it. |
| CI-23 | Matrix over Python versions (3.11 and 3.12) | Compatibility | Later | The two Dockerfiles use different Python versions (B3); decide the supported version first. |
| CI-24 | Scheduled full run including model training | Catches training regressions the unit tests do not | Later | Expensive; run nightly on a larger runner if the cost is acceptable. |
| CI-25 | Branch protection requiring the CI jobs | No merge with red checks | Now (repository setting) | Section 5.4. |
| CI-26 | Gate check: a pull request links its review report (`docs/agent-ops/...`) | The owner's review process is enforced | Later, report only | A small script on `pull_request`; it reads the PR body. Decide the report format first. |
| CI-27 | Workflow linting (`actionlint`) | Broken workflow files are caught before they run | Now | Run locally this session on the proposed files (exit 0). Add to CI with CI-6. |

### 4.2 Security

| ID | Option | What it gives | Recommendation | Notes |
|---|---|---|---|---|
| SEC-1 | Dependabot version updates (pip, npm, actions, docker) | Dependencies stay current, one PR each | Now | Proposed in `dependabot.yml`. Torch updates are large: grouped by minor and patch. Respect the `scikit-learn<1.10` pin (Dependabot does not move past an upper bound). |
| SEC-2 | Dependabot security alerts and security updates | Vulnerable dependencies are reported and fixed | Now (repository setting) | Section 5.4. |
| SEC-3 | CodeQL (python, javascript-typescript) | Code-level vulnerabilities | Now | Proposed in `security.yml`. Requires GitHub code scanning; for a private repository that needs an Advanced Security licence (decision D11). |
| SEC-4 | Dependency review on pull requests | New dependencies with known high-severity advisories are blocked | Now | Proposed in `security.yml`, `fail-on-severity: high`. |
| SEC-5 | Secret scanning in CI (gitleaks) | Secrets in the history | Now | Proposed in `security.yml`. A repository-level push protection (section 5.4) catches secrets before they are pushed. The `ci-only-password` literal in `ci.yml` may be flagged; allowlist it once if it is. |
| SEC-6 | Python dependency audit (`pip-audit`) | Known vulnerabilities in the pinned environment | Now, report only | Proposed as `python-deps`. Torch and its CUDA dependencies make the first run slow; expect findings to triage. |
| SEC-7 | npm audit (production dependencies, high and above) | Known frontend vulnerabilities | Now | Proposed as `npm-deps`. |
| SEC-8 | Container image scan (Trivy or Docker Scout) | Vulnerabilities in the base image and its packages | After B3 | The image choice is pending. Add to the `docker` job after the image builds. |
| SEC-9 | SBOM for the image | Inventory of what is shipped | Now | `sbom: true` in the proposed `release.yml`. |
| SEC-10 | Build provenance attestation | Proof the image came from this workflow | Later | `actions/attest-build-provenance` with `id-token: write` and `attestations: write`. Add after the first release works. `provenance: mode=max` is already set. |
| SEC-11 | Pin every action to a full commit SHA | An action cannot change under the workflow | Now, when adopting | The proposed files use major-version tags for readability. Pin them when a file is activated, and let Dependabot update the SHAs (SEC-1, actions ecosystem). |
| SEC-12 | No `pull_request_target` with checkout of untrusted code | A pull request from a fork cannot read secrets | Now (rule) | None of the proposed workflows use it. Keep it that way. |
| SEC-13 | Inputs reach shell steps through `env:`, not `${{ }}` interpolation | No script injection from a workflow input | Now (rule) | Applied in the proposed `deploy.yml`. |
| SEC-14 | OpenSSF Scorecard | A scored summary of the repository's security practices | Later | Once the items above are in place. Publishes a badge. |
| SEC-15 | Signed commits or tags | Authorship proof | Later | Only if the owner wants it (decision D12). |
| SEC-16 | Licence check of dependencies | Licence compatibility | Later | Several ML dependencies have their own licences; check before any public release. |

### 4.3 Continuous delivery

| ID | Option | What it gives | Recommendation | Notes |
|---|---|---|---|---|
| CD-1 | Backend image pushed to GHCR on a version tag | A versioned, immutable artifact | Now, after B2, B3, B5, B6 | Proposed in `release.yml`, job `image`. Tags: `X.Y.Z`, `X.Y`, `sha`. |
| CD-2 | GitHub Release with generated notes and the frontend archive | A human-readable release with the built frontend | Now | Proposed in `release.yml`, jobs `frontend` and `github-release`. |
| CD-3 | Preview deployments of the frontend per pull request (Netlify, Cloudflare Pages, Vercel) | Reviewers see each change running | After B1 | Needs `VITE_API_BASE` per preview and `CORS_ORIGINS` for the preview origins. Third-party service: decision D2. |
| CD-4 | Frontend on GitHub Pages | Free static hosting | After B1 | Needs a public API origin; the API then is the only server. Not suitable while the API is on a private host. Decision D2. |
| CD-5 | Frontend served from the same host as the API, behind a reverse proxy (Caddy or nginx as a compose service) | One origin, one certificate, no CORS | After B1; recommended with D1 and D2 | The Dockerfile comment says the frontend is "served by its own origin (Vite/ nginx)", but no such service exists in any compose file. This option adds it. |
| CD-6 | Deployment to one Linux host with docker compose over SSH (`deploy.yml`) | Automated deployment that follows the repository's own compose stack | After B1 to B6 and D1 | The template in `docs/cicd/proposed/deploy.yml`. Manual trigger; environment-gated; backs up before migrating; health check at the end. |
| CD-7 | Deployment to a PaaS (Fly.io, Render, Railway) | No host to run | Later | The worker trains models and needs CPU or GPU and persistent volumes (`artifacts`, `uploads` in compose). Check that the platform provides them and a managed Postgres at an acceptable price before choosing. Decision D1. |
| CD-8 | Deployment to a cloud container service (Cloud Run, ECS, Azure Container Apps) | Managed scaling | Later | Needs object storage for artifacts and uploads, because these services have no persistent local disk for them. Larger change than CD-7. |
| CD-9 | Kubernetes or Helm | Orchestration | Skip | One API, one worker, one database. The operational cost is not justified by the current scale. Revisit only with several workers on several machines. |
| CD-10 | Two environments, `staging` and `production`, as GitHub environments | Changes are rehearsed before production | Now (design); activate after D1 | `deploy.yml` takes the environment as an input. |
| CD-11 | Required reviewer on the `production` environment | A human approves each production deployment | Now (repository setting); after D1 | Section 5.4. |
| CD-12 | Database backup before each migration | A rollback point exists | Now (in `deploy.yml`) | `pg_dump` to `backups/pre-<tag>.sql.gz` on the host. |
| CD-13 | Scheduled database backup (nightly, off the host) | Recovery from loss of the host | Later | The operator guide describes manual backups only. Needs an off-host destination: decision D8. |
| CD-14 | Migrations as a gated step, forward only, after `alembic check` in CI | Schema changes are reviewed before they reach production | Now | `alembic check` is already in CI (CI-2). `deploy.yml` runs `upgrade head` before the new api and worker start, because the app refuses to start on an unmigrated database. |
| CD-15 | Expand-and-contract migration policy | Old and new application versions both work against the schema during a deployment, so an application rollback is safe | Now (policy; section 9) | Documented in `docs/cicd/RELEASING.md`. |
| CD-16 | Application rollback to the previous image tag | Fast recovery from a bad release | Now | `deploy.yml` prints the command and fails the job. Rehearse it on staging (phase P6). |
| CD-17 | Automatic schema rollback | Undo a migration automatically | Skip | Unsafe: down-migrations drop data. Recovery of the schema is a restore from backup, a decision taken by a person. |
| CD-18 | Post-deploy smoke test beyond `/healthz` (for example one authenticated read) | Confirms the feature set, not just the process | Later | `/healthz` checks the process and the database (`backend/app/observability.py:206`). Add an authenticated read against a test account when one exists. |
| CD-19 | Blue/green or canary releases | Zero-downtime and gradual rollout | Skip | Single-host compose cannot do it cleanly. Revisit with CD-8. |
| CD-20 | Model artifact registry (promotion of trained models between environments) | Reproducible models and clear provenance | Later | Models are runtime data (section 3). A registry needs object storage first. |
| CD-21 | Cloud authentication through OIDC rather than long-lived keys | No static cloud credentials in GitHub | Later | Applies only when a cloud target is chosen (CD-7, CD-8). |
| CD-22 | Infrastructure as code (OpenTofu or Terraform) for the host or the cloud resources | Reproducible infrastructure | Later | Only once there is more than one host. |
| CD-23 | Deployment notifications (failure to a chat channel) | A failed deployment is seen | Later | Optional; one step in `deploy.yml`. |
| CD-24 | External uptime monitoring of `/healthz` | Outages are seen even when no deployment ran | Later | Not a GitHub feature. Any external monitor works. |

### 4.4 Releases and versioning

| ID | Option | What it gives | Recommendation | Notes |
|---|---|---|---|---|
| REL-1 | Semantic versioning with `vX.Y.Z` tags | Versions people can refer to | Now | Start at `0.1.0`. Decision D4. |
| REL-2 | Tags only from `main`, after CI passed | A release is always a tested commit | Now (rule and ruleset) | Section 5.4 (tag ruleset). `release.yml` also runs CI before building. |
| REL-3 | Generated release notes (`generate_release_notes`) | Notes without writing them by hand | Now | In `release.yml`. |
| REL-4 | Release automation (release-please) | A release pull request generated from commit messages | After a commit convention is adopted | The history mixes styles (`feat(frontend):`, `docs(ops):`, `PLAN:round3 -`, merge commits). release-please needs conventional commits or conventional squash-merge titles. Decision D4. |
| REL-5 | `CHANGELOG.md` | A reviewed history of changes | Now, by hand | Created with the first release. |
| REL-6 | Pre-release tags (`vX.Y.Z-rc.N`) | Test a release on staging before the final tag | Later | The image tag pattern already accepts it. |

### 4.5 Repository hygiene and documentation

| ID | Option | What it gives | Recommendation | Notes |
|---|---|---|---|---|
| REPO-1 | `README.md` at the root | A starting point | Now | Draft on this branch. |
| REPO-2 | `CONTRIBUTING.md` | How to run the checks and what a pull request needs | Now | Draft on this branch. |
| REPO-3 | `SECURITY.md` | How to report a vulnerability | Now | Draft on this branch. Enable private vulnerability reporting (section 5.4) so the link works. |
| REPO-4 | Pull-request template | Every pull request states its tests, risks and rollback | Now | `docs/cicd/proposed/pull_request_template.md`; move to `.github/`. |
| REPO-5 | Issue templates | Structured bug reports | Later | Only once issues are in use. |
| REPO-6 | `CODEOWNERS` | Review requests go to the right people | Later, if others review | Solo owner: not needed. |
| REPO-7 | `.dockerignore` (root and `backend/`) | No local secrets or data in images (B5) | Now (blocker) | Draft: `docs/cicd/proposed/dockerignore.txt`. |
| REPO-8 | `.editorconfig` | Consistent whitespace and line endings | Later | Small and safe. |
| REPO-9 | Pre-commit hooks (ruff, trailing whitespace, secret check) | Problems caught before commit | Later | Only after CI-6 is required, so the hook and the CI agree. |
| REPO-10 | Branching rules documented (`feature/*`, `fix/*`, `docs/*`; merge by pull request) | Consistent history | Now | Written in `CONTRIBUTING.md`. |
| REPO-11 | Operator documentation accurate to the code | The deployment steps work | Now (blockers B2, B4, B8) | `docs/OPERATOR_GUIDE.md` corrected on this branch where the repository could confirm the fact. |
| REPO-12 | Architecture decision records (`docs/adr/`) | Why decisions were taken | Later | The `docs/plans/` and `docs/agent-ops/` folders already record decisions; an ADR index would link them. |
| REPO-13 | Changelog-based release notes | Covered by REL-5 | — | — |
| REPO-14 | Renovate instead of Dependabot | Finer grouping | Skip | Dependabot covers the need; one tool is simpler. |
| REPO-15 | Stale-issue bot | Closes idle issues | Skip | No issue volume yet. |

### 4.6 Repository settings (not files)

These change behaviour without a commit. Each one is a click for the owner; the repository cannot
be changed from a branch.

| ID | Setting | Recommendation |
|---|---|---|
| SET-1 | Branch protection or a ruleset on `main`: pull request required, linear history, no force push, no deletion, required checks "Backend tests and migrations (SQLite)" and "Frontend tests and build" (the job display names) | Now |
| SET-2 | Tag ruleset for `v*`: only from `main`; no deletion | Now |
| SET-3 | Workflow permissions default: read repository contents; do not allow workflows to create or approve pull requests | Now |
| SET-4 | Actions permissions: allow GitHub-created actions and selected verified creators; pin by SHA (SEC-11) | Now |
| SET-5 | Secret scanning and push protection | Now (if the plan allows; see D11) |
| SET-6 | Dependabot alerts and security updates | Now |
| SET-7 | Private vulnerability reporting | Now (REPO-3) |
| SET-8 | Environments `staging` and `production`; required reviewer and a deployment branch rule (`main` only) on `production` | Now (after D1) |
| SET-9 | Environment secrets and variables (section 6) | After D1 |
| SET-10 | Auto-delete head branches after merge | Now |

## 5. Recommended design

### 5.1 CI (`docs/cicd/proposed/ci.yml`)

Four jobs run on every pull request and on pushes to `main`:

- `backend`: install (`scripts/install.sh --backend --cpu`), `alembic upgrade head`,
  `alembic check`, `pytest backend/tests`. Same commands as today, with a timeout, a cache, and
  the least-privilege token.
- `frontend`: `npm ci`, `npm test`, `npm run build`, upload `frontend/dist` for seven days.
  **This is the change that closes B7.**
- `lint`: `ruff` and `hadolint`, report only (`continue-on-error: true`). Promote to required
  after one triage pass.
- `docker`: build the root image without pushing, validate the root compose file (needs B3,
  B4, B5 for a real run).

Manual only (`workflow_dispatch`): `backend-postgres`.

The file is also a reusable workflow (`workflow_call`). The release workflow calls it, so a
release cannot be built from a commit that fails the same checks as a merge.

Required checks (set in SET-1) use the job display names, which is what branch protection shows:
"Backend tests and migrations (SQLite)" and "Frontend tests and build". Add "Build the backend image (no push) and validate compose" once it passes twice.

### 5.2 Security (`docs/cicd/proposed/security.yml`, `docs/cicd/proposed/dependabot.yml`)

Runs on pushes to `main`, pull requests, and weekly:

- `codeql`: two languages, `build-mode: none` (no build needed for analysis).
- `dependency-review`: pull requests only, blocks new high-severity advisories.
- `secrets`: gitleaks over the full history.
- `python-deps` and `npm-deps`: `pip-audit` (report only) and `npm audit --omit=dev --audit-level=high`.

Dependabot (`dependabot.yml`): pip in `/backend`, npm in `/frontend`, actions and docker monthly.
Minor and patch updates are grouped to keep the pull-request count small.

### 5.3 Release (`docs/cicd/proposed/release.yml`)

Trigger: a tag matching `v*.*.*`.

1. `ci` calls the reusable CI workflow. Nothing below runs if it fails.
2. `image` builds the backend from the root `Dockerfile` and pushes it to GHCR with tags
   `X.Y.Z`, `X.Y` and the commit SHA, with an SBOM and maximum provenance.
3. `frontend` builds `frontend/dist` and archives it.
4. `github-release` creates the GitHub Release with generated notes and attaches the archive.

The workflow deploys nothing. Deployment is a separate, manual, environment-gated step
(`deploy.yml`). Keeping them apart means a release can exist without being deployed, and a
deployment never builds anything.

The image name in the file is lower case (GHCR requires it) and hard-codes the owner. Change it
if the repository moves.

### 5.4 Repository settings

Set these once (SET-1 to SET-10 in section 4.6). They are the part of "CI/CD" that files cannot
enforce. In particular: without SET-1 the required checks above do nothing, and without SET-3
a workflow token can write to the repository.

### 5.5 Deployment (`docs/cicd/proposed/deploy.yml`) — template

Trigger: manual, with three inputs: `environment` (`staging` or `production`), `image_tag`, and
`previous_tag` (the rollback target, required so that the rollback is decided before the deploy
starts).

Steps, in order: pin the host key; back up the database; pull the image; run
`alembic -c backend/alembic.ini upgrade head` with the new image; start the new `api` and
`worker`; health check on `${PUBLIC_API_URL}/healthz`; on failure, print the application rollback
command and fail the job. The migration comes before the restart because the app refuses to start
against an unmigrated database.

It stays a template until D1 is decided and B1 to B6 are done. Activating it before then would
deploy a stack that cannot start.

## 6. Environments, secrets and variables

Set in GitHub, under each environment (`staging`, `production`). Names only; values are never in
this document.

| Name | Kind | Used by | Notes |
|---|---|---|---|
| `DEPLOY_SSH_KEY` | secret | `deploy.yml` | Private key of a deploy user on the host. Passed through `env`, written with mode 600. |
| `DEPLOY_KNOWN_HOSTS` | secret | `deploy.yml` | The host's public key line. Obtained once with `ssh-keyscan` and checked against the host. |
| `DEPLOY_HOST` | variable | `deploy.yml` | Host name or address. |
| `DEPLOY_USER` | variable | `deploy.yml` | Deploy user. |
| `DEPLOY_DIR` | variable | `deploy.yml` | Directory on the host that holds the compose files and `.env`. |
| `PUBLIC_API_URL` | variable | `deploy.yml` | Public origin of the API, used for the health check. |

Kept on the host, not in GitHub (decision D8): `POSTGRES_PASSWORD`, `SECRET_KEY`, the production
`.env`, the database backups, and the registry credential the host uses to pull the image if the
image is private.

GitHub's own `GITHUB_TOKEN` is used for GHCR in `release.yml`. It needs no stored secret.

## 7. Rollout

Each phase has an exit criterion. A phase does not start until the previous one has exited.

| Phase | Work | Exit criteria |
|---|---|---|
| P0 | Review this branch: spec, proposed files, drafts | Owner approves the spec and decisions D1 to D12 |
| P1 | Blockers B2 to B6, B8 | `docker compose -f docker-compose.yml config` passes with the root `.env.example` in CI; the migration command in the operator guide works in the container; one image, one compose stack |
| P2 | Adopt `ci.yml`; set SET-1, SET-3, SET-10 | A pull request with a failing frontend test cannot merge (tested once on purpose); `main` is green |
| P3 | Adopt `security.yml` and `dependabot.yml`; set SET-2, SET-5 to SET-7 | Secret scan and CodeQL run on `main`; Dependabot has opened its first pull requests; report-only findings are triaged |
| P4 | Adopt `release.yml`; tag `v0.1.0` from green `main` | The GHCR image exists with the three tags; the GitHub Release has the archive and notes; `docker run` of that image answers `/healthz` once a database is provided |
| P5 | Decision D2; fix B1; set `CORS_ORIGINS` for the frontend origin | The built frontend, served from its host, calls the configured API with no code change |
| P6 | Decision D1; create the `staging` environment; run `deploy.yml` with `previous_tag` | A deployment to staging passes its health check; a deliberate rollback to `previous_tag` passes its health check; both are recorded |
| P7 | Create the `production` environment with a required reviewer (SET-8); first production deployment | One approved deployment; the rollback path was rehearsed on staging |
| P8 | The "Later" items as the owner needs them | Each one has its own entry in the repository's history |

## 8. Verification

Each item must be checked the way it was checked for this proposal: by running it, not by reading
it.

- Workflow files: `actionlint` exits 0 on copies of the four proposed files laid out as they would
  be after adoption (done this session; repeat before each activation).
- YAML parses: checked for every proposed file on this branch.
- Frontend: `npm test` (170 passing on `ca3f917`) and `npm run build` (done).
- Backend: `pytest backend/tests` and `alembic check` on SQLite, and on Postgres once P1 is done.
  **Not yet run** for this spec.
- Image: `docker build` and `docker compose config` (CI-8, CI-9). **Not yet run**: no Docker daemon
  in the environment where this proposal was written.
- Deployment: a rehearsal on staging with a real host (P6). **Not yet run.**

A workflow change is accepted only when its first run on a branch passes, and when a deliberate
failure in the same job makes it fail (a gate that has never failed has not been tested).

## 9. Rollback and recovery

Application rollback is the normal path. Its precondition is the expand-and-contract migration
policy (CD-15): a migration either only adds (new tables, nullable columns, new indexes) or is the
second half of a change whose first half has already been deployed and proven. Under that policy,
the previous image runs correctly against the new schema, so rolling back the application is a
single command (`deploy.yml` prints it).

Schema rollback is a restore from the pre-migration backup (`backups/pre-<tag>.sql.gz`). It loses
every write made after the backup. It is a decision for a person, never automatic (CD-17).

Image rollback needs the previous tag to exist in GHCR. `release.yml` keeps every version tag, so
it does; the tags are never reused.

## 10. Costs and limits

- GitHub Actions: check the plan for the repository's visibility (D11). A backend job that
  installs torch dominates the time. The uv cache (`enable-cache`) reduces it; measure it on the
  first run and record the number here. **Unverified:** the duration.
- GHCR: storage for images. Each release adds one image of several gigabytes if torch is installed
  with CUDA (section 3). Keep the CPU build for the default image (D7) and prune old tags.
- Host: the worker needs CPU and memory for training; the operator guide describes the limits
  and the executor. Size the host from the operator guide, not from this document.

## 11. Relationship to the owner's review process

`docs/agent-ops/` records briefs, implementation reports, reviews and gates for each wave of work.
This spec is an input to that process, not a replacement for it. CI checks what can be checked
automatically (tests, builds, scans). The review gates remain human, recorded in `agent-ops`. CI-26
would link the two, and only as a report until the owner decides how.

`AGENTS.md` requires independent review before a change is committed. This branch has not been
reviewed under that rule; that is the first step of P0.

## 12. Decisions needed from the owner

| ID | Question | Options | Recommendation |
|---|---|---|---|
| D1 | Where does the stack run? | (a) one Linux host with compose; (b) a PaaS; (c) a cloud container service | (a). It matches the repository's own compose stack and operator guide. The worker needs CPU or GPU and persistent volumes, which (b) and (c) make harder. |
| D2 | Where is the frontend hosted? | (a) same host behind a proxy; (b) GitHub Pages; (c) a preview service | (a) for production, which needs no CORS; (c) optionally for previews. |
| D3 | Which registry? | GHCR; Docker Hub; a cloud registry | GHCR: no extra account, integrated with `GITHUB_TOKEN`. |
| D4 | Versioning and release automation | Manual tags; release-please | Manual `v0.1.0` first; release-please once commits follow one convention. |
| D5 | Which checks block a merge? | The two CI jobs; plus the `docker` job | The two CI jobs now; the `docker` job after two green runs. |
| D6 | Is the suite expected to pass on Postgres? | Yes (promote the job); not yet (keep it manual) | Keep manual until one manual run passes. |
| D7 | Which torch build goes in the production image? | CPU; CUDA | CPU by default. The Dockerfile comment already describes a separate GPU build. |
| D8 | Where do secrets and backups live? | Host `.env` and host backups; GitHub secrets; a secret manager | Host `.env` and host backups; GitHub holds only the deploy key, the pinned host key and host names. Backups off-host (CD-13) before production. |
| D9 | Keep the session token in `localStorage`? | Keep for now; move to an httpOnly cookie (backend change) | Keep for now and record it; decide with the next authentication change. |
| D10 | Product name | "PrimeTrade AutoML"; "ALL-of-ML"; another | One name, used in `index.html`, the UI, `package.json` and the image name. |
| D11 | Repository visibility and plan | Public; private | Public is simplest (free runners, CodeQL). Private needs an Advanced Security licence for CodeQL and secret scanning. **Unverified:** the current visibility. |
| D12 | Signed commits or tags? | No; yes | No until needed (SEC-15). |

## 13. Risks

- **The frontend gate is new.** Adding 170 tests to every pull request may make pull requests slow
  or flaky. Measure the first runs; fix flaky tests before making the job required.
- **Torch makes every backend job slow.** The uv cache helps; a split of heavy tests into a nightly
  job (CI-24) may be needed.
- **Report-only jobs stay report-only.** `lint`, `python-deps` and `backend-postgres` are not
  required until someone is named to triage them. Set a date for the decision.
- **The root compose file has never run end to end in this review.** The alembic failure was
  reproduced in isolation (B2); the rest of the stack was not started. Start it in P1 before
  depending on it.
- **Dependabot will update `scikit-learn`** if the pin is loosened. The pin is intentional
  (section 3); keep it in the Dependabot ignore list if it reappears.
- **A workflow with a secret can be copied into a fork.** Only `main` and tags should be able to
  use the production secrets (SET-8, deployment branch rule).

## 14. Out of scope

- Application features, model accuracy and the training pipeline.
- The user-interface work. It is recorded under `docs/plans/` on `origin/main` (for example
  `frontend-ui-full-redesign` and `frontend-ui-round1-revised`); it is not part of this branch.
- The backend API contract (no change proposed).

## 15. Files on this branch

| Path | Status | Purpose |
|---|---|---|
| `docs/cicd/SPEC.md` | this file | the specification |
| `docs/cicd/RELEASING.md` | new | the release and rollback procedure |
| `docs/cicd/proposed/ci.yml` | proposal, inactive | section 5.1 |
| `docs/cicd/proposed/security.yml` | proposal, inactive | section 5.2 |
| `docs/cicd/proposed/dependabot.yml` | proposal, inactive | section 5.2 |
| `docs/cicd/proposed/release.yml` | proposal, inactive | section 5.3 |
| `docs/cicd/proposed/deploy.yml` | template, inactive | section 5.5 |
| `docs/cicd/proposed/pull_request_template.md` | proposal, inactive | REPO-4 |
| `docs/cicd/proposed/dockerignore.txt` | proposal, inactive | REPO-7 (B5), root build context |
| `docs/cicd/proposed/backend-dockerignore.txt` | proposal, inactive | REPO-7 (B5), build context `backend/` |
| `README.md` | new | REPO-1 |
| `CONTRIBUTING.md` | new | REPO-2, REPO-10 |
| `SECURITY.md` | new | REPO-3 |
| `docs/OPERATOR_GUIDE.md` | corrected | B4 and B8: removes references to a missing workflow and a missing file |
