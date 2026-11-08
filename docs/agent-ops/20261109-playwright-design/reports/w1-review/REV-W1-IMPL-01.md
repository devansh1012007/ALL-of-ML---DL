<!-- ORCH-DIGEST:START -->
agent: W1-REV-01 | scope: wave 1 / T-301..T-304 (commit f53e4ba) | verdict: APPROVE
findings: BLOCKER 0 | MAJOR 0 | MINOR 1 | NIT 2
claims_audit: 14 claims checked / 0 unsupported or false (4 partial: scoped-only scope, no full-suite/build re-run)
band_aids_found: none
top_3_risks: T-304 both-fields aria-invalid is semantically broad for 409/429/network errors | invite flex-wrap does not break an unbreakable long code string | Playwright rendered proof still NOT-RUN (honest carry-over from W1-IMPL-01)
optimizations: DO-NOW 0 | DO-LATER 2 | NOT-WORTH-IT 1
reversal_check: reasoned-only (post-fix scoped pass executed; pre-fix failure verified by pins matching strings, no revert performed per read-only brief)
confidence: high (blind diff + in-context files + own scoped vitest pass; full suite/build deliberately not re-run per standing orders)
<!-- ORCH-DIGEST:END -->

# Code review — W1-REV-01 (f53e4ba, T-301..T-304)

## 0. Method
Diff range reviewed: `git show f53e4ba` / `git diff f53e4ba^..f53e4ba` (7 files, 126 insertions, 5 deletions). Order followed per brief §2: blind pass first (`git show f53e4ba`, `frontend/index.html`, `frontend/views/NewJob.jsx:660`, `frontend/AdminScreen.jsx:628/670`, `frontend/styles.css:310`, `frontend/views/AuthView.jsx`) — all inspected **before** reading the implementer report or the plan's Decisions section. Then claims audit against `docs/plans/2026-11-09-playwright-fine-tune.md` and `docs/agent-ops/20261109-playwright-design/reports/w1-impl/W1-IMPL-01-T301-T304.md`. Commands run by reviewer: `git show f53e4ba --stat` + name-only diff; targeted `grep` for `auth-error`, `aria-invalid`, `📊`, `file:btn`; `npm test -- tests/static.test.js tests/auth.test.jsx` (frontend, post-fix) → 2 files passed, 51 passed. COMMS last line read: header/rules block (no task lines consumed beyond standing rules). No code edited. Full suite and `npm run build` deliberately NOT re-run (standing orders §16: scoped checks only; build writes `dist/`).

## 1. Blind-pass findings (before reading implementer reports)
1. Favicon: `frontend/index.html:5-6` — `<link rel="icon" href="data:image/svg+xml,%3Csvg ...">` sits between `meta[name=color-scheme]` (L5) and the pre-paint init `<script>` (L7). The diff is +1 line only; init script text unmoved (L7-27 identical). Decoded SVG parses as well-formed XML: `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><rect width='16' height='16' rx='3' fill='#121821'/><path d='M3 8h3l1.5-4 2 8 1.5-4h2' stroke='#5b9df0' stroke-width='1.4' fill='none'/></svg>` — `%3C`/`%3E`/`%23` correct; single quotes safe inside the double-quoted attribute. Direct `node` decode attempt was blocked by the portable shell scanner (unterminated-quote); XML validity established by manual decode [ASSUMED-browser decode] — see §9.
2. Type strips exact: `NewJob.jsx:660` `<h3 className="font-semibold text-strong mb-4">Model Intelligence</h3>` — `text-lg` + 📊 gone, brief's keep-list preserved verbatim. `AdminScreen.jsx:670` `<h1>Admin</h1>` bare — no `mb-1` invented; subtitle `mt-1` (L671) supplies the gap. Global scales (`styles.css:69-72`) confirm convergence: h1 1.5rem/600, h3 0.9375rem/600.
3. Audit title: `AdminScreen.jsx:628-630` — unchanged guard `event.detail && Object.keys(event.detail).length` preserved; `title={JSON.stringify(event.detail)}` duplicates the body `JSON.stringify` (identical pre-existing inline expression, no new failure mode).
4. Invite wrap: `styles.css:310` — `flex-wrap: wrap` inserted inside `.admin-invite-code` after `display: flex`; `justify-content: space-between` + `gap: 1rem` retained. CSS declaration order irrelevant; short codes unchanged.
5. Auth aria: `AuthView.jsx:59,67-68,79-80` — `id="auth-error"` on the `role="alert"` `<p>` rendered only when `error` truthy; both inputs carry `aria-invalid={error ? true : undefined}` + `aria-describedby={error ? 'auth-error' : undefined}` — same truthy gate, so no dangling describedby, and initial DOM unchanged (React omits `undefined`). `App.jsx:198-207` renders exactly one `<AuthView>` → id unique. §15 concern (both-fields vs per-field) examined in §4 R-W1-001.
6. Scope: `git diff f53e4ba^..f53e4ba --name-only` = exactly 7 files: `index.html`, `views/NewJob.jsx`, `AdminScreen.jsx`, `styles.css`, `views/AuthView.jsx`, `tests/static.test.js`, `tests/auth.test.jsx`. Diff for `PredictPanel.jsx`, `tailwind.config.js`, `App.jsx`, `components/theme.jsx` empty. `file:btn` only at `PredictPanel.jsx:232` (untouched); `NewJob.jsx:431` file input uses `file:` utilities without `file:btn` (untouched).

