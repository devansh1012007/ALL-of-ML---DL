# Brief — W2-IMPL-01 (coder) · wave 2 · run 20261108-light-negative

## 1. Role and mission
Mission: implement T-101 light mode mechanically from the APPROVED design record (docs/agent-ops/20261108-light-negative/reports/w2-impl/W2-DEEP-01-T-101.md, D1-D7 + acceptance checklist — that report is your binding spec along with docs/plans/2026-11-08-light-mode.md). Zero design freedom left: copy the 14 light triples exactly, place the toggle exactly, pin the guards exactly. Failure mode to avoid: any palette "improvement" by eye, any component redesign, any touch of RunDetails.jsx / tailwind.config.js (both FORBIDDEN).
Your role: coder (implementation). Branch: frontend-ui-round2. Working dir: D:\dev work\coding\Projects\ALL-of-ML---DL.

## 2. Required reading (in this order)
1. docs/agent-ops/20261108-light-negative/templates/STANDING-ORDERS.md (binding)
2. AGENTS.md (frontend conventions: tailwind content globs, single SPA, no router)
3. docs/plans/2026-11-08-light-mode.md (THE spec §§1-7, incl. folded planner resolutions P-01..P-10 — acceptance criteria §5)
4. Design record: docs/agent-ops/20261108-light-negative/reports/w2-impl/W2-DEEP-01-T-101.md (D1-D7 + ACCEPTANCE CHECKLIST at the bottom — follow it line by line)
5. Template: docs/agent-ops/20261108-light-negative/templates/report-implementation.md (plus report-deepdive-addendum.md D1-D7 — you inherit the design; answer D1-D6 as-impl'd, D7 = probe outcome + follow-ups)
6. Code entry points: frontend/styles.css (all 323 lines), frontend/index.html, frontend/main.jsx, frontend/App.jsx, frontend/views/AuthView.jsx, frontend/views/NewJob.jsx:678 area, frontend/components/shared.jsx:150-200, frontend/tests/helpers.jsx:1030-1063, frontend/tests/static.test.js (guard style)
7. COMMS.md

## 3. Task and acceptance criteria
Task T-101-impl (DEEP, Phase 1+2 in one agent — the token census keeps it mechanical). Implementation order (design D5):
1. **styles.css:** add `[data-theme="light"]` block with EXACTLY the 14 design triples + `color-scheme: light` (verbatim from D2 §2.1). `:root` untouched (byte-identical values).
2. **index.html:** head init script (head, before stylesheet/module entries) with ONE outer try/catch, setting attribute+meta from one resolution; meta color-scheme starts at the resolved theme.
3. **components/theme.jsx (new):** `resolveTheme()` (guards: `typeof matchMedia === 'function'`, storage read in try/catch, fall-through dark), `applyTheme()` (attribute + meta + storage write in try/catch — write throw still flips in-memory), `toggleTheme()`, `ThemeToggle` (button aria-pressed, labels EXACTLY "Switch to light mode"/"Switch to dark mode" from design).
4. **App.jsx:** `App`-level theme state (holds dataset-derived theme), header toggle in the `ml-auto` cluster next to "Sign out", OUTSIDE `<nav>`.
5. **AuthView.jsx:** SAME `ThemeToggle` on the sign-in card.
6. **NewJob.jsx:678:** `text-orange-400` → `text-warn`. No `--warn-strong` (decision N).
7. **Tests:** `tests/theme.test.jsx` (new): resolution order (with `matchMedia` stubbed per test — jsdom lacks it), hostile stored values (XSS/10KB/unicode/empty/"LIGHT" → default, no element/script created, toggle still works), localStorage-throw fallback (no crash, in-memory flip), toggle side effects (attribute+meta+storage, sign-out does NOT clear prime_theme), afterEach removes `prime_theme` + `dataset.theme`. `tests/static.test.js` (ADDITIVE): structural (14 names + color-scheme: light), dark-invariance (14 :root triples == 85acdda literals), ratio guards (parse light triples, compute ratios for the D2 inventory, assert ≥ thresholds incl. accent-ink dual, badge composites; raised/canvas EXCLUDED as documented exception).
8. **Probe (impl-owned, production build per P-07):** `npm run build` + `vite preview`, manually load all 7 views + Admin at 390px + desktop in both themes, keyboard focus, stored-light no-flash on throttled reload. Record outcome (with screenshots described, or explicit NOT-RUN with reason) in docs/tech-debt.md as a light-mode entry (do NOT delete historical deferral lines; ADD the probe outcome line). If a component-level CSS fix beyond token values is demanded by the probe: token values only (no component class churn); if a token literally cannot fix a surface, STOP and report BLOCKED with the evidence (spec amendment needed).
Acceptance (measurable — spec §5 + design checklist):
- Dark default at 85acdda: 14 `:root` triples textually unchanged (automated by static guard).
- Every D2 ratio recomputable from shipped CSS (reviewer recomputes; ratio guards fail below threshold).
- Toggle: one click flips attribute+meta+storage, persists across reload, first paint matches (no flash, build+preview probe).
- `cd frontend; npm test` full green; `npm run build` green; §5.5 literal greps zero outside allowlisted styles.css:16-19 comments + tests.
- Hostile + throw tests pass. All new tests shown failing against pre-fix tree (attribute never set / toggle never rendered — prove for at least the toggle + hostile tests).

## 4. Ownership
WRITE-SET: exactly the 8 files in docs/agent-ops/20261108-light-negative/ownership/W2.tsv (styles.css, index.html, components/theme.jsx [new], App.jsx, views/AuthView.jsx, views/NewJob.jsx, tests/theme.test.jsx [new], tests/static.test.js) + docs/tech-debt.md (probe record only) + your report.
READ-ONLY: everything else. FORBIDDEN: frontend/views/RunDetails.jsx (T-102 territory → C1), frontend/tailwind.config.js (untouched per design), frontend/format.js, frontend/views/PredictPanel.jsx, RunsDashboard.jsx, ModelsCatalog.jsx, AdminScreen.jsx, metrics.jsx. Need something outside? Post NEED; report DEFERRED-DEPENDENCY.
Ownership tables already list you — do not modify them.

## 5. Parallel siblings this wave
None (single DEEP agent). W1 closed (RunDetails.jsx + tech-debt touched there — do NOT touch RunDetails; tech-debt probe line is the only W2 touch).

## 6. Skip list and known traps
- Do NOT: warn-strong token, tailwind darkMode, system-listener, cross-tab storage listener, warn-chip (T-102 done), wall_seconds, any palette "tweaks" beyond the design table. Any deviation = ESCALATE.
- `matchMedia` absent in jsdom (stub per test). helpers.jsx teardown removes only prime_token (afterEach must clean prime_theme + dataset.theme). `toggleTheme` writes must never go through innerHTML. localStorage access itself can throw (sandbox) → guard the READ.
- Sign-out must NOT clear prime_theme (existing `logout` already removes only prime_token — don't "fix" it).
- Smoke tests query `<nav>` by role/name — toggle stays outside `<nav>` or smoke breaks.
- Known flake: runs.test.jsx Progress-poll (pre-existing; re-run once + record).

## 7. Environment and tests
Scoped: single-file vitest (`npx vitest run tests/theme.test.jsx`, `tests/static.test.js`, `tests/smoke.test.jsx`); full `npm test` + `npm run build` only once at the end (W2 gate step — allowed since single-writer; don't parallelize with anything else). Probe: `vite preview` on a non-default port (e.g. 3100) — kill it when done. No DB/containers. Kill processes. No secrets/PII.

## 8. Deliverables
Report: docs/agent-ops/20261108-light-negative/reports/w2-impl/W2-IMPL-01-T-101.md (start NOW; ORCH-DIGEST first; D1-D7 as-impl'd + probe outcome). Commits (verify `git branch --show-current` = frontend-ui-round2 first, explicit paths only): 1) implementation commit (code+tests+tech-debt probe line) with trailers Task/Agent/Wave/Report; 2) separate docs-only report commit listing the code SHA.
Final message ≤8 lines: STATUS | W2-IMPL-01 | T-101-impl | report path | commit SHAs | probe result | blockers.

## 9. Role notes (coder)
Root cause of "no light UI" is the missing subsystem (palette + state + init) — you build it from the design, not by improvisation. Long-run test in report: hostile stored values ignored, storage throw falls through, attribute/meta/storage always agree, reversal = new guards fail on deletion/value-drift. Stop + BLOCKED if: a probe-revealed surface can't be fixed by token values, or any edit outside the write-set seems needed. PARTIAL ok; fake DONE never.
