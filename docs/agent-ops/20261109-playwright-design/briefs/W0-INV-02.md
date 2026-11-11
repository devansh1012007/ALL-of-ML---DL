# Brief — W0-INV-02 (investigator) · wave 0 · run 20261109-playwright-design

## 1. Role and mission
You are a READ-ONLY investigator. Mission: audit the code-level design surface (tokens, components, a11y, responsive) to cross-check what Playwright will find rendered, and to give the fine-tune wave an exact file:line fix map. You edit NO source files. You may write ONLY: `docs/agent-ops/20261109-playwright-design/reports/w0-investigation/INV-code-design.md`.
Branch: `frontend-ui-round2`. Working dir: `D:\dev work\coding\Projects\ALL-of-ML---DL`.

## 2. Required reading (in this order)
1. `docs/agent-ops/20261109-playwright-design/templates/STANDING-ORDERS.md` (binding)
2. `AGENTS.md` (frontend conventions)
3. `docs/agent-ops/20261109-playwright-design/00-mission.md`, `01-work-ledger.md`, `COMMS.md`
4. `docs/agent-ops/20261109-playwright-design/templates/report-investigation.md` (your template — ORCH-DIGEST first)
5. `frontend/styles.css` (all lines — 14-token dark/light blocks, component classes, badges, focus `:focus-visible`, buttons), `frontend/tailwind.config.js` (token mapping, content globs), `frontend/index.html` (theme init)
6. `frontend/App.jsx`, `frontend/components/theme.jsx`, `frontend/views/*.jsx` (AuthView, RunsDashboard, RunDetails, NewJob, PredictPanel, ModelsCatalog, AdminScreen), `frontend/components/metrics.jsx`, `frontend/components/shared.jsx`
7. `frontend/tests/static.test.js` (what guards exist — what is unguarded), `docs/plans/2026-11-08-light-mode.md` (design intent + exceptions: raised/canvas, accent-ink white)

## 3. Task and acceptance criteria
Task T-202. Method: grep counts + `path:line` evidence (`[RAN grep ...]`), no browser needed.
- Token census: any remaining hardcoded hex / `dark:` / palette utilities / arbitrary values (`bg-[#..]`, `text-[..]`) in shipped JSX/CSS? (Prior census said only NewJob:678 outlier, now fixed — verify, don't trust.)
- Per-component inventory: for each view, which tokens/classes it uses; any component that would break in light vs dark (e.g. `ring-canvas` noted as cosmetic in light)? Potential fine-tune sites: spacing (`gap-*`, `p-*` inconsistencies), tap-target sizing, table overflow (`overflow-x-auto` present?), card grids at 390px, focus styles (`.btn` vs `.btn-quiet` vs native buttons).
- Accessibility patterns: `aria-pressed` toggle, nav landmarks, form labels, `role=status` announcements — where missing?
- Responsive risks: fixed widths, `min-w-*`, non-wrapping flex rows, tables without scroll containers.
- Test gaps: what do jsdom tests NOT cover that Playwright can (rendered contrast, overflow, focus)? Name the gaps.
Deliverable: defect/fine-tune candidate table (severity, file:line, evidence, proposed minimal fix + WRITE-SET, confidence FACT vs INFERENCE). Classify SURFACE vs DEEP per candidate. Long-run test (Source/Load/Hostile/Operability/Reversal) per candidate class. DO NOT run the full suite/build. Single-file scoped vitest allowed.

## 4. Ownership
READ-ONLY except your report. Do NOT commit. Need something outside? `DEFERRED-DEPENDENCY`.

## 5. Environment
Scoped greps/reads only. Kill processes. No secrets/PII.

## 6. Deliverables
Report first (ORCH-DIGEST first; append as you work). Final ≤8 lines: STATUS | agent | report path | candidates count | top risk | blockers.