## 2. Claims audit
| # | Implementer claim | Verified? | Evidence / finding |
|---|---|---|---|
| 1 | T-301 favicon data-URI after color-scheme, before init; init unmoved | Yes | [VERIFIED frontend/index.html:5-7] +1 line in diff; init body byte-identical |
| 2 | T-302 NewJob h3 keeps `font-semibold text-strong mb-4`, drops `text-lg` + 📊 | Yes | [VERIFIED frontend/views/NewJob.jsx:660]; `grep 📊 frontend` → 0 matches [RAN grep -> 0] |
| 3 | T-302 Admin h1 bare, no `mb-1` invented | Yes | [VERIFIED frontend/AdminScreen.jsx:670-671] `<h1>Admin</h1>` + `mt-1` subtitle |
| 4 | T-303 audit `title={JSON.stringify(event.detail)}`, guard preserved | Yes | [VERIFIED frontend/AdminScreen.jsx:628-630] guard text unchanged |
| 5 | T-303 `.admin-invite-code` gains `flex-wrap: wrap` | Yes | [VERIFIED frontend/styles.css:310] |
| 6 | T-304 alert `id="auth-error"`; both fields `aria-invalid`/`aria-describedby` gated on `error` | Yes | [VERIFIED frontend/views/AuthView.jsx:59,67-68,79-80]; single mount [VERIFIED frontend/App.jsx:201-207]; `grep auth-error frontend` → only these 3 lines |
| 7 | 7 files, forbidden files untouched (PredictPanel/Tailwind/App/theme) | Yes | [RAN git diff --name-only -> 7 listed]; empty diff for forbidden set |
| 8 | No token/floor/config edits | Yes | `styles.css` diff is the single flex-wrap declaration; no tailwind.config change; no 24px/min-height/px value touched |
| 9 | Tests added: 6 static + 2 auth, 0 changed | Yes | Diff adds 65 lines `static.test.js` (4 `it` blocks incl. 2 compound), 51 lines `auth.test.jsx` (2 `it`); no test deletions |
| 10 | Scoped run pass 79 (4 files) / full 162 / build green | Partial | [RAN npm test -- tests/static.test.js tests/auth.test.jsx -> 2 passed / 51 passed] independently reproduces the pass for the 2 touched test files. 4-file 79, full 162, and build claims are implementer-reported only; reviewer did not re-run full suite/build (standing orders §16). No contradiction observed. |
| 11 | Pre-fix mutation: 7 failed, 44 passed | Reasoned | Pins target exact pre-fix literals; guard self-checks assert pre-fix strings fail the pins (e.g. `static.test.js` "Guard self-check" lines). Revert-then-run not performed (read-only brief). |
| 12 | Playwright rendered check NOT-RUN (MCP unavailable), preview+curl proxy used | Accepted / honest | No Playwright claim made; report §7/§14 marks rendered console/contrast/overflow unverified. Matches plan's acceptance split honestly. |
| 13 | Blast radius: emoji 0, palette 0, `auth-error` unique, `newjob`/`admin` tests unaffected | Mostly | Emoji 0 re-verified [RAN grep -> 0] (and again in §1); `auth-error` uniqueness confirmed. Palette grep and newjob/admin suite not re-run (scoped-only); no diff contradicts them (no utility classes added). |
| 14 | `least_confident_about`: T-304 both-fields vs per-field | Confirmed as real trade-off, not a defect per pinned plan | See R-W1-001 (MINOR, DO-LATER): INV P-12 plural-fields + brief "fields" justify both; 409/429/network over-marking is semantically broad but announce-equivalent via `role=alert` + `describedby`. |

