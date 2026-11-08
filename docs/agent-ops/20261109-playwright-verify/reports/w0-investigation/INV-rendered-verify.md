<!-- ORCH-DIGEST:START -->
agent: W0-INV-01 | domain: playwright-rendered-verify-auth | status: DONE
items: 3 verified EXISTS (aria both-fields, .link 24px, deferred NOT-RENDERABLE) / 3 verified-clean (favicon, overflow, contrast, theme, focus, error) / 0 ALREADY-FIXED
proposed_tasks: 2 (V-103 status-mapped aria, backend-up data-view pass) — no source tasks from this verify
top_risks: both-fields aria-invalid mislabels 409/429 (V-103 input); data surfaces unaudited (backend down)
cross_domain_conflicts: none
out_of_plan_discoveries: 2 (COMMS stray line; AGENTS.md hash-routing staleness confirmed)
confidence: high (auth matrix fully probed live; data views honestly NOT-RENDERABLE)
last_comms_line_read: 2026-11-08T16:07:02Z
<!-- ORCH-DIGEST:END -->

# Investigation report — W0-INV-01 — rendered re-verify Auth matrix (V-101)

## 0. Scope and method
Task V-101: re-run the W1 rendered re-verify (Auth × 1280×800 & 390×844 × dark/light) with Playwright
via `execute` → `tools.playwright.*` (discovered by `search` inside execute: browser_navigate,
browser_snapshot, browser_take_screenshot, browser_evaluate, browser_resize, browser_press_key,
browser_click, browser_console_messages, browser_wait_for, browser_close), plus deferred-hypothesis
probes (ResultLine clamp, header gap-x-8, Compare title-only hint). Server: `npm run build`
[RAN npm run build -> 1671 modules, built in 2.89s] + vite preview on :3103 [RAN curl -> 200;
killed after -> curl 000]. Backend 8010 probe [RAN python urllib -> connection refused]:
backend DOWN; no data faked; brief forbids starting backend.
Required reading: STANDING-ORDERS, AGENTS.md frontend, 00-mission, 01-work-ledger, COMMS, template,
prior audit (path correction: brief's `20261109-playwright-verify/.../INV-playwright-audit.md` does
not exist; the actual prior audit is `20261109-playwright-design/reports/w0-investigation/INV-playwright-audit.md`),
fine-tune plan, index.html/AuthView.jsx/styles.css/App.jsx. HEAD `3f5b220`, branch frontend-ui-round2
[RAN git log/branch]. COMMS last line read: 2026-11-08T16:07:02Z (the sole log line).

## 1. Matrix verdicts (Auth, live Playwright)
| Check | Verdict | Evidence |
|---|---|---|
| Console errors (plain load) | CLEAN — favicon 404 GONE | `browser_console_messages error all=true` on load -> 0 errors [RAN]. Sole errors after submit are `net::ERR_CONNECTION_REFUSED @ localhost:8010/token` (expected, backend down) [RAN]. f53e4ba T-301 held. |
| Favicon | CLEAN | `link[rel=icon]` present, href `data:image/svg+xml,%3Csvg xmln...` [RAN]; source `frontend/index.html:6` [VERIFIED]. |
| Theme toggle both directions | CLEAN | dark->light and light->dark both flip `dataset.theme` + `meta[name=color-scheme]` + `localStorage prime_theme` [RAN x4]. |
| Overflow | CLEAN (0) | 1280 light/dark: scrollW=1280=clientW, right>innerWidth elements 0 [RAN]. 390 dark/light: scrollW=390=clientW, 0 [RAN]. Mobile main padding `48px 24px` measured [RAN]. |
| Contrast rendered | CLEAN | Light: h1 17.06, muted 8.59, primary 6.70 [RAN compute]. Dark: h1 16.73, muted 7.30, primary 6.72 [RAN]. All >=4.5. Raw computed rgb match shipped triples `styles.css:15-53` [VERIFIED vs RAN]. |
| Submit error (backend down) | CLEAN + recorded behavior | Alert `role=alert id=auth-error` "Could not reach the server. Check your connection and try again." present desktop+mobile [RAN]; BOTH inputs `aria-invalid=true` + `aria-describedby=auth-error` [RAN] — matches `AuthView.jsx:67-68,79-80` [VERIFIED]; this both-fields behavior is the V-103 input (409/429 mislabel), NOT a regression. |
| Tap targets | RECORDED — accepted 24px | Measured 1280 light [RAN]: theme toggle `.btn` 39.7px, inputs `.field` 41.3px, primary `.btn` 39.7px, `.link` "Create an account" **24.0px** (w 113.6). Identical discipline as prior audit P-01 (test-pinned R5 floor, WCAG 2.2 2.5.8 AA exact). No defect. |
| Focus | CLEAN | Tab-walk: buttons show `outline solid 2px` (`:focus-visible`, `styles.css:75`), inputs `box-shadow 0 0 0 3px` ring [RAN]; 5 Auth controls reachable in DOM order. |
| Register mode | CLEAN | h1 "Create an account" + "At least 8 characters." hint rendered [RAN]; screenshot `auth-desktop-dark-register.png`. |

