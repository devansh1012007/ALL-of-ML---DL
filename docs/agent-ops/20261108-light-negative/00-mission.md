# Mission — 20261108-light-negative (orchestrator-owned)

## Scope
User-directed 3 fixes on frontend-ui-round2 (HEAD 85acdda, 117/117 green):
1. **Light mode** — tokens are dark-only today (color-scheme:dark, tech-debt). "Separate spec, do not invert ad-hoc" → this run WRITES a spec/plan first (docs/plans/), planner-reviewed, then implements cleanly.
2. **Negative-diff duration** — `finished_at < started_at` clamps to "Took 0 s" (pre-existing, RunDetails.jsx:222). Honesty question: hide the chip on negative diff (safest honest default; log in SUMMARY).
3. **tech-debt:17 dual counts** — reword 115/115 history + 117/117 gate genealogy explicitly (deferred NIT from prior review).

## Git safety
- BASE_SHA: 85acdda. Branch: frontend-ui-round2 (PR #2 continuity; no ops/ cut per A-002).
- Pre-existing uncommitted changes: none (git status --porcelain empty at preflight).
- Never push/merge/rebase unless post-review; PR #2 merge needs explicit approval (still NOT granted).

## Commands
- `cd frontend; npm test` (Vitest jsdom) · `npm run build` → frontend/dist/ · `npm run dev` → :3000.
- Scoped test: `cd frontend; npx vitest run tests/<file>`.

## Baseline (Step 0, ORCH, at 85acdda, pre-investigation)
- `npm test` 117/117 (10 files, 13.75s); `npm run build` 1670 modules green (4.15s).
- Known flake: runs.test.jsx Progress-poll timing (pre-existing; passed both runs this session).

## Hotspots (single-writer)
- frontend/tailwind.config.js, frontend/styles.css, frontend/format.js, frontend/tests/*, docs/tech-debt.md, docs/plans/*.

## Assumptions
- A-010: Negative-diff remedy = hide chip (null sentinel) — reviewer called this a product call; safest honest default, reversible.
- A-011: Light mode = CSS-variable token inversion keyed off data-theme + toggle persisted in localStorage, default from prefers-color-scheme. To be pinned by investigation + plan (investigation may change this).

## Sample structure (preflight-created)
```
docs/agent-ops/20261108-light-negative/
├── 00-mission.md, 01-work-ledger.md, COMMS.md, SUMMARY.md (last)
├── templates/ (copied from 20261108-p3-wave)
├── briefs/, ownership/, gates/
└── reports/w0-investigation|w1-impl|w1-review|w2-impl|final/
```