## 3. Long-run test (independent answers)
**Source:** Static pins read source text (`index.htmlSource`, `newJobSource`, `source`, `stylesSource`); auth pins assert jsdom DOM attributes. Deterministic, no network, no timing dependence. New tests are isolated: pre-submit clean-state test + failed-submit test; each restores module state via fresh `renderApp`. No shared-env mutation.
**Load (100x, concurrency, partial failure):** No logic changed except attrs gated on the existing `error` state. `aria-invalid`/`aria-describedby` are two props; no I/O, no loops. Double `JSON.stringify(event.detail)` per audit row is negligible (detail is a small JSON object behind the guard). Partial failure (backend down) is the tested path: same alert text, now addressable by id. Concurrent submits unchanged (`setError(null)`/`setLoading` flow untouched).
**Hostile input:** Oversized audit detail still truncates visually but full JSON now exposed via `title` (React escapes attribute values — no injection). Long invite code: `flex-wrap` lets the copy button drop to a new line instead of squeezing; residual limit — an unbreakable code string longer than the card still needs `overflow-wrap` on the code element (R-W1-002, not pinned). Credentials overflow unchanged.
**Operability:** One declaration per file, no migration, no config. Rollback = revert 4 small hunks independently. No observability change needed (design polish, not behavior).
**Reversal:** Which test fails if the fix is reverted? Each fix has a pin asserting its exact post-fix literal/id: favicon order pin, no-emoji/h3/h1 pins, `title=` + `flex-wrap` pins, auth `aria-invalid="true"` + `aria-describedby===alert.id` + target-is-alert assertions. Removing any fix makes its pin fail for the right reason (pins match/removal-test logic verified by reading, not by executing a revert).

## 4. Findings

### R-W1-001 [MINOR] T-304 marks both fields invalid for form-level errors (409 username-taken, 429 rate-limit, network) where neither/both are semantically wrong
- Location: `frontend/views/AuthView.jsx:67-68,79-80` · Evidence: both inputs gate on the single form-level `error: string`; 409 message is username-specific (`"Username already taken..."`, AuthView.jsx:38-39) yet password also gets `aria-invalid="true"`; network/429 errors mark both invalid although neither field is wrong. · Why it matters: screen readers announce "invalid entry" for a field that is not invalid — misleading but not blocking: the alert text itself is still announced via `role="alert"` and now via `aria-describedby` on both fields, and per-field server detail does not exist. Plan decision (Decisions: "Auth aria-invalid: INCLUDED") + INV P-12 plural-fields + brief scope ("Auth first only") justify the shipped choice; narrowing needs error-type mapping beyond the pinned brief (coder §15 correctly flagged it). · Recommended fix (DO-LATER, root cause): map by status already available in `handleSubmit`: 409 → `aria-invalid` on username only; 429/network → `aria-describedby` on both but `aria-invalid` omitted; credential errors (401-ish) → both. Pair with auth tests per branch. Do NOT gate on parsing the message string.

### R-W1-002 [NIT] `.admin-invite-code` wrap does not break an unbreakable long code string
- Location: `frontend/styles.css:310` + `frontend/AdminScreen.jsx:554-556` · Evidence: `flex-wrap: wrap` moves the copy button below, but the code text (`tabular-nums`, no `overflow-wrap`/`word-break`) is a single unbreakable flex item whose min-content width can still exceed the card at 390px. · Why it matters: pinned T-303 fix only; overflow at extreme code lengths remains possible — not a regression (pre-fix behavior identical-or-worse). · Recommended fix (DO-LATER): add `overflow-wrap: anywhere` (or `word-break: break-all`) to the code element, only if INV P-08 hostile lengths are in scope for a later pass. Not required for this verdict.

### R-W1-003 [NIT] Favicon data-URI contains literal spaces (not `%20`)
- Location: `frontend/index.html:6` · Evidence: `viewBox='0 0 16 16'`, `d='M3 8h3...'` etc. are unencoded; `<`, `>`, `#` are encoded. Browsers accept spaces inside a quoted `href` data-URI, and the static pin only checks presence/order. · Why it matters: strict URL parsing would want `%20`; practically browsers handle it, and the SVG itself decodes to valid XML. · Recommended fix (NOT WORTH IT now): percent-encode spaces if a future favicon edit touches the line. Do not churn.

