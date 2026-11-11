<!-- ORCH-DIGEST:START -->
agent: W0-INV-01 | domain: playwright-rendered-ui-audit | status: PARTIAL
items: 2 EXISTS (both NIT/decision) / 4 verified-clean / 1 NOT-RENDERABLE set (data views)
proposed_tasks: 3 (SURFACE 2, backlog-audit 1)
top_risks: data surfaces unaudited (backend down) — Runs/RunDetails/NewJob/Predict/Models/Admin still need Playwright evidence; 24px targets are test-pinned so a 40px fix is a contract change, not a silent CSS edit
cross_domain_conflicts: none
out_of_plan_discoveries: 1
confidence: high (auth surface fully probed; data views honestly excluded)
last_comms_line_read: none (COMMS empty beyond header)
<!-- ORCH-DIGEST:END -->

# Investigation report — W0-INV-01 — Playwright rendered-UI audit (T-201)

## 0. Scope and method
Task: audit the real rendered UI with Playwright MCP (via `execute` → `tools.playwright.*`, discovered by `search`). Server: `npm run build` (1671 modules, built in 5.35s) then `npx vite preview --port 3101` on `http://127.0.0.1:3101/` [RAN npm run build -> ✓ built; RAN curl http://127.0.0.1:3101/ -> 200]. Vite process killed after audit (curl -> 000).
Backend (localhost:8010) check [RAN python urllib -> connection refused]: **backend down**. Brief forbids starting the backend, so only the unauthenticated Auth surface is renderable. Data views (Runs, RunDetails, NewJob, Predict, Models, Admin) are **NOT-RENDERABLE** — no data faked (see §1.F).
All probes per surface: `browser_evaluate` DOM/computed-style checks + snapshot + fullPage screenshot. Matrix covered: Auth × 1280×800 & 390×844 × dark & light (register mode and submitted-error state also captured). 7 screenshots in `screenshots/before/`.

## 1. Per plan item

### P-01 `.link` mode-switch target is 24px tall (below the 40px audit bar)
- **Existence verdict:** EXISTS (measured), but **test-pinned by design** — see nuance below.
- **Evidence:** [RAN Playwright evaluate] All `button,a,input,select` on Auth measured: theme toggle `.btn` = 39.7px, `.field` inputs = 41.3px (clear), primary `.btn` = 39.7px, **`.link` "Create an account"/"Sign in" = 24.0px** — identical at 1280 dark, 1280 light, 390 dark, 390 light. Source: `frontend/views/AuthView.jsx:86` (`className="link"`), `frontend/styles.css:122` (`.link { min-height: 1.5rem }`).
- **Root cause chain:** R5 round set a documented 24px touch floor (`styles.css:86,111,290` comments). The floor is **explicitly pinned by tests**: `frontend/tests/static.test.js:212-221` asserts `.link { min-height: 1.5rem }` ("interactive classes declare a 24px floor"), `frontend/tests/smoke.test.jsx:220` pins the same 24px for `.nav-link`. 24px exactly meets WCAG 2.2 SC 2.5.8 AA minimum (24×24) — with zero margin.
- **Blast radius:** `.link` usages: `AuthView.jsx:86` (mode switch), `RunDetails.jsx:312` (HF URL). Sibling classes with the same floor: `.nav-link` (`styles.css:131`, App.jsx:143 header), `.admin-icon-btn` (`styles.css:326`), `.breadcrumb a` (`styles.css:144`), `.compare-check` (`styles.css:177`). [ASSUMED from source — not rendered, backend down.]
- **Fix options:** A) Accept 24px as the WCAG-AA decision (no code change; record it). B) Raise `.link`/`.nav-link` to 2.5rem (40px) in `styles.css` **and** update the pinning assertions in `static.test.js`/`smoke.test.jsx` as a deliberate contract change (requires ORCH approval — the tests are a feature, not an obstacle). **Recommended:** ORCH decides; this investigator takes no position on the 40px bar.
- **Long-run test:** Source: rendered measurement. Load/Hostile/Operability: n/a (pure CSS floor). Reversal: if reverted, `static.test.js` "interactive classes declare a 24px floor" is the test that would need to change with the fix — it fails without the paired test update, which is the correct tripwire.
- **Classification:** SURFACE (rendering-only), but **contract-touching** (test-pinned) — needs an explicit decision, not a drive-by.
- **WRITE-SET (proposed):** `frontend/styles.css` + `frontend/tests/static.test.js` + `frontend/tests/smoke.test.jsx` (only under option B).
- **Severity:** MINOR as measured vs the brief's 40px bar; NIT vs the shipped/tested discipline (AA met exactly). Prioritize: **polish/decision, not must-fix**.

