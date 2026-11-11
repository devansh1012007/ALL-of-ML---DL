# Brief — W1-TREV-01 (test reviewer) · wave 1 · run 20261109-playwright-design

## 1. Role and mission
Independent test-quality audit of W1 additions (6 static + 2 auth tests, commit f53e4ba). Prove reversal, determinism, non-over-mocking.

## 2. Required reading
1. docs/agent-ops/20261109-playwright-design/templates/STANDING-ORDERS.md (binding)
2. docs/agent-ops/20261109-playwright-design/templates/review-tests.md (ORCH-DIGEST first)
3. Blind: frontend/tests/static.test.js (new: T-301..T-303 pins), frontend/tests/auth.test.jsx (new: T-304), frontend/views/AuthView.jsx
4. Then: W1-IMPL-01-T301-T304.md §7/§11 claims; docs/plans/2026-11-09-playwright-fine-tune.md acceptance

## 3. Task and acceptance criteria
One scoped run: cd frontend; npx vitest run tests/static.test.js tests/auth.test.jsx (record actual). Reversal: each pin fails pre-fix (coder claims 7 failed/44 passed — verify reasonableness or demonstrate). Check: aria test asserts aria-invalid true + describedby == alert id + target === alert; pins targeted not whole-file (no false-trip on legit text-lg elsewhere); determinism (sync, no timers); no mocking of unit under test. Verdict APPROVE/APPROVE-WITH-CHANGES/REJECT. Write to docs/agent-ops/20261109-playwright-design/reports/w1-review/TREV-W1-IMPL-01.md. Read-only; scoped single-file only.

## 4. Deliverables
Final ≤8 lines: STATUS | agent | report path | verdict | counts | blockers.
