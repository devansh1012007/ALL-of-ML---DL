# Brief — W2-TREV-01 (test reviewer) · wave 2 · run 20261108-light-negative

## 1. Role and mission
You independently judge the TEST side of T-101 light mode (`21f65c13`): new `frontend/tests/theme.test.jsx` (19 tests) + additive `static.test.js` ratio/structure/invariance guards. Your job: independently confirm fail-before/pass-after for the new tests (reversal), determinism/isolation, no over-mocking, and that the ratio guards genuinely compute luminance (not presence-only theater). Failure mode: guards that pass on wrong values, or DOM tests that assert the toggle exists but never prove it flips/persists.

## 2. Required reading
1. docs/agent-ops/20261108-light-negative/templates/STANDING-ORDERS.md (binding)
2. docs/agent-ops/20261108-light-negative/templates/review-tests.md (report template — ORCH-DIGEST first)
3. docs/agent-ops/20261108-light-negative/briefs/W2-IMPL-01.md (test requirements)
4. Blind pass: frontend/tests/theme.test.jsx (full), frontend/tests/static.test.js (new: ratio/structure/dark-invariance guards), frontend/components/theme.jsx
5. THEN read: implementation report W2-IMPL-01-T-101.md (claims audit after blind pass)

## 3. Task and acceptance criteria
Run scoped checks (record actual output): `cd frontend; npx vitest run tests/theme.test.jsx` and `npx vitest run tests/static.test.js`.
Reversal (reason or demonstrate): do the guards FAIL if the light block is deleted? Do they fail if one light value is swapped to near-white? Does the toggle test fail if App renders no toggle? Do resolution/hostile tests fail if resolveTheme is unguarded (`matchMedia` missing / storage throws)?
Check: matchMedia stubbed per test (both preferences)? afterEach removes prime_theme + dataset.theme (helpers teardown only prime_token)? Hostile values covered (XSS/10KB/unicode/empty/"LIGHT")? Toggle-side-effect test asserts attribute+meta+storage agreement AND sign-out does NOT clear prime_theme? Ratio math correct (WCAG formula, composites for badges/confusion, raised/canvas excluded as documented)?
Verdict APPROVE | APPROVE-WITH-CHANGES | REJECT. Write to: docs/agent-ops/20261108-light-negative/reports/w2-review/TREV-W2-IMPL-01.md. Read-only; do NOT edit/commit.

## 4. Ownership
READ-ONLY. Scoped single-file vitest only (theme.test.jsx, static.test.js); never full suite/build (ORCH gate owns those).

## 5. Deliverables
Report first (append as you work; ORCH-DIGEST first). Final message ≤8 lines: STATUS | agent | report path | verdict | counts | blockers.