### P-02 favicon 404 on every page load (sole console error)
- **Existence verdict:** EXISTS.
- **Evidence:** [RAN browser_console_messages level error] `[ERROR] Failed to load resource: 404 (Not Found) @ http://localhost:3101/favicon.ico` — the only console error on plain load (a second error, `ERR_CONNECTION_REFUSED /token`, appears only when submitting while the backend is down — that is expected behavior, not a defect). No `<link rel="icon">` in `frontend/index.html:5-28`, so the browser auto-requests `/favicon.ico`.
- **Root cause chain:** nobody shipped a favicon; the 404 is a browser default request.
- **Blast radius:** global (every view, every load).
- **Fix options:** add an inline data-URI SVG `<link rel="icon">` in `index.html` (no new dep, no new file). **Recommended:** that. Effort: trivial.
- **Long-run test:** Reversal: none pins this today — add/extend a static assertion in `static.test.js` for the icon link so the 404 can't regress silently. Operability: zero-risk, one line.
- **Classification:** SURFACE.
- **WRITE-SET (proposed):** `frontend/index.html` (+ a one-line test in `frontend/tests/static.test.js`).
- **Severity:** NIT. Priority: polish — bundle with any other index.html touch.

### P-03 Contrast (rendered vs shipped triples)
- **Verdict:** VERIFIED CLEAN (no defect).
- **Evidence:** [RAN Playwright evaluate, both themes] Light: h1 16.30, muted/labels 8.20, primary btn (accent-ink on accent) 6.70, toggle 13.35. Dark: h1 15.40, muted 6.72, primary 6.72, toggle 13.69. All ≥ 4.5:1. Rendered triples match `frontend/styles.css:15-53` exactly (light canvas `248 250 252`, dark canvas `18 24 33`, etc.); the dark 6.72 matches the `styles.css:13` comment ("muted is 6.7:1"), and accent-ink 6.7 matches `styles.css:26`. No fix.

### P-04 Horizontal overflow / tap overflow / truncation
- **Verdict:** VERIFIED CLEAN on Auth.
- **Evidence:** [RAN Playwright evaluate] 1280 dark: scrollW=1280, clientW=1280, 0 elements with `right > innerWidth`. 1280 light: same. 390 dark & 390 light: scrollW=390, 0 overflowing elements. Mobile card: `main` padding `32px 24px` (measured), so 24px gutters at 390px. Screenshots show no truncation, overlap, or misalignment; card max-width 24rem with comfortable margins. No fix.

### P-05 Focus visibility and order
- **Verdict:** VERIFIED CLEAN.
- **Evidence:** [RAN Tab ×6 + evaluate] Sequence: username input → password input → Sign in → Create an account → (wrap) theme toggle. Buttons show `outline: solid 2px` when focused (the `:focus-visible` rule, `styles.css:75`); `.field` inputs use `box-shadow: 0 0 0 3px` (outline none + visible ring, `styles.css:107`). All 5 Auth focusables reachable in DOM order with visible focus. Theme toggle flips `data-theme` dark↔light, updates `meta[name=color-scheme]` and `localStorage prime_theme` (verified both directions); `aria-pressed={isLight}` per `frontend/components/theme.jsx:70` matches the pinned test expectation (`theme.test.jsx:141-142`) — not a defect. No fix.

### P-06 Error state when backend is unreachable
- **Verdict:** VERIFIED CLEAN.
- **Evidence:** [RAN submit with backend down] DOM shows `<alert role="alert">` "Could not reach the server. Check your connection and try again." with the `.notice-bad` border (rendered light `rgb(185, 28, 28)` = shipped `--bad` triple). Network: `POST http://localhost:8010/token => ERR_CONNECTION_REFUSED`. Screenshots `auth-desktop-light-error.png`, `auth-mobile-dark-error.png`. No fix.

