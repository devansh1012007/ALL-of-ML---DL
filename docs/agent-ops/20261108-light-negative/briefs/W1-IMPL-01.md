# Brief — W1-IMPL-01 (coder) · wave 1 · run 20261108-light-negative

## 1. Role and mission
Mission: fix N1 — negative-diff duration (`finished_at < started_at`) currently renders a false "Took 0 s". You hide the chip (null sentinel) with one condition + 2 tests. Failure mode to avoid: showing a warning widget (invents UX/copy, rejected in investigation), showing "Took -60 s", or touching wall_seconds (product decision, out of scope).
Your role: coder. Branch: frontend-ui-round2. Working dir: D:\dev work\coding\Projects\ALL-of-ML---DL.

## 2. Required reading (in this order)
1. docs/agent-ops/20261108-light-negative/templates/STANDING-ORDERS.md (binding)
2. AGENTS.md (frontend conventions)
3. docs/agent-ops/20261108-light-negative/00-mission.md (A-010 hide-chip default, baseline)
4. Investigation report docs/agent-ops/20261108-light-negative/reports/w0-investigation/INV-negative-counts.md (sections "N1" §1 + §5) — your primary spec; the exact 1-2-line change and 2 test cases are spelled out there
5. Template: docs/agent-ops/20261108-light-negative/templates/report-implementation.md
6. COMMS.md (Log empty at read time)

## 3. Task and acceptance criteria
Task T-102 (SURFACE). Recommended approach (INV-negative-counts §N1, deviate only with evidence):
- frontend/views/RunDetails.jsx:220: extend condition to `durationMs === null || Number.isNaN(durationMs) || durationMs < 0`. Update invariant comment :214-216 to add negative ("parses to a non-negative diff"). Keep Math.max(0,·) on line 222 (redundant defense-in-depth now; do NOT remove in the same change).
- frontend/tests/runs.test.jsx: add exactly 2 tests in/around the P3 describe block (same renderApp + runDetails override pattern as :571-622): (1) negative-diff started 2026-11-08T00:01:00Z / finished 2026-11-08T00:00:00Z → no "Took" text, no "NaN" (MUST FAIL before fix — prove by running it against the reverted one-liner in a temp worktree or by assertion on the pre-fix code path; record the evidence); (2) mixed garbage/valid → no "Took" text (proves NaN genericity).
Acceptance (measurable):
- Negative diff → no "Took" text in DOM. Mixed → no "Took" text. started == finished → "Took 0 s" still rendered (existing zero test stays green — do NOT modify it).
- `cd frontend; npx vitest run tests/runs.test.jsx` → 16/16 (14 prior + 2 new). Do NOT run full suite (ORCH gate does).
- Diff touches ONLY RunDetails.jsx + runs.test.jsx. No OpenAPI/backend/wall_seconds changes.

## 4. Ownership
WRITE-SET: exactly frontend/views/RunDetails.jsx, frontend/tests/runs.test.jsx, and your report docs/agent-ops/20261108-light-negative/reports/w1-impl/W1-IMPL-01-T-102.md.
READ-ONLY: everything else. FORBIDDEN: hotspot files (styles.css, tailwind.config.js, format.js, docs/tech-debt.md, index.html, App.jsx, components/*). Need something outside? Post NEED; report DEFERRED-DEPENDENCY.
Ownership table docs/agent-ops/20261108-light-negative/ownership/W1.tsv already lists you — do not modify it.

## 5. Parallel siblings this wave
W1-IMPL-02 owns docs/tech-debt.md (T-103, one-line reword) — disjoint from you. C1: light mode (W2) is forbidden from touching RunDetails.jsx class strings in a way that conflicts; you land first.

## 6. Skip list and known traps
- Do NOT implement warn-chip/negative-seconds/wall_seconds (all rejected).
- Already fixed, don't redo: P3 NaN guard (f292a9c), timeAgo, format.js.
- Known flake: runs.test.jsx Progress-poll test is timing-sensitive (pre-existing, unrelated) — if your scoped run trips it, re-run once and record.

## 7. Environment and tests
Scoped only: `cd frontend; npx vitest run tests/runs.test.jsx` (repo root cwd). Never full suite/containers/ports. Kill processes. No secrets/PII.

## 8. Deliverables
Report: docs/agent-ops/20261108-light-negative/reports/w1-impl/W1-IMPL-01-T-102.md (start NOW; ORCH-DIGEST first). Commits (verify `git branch --show-current` = frontend-ui-round2 first, explicit paths only): 1) code commit (code+tests) with trailers Task/Agent/Wave/Report; 2) separate docs-only report commit listing the code SHA.
Final message ≤8 lines: STATUS | W1-IMPL-01 | T-102 | report path | commit SHAs | blockers.

## 9. Role notes (coder)
Root cause is display honesty (false "0 s"), not parsing. Answer the long-run test in your report (negative/huge/garbage timestamps never render raw, chip hides; reversal = negative test fails on pre-fix code). Stop + BLOCKED if a needed edit is outside the write-set.
