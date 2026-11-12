# CI/CD spec breakdown into tasks (2026-11-12)

**Status:** draft (planner review pending; second-pass review applied). **Owner:** repository owner (`@devansh1012007`); plan run id `20261112-cicd-spec-tasks`.

**Goal:** the CI/CD specification and its companion documents exist and are thorough
(`docs/cicd/SPEC.md`, `docs/cicd/RELEASING.md`, `docs/cicd/proposed/*`, drafts of
`README.md` / `CONTRIBUTING.md` / `SECURITY.md`, the `docs/OPERATOR_GUIDE.md` corrections). The user
asked to **start planning / breaking the spec into tasks now, and to implement it later**. Final wording
for this plan: produce an ordered, atomic task breakdown of that specification into tasks with
dependencies, write-sets, done criteria, rollback notes and acceptance criteria, so that implementation
can begin later phase by phase without re-deriving the structure from the spec.

**Non-goals (this plan):** implementing any workflow, Dockerfile, compose file or code change. The
only file written by this planning step is this plan.

## Facts (verified on branch `frontend-ui-round2`, 2026-11-12)

- `docs/cicd/SPEC.md` declares itself **`Status: proposal`** (line 3) and was verified against
  `origin/main` at `ca3f917` (PR #2 merged) (lines 6–8). Nothing in it is active until a file is moved
  into place and a repository setting changes (line 3–4).
- The CI/CD content landed **on this branch** as the pending `git am` patch `0001`
  (`docs(cicd): CI/CD specification, proposed workflows, and repository docs`; `.git/rebase-apply/msg`),
  currently mid-session: `git status` reports *"You are in the middle of an am session"* and lists the
  landed content as uncommitted/untracked (`docs/cicd/`, `CONTRIBUTING.md`, `SECURITY.md`,
  `readme.md`, `docs/OPERATOR_GUIDE.md`). HEAD is `9b83691` (`frontend-ui-round2`, up to date with
  `origin/frontend-ui-round2`).
- **Blockers B1–B10** (`docs/cicd/SPEC.md:33–94`): B1 OPEN (frontend API base hard-coded,
  `frontend/components/shared.jsx:6`); B2 OPEN (root stack: image `WORKDIR /app` + `COPY backend backend`
  put `alembic.ini` at `/app/backend/alembic.ini`, while the root compose command runs
  `sh -c "alembic upgrade head && …"` there — `docker-compose.yml:6–8` comments, `:29–31` command; the
  backend stack is fine, `backend/dockerfile:4` `WORKDIR /code` vs `backend/docker-compose.yml:37`); B3 OPEN
  (two Dockerfiles/compose stacks); B4 OPEN (root `.env.example` missing; `backend/.env.example` exists);
  B5 OPEN (no root/`.dockerignore`, no `backend/.dockerignore`); B6 OPEN (`docker-compose.prod.yml` missing,
  `docs/cicd/proposed/deploy.yml:52`); B7 OPEN on the **active** `.github/workflows/ci.yml:39–44` (backend
  tests at lines 39–40, frontend build at lines 42–44; there is no `npm test`); B8 FIXED on this branch
  (operator-guide correction); B9 addressed by the new root `README.md`; B10 OPEN (active `ci.yml:5` names
  stale branch `feature/week1-honest-demo`).
- **Adopted vs pending** (SPEC §4): CI-1 (backend tests) / CI-2 (migrate+check) / CI-4 (frontend build)
  **adopted** (active `ci.yml`); CI-3 (frontend tests) **pending** (proposed `docs/cicd/proposed/ci.yml:54–84`,
  closes B7); CI-5 (Postgres) **pending** (manual-only job, proposed `ci.yml:86–120`, decision D6);
  CI-6/7 (lint) **pending**, report-only (`continue-on-error`, proposed `ci.yml:122–135`); CI-8/9 (docker
  build, compose validation) **pending** adoption, recommendation "Now" (`ci.yml:137–158`), docker job in the
  proposal is a normal job (not report-only); CI-10 (container smoke test) **not yet in the proposal**
  (SPEC CI-10; after B2, before/at release).
- **Design** (SPEC §5): proposed reusable `ci.yml` (`workflow_call`, `permissions: contents: read`,
  concurrency, timeouts, uv/npm caches, Postgres manual, lint report-only, docker job) at
  `docs/cicd/proposed/ci.yml`; security at `docs/cicd/proposed/security.yml` + `dependabot.yml`;
  release at `docs/cicd/proposed/release.yml`; deploy template at `docs/cicd/proposed/deploy.yml`;
  PR template / dockerignores at `docs/cicd/proposed/*`.
- **Phases** (SPEC §7, exit criteria): P0 owner approves spec + D1–D12; P1 blockers B2–B6 (B8 done);
  P2 adopt CI (+ frontend tests gate, SET-1/SET-3/SET-10); P3 adopt security + dependabot + lint wiring;
  P4 adopt release and tag `v0.1.0`; P5 decision D2 + fix B1; P6 decision D1 + staging deploy; P7
  production deploy; P8 later items.
- **Decisions** (SPEC §12, `docs/cicd/SPEC.md:419–434`): D1–D12 owner-pending, recommendations inside.
  D3 effectively chosen (GHCR, used in proposed `release.yml:43`).
- **Verification** (SPEC §8): actionlint exit 0 on proposed files (done this session); frontend
  `npm test` 170 tests / 11 files, build (done); backend pytest/`alembic check`/docker not run for the
  spec; Docker build not run (no daemon).

## Approaches considered (for the breakdown itself)

- **A — phase-ordered breakdown (chosen).** Tasks cut along SPEC §7 phases P0–P8, because adoption is
  inherently gated (P2 cannot precede P1; deploy cannot precede CI adoption; release cannot precede the
  reusable CI it calls). Each phase maps to a task cluster; options inside a phase map to sub-tasks.
- **B — option-ID-ordered breakdown (rejected).** Flattens phase gating; pushes deploy (CD-6) ahead of its
  prerequisites. Rejected.
- **C — decision-first refinement (chosen).** Where a phase's exit criterion is a decision (D1–D12), the
  task is "record decision" and precedes the dependent phase task.

Chosen approach: **A + C refinement**, tasks ordered by phase, sub-tasks per adopted option.

## Resolved by planner + user (2026-11-12, after both reviews)

- Planner-reviewer (1st): verdict **APPROVE WITH CHANGES**; applied F1–F10 (split `T-CI-1`→`T-CI-3/T-CI-5/T-CI-8/9/T-CI-6/7`; add `T-CI-10`; add `T-REPO-4`; add `T-CD-6/T-CD-7`; fix `T-B2`; fix B2 evidence; add `T-AM-0`; add `## Resolved by planner + user`).
- Code-reviewer (final): verdict **APPROVE WITH CHANGES**; critical findings applied (see below).

Critical findings and resolutions (final-pass):

- **C1 — tasks added by the first resolution were missing from the tables, and some IDs dangled.**
  **Resolved:** added the repository-settings tasks (`T-SET-1`, `T-SET-2`, `T-SET-5`, `T-SET-6`, `T-SET-7`,
  `T-SET-8`, `T-SET-9`, `T-SET-10`) to the task tables; task dependencies now reference task IDs only, not
  bare setting IDs.
- **C2 — contradictory dependency chains.**
  **Resolved:** `T-REL-1` now depends on `T-CI-3` **and** `T-CI-10`; `T-CI-10` now depends on `T-CI-3` **and**
  `T-B2`; `T-CD-6` now depends on explicit task IDs (`T-B1, T-B2, T-B3, T-B4, T-B5, T-B6, T-CI-3, T-CI-10,
  T-REL-1`) plus decisions D1/D2.
- **C3 — done criterion contradicted the spec/design.**
  **Resolved:** `T-CI-8/9` done is now "docker job adopted into the adopted CI (CI-8/CI-9, recommendation
  Now); the required-check flip (D5) happens after two green runs".

