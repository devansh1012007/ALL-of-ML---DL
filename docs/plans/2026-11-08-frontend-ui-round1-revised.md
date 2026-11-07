# Plan: Frontend UI/UX Round 1 (revised — spec as target)

Status: In progress — implementation started 2026-11-08
Baseline: `main` @ `091e0cf`, clean tree
Spec: operator message "Frontend spec: UI/UX round 1" (target state; **not present** in checkout — see Facts)
Decisions: D1 scope Phase 1–2 (Option A), D2 recon+baseline yes, D3 keep "PrimeTrade AutoML" for now, D4 keep `localStorage` token, D5 24px AA touch, defer Playwright, D6 Phase 3 (admin/E1) before Phase 4 (split) — D6 applies after this round, Q7-a spec-is-target (user: "Start with your default")

## 1. Problem, goal, non-goals, acceptance

Problem: Round-1 defects exist in current code but no frontend tests exist to catch regressions. Admin mutations report success as failure, failed reads render as zero/defaults, raw JS/network errors reach users, the runs list is empty against the real backend, and live regions spam screen readers.

Goal (this round): (a) test harness that renders real `<App/>` against a fake backend matching **backend truth**; (b) Workstream A truthful-state fixes; (c) Phase-2 a11y/mobile fixes C2, C3, C4, D1, D2 — each with a test that fails on old code.

Non-goals: light theme, router/state library, training-flow redesign, backend API changes, B1–B3 (need backend), C1 copy, E1 admin shared-classes migration, F1 `App.jsx` split, F2 env API base, F4 rename, Playwright/contrast CI (Phase 6 of spec), manual SR pass (H), runs pagination UI beyond backend default limit=20 (known limitation, see §5).

Acceptance:
- `npm test` (Vitest) green from `frontend/`; `npm run build` succeeds.
- Admin: resolved `apiFetch` = success, thrown = failure with server reason in `role="alert"`; list stays on refusal; failed reads show unknown ("—") + what could not load. Every admin mutation site has try/catch → `err.message` (no unhandled rejections).
- Runs list renders rows from real backend `{items,…}` response (and tolerates bare array).
- C2: exactly one live region per view — RunEvents status (`role="status"`, phase-change only) and PredictionResult result-summary status; log `<ol>` and result container have no `aria-live`.
- C3: best bar at CompareRuns (`App.jsx:1263`) has text cue, not colour only (prediction-probability `Bar` at `:1162` unchanged unless cue is generic). C4: Runs checkbox column purpose perceivable (visible header hint, e.g. "Compare" text or hint on Compare button). D1/D2: static guards + manual browser probe (jsdom cannot measure layout — recorded).
- No behaviour change to `apiFetch` throw contract, auth flow, or polling cadences except C2 announcement logic. 401 path preserved (test).

## 2. Facts vs assumptions

Facts [verified by investigators + orchestrator spot-checks]:
- `frontend/App.jsx:5` `API_BASE=http://localhost:8010`; `:8` `RUN_POLL_INTERVAL_MS=2000`; `:153` `localStorage prime_token`; `:173-221` `apiFetch` throws on `!ok`, returns parsed JSON on success.
- `frontend/package.json:6-10` scripts dev/build/preview only; no test runner/deps; `frontend/tests/` absent.
- `AdminScreen.jsx:88,264,335,423,502` 5 sites inspect `response.ok` on parsed JSON (always undefined) → success reported as failure; error branch reads `err.detail` which never exists. Only `:88` has try/catch; `:264,335,423,502` have none.
- `AdminScreen.jsx:640-646,149-151,165` failed usage/profiles fetches swallowed (`.catch(()=>{})`) → `0` / invented `'free'`.
- `App.jsx:367-370,411` catalog failure renders fallback count as "can run on this server" with warn (not bad) notice.
- `App.jsx:195-198` bare fetch (network `TypeError` verbatim); `:967,1020` `JSON.parse` `SyntaxError` verbatim.
- `App.jsx:500-502` runs expects bare array; `backend/app/main.py:2378` returns `{items,total,limit,offset}` → always `[]` on real backend.
- `App.jsx:1366` `<ol aria-live="polite">` polled 1.5s; `:1129` second `aria-live` in PredictionResult; `:1263` best bar `tone`-only (table `:1295-97` already has "best" text); `:547` checkbox header sr-only "Compare"; `:543-544` wrapper `overflow-x-auto -mx-3`, `.td` 12px/side (`styles.css:96-97`); `styles.css:57-60` global `summary::before` '+' marker.

