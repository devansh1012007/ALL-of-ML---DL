# Brief — W1-TREV-01 (test reviewer) · wave 1 · run 20261108-p3-wave

## 1. Role and mission
You independently judge whether the TEST side of T-004 is sound: T-004 changed no tests, but it claims "117/117 at gate" and pins "+2 tests (garbage-hide, zero-render)". Your job: independently confirm those 2 P3 tests exist, that they genuinely fail without the f292a9c fix (reversal), and that no test file was silently degraded in the wave. Failure mode: a docs claim about test coverage that the actual tests don't support.

## 2. Required reading
1. docs/agent-ops/20261108-p3-wave/templates/STANDING-ORDERS.md (binding)
2. docs/agent-ops/20261108-p3-wave/templates/review-tests.md (your report template — mirror ORCH-DIGEST)
3. docs/agent-ops/20261108-p3-wave/briefs/W1-IMPL-04.md (acceptance criteria)
4. frontend/tests/runs.test.jsx:571-619 (P3 describe block)
5. frontend/views/RunDetails.jsx:214-238 (code under test)
6. Implementer report docs/agent-ops/20261108-p3-wave/reports/w1-impl/W1-IMPL-04-T-004.md (read AFTER blind pass)

## 3. Task and acceptance criteria
Blind pass: read the P3 tests + code, run `cd frontend; npx vitest run tests/runs.test.jsx` (scoped single file — allowed; repo root cwd) and record actual result. Reason (or demonstrate in a temp worktree if cheap) whether the garbage-hide test fails if the f292a9c guard is removed, and whether the zero-render test passes on both versions (guard-rail). Check git diff of the wave (WAVE_BASE_SHA=69fe44e — `git diff 69fe44e..HEAD -- frontend/` must be EMPTY; any test change here is a finding).
Verdict APPROVE | APPROVE-WITH-CHANGES | REJECT with severity findings. Missing tests for behavior change = automatic MAJOR — but note this task changed no behavior (docs only), so assess whether a test was OWED (none, per investigation).

## 4. Ownership
READ-ONLY on source. Write ONLY: docs/agent-ops/20261108-p3-wave/reports/w1-review/TREV-W1-IMPL-04.md. Do NOT edit source or commit.

## 5. Deliverables
Report first (append as you work; ORCH-DIGEST first). Final message ≤8 lines: STATUS | agent | report path | verdict | counts | blockers. Scoped checks only (single-file vitest); never full suite/build (ORCH gate owns those).