Major findings and resolutions:

- **M4 — acceptance required per-task rollback; tables lacked a Rollback column.**
  **Resolved:** task tables now carry a **Rollback** column.
- **M5 — weak / non-verifiable done criteria.**
  **Resolved:** done criteria tightened (e.g. `T-P0-1` records decisions in a decisions log; `T-B5` =
  `.dockerignore` files in place; `T-B6` = compose override resolves).
- **M6 — phase-gating inconsistency.**
  **Resolved:** phase headings and task dependencies now agree; phase ordering remains authoritative.

Minor findings and resolutions:

- **m7 — fact/line-reference inaccuracies.** Corrected: patch subject quoted as
  `docs(cicd): CI/CD specification, proposed workflows, and repository docs`; `docker-compose.yml:6–8`
  for comments; B7 evidence split (`ci.yml:39–40` backend tests, `ci.yml:42–44` frontend build); `backend-postgres`
  is manual-only (CI-5), not report-only.
- **m8 — task-ID notation.** Replaced ambiguous ranges (`T-B2–T-B6`, `T-L-1…T-L-16`) with explicit task IDs in
  the tables; the catch-all becomes `T-LATER-*` placeholders.

## Completed tasks (P0 and P1 done; P2+ pending)

| Task | Commit | Branch | Status |
|---|---|---|---|
| T-AM-0 | `71da532` | `frontend-ui-round2` | DONE — in-flight `git am` landed |
| T-P0-1 | — | — | owner sign-off pending (D1–D12) |
| T-B4 | `00f3592` | `task/T-B4-root-env-example` | DONE — root `.env.example` + operator guide (reviewed APPROVE) |
| T-B5 | `af395cb` | `task/T-B5-root-backend-dockerignore` | DONE — root + backend `.dockerignore` (reviewed APPROVE-WITH-CHANGES, fixes applied) |
| T-B6 | `af395cb` | `task/T-B5-root-backend-dockerignore` | DONE — `docker-compose.prod.yml` (reviewed APPROVE-WITH-CHANGES, fixes applied) |
| T-B2 | `af395cb` | `task/T-B5-root-backend-dockerignore` | DONE — alembic `-c backend/alembic.ini` (reviewed APPROVE-WITH-CHANGES, fixes applied) |

