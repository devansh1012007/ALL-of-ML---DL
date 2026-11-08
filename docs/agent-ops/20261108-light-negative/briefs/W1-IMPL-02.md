# Brief — W1-IMPL-02 (coder) · wave 1 · run 20261108-light-negative

## 1. Role and mission
Mission: D1 — make the test-count genealogy on docs/tech-debt.md:17 unambiguous (115/115 at 2502fd9; +2 P3 tests → 117/117 at gate). The line today carries both counts with neither qualified by its commit, so a reader can't tell which is current. Failure mode to avoid: touching any other line (especially 18-22 B1/C1/D1/light-mode/probes) or changing the A1/B2/E citations by even one byte.
Your role: coder (docs task). Branch: frontend-ui-round2. Working dir: D:\dev work\coding\Projects\ALL-of-ML---DL.

## 2. Required reading (in this order)
1. docs/agent-ops/20261108-light-negative/templates/STANDING-ORDERS.md (binding)
2. docs/agent-ops/20261108-light-negative/00-mission.md
3. Investigation report docs/agent-ops/20261108-light-negative/reports/w0-investigation/INV-negative-counts.md (section "D1" §1 — contains the exact replacement line) — your primary spec
4. docs/tech-debt.md (full — see line 17 + forbidden zone 18-22)
5. Template: docs/agent-ops/20261108-light-negative/templates/report-implementation.md
6. COMMS.md

## 3. Task and acceptance criteria
Task T-103 (SURFACE, docs-only). Recommended approach (INV §D1 Option A):
- Replace line 17 with the exact proposed text: header becomes `(FIXED 2026-11-08, `frontend-ui-round2` 115/115 at 2502fd9; +2 P3 tests → 117/117 at gate)` and the tail retains P3 FIXED at f292a9c with NO duplicated count. Keep citations `092e800`/`64c99f8`/`6c72d75`/`f292a9c` and all FIXED dates verbatim. (Copy the line from the investigation report verbatim to avoid drift; if the report text and current file differ in any citation, STOP and report BLOCKED with the discrepancy — do not guess.)
Acceptance (measurable):
- Line 17 reads `115/115 at 2502fd9; +2 P3 tests → 117/117 at gate` in the header; no `117/117` remains in the tail.
- `git diff -U0 docs/tech-debt.md` shows exactly ONE hunk (line 17). Lines 18-22 byte-identical.
- Diff touches ONLY docs/tech-debt.md (+ your report in a separate commit). No code, tests, or other docs.
Verification: `git diff --stat docs/tech-debt.md` = 1 insertion, 1 deletion. No test run needed (docs have no executable effect); do NOT run the full suite. A scoped diff-based check IS required (above).

## 4. Ownership
WRITE-SET: exactly docs/tech-debt.md and your report docs/agent-ops/20261108-light-negative/reports/w1-impl/W1-IMPL-02-T-103.md.
READ-ONLY: everything else. FORBIDDEN: any code/test/frontend file, styles.css, RunDetails.jsx, other docs files. Need something outside? Post NEED; report DEFERRED-DEPENDENCY. Ownership table already lists you — do not modify it.

## 5. Parallel siblings this wave
W1-IMPL-01 owns RunDetails.jsx + runs.test.jsx (T-102) — disjoint from you. tech-debt is a hotspot but you are its single writer this wave.

## 6. Skip list and known traps
- Do NOT reword lines 18-22, the Round-1 entries (5-12), or the light-mode/probe/backend-pytest lines. Do NOT add a light-mode deferral note (tracks W2 separately).
- If the file's line 17 doesn't match the "verbatim line 17" quote in the investigation, STOP and BLOCKED (expect: the coder of 6409d0e already applied a version — verify before writing).

## 7. Environment and tests
No test/build commands needed or wanted for a docs one-liner (do not run full suite — ORCH gate owns that). Kill processes. No secrets/PII.

## 8. Deliverables
Report: docs/agent-ops/20261108-light-negative/reports/w1-impl/W1-IMPL-02-T-103.md (start NOW; ORCH-DIGEST first). Commits (verify `git branch --show-current` = frontend-ui-round2 first, explicit paths only): 1) docs commit with trailers Task/Agent/Wave/Report (follow repo `docs:` convention); 2) separate docs-only report commit listing the code SHA.
Final message ≤8 lines: STATUS | W1-IMPL-02 | T-103 | report path | commit SHAs | blockers.

## 9. Role notes (coder)
Root cause is prose ambiguity from two dated counts appended at different commits. Answer the long-run test at the drift level (what stops the next count going stale?). Stop + BLOCKED if the verbatim line check fails.
