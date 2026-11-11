# Gate — wave 1 — 2026-11-09 (ORCH)

- Tree: HEAD `21c3420` before gate (code `f53e4ba` + report). Base for wave: `a2a5194`.
- Baseline: 7ce8bed at 154/154 (flake run 153/154 once, then 16/16 scoped + full green — pre-existing runs.test.jsx timing). This gate: **162/162**.

| Step | Command | Result | vs baseline |
|---|---|---|---|
| Unit (frontend) | `cd frontend; npm test` | 11 files, **162/162 passed** (11.33s) | +8 (6 static + 2 auth), no regressions |
| Build | `cd frontend; npm run build` | 1671 modules, built in 3.20s | green (was 1670 — +1 file? no: module count 1671 vs 1670 prior, build green) |
| Scoped | `npx vitest run tests/static.test.js tests/auth.test.jsx` | 51/51 (TREV + REV independent) | — |
| Playwright rendered (W0) | vite preview :3101, Auth matrix | 7 screenshots, clean except favicon 404 + 24px floor pin | — |
| Playwright rendered (W1 after) | — | **NOT-RUN in this session window** (MCP catalog empty at gate time; coder + orchestrator `search → 0 items`). Proxy: preview 200 + icon present, jsdom aria, static contrast math (T-101 guards green). | — |
| Backend pytest | — | NOT-RUN (frontend-only diff) | pre-existing |

New failures: none. Flake: none observed this gate run.
Verdict: **GREEN**. Findings triage: 0 BLOCKER/MAJOR across REV/TREV/FINAL; R-W1-001 both-fields aria → DO-LATER (status mapping), R-W1-002 long-code overflow-wrap → DO-LATER, R-W1-003 favicon spaces → NOT-WORTH-IT (all recorded, none blocking).
Playwright MCP outage: catalog `search({query:"browser"}) → 0 items`, `search playwright → 0` at gate time (worked during W0). Rendered re-verify deferred to MCP restoration — follower issue.