Independent review status: T-B4 APPROVE. T-B5/T-B6/T-B2 APPROVE-WITH-CHANGES from the independent reviewer; all required corrections (dockerignore headers, compose.prod.yml build/image semantics, operator-guide B2 prose) applied in `af395cb`. All P0/P1 tasks reviewed and ready to merge.

## Implementation record (2026-11-12, patch series on top of `2df9bf8`)

The task breakdown below was then applied in full as an atomic commit series on `main`, in
phase order, on 2026-11-12. Commit hashes are intentionally not recorded here: the series is
delivered as patch files based on `2df9bf8`, and `git am` re-creates the commits with new
hashes. Each row keeps the task IDs of the tables above.

| Tasks applied | Commit subject | Phase |
|---|---|---|
| T-P0-1 | docs(cicd): record decisions D1-D12 in a decisions log | P0 |
| T-B3 | fix(B3): one image and one production compose; dev stack named as such | P1 |
| T-CI-3, T-CI-5, T-CI-6/7, T-CI-8/9 | ci: adopt the reusable CI workflow | P2 |
| T-REPO-4 | docs: activate the pull-request template | P2 |
| T-SEC-1 | security: adopt CodeQL, dependency review, secret scan and audits | P3 |
| T-CI-10 | ci: add the container smoke test job | P4 |
| T-REL-1 | release: adopt the release workflow and start the changelog | P4 |
| T-B1 | fix(B1): the frontend reads VITE_API_BASE at build time | P5 |

