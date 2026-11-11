# Brief — W1-IMPL-02 (coder) · V-104 invite overflow-wrap

## 1. Role and mission
Implement V-104 exactly per docs/plans/2026-11-09-playwright-verify.md (Wrap A) + INV-aria-wrap.md §2. Branch frontend-ui-round2.

## 2. Required reading
1. docs/agent-ops/20261109-playwright-verify/templates/STANDING-ORDERS.md
2. docs/plans/2026-11-09-playwright-verify.md (FULL)
3. docs/agent-ops/20261109-playwright-verify/reports/w0-investigation/INV-aria-wrap.md §2 (exact point + test plan)
4. docs/agent-ops/20261109-playwright-verify/reports/w1-review/PLAN-W1-PLAN-01.md (F-04 closure rule, F-10)
5. Code: frontend/styles.css:310, frontend/AdminScreen.jsx:554-556, frontend/tests/static.test.js (T-303 describe)

## 3. Task and acceptance criteria
- styles.css: add `.admin-invite-code-text { min-width: 0; overflow-wrap: anywhere; }` next to :310 (precedent-paired; anywhere NOT break-all).
- AdminScreen.jsx:556 code div → `text-sm tabular-nums text-accent admin-invite-code-text`; wrapper :555 → add `min-w-0`.
- static.test.js: extend T-303 describe with pin (rule regex + AdminScreen contains class; self-check pre-fix literal fails pin).
- Scoped: `npx vitest run tests/static.test.js` green. Playwright hostile ATTEMPT (route-mock `/api/v1/me`→admin + invites POST 64/256-char at 390; short 16-char heights unchanged via getBoundingClientRect if runnable). If NOT-RUN (MCP/seed infeasible), close as static-only + name follow-up owner (future backend-up run), NOT as rendered-verified.

## 4. Ownership
WRITE-SET: exactly frontend/styles.css, frontend/AdminScreen.jsx, frontend/tests/static.test.js, report docs/agent-ops/20261109-playwright-verify/reports/w1-impl/W1-IMPL-02-V104.md. READ-ONLY else. FORBIDDEN: AuthView.jsx, auth.test.jsx, tailwind.config.js. Sibling W1-IMPL-01 owns AuthView+auth.test.

## 5. Commits
Code commit first (Task/Agent/Wave/Report trailers), then report docs-only commit listing SHA. Explicit paths. Verify branch.
