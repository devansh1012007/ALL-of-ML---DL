# Mission — 20261108-p3-wave (orchestrator-owned)

## Scope
- Close the last frontend code item: P3 "Took NaN s" guard in `frontend/views/RunDetails.jsx:214-216`.
- Context: follow-ups A1/B1/B2/C1/D1/E are already landed on `frontend-ui-round2` (see `docs/plans/2026-11-08-frontend-deferred-followups.md`).
- Out of scope: light mode, Chromium/SR probes, backend pytest (manual/NOT-RUN, accepted risk).

## Git safety
- BASE_SHA: `f292a9ce592f2b7099e093bfd6c62c1e524d6e97` (`f292a9c` — P3 fix already committed by coder subagent).
- Branch: `frontend-ui-round2` (today's feature branch). P3 fix is already on it; this run folder records the orchestrated verification + review gate for it.
- Pre-existing uncommitted changes: none at preflight (`git status --porcelain` empty except this new run folder).
- Never push, merge, rebase, or amend unless the user asks. Do not merge PR #2 without explicit approval.

## Commands (from AGENTS.md)
- Unit: `.venv/bin/python -m pytest backend/tests` from repo root (backend suite — NOT-RUN, no `.venv` evidence required; frontend-only diff).
- Frontend: from `frontend/`: `npm test` (Vitest, jsdom) · `npm run build` → `frontend/dist/` · `npm run dev` → http://localhost:3000.
- Scoped test: `npx vitest run tests/<file>` from `frontend/`.

## Baseline (captured at preflight, no other agent running)
- `npm test` 117/117 expected at `f292a9c` (115 at `2502fd9` + 2 P3 tests) — re-verify at gate.
- `npm run build` green (1670 modules) per coder report; re-verify at gate.
- Pre-existing flake (not a regression): `runs.test.jsx` Progress-poll test is timing-sensitive under load (observed 1/3 runs failing in multiple reviews). If the gate hits it, re-run once and record.

## Hotspots (single-writer)
- `frontend/format.js` (shared formatter contract), `frontend/tests/*` (shared fixture helpers), `docs/plans/*`, `docs/tech-debt.md`.

## Assumptions
- A-001: P3 fix at `f292a9c` is the correct remedy (NaN → hide chip; valid 0s still renders). Verified by independent reviewer APPROVE; gate re-checks.
- A-002: No `ops/` branch is used for this run — work stays on `frontend-ui-round2` to preserve PR #2 continuity. If a future wave needs isolation, create `ops/20261108-p3-wave` then.

## Sample structure (created at preflight)
```
docs/agent-ops/20261108-p3-wave/
├── 00-mission.md
├── 01-work-ledger.md
├── COMMS.md
├── templates/ (STANDING-ORDERS, report-*, review-*, gate-report, summary, brief, spawn-wrapper)
├── briefs/
├── ownership/
├── gates/
└── reports/w0-investigation|w1-impl|w1-review|w1-improve|final/
```