Assumptions (verify in implementation):
- Vitest 2.x/3.x + jsdom + Testing Library 14–16 compatible with React 18.3.1 / Vite 5.4.1 / Node 24 — to be proven by P1 install+smoke test. Pin `vitest@^2` if v4 demands Vite 6.
- Exact user-facing copy for F3/F4/F16/F17 (spec wording used: unknown "—", outage/degraded header, connectivity sentence, "rows must be valid JSON" sentence) — content owner may adjust later; non-blocking.
- D1 exact 5px and D2 visual cause need browser measurement — not reproducible from source/jsdom; static guard + manual probe recorded as the check, px value unverified.

## 3. Approaches

A. **Fix at source, keep `apiFetch` throw contract (chosen).** Fix the 5 admin sites to treat resolve=success/throw=failure (adding try/catch where missing); fix runs parser to accept `{items}` (keeping bare-array tolerance); move `aria-live` off containers to a single phase-change status per view; add text cue to best bar. Correctness: fixes invariants where they break. Blast radius: frontend only. Reversible per phase commit.
B. Change `apiFetch` to return `Response`. Rejected: every `App.jsx` caller already uses the throw contract correctly (auth, models, runs, predict); flipping it breaks 401 handling (`App.jsx:200-208`) and the whole SPA for 5 admin sites.
C. Fix admin only, mock runs as bare array in tests. Rejected: encodes the real-backend bug; violates Truth-over-polish; list stays empty in production.
D. C2 throttle (keep `aria-live`, update less often). Rejected: still announces a stream; spec target is a single latest-phase status. Phase-change-only announcement is the root-cause fix.

## 4. Atomic phases (sequential — all touch `App.jsx`/`AdminScreen.jsx`, no parallel file ownership)

- **P1 Test harness.** Files: `frontend/package.json`, `frontend/package-lock.json`, `frontend/vite.config.js` (or `vitest.config.js`), `frontend/tests/helpers.jsx`, `frontend/tests/smoke.test.jsx` (login + one admin-shaped response to prove mock contract), `frontend/tests/static.test.js` (initial guard: no `response.ok` in AdminScreen — will fail until P2a, so add it in P2a instead; P1 ships smoke only). Interfaces: `installFakeBackend(seed)` mocks **`global.fetch` at fetch level**, returning Response-like `{ok,status,json(),blob()}` matching `backend/app/main.py`/`admin.py` shapes (never parsed objects, never real `Response` required); `renderApp({hash,token})` black-box via `App`, seeds `localStorage.prime_token` with crafted decodable JWT, seeds `/api/v1/me` (role admin for admin cases), fake timers + cleanup where polling involved. Scripts: `"test":"vitest run"`, `"test:watch":"vitest"`. Tests: smoke only. Done: `npm test` green, `npm run build` green.
- **P2a Admin truth (F1,F2,F4,F5).** Files: `frontend/AdminScreen.jsx`, `frontend/tests/admin.test.jsx`, `frontend/tests/static.test.js`. Fix: all 5 mutation sites → try/catch, resolve=success, throw→`err.message` in `role="alert"`, no hardcoded failure strings losing server reason; F1 invite code reachable; F4/F5 unknown "—"/failed-loaded (reuse `formatBytes` null→"—"); static guard no `response.ok`/`err.detail` in AdminScreen. Tests: approve/patch/quota-save/profile-save/invite-create/queue-cancel resolve→success+reload, reject→server reason shown; invite code visible; failed usage→"—" not 0 (and true 0 still 0); failed profiles→not 'free'. Each fails on old code. Done: suite+build green.
- **P2b App truth (F3,F16,F17,R1).** Files: `frontend/App.jsx`, `frontend/tests/models.test.jsx`, `auth.test.jsx`, `runs.test.jsx`. Fix: F3 outage header + bad notice; F16 friendly connectivity message at `apiFetch` boundary (preserve 401 throw + logout, preserve `/artifact` blob); F17 friendly JSON message in PredictPanel; R1 runs parser accepts `{items}` and bare array. Tests: catalog reject→outage header not "8 of 8"; network reject→friendly text not browser string; 401→logout still; bad JSON→friendly not `Unexpected token`; server predict error still shown; runs `{items}`→rows render, bare array→rows render. Done: suite+build green.
- **P3 Phase-2 a11y/mobile (C2,C3,C4,D1,D2).** Files: `frontend/App.jsx`, `frontend/styles.css`, `frontend/tests/runs.test.jsx` (extend), compare/predict cases, `static.test.js` (extend). C2: RunEvents — remove `aria-live` from `<ol>`, add single visually-hidden `role="status"` announcing only on phase-string change (dedup state, phase from event `kind`/`payload.phase`); PredictionResult — remove `aria-live` from container, add single `role="status"` result-summary. C3: text cue ("best") on CompareRuns best `Bar` (label/note), ranking unchanged. C4: visible "Compare" header text or hint (exact copy in code, test asserts visible text). D1: scoped wrapper fix (remove `-mx-3` overflow source / reduce checkbox cell padding below `sm` via scoped class, **not** global `.th/.td`), verified by static guard + manual probe note (jsdom vacuous). D2: scoped inline marker for the 3 disclosures (catalog `:439`, run-details `:1572,1595`), not a global `summary` redesign. Done: suite+build green; D1/D2 browser probe recorded as follow-up (spec H).

