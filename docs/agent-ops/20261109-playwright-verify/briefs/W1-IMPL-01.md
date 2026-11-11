# Brief — W1-IMPL-01 (coder) · V-103 status-mapped aria

## 1. Role and mission
Implement V-103 exactly per docs/plans/2026-11-09-playwright-verify.md (Resolved + Phases). Whitelist rule: `409→username-only; 400→both; else→describedby-only` (else = 403,404,405,422,401,429,network/undefined,>=500). User-confirmed 403→describedby-only. Branch frontend-ui-round2.

## 2. Required reading
1. docs/agent-ops/20261109-playwright-verify/templates/STANDING-ORDERS.md
2. AGENTS.md frontend conventions
3. docs/plans/2026-11-09-playwright-verify.md (FULL — Decisions + Phases + Acceptance)
4. docs/agent-ops/20261109-playwright-verify/reports/w0-investigation/INV-aria-wrap.md §1 (exact state shape) + INV-rendered-verify.md §1 (baseline behavior)
5. docs/agent-ops/20261109-playwright-verify/reports/w1-review/PLAN-W1-PLAN-01.md (F-01..F-10)
6. Code: frontend/views/AuthView.jsx, frontend/components/shared.jsx:200-240, frontend/tests/auth.test.jsx, frontend/tests/helpers.jsx:481-525

## 3. Task and acceptance criteria
- State: `error: string|null` (unchanged) + `errorStatus: number|null|undefined` (`null`=none initial, `undefined`=network/no-status). `handleSubmit` clears BOTH (`setError(null); setErrorStatus(null)`). Catch: `setError(...)` unchanged text mapping + `setErrorStatus(err.status ?? null)`?? — careful: network has NO status → store `undefined`. NEVER string-parse messages.
- Helper: pure `ariaFor(status)` inside AuthView module (test-through-DOM): 409→{uIn:true,pIn:false,uDe:true,pDe:false}; 400→{true,true,true,true}; else→{false,false,true,true}. Attrs: `aria-invalid={error && xIn ? true : undefined}`, `aria-describedby={error && xDe ? 'auth-error' : undefined}`. Never `false`. Alert `id="auth-error"` unchanged.
- Tests (auth.test.jsx): edit :201-232 IN PLACE (preserve pre-submit guard :184-199 + bare-input self-check :196-198): network→describedby-only; ADD register-mode 409 (fail {'/api/v1/register':{status:409}} → username-only, password-negative absent); 429 login→describedby-only; 502/500→describedby-only; 400→both guard-rail; 403→describedby-only; invariant: every present describedby resolves to alert. helpers.jsx UNTOUCHED (already supports fail status/network).
- Scoped: `npx vitest run tests/auth.test.jsx` green; discriminating tests fail pre-fix (prove by running against stashed pre-fix or reason + mutation craft; record evidence; do not break prod permanently).

## 4. Ownership
WRITE-SET: exactly frontend/views/AuthView.jsx, frontend/tests/auth.test.jsx, report docs/agent-ops/20261109-playwright-verify/reports/w1-impl/W1-IMPL-01-V103.md. READ-ONLY else. FORBIDDEN: styles.css, AdminScreen.jsx, static.test.js, shared.jsx, helpers.jsx. Parallel sibling W1-IMPL-02 owns styles+AdminScreen+static.

## 5. Playwright spot-check (best effort)
If MCP available via execute→tools.playwright.*, attempt 429/network describedby-only spot on :3103 preview; if MCP dead, mark NOT-RUN honestly with `search→0` evidence. Do NOT block the wave on it.

## 6. Commits
Code commit first (Task/Agent/Wave/Report trailers), then report docs-only commit listing SHA. Explicit paths. Verify branch.