Screenshots (7) in `docs/agent-ops/20261109-playwright-verify/screenshots/after/`:
auth-desktop-light-initial.png, auth-desktop-dark.png, auth-desktop-dark-error.png,
auth-desktop-dark-register.png, auth-mobile-dark.png, auth-mobile-light.png,
auth-mobile-light-error.png [RAN Get-ChildItem].

## 2. Deferred hypotheses — NOT-RENDERABLE (honest, no fake data)
**Verdict: NOT-RENDERABLE.** Probe [RAN]: `browser_navigate #/runs` still renders AuthView
(h1 "Sign in", header absent, no ResultLine/Compare text — evaluate: hasHeader=false,
hasResultLine=false, hasCompare=false). Exact wall: token gate `frontend/App.jsx:197-207`
(`token ? <MainApp/> : <AuthView/>`) — no token without backend auth; header `App.jsx:135`,
ResultLine (`frontend/components/metrics.jsx:102-199`, via RunDetails EvaluationPanel
`metrics.jsx:208-229`), Compare (`frontend/views/CompareRuns.jsx`, needs `apiFetch /api/v1/ml/runs/:id`
`CompareRuns.jsx:17`) all live behind MainApp/data fetch. No facts claimed about clamp/gap/title
rendering. Code pointers for the backend-up pass (not defects): `.result-headline-row` flex-wrap
exists (`styles.css:199`) so the label wraps rather than clamps — [ASSUMED] clamp hypothesis may
be misclassified; `.compare-run-link` has NO `title=` [VERIFIED grep] — the "title-only hint"
hypothesis has no source basis in CompareRuns.jsx today.

## 3. Proposed tasks (no source edits made — verify-only)
1. V-103 (already ledgered): status-mapped aria — this report is its rendered baseline
   (both-fields `aria-invalid=true` recorded verbatim in §1). SURFACE-visible, DEEP-test (mutation
   tripwire already in `frontend/tests/auth.test.jsx:230` [VERIFIED grep]).
2. Backend-up data-view pass: ResultLine/header/Compare focus-walk (deferred hypotheses).
   Environment: needs backend env (install per AGENTS.md); explicitly NOT started here.

## 4. Out-of-scope observations
1. `docs/agent-ops/20261109-playwright-verify/COMMS.md:34` — a single DONE line dated 2026-11-08
   describes the *prior* design run's audit in this run's COMMS file; likely misfiled. ORCH cleanup.
2. AGENTS.md "no router" claim vs hash-routing `frontend/App.jsx:78-109` — re-confirmed [VERIFIED
   App.jsx:81-109]; prior audit §3 already flagged. Not investigated further.

## 5. Assumptions and unknowns
- [ASSUMED] vite preview of the prod build matches dev behavior for Auth (same mode as prior audit).
- [UNKNOWN] data surfaces until backend-up pass (owner: V-103 follow-up with backend env).
- Git status: report + screenshots are untracked new files only; no source files edited [RAN].

## 6. Scratch files created
- `C:\Users\devan\AppData\Local\Temp\opencode\wit3103.log` + `.err.log` (vite preview output, outside repo).
- Failed first attempt: Start-Process npx rejected ("%1 is not a valid Win32 application"); vite run via
  background shell tool instead. No files inside repo except report + screenshots.
