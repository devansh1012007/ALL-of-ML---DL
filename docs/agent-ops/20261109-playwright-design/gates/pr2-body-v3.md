Frontend UI round 2 redesign — full redesign (R1–R6) plus deferred follow-ups A1/B1/B2/C1/D1/E and P3 "Took NaN s", with docs-close.

## Deferred follow-ups (this branch)
- A1: Invalid Date NaN guard in format.js (092e800)
- B1: Runs row link-based, mouse-only tr onClick removed (c2dd5db)
- B2: Runs tooltip via formatWhen (64c99f8)
- C1: Predict segmented Arrow/Home/End select-on-arrow (87a6f08)
- D1: RL env-id label seeded per-test + submit env_id pinned (736339a)
- E: RunDetails + quota residual date leaks (6c72d75)
- P3: RunDetails duration chip hides on NaN diff (null sentinel; valid 0s still renders "Took 0 s"), +2 tests (f292a9c)
- N1/D1: negative-diff hidden chip (ca5d950, +2 tests) + tech-debt 115→117 genealogy (9c73971)
- Light mode: [data-theme="light"] token inversion (14 design tokens), pre-paint init, App toggle (header + sign-in), NewJob tokenized (21f65c13 + 94963e6); dark default byte-identical
- Playwright fine-tune: favicon data-URI, NewJob emoji/h3 + Admin h1 type convergence, audit title + invite wrap, Auth aria-invalid/describedby (f53e4ba, +8 tests); file-buttons dropped, 24px floors accepted, backend-up 7-surface pass deferred (T-204)
- Docs-close: tech-debt + plan marked P3 FIXED at f292a9c (6409d0e)

## Verification
- Frontend: 162/162 Vitest green (11 files) + build 1671 modules green at HEAD (gate-w1-1.md, 20261109-playwright-design).
- Wave orchestrator runs `docs/agent-ops/20261108-p3-wave/`, `docs/agent-ops/20261108-light-negative/`, and `docs/agent-ops/20261109-playwright-design/` (W0 rendered audit 7 screenshots, planner review, independent code+test+final reviews all APPROVE).
- Production-build probe (light mode) passed in real Chrome (7 views, 390px+desktop, both themes) — evidence recorded described-only in docs/tech-debt.md.
- Backend pytest NOT-RUN (frontend-only diff). SR/NVDA pass NOT-RUN (jsdom limits) — accepted risk recorded in docs/tech-debt.md.
- W1 rendered re-verify NOT-RUN (Playwright MCP unavailable mid-run; W0 used it). Proxy: preview 200 + jsdom aria + static contrast math.

## Not merging yet — needs approval.
- Probes (SR pass) + backend pytest still manual/NOT-RUN.
- Probe screenshots for light mode described, not persisted in repo (accepted).
- Backend-up Playwright matrix (T-204) deferred — needs backend env.