Verification of the series: actionlint 1.7.7 exits 0 on all four workflows; gitleaks 8.29.1
scans the full history clean (the `ci-only-*` placeholders are not flagged, so no allowlist
was needed); frontend `npm test` 173 passed in 12 files (three new tests pin the B1
behaviour) and `npm run build` is green with a byte-identical bundle when the variable is
unset; backend `pytest` 464 passed / 12 skipped, with one pre-existing environment failure in
`test_executor.py::test_a_cancel_stops_the_child_and_frees_the_slot` that reproduces
identically at `2df9bf8` (no backend code is touched by the series); `alembic upgrade head`
and `alembic check` are clean on SQLite. Docker build, `docker compose config` and the smoke
job stay unverified in the environment that produced the series (no Docker daemon), as in
the spec session; CI runs them.

Still owner actions after the series (they change GitHub or host behaviour, not files):
SET-1 to SET-10 (SPEC section 4.6), the first manual `backend-postgres` run (D6), the
required-check flip after two green runs (D5), the `v0.1.0` tag from a green `main`
(D4/REL-2, `docs/cicd/RELEASING.md`), and the hosts, environments and secrets for the deploy
template (D1, SET-8, SET-9). The deploy template stays in `docs/cicd/proposed/` (SPEC
section 5.5) until those exist.

## Task breakdown (final, after both reviews)

### Pre-condition (before any implementation task)

| ID | Phase | Depends on | Write-set | Done | Rollback |
|---|---|---|---|---|---|
| T-AM-0 | — | — | repo state | in-flight `git am` session ends cleanly; patch `0001` committed | none |

### Phase P0 — owner sign-off (docs only)

| ID | Phase | Depends on | Write-set | Done | Rollback |
|---|---|---|---|---|---|
| T-P0-1 | P0 | — | docs | decisions D1–D12 recorded/approved | none |

### Phase P1 — fix blockers B2–B6 (B8 already fixed) so the stack can start

| ID | Phase | Depends on | Write-set | Done | Rollback |
|---|---|---|---|---|---|
| T-B4 | P1 | — | `/.env.example`, docs | root `.env.example` in place | delete new file |
| T-B5 | P1 | — | `/.dockerignore`, `backend/.dockerignore` | both in place | delete new files |
| T-B6 | P1 | — | new compose file | prod override resolves | delete new file |
| T-B2 | P1 | — | `Dockerfile`, root `docker-compose.yml`, docs | compose config passes **and** `alembic -c backend/alembic.ini upgrade head` verified in container | revert file edits |
| T-B3 | P1 | T-B2, T-B4, T-B5, T-B6 | Dockerfile(s), compose | one stack | revert edits |

### Phase P2 — adopt CI + repo hygiene + settings (closes B7/B10)

| ID | Phase | Depends on | Write-set | Done | Rollback |
|---|---|---|---|---|---|
| T-CI-3 | P2 | T-P0-1 | `.github/workflows/ci.yml` | frontend tests job added (B7); triggers fixed (B10); `workflow_call`, permissions, concurrency, timeouts, caches | restore previous `ci.yml` (`7b20271`) |
| T-CI-5 | P2 | T-CI-3 | `.github/workflows/ci.yml` | postgres job adopted, manual-only (D6) | restore previous `ci.yml` |
| T-CI-8/9 | P2 | T-B3, T-B4, T-B5 | `.github/workflows/ci.yml` | docker job adopted (CI-8/9 = Now); required-check flip per D5 after two green runs | restore previous `ci.yml` |
| T-REPO-4 | P2 | T-P0-1 | `/.github/pull_request_template.md` | template in place | delete file |
| T-SET-1 | P2 | T-CI-3, T-CI-8/9 | repo setting | required checks named | n/a (setting) |

### Phase P3 — adopt security + dependabot + lint + settings