Dependency graph: P1 → P2a → P2b → P3 (strictly sequential due to shared `App.jsx`). Checkpoint after each: `npm test` + `npm run build` + independent code-review + test-review.

## 5. Blast radius, rollback, risks

Blast radius: frontend only; no backend, migration, config, or API change. `Bar`, `.th/.td`, global `summary`, `apiFetch` 401 semantics are shared — changes scoped to avoid neighbours. Rollback: revert phase commit on feature branch `frontend-ui-round1`.

Risks: mock drift (mitigate: fetch-level Response-like mock from backend shapes, `{items}` truth); F16 boundary change (preserve 401/cancel — tested); D1/D2 global CSS (scope below `sm`, check ConfusionMatrix/Compare tables); C2 still chatty if status updates every poll (dedup by phase string — test asserts single announcement across repeated same-phase polls); test deps pinning (Vitest v4/Vite 6 trap).

Second-order: runs list will now show data in production, truncated at backend default `limit=20` (`main.py:2338`) with no pagination UI — known limitation, out of scope, noted here and for follow-up. Test harness adds install size; C2 phase state couples RunEvents to event schema (`payload.phase`).

Open questions (non-blocking): exact F3/F4/F16/F17 copy (owner), D1 px + SR verification (manual probe, spec H).

## 6. Planner-reviewer objections → resolutions (2026-11-08)

- F1 major, 4/5 sites lack try/catch → P2a now requires per-site try/catch→`err.message`, hardcoded strings removed; throw-path tests added for quota/profile/queue/invite.
- F2 major, mock contract incoherent → P1 mock is fetch-level Response-like `{ok,status,json,blob}`; smoke test proves admin shape.
- F3 major, jsdom overflow vacuous → D1 acceptance = static guard + manual probe; px unverified.
- F4 major, P2 oversized → split P2a/P2b.
- F5 minor, C2 per-view scope → RunEvents + PredictionResult each get one `role="status"`; phase=diamond dedup on phase string.
- F6 minor, C3/C4/D1 underspecified → exact call-sites/hints/scoped selectors named in P3.
- F7 minor, P1 missing pieces → `/me` seed, JWT crafting, fake timers/cleanup, `vitest run` in P1 done-criteria.
- Test gaps → 401-preservation, bare-array tolerance, prediction announcement, all throw-paths added.
