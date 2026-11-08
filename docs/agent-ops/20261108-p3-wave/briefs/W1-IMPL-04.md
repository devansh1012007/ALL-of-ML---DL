# Brief — W1-IMPL-04 (coder) · wave 1 · run 20261108-p3-wave

## 1. Role and mission
Mission: Close the last stale-docs item (T-004): mark P3 "Took NaN s" as FIXED in the two docs that still call it a future backlog. The code fix already landed at f292a9c and is verified — your change is docs-only so the paper trail matches HEAD. Failure mode to avoid: editing any code, test, or any docs line other than the two P3 sentences (would create churn + regression risk).
Your role: coder (implementation agent). Branch: frontend-ui-round2. Working directory: D:\dev work\coding\Projects\ALL-of-ML---DL.

## 2. Required reading (in this order)
1. docs/agent-ops/20261108-p3-wave/templates/STANDING-ORDERS.md (binding)
2. AGENTS.md (repo conventions, frontend section)
3. docs/agent-ops/20261108-p3-wave/00-mission.md (commands, hotspots, baseline: 117/117 + build green observed by ORCH)
4. Investigation reports (read in full): docs/agent-ops/20261108-p3-wave/reports/w0-investigation/INV-frontend-P3.md and INV-docs-PR.md (sections "P3 — Took-NaN", "5. Recommended task breakdown")
5. Template for your report: docs/agent-ops/20261108-p3-wave/templates/report-implementation.md
6. docs/agent-ops/20261108-p3-wave/COMMS.md (protocol header; Log currently empty)

## 3. Task and acceptance criteria
Task T-004 (SURFACE, docs-close). Root cause: f292a9c fixed the RunDetails duration chip (frontend/views/RunDetails.jsx:214-222: NaN → null → chip hidden; valid 0s still renders "Took 0 s"; +2 tests in frontend/tests/runs.test.jsx:571-619). Two docs still describe P3 as unfixed.
Recommended approach (from INV-docs-PR §5, you may deviate with evidence):
- docs/tech-debt.md line 17: replace trailing sentence `P3 remainder: RunDetails.jsx:214-216 garbage started_at/finished_at → "Took NaN s" (not a date leak; future phase).` with a FIXED statement citing f292a9c, e.g.: `P3 "Took NaN s" (FIXED 2026-11-08, f292a9c): RunDetails.jsx duration chip hides on NaN diff (null sentinel; valid 0s still renders); +2 tests (117/117 at gate).` Keep all A1/B2/E citations in that line verbatim.
- docs/plans/2026-11-08-frontend-deferred-followups.md line 113 (F5): append a `P3 FIXED f292a9c` clause to the F5 bullet. Do not re-plan; do not touch other F-items.
Acceptance criteria (measurable):
- No remaining text in either file claims P3 is unfixed/remainder/future-phase. Verified by grep for `future phase`, `remainder`, `not fixed here` over the two files → zero hits for P3.
- Lines 18-22 of docs/tech-debt.md byte-identical (B1/C1/D1 FIXED wording, light-mode, probes/manual, backend-pytest NOT-RUN).
- No code / test / frontend files changed. Diff of your commits touches ONLY the two docs files (+ your report file in a separate docs-only commit).
Verify: `cd frontend; npx vitest run tests/runs.test.jsx` (scoped) — 14/14 pass (proves you didn't touch tests). Do NOT run the full suite (ORCH gate does that).

## 4. Ownership
WRITE-SET (may edit): exactly `docs/tech-debt.md`, `docs/plans/2026-11-08-frontend-deferred-followups.md`, and your report `docs/agent-ops/20261108-p3-wave/reports/w1-impl/W1-IMPL-04-T-004.md`.
READ-ONLY: everything else (including frontend/views/RunDetails.jsx, frontend/tests/runs.test.jsx, frontend/format.js, 00-mission.md, 01-work-ledger.md, COMMS.md).
FORBIDDEN: any code, test, frontend file; any other docs file (including other docs/plans entries, docs/agent-ops files except your report); hotspot files beyond the two listed. Need something outside? Do NOT edit; post NEED and report DEFERRED-DEPENDENCY.
Ownership table already includes your two files (docs/agent-ops/20261108-p3-wave/ownership/W1.tsv) — do not modify it.

## 5. Parallel siblings this wave
None running in parallel (single-task wave). W1-CODER-001 (already done, f292a9c) owned RunDetails.jsx + runs.test.jsx — disjoint from you. No contracts change.

## 6. Skip list and known traps
- Already fixed, do NOT redo: A1 (092e800), B1 (c2dd5db), B2 (64c99f8), C1 (87a6f08), D1 (736339a), E (6c72d75), P3 code (f292a9c).
- False leads: none. Known: `runs.test.jsx` Progress-poll test is timing-sensitive (flaky, unrelated) — if your scoped run trips it, re-run once per STANDING-ORDERS §18 and record.
- Do NOT touch light-mode / probes / backend-pytest lines (accepted risk, manual/NOT-RUN).

## 7. Environment and tests
Scoped command only: `cd frontend; npx vitest run tests/runs.test.jsx` from repo root. Never run full suite, container restarts, shared-DB migrations, or bind ports. Kill any process you start. No secrets/PII.

## 8. Deliverables
Report: docs/agent-ops/20261108-p3-wave/reports/w1-impl/W1-IMPL-04-T-004.md (start NOW, append as you work; ORCH-DIGEST block first per template).
Commits (explicit paths only, verify branch first: `git branch --show-current` = frontend-ui-round2):
1. Code (docs) commit: `git add -- docs/tech-debt.md docs/plans/2026-11-08-frontend-deferred-followups.md` then `git commit -m "..." -- <paths>` with trailers Task: T-004 / Agent: W1-IMPL-04 / Wave: 1 / Report: ... (follow repo convention: `docs: ...`).
2. Report commit: separate docs-only commit with the report path, listing code commit SHA in body.
Final message (≤ 8 lines): STATUS | agent | task | report path | commit SHAs | blockers.

## 9. Role-specific notes (implementer)
Root cause is docs staleness only — no code logic to change (investigation explicitly rejected a code change as churn). Answer the long-run test in your report (Source/Load/Hostile/Operability/Reversal — for a docs edit, operate at the "drift" level: what stops the next doc going stale?). Stop and report BLOCKED if: an edit outside the write-set seems needed, or the plan contradicts the code.