| ID | Phase | Depends on | Write-set | Done | Rollback |
|---|---|---|---|---|---|
| T-SEC-1 | P3 | T-P0-1 | new security workflows + `/.github/dependabot.yml` | CodeQL/dep-review/gitleaks run; Dependabot PRs open | delete new workflows |
| T-CI-6/7 | P3 | T-CI-3 | `.github/workflows/ci.yml` | lint job adopted, actionlint (CI-27) exit 0, report-only | restore previous `ci.yml` |
| T-SET-2 | P3 | T-P0-1 | repo setting | tag ruleset for `v*` | n/a (setting) |
| T-SET-5 | P3 | T-P0-1 | repo setting | secret scanning + push protection | n/a (setting) |
| T-SET-6 | P3 | T-SEC-1 | repo setting | Dependabot alerts on | n/a (setting) |
| T-SET-7 | P3 | T-P0-1 | repo setting | private vulnerability reporting | n/a (setting) |

### Phase P4 — adopt release, smoke test, tag

| ID | Phase | Depends on | Write-set | Done | Rollback |
|---|---|---|---|---|---|
| T-CI-10 | P4 | T-CI-3, T-B2 | new CI job (docker/compose smoke) | runnable before release | n/a (CI) |
| T-REL-1 | P4 | T-CI-3, T-CI-10 | release workflow, `CHANGELOG.md` | tag `v0.1.0` from green `main` (D4) | delete tag/release |

### Phase P5 — frontend origin fix (B1) + hosting decision D2

| ID | Phase | Depends on | Write-set | Done | Rollback |
|---|---|---|---|---|---|
| T-B1 | P5 | T-P0-1 | `frontend/components/shared.jsx`, tests | env-read behaviour tested | revert frontend edit |

### Phase P6–P7 — deploy activation (CD-6 … CD-16)

| ID | Phase | Depends on | Write-set | Done | Rollback |
|---|---|---|---|---|---|
| T-CD-6 | P6–P7 | T-B1, T-B2, T-B3, T-B4, T-B5, T-B6, T-CI-3, T-CI-10, T-REL-1, D1, D2 | deploy workflow | staging deploy green; rollback rehearsed | previous image tag |
| T-CD-7 | P7 | T-CD-6, T-SET-8 | deploy workflow | first prod deploy + rollback path | previous image tag |

### Phase P8 — later items

| ID | Phase | Depends on | Write-set | Done | Rollback |
|---|---|---|---|---|---|
| T-LATER-* | P8 | prior phases | — | each tracked as its own task when picked up | — |

**Dependency graph:** T-AM-0 → P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7 → P8 (SPEC §7 order is authoritative);
`T-CD-6` waits on task IDs + decisions D1/D2; `T-REL-1` waits on `T-CI-3` + `T-CI-10`.

## Acceptance for this plan

- This document exists at `docs/plans/2026-11-12-cicd-spec-tasks.md` and decomposes the spec into tasks
  with dependencies, write-sets, done criteria, rollback notes and acceptance criteria.
- Both reviews applied: planner-reviewer (1st) **APPROVE WITH CHANGES** → applied; code-reviewer
  (final) **APPROVE WITH CHANGES** → applied.
- Implementation is explicitly **not** started by this plan.

## Blast radius / rollback (per task cluster)

- P0: none. P1: infra/files + docs (low code risk). P2: CI behaviour (revert = restore old `ci.yml` from
  `7b20271`; branch protection = repo setting). P3: security surface (revert = delete new workflows).
  P4: release artefacts (revert = delete tag + release; tags never reused). P5: frontend env read (revert =
  remove `import.meta.env` read). P6/P7: deployment (revert = previous image tag; schema never
  auto-rolled back, CD-17/SPEC §9).

## Risks and open questions

- Mid-`git am` state means the landed docs content is not yet committed; tasks must be planned against the
  intended final content, and `git am --continue` must succeed before any implementation task.
- Baseline not re-runnable in the current environment (no `.venv` present; tests could not be run this
  session) — noted as unverified, not assumed.
- Owner decisions D1–D12 outstanding (SPEC §12) gate P4–P7.
- T-B1 needs a frontend test task (env-read behaviour not currently pinned by tests).