### P-07 Initial theme in this browser is light
- **Verdict:** NOT A DEFECT (by design — recorded so the fix wave isn't surprised).
- **Evidence:** first load rendered `data-theme="light"` because Playwright emulates `prefers-color-scheme: light`; `frontend/index.html:10-24` resolves stored → media query → dark default. With no preference the shipped default is dark. Verified both themes by clicking the toggle. No fix.

### F. Data surfaces (Runs, RunDetails, NewJob, Predict, Models, Admin) — NOT-RENDERABLE
- **Why:** backend 8010 refused connections throughout the audit; brief forbids starting the backend or faking data. Without a valid token the SPA renders AuthView only (auth gate: `AuthProvider` + `apiFetch('/api/v1/me')`, `frontend/App.jsx:75`). These surfaces need a **follow-up Playwright pass with the backend up** — proposed as the first W1 task, same probe set (overflow, taps, contrast, focus, console, table/metric-card alignment at 390px where `styles.css:184-195,227-228,306-307` scroll-wrappers exist).
- **Source-pointer leads for that pass (NOT defects, [ASSUMED] only):** `.runs-table-wrap table { min-width: 34rem }` scrolls at 390px by design (`styles.css:185`); `.compare-table-wrap` 30rem (`styles.css:228`); `.admin-table-wrap` 34rem (`styles.css:307`); `.nav-link` 24px (`App.jsx:143`, test-pinned `smoke.test.jsx:220`). All need rendered confirmation before any defect is claimed.

## 2. Duplicates / shared root causes
P-01 and the `.nav-link`/`.admin-icon-btn`/`.breadcrumb a` family share one root cause (the R5 24px floor) — one decision settles all of them. P-02 is independent.

## 3. Out-of-plan discoveries
1. `AGENTS.md` says "Single-file SPA, no router, no react-router: navigation is `navigate(view, params)` state in MainApp". Code (`frontend/App.jsx:81-109`) shows hash-URL routing (`#/run-details/3`, `#/compare/3+5+8`) layered on that state — i.e. pages ARE addressable/reloadable. AGENTS.md is slightly stale on this point. [VERIFIED read App.jsx:78-109] No audit impact; suggest a doc touch-up in the fine-tune wave if desired.

## 4. Assumptions and unknowns
- [ASSUMED] Data-surface layout is as the CSS implies (scroll-wrappers, grids) — unverified until backend-up pass. Owner of the answer: W1 follow-up auditor with backend running.
- [UNKNOWN] Whether any data view has real rendered defects — cannot be determined in this run without the backend.
- [ASSUMED] Playwright's default light color-scheme is an emulator default, not user-visible behavior (index.html logic verified).

## 5. Recommended task breakdown and ordering
1. **W1-T1 (backlog audit):** re-run this matrix on data surfaces with backend up — probe set identical to §0. WRITE-SET: audit report + screenshots. Blocks any claims about Runs/RunDetails/NewJob/Predict/Models/Admin layout.
2. **W1-T2 (favicon):** P-02, one line in `frontend/index.html` + one static assertion. SURFACE, NIT.
3. **Decision D-40px (ORCH):** whether the tap-target bar is WCAG AA 24px (current, test-pinned — close) or 40px (reopen P-01 + family with paired test updates). Do not let an agent change `styles.css` floors without the paired `static.test.js`/`smoke.test.jsx` change and ORCH sign-off.

## Method note / scratch files
- Screenshots: 7 under `docs/agent-ops/20261109-playwright-design/screenshots/before/`: `auth-desktop-light-initial.png`, `auth-desktop-dark.png`, `auth-desktop-dark-register.png`, `auth-desktop-light-error.png`, `auth-mobile-dark.png`, `auth-mobile-light.png`, `auth-mobile-dark-error.png`.
- Scratch files outside the repo: none inside the repo; vite log `C:\Users\devan\AppData\Local\Temp\opencode\wit-3101.log` only. No source files edited. Server killed.
