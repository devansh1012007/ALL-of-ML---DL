# Brief — W0-INV-01 (investigator) · wave 0 · run 20261109-playwright-verify

## 1. Role and mission
READ-ONLY investigator. Mission: run the missing W1 rendered re-verify with Playwright (Auth matrix after `f53e4ba`) + probe whether the 3 deferred hypotheses (ResultLine clamp, header gap-x-8, Compare title-only hint) are renderable without a backend. No source edits. Write ONLY your report + screenshots under `docs/agent-ops/20261109-playwright-verify/screenshots/after/`.
Branch: frontend-ui-round2. Dir: D:\dev work\coding\Projects\ALL-of-ML---DL.

## Playwright via execute (CRITICAL)
Call ONLY inside `execute` as JS: `await tools.playwright.browser_navigate({url})`, `browser_snapshot`, `browser_take_screenshot({filename, fullPage})`, `browser_evaluate({function})`, `browser_resize({width,height})`, `browser_click({element,target})`, `browser_press_key`, `browser_console_messages`, `browser_wait_for`. Discover with `search({query,namespace:"playwright"})` inside `execute` first. Screenshot filenames relative to workspace root — use `docs/agent-ops/20261109-playwright-verify/screenshots/after/<name>.png`.

## 2. Required reading (in order)
1. docs/agent-ops/20261109-playwright-verify/templates/STANDING-ORDERS.md (binding)
2. AGENTS.md frontend conventions
3. docs/agent-ops/20261109-playwright-verify/00-mission.md, 01-work-ledger.md, COMMS.md
4. docs/agent-ops/20261109-playwright-verify/templates/report-investigation.md (ORCH-DIGEST first)
5. Prior run: docs/agent-ops/20261109-playwright-design/reports/w0-investigation/INV-playwright-audit.md (W0 matrix + probes to re-run), docs/plans/2026-11-09-playwright-fine-tune.md
6. Code: frontend/index.html, frontend/views/AuthView.jsx, frontend/styles.css, frontend/App.jsx

## 3. Task and acceptance criteria
Task V-101. Server: `cd frontend; npm run build` (once) + `npx vite preview --port 3103 --host 127.0.0.1` background; kill after. Backend on 8010 is down — verify with a probe and document; do NOT start backend, do NOT fake data.
Matrix (Auth × 1280×800 & 390×844 × dark/light):
- Console: `browser_console_messages` error — expect favicon 404 GONE (icon link present). List all errors.
- Favicon: `document.querySelector('link[rel=icon]')` present + href starts `data:image/svg+xml`.
- Theme: toggle flips `dataset.theme` + meta + localStorage both directions; both themes screenshot.
- Overflow: scrollWidth<=clientWidth, list `right>innerWidth` elements (expect 0).
- Contrast rendered: h1/muted/primary via getComputedStyle vs shipped triples (≥4.5).
- Submit error (backend down → /token refused): alert `role=alert` + `id=auth-error` present; BOTH inputs `aria-invalid=true` + `aria-describedby=auth-error` (current both-fields behavior — record before V-103 changes it); screenshot.
- Tap targets: `.link` 24px recorded (accepted, no defect); inputs/primary ~40px re-measure.
- Focus: Tab-walk 5 Auth controls, visible ring recorded.
Deferred probes (ResultLine/header/Compare): attempt to reach via navigation; if auth-gated (NOT-RENDERABLE), mark honestly with the exact wall (auth gate code) and stop — no fake data.
Deliverable: defect-or-clean table with evidence (filenames, evaluate outputs, file:line). Classify SURFACE/DEEP. Long-run test (Source/Load/Hostile/Operability/Reversal) for the verify step.

## 4. Ownership
READ-ONLY except report + screenshots. No commits.

## 5. Environment
Kill vite. No full suite/build beyond the one proxy build. No secrets/PII.

## 6. Deliverables
Report NOW (append as you work; ORCH-DIGEST first). Final ≤8 lines: STATUS | agent | report path | screenshots | verdicts | blockers.