## 5. Attempts to break it
- Reversal reasoning: removing `title=` from the audit div fails the `title={JSON.stringify(event.detail)}` pin; removing `flex-wrap` fails the `/flex-wrap:\s*wrap/` rule pin; removing `aria-invalid`/`aria-describedby` fails the failed-submit loop assertions (`toHaveAttribute('aria-invalid','true')` + describedby-target-is-alert). Guard self-checks inside each new test confirm the pre-fix literal fails the pin (not vacuous tests).
- Error-truthy gate: with `error=null`, React omits `undefined` attrs — pre-submit test asserts no `aria-invalid="true"` and no `aria-describedby` [RAN scoped suite -> 51 passed confirms].
- Dangling reference: `id="auth-error"` and `aria-describedby` share the identical `error` truthy condition, so describedby can never point at a missing element (and vice versa) — verified by reading L59/L68/L80, not by DOM inspection of error-null. [RAN scoped suite post-fix pass].
- Hostile strings: audit `title` uses React attribute escaping — no breakout via `detail` containing quotes; invite long string covered by R-W1-002 residual limit.
- No concurrency/interleaving surface introduced (no async, state, or I/O changes).
- Not executed: full 162-test suite, `npm run build`, real-browser favicon/contrast/overflow checks (standing orders scope + plan defers rendered data-view parity; coder honestly marked Playwright NOT-RUN).

## 6. Dimension checklist
- Correctness: PASS — each pin lands exactly on the defect line the brief names.
- Root cause vs symptom: PASS — favicon data-URI (no missing-file fetch), type convergence to global scale, tooltip/wrap (exposure/overflow) address causes.
- Regression/compat: PASS — initial DOM unchanged when `error` null; `title` additive; `flex-wrap` inert for short codes; no caller depends on removed classes (h3 no longer `text-lg` but brief-mandated, global h3 0.9375rem is the target).
- Concurrency/idempotency: PASS — no async touchpoints added.
- Error handling: PASS — aria follows existing `error` state; no new throws.
- Security/abuse: PASS — no input handling, secrets, or fetch changes; React escaping; static data-URI.
- Performance/scalability: PASS — one link tag, one CSS declaration, prop-level aria; duplicate `JSON.stringify` negligible.
- Migration/rollback: PASS — none needed; per-hunk revert.
- Observability: N/A (no behavior/metrics change).
- Maintainability/conventions: PASS — keep-list honored (`font-semibold text-strong mb-4`), bare h1 without invented `mb-1`, token-only CSS untouched.
- Docs impact: None required (no behavior/API change; plan Decisions already record accepted/dropped items).

## 7. Optimization and simplification opportunities
| # | Location | Evidence | Impact | Effort | Risk | Verdict |
|---|---|---|---|---|---|---|
| 1 | AuthView 409/network/429 per-field aria mapping (R-W1-001) | Status available in catch; only message string varies | a11y semantic accuracy | Small (state per field or derived flags + tests) | Medium (new branch tests; plan scope) | DO LATER |
| 2 | Invite code `overflow-wrap: anywhere` (R-W1-002) | Unbreakable code vs 390px card | Extreme-length overflow edge | Trivial CSS | Low | DO LATER |
| 3 | De-duplicate `JSON.stringify(event.detail)` in audit row | Two identical calls per row (L629 body + title) | Negligible CPU | Trivial (variable) | Very low | NOT WORTH IT |

## 8. Cross-agent / cross-task interactions observed
None in the diff. Forbidden/set-touching confirmed empty (PredictPanel, tailwind.config, App, theme). `frontend/dist/` not touched by this commit (build output not in source tree; coder's preview on :3101 claimed killed with connection-refused evidence). No conflict with other wave-1 files observed.

## 9. What I could not verify
- Full `npm test` (162) and `npm run build` green — implementer-reported only; reviewer ran the 2 touched test files (51 passed). [RAN npm test -- static/auth -> 51 passed]
- Rendered Playwright evidence (favicon 404 absence, dark/light contrast, 390/1280 overflow) — NOT-RUN in both implementer and reviewer sessions (no MCP); coder's preview+curl proxy not independently re-run.
- Real-browser decode of the data-URI SVG (XML well-formedness established by manual decode only; automated `node` decode was scanner-blocked — see §0).
- Palette-utility-0 and `newjob.test.jsx`/`admin.test.jsx` green — not re-run (scoped-only rule); diff adds no utility classes so no contradiction is visible.
- Pre-fix 7-failed mutation run — reasoned from pins/self-checks, not re-executed (read-only brief).

## 10. Band-aid hunt
None found. No try/catch added, no sleep/retry/timeout, no test weakening (tests only added), no hardcoded test inputs, no type suppression, no flag-gated path, no fix-at-callsite vs source. The `auth-error` string is a static literal (not input-derived).
