# Brief — W1-IMPL-01 (coder) · wave 1 · run 20261109-playwright-design

## 1. Role and mission
Mission: implement the reviewed fine-tune batch (T-301..T-304 decisions in docs/plans/2026-11-09-playwright-fine-tune.md — read it fully, decisions section is binding). Small, evidence-driven polish; no redesign. Failure mode to avoid: touching file-buttons (DROPPED), raising 24px floors (ACCEPTED), inventing aria beyond Auth, or scope creep into ResultLine/header/Compare.
Branch: frontend-ui-round2. Working dir: D:\dev work\coding\Projects\ALL-of-ML---DL.

## 2. Required reading (in this order)
1. docs/agent-ops/20261109-playwright-design/templates/STANDING-ORDERS.md (binding)
2. AGENTS.md (frontend conventions)
3. docs/plans/2026-11-09-playwright-fine-tune.md (Decisions + phases + acceptance, split by surface)
4. INV reports: docs/agent-ops/20261109-playwright-design/reports/w0-investigation/INV-playwright-audit.md, INV-code-design.md
5. Planner review: docs/agent-ops/20261109-playwright-design/reports/w1-review/PLAN-W1-PLAN-01.md (B1 overruled note; M1/M3 resolutions in plan)
6. Code: frontend/index.html, frontend/views/NewJob.jsx, frontend/AdminScreen.jsx, frontend/styles.css, frontend/views/AuthView.jsx
7. Tests: frontend/tests/static.test.js, frontend/tests/auth.test.jsx, frontend/tests/newjob.test.jsx, frontend/tests/admin.test.jsx

## 3. Task and acceptance criteria
- **T-301 favicon:** inline data-URI SVG `<link rel="icon">` in index.html after meta color-scheme (L5), before init script (L6); do not move init script. Static pin: icon link present.
- **T-302 type:** NewJob.jsx:660 → keep `font-semibold text-strong mb-4`, drop emoji + `text-lg` (inherit h3). AdminScreen.jsx:670 → bare `<h1>` (drop classes, do not add mb-1). Static pins: no 📊 in shipped JSX; NewJob h3 no `text-lg`; Admin h1 no `text-2xl`/`font-bold`.
- **T-303 reduced:** AdminScreen.jsx:628-630 audit truncate → add `title={JSON.stringify(event.detail)}` (+ static pin `title=` on audit truncate). styles.css:310 `.admin-invite-code` → add `flex-wrap: wrap` (+ static pin). DO NOT touch file inputs (NewJob.jsx:431, PredictPanel.jsx:232).
- **T-304 Auth aria (DEEP, Auth only):** AuthView.jsx fields → add `aria-invalid` + `aria-describedby` wired to failed-submission error (form-level alert at :59; associate per-field for the invalid field(s); NewJob/Predict deferred). Add `auth.test.jsx` tests (failed submit exposes aria-invalid="true" + aria-describedby; fails if attrs removed). Playwright error-state already proven in W0.
- **Acceptance:** Auth Playwright: console clean, aria association rendered, contrast still ≥4.5. Static/jsdom: full `npm test` green + `npm run build` green; greps 0 emoji / 0 palette utilities / icon present. No floor/token/config edits.

## 4. Ownership
WRITE-SET: exactly frontend/index.html, frontend/views/NewJob.jsx, frontend/AdminScreen.jsx, frontend/styles.css, frontend/views/AuthView.jsx, frontend/tests/static.test.js, frontend/tests/auth.test.jsx, and your report docs/agent-ops/20261109-playwright-design/reports/w1-impl/W1-IMPL-01-T301-T304.md. READ-ONLY: everything else. FORBIDDEN: frontend/views/PredictPanel.jsx, RunsDashboard.jsx, RunDetails.jsx, App.jsx, components/theme.jsx, tailwind.config.js. Need outside? NEED + DEFERRED-DEPENDENCY.

## 5. Tests / verification
Scoped: `npx vitest run tests/static.test.js tests/auth.test.jsx tests/newjob.test.jsx tests/admin.test.jsx` then ONE full `npm test` + `npm run build` at end (single-writer). Playwright Auth check only (vite preview :3101, dark+light, console + aria). Kill processes. Prove each static pin fails pre-fix (mutation check).

## 6. Commits
Code commit(s) first (Task/Agent/Wave/Report trailers), then separate docs-only report commit listing SHAs. Explicit paths only. Verify branch before committing.

## 7. Deliverables
Report first (ORCH-DIGEST first, finding-by-finding). Final ≤8 lines: STATUS | agent | report path | commit SHAs | blockers.
