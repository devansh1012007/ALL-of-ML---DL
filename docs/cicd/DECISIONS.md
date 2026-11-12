# Decisions log (SPEC section 12)

The decisions the specification asks the owner to take, recorded with the value that was
adopted, when, and what it means concretely. A decision can be overturned: change the value
here, then propagate it in a follow-up change (the "reflected in" column lists where each one
lives).

| ID | Decision | Adopted value | Reflected in | Notes |
|---|---|---|---|---|
| D1 | Where the stack runs | One Linux host with docker compose over SSH (option a) | `docs/cicd/proposed/deploy.yml` (still a template until the host, environments and secrets exist) | Matches the repository's own compose stack and `docs/OPERATOR_GUIDE.md`; the worker needs CPU and persistent volumes, which a PaaS or a container service make harder. |
| D2 | Where the frontend is hosted | Same host as the API, behind a reverse proxy (option a) for production; preview services stay optional | `frontend/components/shared.jsx` (`VITE_API_BASE`), `CORS_ORIGINS` in `.env.example` | One origin means no CORS for production. The built frontend is rebuilt with `VITE_API_BASE` pointing at the public origin of its deployment. |
| D3 | Which registry | GHCR (option GHCR) | `docs/cicd/proposed/release.yml` (`ghcr.io/devansh1012007/allml-backend`) | No extra account; `GITHUB_TOKEN` authenticates the push. Already the registry the proposal used. |
| D4 | Versioning and release automation | Manual `vX.Y.Z` tags first; release-please only once commits follow one convention | `docs/cicd/RELEASING.md`, `CHANGELOG.md` | The first tag is `v0.1.0`, cut by hand from a green `main` (see RELEASING, "Cutting a release"). |
| D5 | Which checks block a merge | The two CI jobs now ("Backend tests and migrations (SQLite)", "Frontend tests and build"); the `docker` job ("Build the backend image (no push) and validate compose") joins after two green runs | `.github/workflows/ci.yml` job display names; the setting itself is SET-1 | The flip from "recommended" to "required" is a repository setting and stays an owner action. |
| D6 | Is the suite expected to pass on Postgres? | Not yet: the Postgres job stays manual until one manual run passes | `.github/workflows/ci.yml`, job `backend-postgres` (`if: github.event_name == 'workflow_dispatch'`) | Run it once by hand ("Run workflow" in the Actions tab), triage the findings, then promote it. |
| D7 | Which torch build ships in the image | CPU (option CPU) | `scripts/install.sh --cpu` in CI; the Dockerfile comment keeps the GPU path documented | The CUDA build is several gigabytes for no benefit on a CPU host. |
| D8 | Where secrets and backups live | On the host: `.env`, `SECRET_KEY`, `POSTGRES_PASSWORD`, the database backups. GitHub holds only the deploy key, the pinned host key and the environment variables | `docs/cicd/SPEC.md` section 6; `docs/cicd/proposed/deploy.yml` | Nothing secret is committed. Backups go off-host (CD-13) before production. |
| D9 | Session token in `localStorage` | Keep for now | `frontend/components/shared.jsx` (`prime_token`) | Recorded so the trade-off is visible; revisit with the next authentication change. |
| D10 | Product name | One name: **PrimeTrade AutoML** | `frontend/index.html` (title), the sign-in and account pages, `frontend/package.json` (`primetrade-frontend`) | The GHCR image keeps its repository identifier `allml-backend`; renaming the image is a mechanical follow-up if the owner wants the product name there too. |
| D11 | Repository visibility and plan | Public | verified 2026-11-12: the repository clones anonymously over HTTPS | Public means free hosted runners, CodeQL and secret scanning without an Advanced Security licence. |
| D12 | Signed commits or tags | No, until needed (SEC-15) | — | Revisit if the repository gains external contributors. |

## Provenance

- Source of the decisions and their recommendations: `docs/cicd/SPEC.md`, section 12.
- Recorded on 2026-11-12, plan run `20261112-cicd-spec-tasks`
  (`docs/plans/2026-11-12-cicd-spec-tasks.md`), task T-P0-1: the owner instructed that the plan
  be applied in full, which adopts the recommendation of each decision. Every value above is
  the recommendation the specification already carried; nothing new was decided here.
- Still owner actions (they change GitHub or host behaviour, not files): SET-1, SET-2, SET-3,
  SET-4, SET-5, SET-6, SET-7, SET-8, SET-9, SET-10 (SPEC section 4.6); the first manual
  `backend-postgres` run (D6); the `v0.1.0` tag (D4); the staging host, environments and
  secrets for the deploy template (D1, SET-8, SET-9).
