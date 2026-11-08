Frontend UI round 2 redesign — full redesign (R1–R6) plus deferred follow-ups A1/B1/B2/C1/D1/E and P3 "Took NaN s", with docs-close.

## Deferred follow-ups (this branch)
- A1: Invalid Date NaN guard in format.js (092e800)
- B1: Runs row link-based, mouse-only tr onClick removed (c2dd5db)
- B2: Runs tooltip via formatWhen (64c99f8)
- C1: Predict segmented Arrow/Home/End select-on-arrow (87a6f08)
- D1: RL env-id label seeded per-test + submit env_id pinned (736339a)
- E: RunDetails + quota residual date leaks (6c72d75)
- P3: RunDetails duration chip hides on NaN diff (null sentinel; valid 0s still renders "Took 0 s"), +2 tests (f292a9c)
- Docs-close: tech-debt + plan marked P3 FIXED at f292a9c (6409d0e)

## Verification
- Frontend: 117/117 Vitest green (10 files) + build 1670 modules green at HEAD (gate-w1-1.md).
- Wave orchestrator run `docs/agent-ops/20261108-p3-wave/` (mission/ledger/COMMS/reports/briefs) — independent code review APPROVE, test review APPROVE, final integration review APPROVE.
- Backend pytest NOT-RUN (frontend-only diff). Chromium/SR probes NOT-RUN (jsdom only) — accepted risk recorded in docs/tech-debt.md.

## Not merging yet — needs approval.
- Light mode deferred (tokens dark-only). Probes + backend pytest still manual/NOT-RUN.
