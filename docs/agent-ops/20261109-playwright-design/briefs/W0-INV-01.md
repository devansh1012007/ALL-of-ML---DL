# Brief — W0-INV-01 (investigator) · wave 0 · run 20261109-playwright-design

## 1. Role and mission
You are a READ-ONLY investigator. Mission: audit the REAL RENDERED UI with Playwright MCP and produce a concrete defect list (with evidence) that a fine-tune wave will fix. You edit NO source files. You may write ONLY: your report `docs/agent-ops/20261109-playwright-design/reports/w0-investigation/INV-playwright-audit.md` and screenshots under `docs/agent-ops/20261109-playwright-design/screenshots/before/`.
Branch: `frontend-ui-round2`. Working dir: `D:\dev work\coding\Projects\ALL-of-ML---DL`.

## How to use Playwright MCP (CRITICAL)
Playwright tools are NOT direct tools. You call them ONLY inside the `execute` tool as JavaScript:
`await tools.playwright.browser_navigate({url: "..."})`, `await tools.playwright.browser_snapshot({})`, `await tools.playwright.browser_take_screenshot({filename: "...", fullPage: true})`, `await tools.playwright.browser_evaluate({function: "() => { ... }"})`, `await tools.playwright.browser_resize({width: 390, height: 844})`, `await tools.playwright.browser_click({element: "...", target: "..."})`, `await tools.playwright.browser_press_key({key: "Tab"})`, `await tools.playwright.browser_console_messages({level: "error"})`.
Discover the full set first with `search({query: "...", namespace: "playwright"})` inside `execute` (same mechanism). Screenshots: `browser_take_screenshot` saves relative to workspace root — use paths like `screenshots/before/runs-desktop-dark.png` (ORCH created `docs/agent-ops/20261109-playwright-design/screenshots/before/`; use paths under that dir).
App URL: frontend dev server (below) serves the SPA at `http://localhost:3101/`. The SPA requires auth + API (localhost:8010 backend). If backend is not running, most views will show auth/loading states — document exactly what rendered (do NOT fake data). At minimum: Auth sign-in surface + any view reachable without backend, plus console errors. If backend is unreachable, say so and audit what IS renderable.

## 2. Required reading (in this order)
1. `docs/agent-ops/20261109-playwright-design/templates/STANDING-ORDERS.md` (binding)
2. `AGENTS.md` (frontend conventions: no router, `navigate(view)`, dual-shell AuthView vs MainApp, token colors)
3. `docs/agent-ops/20261109-playwright-design/00-mission.md`, `01-work-ledger.md`, `COMMS.md`
4. `docs/agent-ops/20261109-playwright-design/templates/report-investigation.md` (your report template — ORCH-DIGEST first)
5. `frontend/styles.css`, `frontend/tailwind.config.js`, `frontend/App.jsx`, `frontend/index.html`, `frontend/vite.config.js` (how to run: `npm run build` + `vite preview` or `npm run dev` on port 3101)
6. `frontend/views/` list (RunsDashboard, RunDetails, NewJob, PredictPanel, ModelsCatalog, AdminScreen, AuthView)

## 3. Task and acceptance criteria
Task T-201. Audit matrix (each cell: screenshot + snapshot + defects):
- Surfaces: Auth/sign-in, Runs list, RunDetails, NewJob, Predict, Models catalog, Admin (if reachable).
- Viewports: desktop 1280x800, mobile 390x844. Themes: dark (default) + light (click "Switch to light mode" toggle, verify `documentElement.dataset.theme === "light"`).
- Probes per surface (via `browser_evaluate` for DOM/computed-style checks + snapshot + screenshot):
  - Horizontal overflow: `document.documentElement.scrollWidth <= clientWidth`? List any overflowing elements (`el.getBoundingClientRect().right > innerWidth`).
  - Tap targets: buttons/links < 40px height (list selector + size).
  - Contrast (rendered): sample body text vs backgrounds via `getComputedStyle` — do NOT recompute the static 27-pair table, verify rendered values match shipped triples.
  - Focus: Tab through header/nav/toggle; is focus visible (outline)? Record `document.activeElement` sequence.
  - Spacing/alignment: note visibly inconsistent gaps/padding (with screenshot region), truncated text, overlapping, misaligned columns (Runs table, metrics cards).
  - Console errors: `browser_console_messages` level error — list.
  - Empty/loading states if backend missing: describe honestly.
Deliverable: defect table (severity BLOCKER/MAJOR/MINOR/NIT × surface × viewport × theme) with Playwright evidence (screenshot filename, snapshot excerpt, evaluate output) + file:line pointer where you can infer the source. Classify SURFACE vs DEEP. Propose WRITE-SET per defect (which files a fix would touch) and prioritize (must-fix vs polish). Long-run test (Source/Load/Hostile/Operability/Reversal) for the audit itself.

## 4. Ownership
WRITE-SET: only your report + screenshots under `docs/agent-ops/20261109-playwright-design/screenshots/before/`. Everything else READ-ONLY. FORBIDDEN: any source edit, any commit (ORCH commits reports). Need something outside? Post NEED via report `DEFERRED-DEPENDENCY`.

## 5. Environment and commands
- Start server: `cd frontend; npm run build` (once) then `npx vite preview --port 3101 --host 127.0.0.1` as background, OR `npm run dev -- --port 3101 --host 127.0.0.1`. Kill it when done. Do NOT use port 3000/8010 (shared). Do NOT run backend, migrations, containers.
- Scoped checks only; never the full test suite (ORCH owns gates). Kill processes. No secrets/PII.

## 6. Skip list / traps
- Do NOT redesign, do NOT edit code, do NOT claim a defect from code reading alone — Playwright evidence required for rendered claims.
- Do NOT use `browser_run_code_unsafe` unless needed (RCE-risky); prefer `browser_evaluate`.
- Auth: if you log in / seed data, document credentials used (test-only) and do NOT commit them. If backend is down, audit the auth surface honestly and mark data views NOT-RENDERABLE.

## 7. Deliverables
Report first (start NOW; ORCH-DIGEST first; append as you work). Final message ≤8 lines: STATUS | agent | report path | screenshots count | top defects | blockers.
