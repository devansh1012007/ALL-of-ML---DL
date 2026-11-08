# Brief — W1-TREV-01 (test reviewer) · V-103+V-104

Read-only. Write ONLY docs/agent-ops/20261109-playwright-verify/reports/w1-review/TREV-W1-IMPL-01.md. Do NOT edit/commit.
Blind: frontend/tests/auth.test.jsx (new branches), frontend/tests/static.test.js (new pin). Scoped run: cd frontend; npx vitest run tests/auth.test.jsx tests/static.test.js (record actual). Reversal: discriminating (409-neg, 429, network, 500/502) fail pre-fix; 400/401 guard-rails pass both ways; verify old :201-232 edited in place preserving guard + self-check. Template review-tests.md (ORCH-DIGEST first). Verdict APPROVE/APPROVE-WITH-CHANGES/REJECT.
