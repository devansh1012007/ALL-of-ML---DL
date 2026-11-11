<!-- ORCH-DIGEST:START -->
agent: W1-PLAN-01 | domain: planner-review fine-tune plan T-203 | status: DONE
items: 6 SURFACE fixes claimed + 24px accept + 5 deferred hypotheses | verdict: APPROVE-WITH-CHANGES
top_risks: T-303 file:btn copy likely dead (Tailwind v3 custom class + file: variant) — would REGRESS NewJob upload; acceptance demands NewJob/Admin Playwright while deferring backend-up pass (unachievable as written); Auth aria-invalid gap mis-bucketed as hypothesis
cross_domain_conflicts: none
out_of_plan_discoveries: file:btn mechanism may be broken in PredictPanel itself; smoke.test pin overstatement; 9 vs 8 keep-count mismatch
confidence: medium (plan + W0 reports + targeted spot-reads; build/test not run per brief)
last_comms_line_read: COMMS header only
<!-- ORCH-DIGEST:END -->

# Plan review — W1-PLAN-01 — fine-tune plan (T-203)

## 0. Scope and method
Plan under review: `docs/plans/2026-11-09-playwright-fine-tune.md` (draft, T-203). W0: `INV-playwright-audit.md` (W0-INV-01, rendered, auth-only), `INV-code-design.md` (W0-INV-02, code census, 21 items). Spot-verified this session (read-only): `frontend/index.html` (no icon link), `frontend/views/NewJob.jsx:660` (emoji h3), `:431` (bespoke file button), `frontend/AdminScreen.jsx:670` (h1 override), `:628-630` (audit truncate, no title), `frontend/styles.css:310` (invite-code, no flex-wrap), `frontend/tests/static.test.js:212-222` (24px floor pins), `frontend/tests/smoke.test.jsx:220-223` (nav-link class pin), `frontend/views/PredictPanel.jsx:232` (`file:btn`), `frontend/tailwind.config.js` (no plugin), `frontend/package.json` (tailwindcss ^3.4.4). Scoped greps/reads only; no suite/build per brief. Branch `frontend-ui-round2` verified.

## 1. Verdict
**APPROVE-WITH-CHANGES** — the surface-batch approach is sound and the W0 evidence is honestly carried, but T-303 must not land as written (likely-dead `file:btn` copy), and acceptance must be rewritten to match the no-backend scope. Resolve B1 + M1 before any implementation.

## 2. Plan in my words
User asked for Playwright MCP design fine-tune. W0 rendered Auth clean (contrast/overflow/focus/error-state all verified) and could not render data views (backend down, brief forbids starting it). Plan therefore: (T-301) favicon data-URI; (T-302) NewJob emoji+h3 and Admin h1 type fixes; (T-303) NewJob file button → Predict pattern, audit title, invite flex-wrap; (T-304) document-only: accept 24px test-pinned floor, defer ResultLine/header/Compare/aria hypotheses until backend-up pass; close 9 keep items as docs. Rejected: full backend install + 7-surface matrix (heavy, low value), immediate 40px raise (contract change). Success = `npm test` + build green, Auth Playwright clean, greps clean, header/row heights unchanged. I understand the bar as "code-certain 1-2-line defects only, no redesign, no silent contract changes."

## 3. Claim-by-claim classification
| Plan claim | Classification | Evidence |
|---|---|---|
| Auth rendered clean except favicon 404 + 24px `.link` (test-pinned R5 floor, WCAG 2.2 2.5.8 AA exact) | SUPPORTED | INV-playwright §P-01/P-02 measured 24.0px 1280/390 × themes; `styles.css:122` `.link {min-height:1.5rem}` [VERIFIED this session]; pins `static.test.js:212-222` [VERIFIED] |
| Token census clean (0 hex JSX, 0 `dark:`, token map 14) | SUPPORTED (adopted from W0, not re-ran) | INV-code-design §0 grep counts; not re-grepped this session |
| Candidates P-03..P-21 + 9 verified-keep | SUPPORTED with count error (see m2) | INV lists 8 document-only items in §5 (P-05/P-07/P-09/P-10/P-11/P-16/P-18/P-21); plan says 9 |
| T-301 favicon data-URI, head before init, console clean | SUPPORTED | `index.html:5-6` meta+script, no icon link [VERIFIED]; static head pins `static.test.js:513-520` [VERIFIED] allow insertion anywhere in head before `</head>` |
| T-302 NewJob drop 📊 + `text-lg`; Admin drop `text-2xl font-bold tracking-tight` | SUPPORTED | `NewJob.jsx:660` sole emoji + override [VERIFIED]; `AdminScreen.jsx:670` sole h1 override vs 6 bare `mb-1` h1s [VERIFIED grep `h1 className` → 7 hits]; global `h1 1.5rem/600` `styles.css:70` [VERIFIED]; `newjob.test.jsx:149` regex `/model intelligence/i` survives glyph removal [VERIFIED] |
| T-303 NewJob `file:btn file:btn-quiet` matches Predict | UNSUPPORTED / likely broken (B1) | Predict `PredictPanel.jsx:232` uses `file:btn` [VERIFIED]; but `package.json` tailwind ^3.4.4 + `.btn` in `@layer components` (`styles.css:109`) + `tailwind.config.js` (no plugin/`@utility`) ⇒ `file:btn` has no utility to generate (see B1) |
| T-303 audit `title={...}` zero layout change | SUPPORTED | `AdminScreen.jsx:628-630` truncate, no title [VERIFIED]; detail is JSON (`models.py:255` `Column(JSON)`) so `JSON.stringify` is correct type |
| T-303 invite `flex-wrap: wrap` safe when short | SUPPORTED | `styles.css:310` flex, no wrap [VERIFIED]; wrap engages only on overflow — INV P-08 concur |
| Defer ResultLine/header/Compare/aria (hypotheses) until backend-up | PARTIALLY UNSUPPORTED (aria not hypothesis, see M3) | ResultLine/header/Compare/focus-walk correctly deferred (INV P-06/P-15/P-19/P-20 need render); `aria-invalid` 0 hits [VERIFIED grep → none] is code-certain gap, not hypothesis |
| Acceptance: `npm test` 154 baseline + build green; Auth screenshots + greps; heights unchanged | MISSING/UNVERIFIED pieces | 154 count not verifiable (no suite per brief); heights probe undefined; NewJob/Admin Playwright impossible under deferral (M1) |

## 4. Findings

### BLOCKER
- **B1 — T-303 file-button copy is likely dead and would regress the upload control.**
  Problem: plan copies Predict's `file:btn file:btn-quiet` into NewJob. `.btn`/`.btn-quiet` are plain-CSS component classes (`styles.css:109-119`), not Tailwind utilities; `tailwindcss ^3.4.4` (`package.json`) with `tailwind.config.js` (no plugins, no utility registration) cannot resolve `file:btn` to any declaration — Tailwind v3 silently ignores unknown candidates, so the pseudo-button keeps browser defaults plus only `file:mr-4`/`file:cursor-pointer`. Meanwhile NewJob's current bespoke `file:rounded-md file:border-0 file:bg-raised file:px-3 file:py-1.5 ...` (`NewJob.jsx:431`) *does* resolve (core utilities + registered token colors) and renders. As written, T-303 deletes working styles and adds dead ones: a visible regression the plan's verification cannot catch (Auth-only Playwright; data views not rendered). Focus coupling compounds it: `.btn` is `display:inline-flex; min-height:2rem` — even if the variant worked, restyling `::file-selector-button` changes upload-row height and pseudo-element focus behavior, which INV P-13 explicitly left unverified and requires rendered focus proof (acceptance for P-13: screenshots + visible ring at 390). Plan supplies no such probe.
  Consequence: merged T-303 makes the NewJob CSV button worse while "unifying" it; Predict's own button is likely already unstyled (both need fixing, not copying).
  Evidence: [VERIFIED PredictPanel.jsx:232 `file:btn`]; [VERIFIED NewJob.jsx:431 working utilities]; [VERIFIED styles.css:109-119 `.btn` component layer]; [VERIFIED tailwind.config.js:32 `plugins: []`, package.json tailwind ^3.4.4]; [INFERENCE Tailwind v3 JIT ignores unknown `file:btn` — build CSS not run per brief, so mark UNVERIFIED mechanism, load-bearing].
  Suggested change: stop T-303 file-button until implementer runs `npm run build` and greps `dist/assets/*.css` for a `::file-selector-button` rule derived from `file:btn`; if absent (expected), replace the plan instruction with a CSS rule (`input[type=file]::file-selector-button` styled from `.btn` tokens) or real utilities, applied to *both* inputs, with a static assertion + jsdom class pin. Do not land the class swap on string identity alone.

### MAJOR
- **M1 — Acceptance contradicts the deferral: NewJob/Admin Playwright is required but backend-up is deferred.**
  Problem: T-302/T-303 acceptance says "Playwright: NewJob/Auth... headings at 24px/600" / NewJob/Admin verification, yet Approach A defers the only way to render them (backend + seed/admin + token) and Facts honestly excludes data views as NOT-RENDERABLE. Implementer cannot satisfy acceptance without breaking Approach A (installing torch-scale deps, starting backend). INV-code-design §5 ordered T1 (backend-up audit) *first* precisely to ground data-view claims; plan inverts the order and still claims rendered verification for the inverted work.
  Consequence: failed delivery / unverifiable sign-off; implementer either skips the Playwright step (silent acceptance failure) or drags in the rejected Approach B blast radius.
  Evidence: plan §Approach A + §Atomic phases T-302/T-303 vs §Acceptance; INV-playwright §F + §5 W1-T1; INV-code-design §5 W1-T1 first, P-13 acceptance requires 390 screenshots.
  Suggested change: split acceptance by surface — Auth: Playwright console + screenshots (backend-down OK); NewJob/Admin: static assertions + jsdom (`newjob.test.jsx`, `admin.test.jsx`) + grep, explicitly "rendered parity deferred to backend-up pass." Add backend-up as a named follow-up with owner, not as acceptance for this wave.
- **M2 — `aria-invalid`/`aria-describedby` gap misclassified as hypothesis and deferred without rationale.**
  Problem: plan T-304 lumps "aria hypotheses" with ResultLine/header/Compare (all need render). But P-12 is code-certain: grep → 0 hits across `{App,AdminScreen}.jsx`, `views/**`, `components/**` [VERIFIED this session: no matches in `frontend/*.jsx`]. INV P-12 recommends fix for Auth first (highest value) and Auth *is* renderable this wave (W0 rendered it), so the fix is uniquely verifiable now — unlike the other deferrals. Plan neither includes it nor explains exclusion under "fixes ONLY concrete defects found."
  Consequence: leaves the one a11y gap verifiable today for a later sweep with no trigger; mislabeling invites a future agent to treat a proven gap as speculative.
  Evidence: [VERIFIED grep `aria-invalid|aria-describedby|aria-errormessage` → no matches]; INV-code-design P-12 (DEEP, Auth-first) + §5 W1-T4.
  Suggested change: either add Auth `aria-invalid`+`aria-describedby` as T-3xx (AuthView + `auth.test.jsx`, Playwright error-state already proven) or state explicitly: "P-12 deferred to a11y sweep because DEEP/test-contract, Auth visual fine-tune only" — do not list it as a hypothesis.
- **M3 — Test strategy is grep-only for 5 of 6 fixes; no reversal tripwires.**
  Problem: plan adds 1-2 static assertions for favicon only. Emoji removal, Admin h1 de-override, file button, audit title, invite wrap get grep/manual-screenshot acceptance but no pinned test. Standing orders §10 + INV long-run pattern require a test that fails without the fix; precedent is abundant (`static.test.js` already pins classes, floors, head order, warn token at :532-536). A future edit can reintroduce 📊 / `text-2xl` / missing title with zero suite failure.
  Consequence: regression drift on exactly the inconsistencies this wave cleans.
  Evidence: plan §Atomic phases / §Blast radius (`static.test.js (+1–2 assertions)` — those go to favicon); [VERIFIED `newjob.test.jsx:149` matches text without pinning glyph/size; no test pins Admin h1 classes, audit `title`, or `.admin-invite-code` wrap — greps for those → none]; `static.test.js:137-176` shows the pinned-class pattern exists.
  Suggested change: add cheap static pins: no `📊` in shipped JSX + NewJob h3 has no `text-lg`; AdminScreen h1 carries no `text-2xl/font-bold`; audit truncate carries `title=`; `.admin-invite-code` declares `flex-wrap: wrap`. (File-button pin only after B1 mechanism is settled.)

### MINOR
- **m1 — 24px framing is correct on AA/test-pin, but plan overstates smoke coverage and omits the width half.**
  WCAG 2.2 SC 2.5.8 AA minimum is 24×24 CSS px (or spacing exception) — plan's "24 exactly, test-pinned" is accurate for height (`styles.css:122` + measured 24.0px, INV §P-01). Two refinements: (a) width is never measured — `.link` width is text-driven so compliance is near-certain, but plan should cite it (INV measured height only); (b) `smoke.test.jsx:220-223` pins only `className` contains `nav-link` with a "24px" comment [VERIFIED], not the value — `static.test.js:212-222` is the real value pin. Raising the floor would not fail smoke by assertion (comment update only). Plan §Approach C ("rewrites `static.test.js`/`smoke.test.jsx` pins") inherits INV's overstatement. Suggested: record "24×24 (height measured 24.0; width text-driven >24 — [UNVERIFIED rendered width])" and list `static.test.js` as the contract, smoke as comment.
- **m2 — "9 verified-keep items" count is off by one; list them.**
  INV §5 closes P-05/P-07/P-09/P-10/P-11/P-16/P-18/P-21 = 8 items. Plan says 9. No defect risk, but a cold reader cannot reconcile the list. Suggested: enumerate the 8 + state which 9th was meant (or correct to 8).
- **m3 — T-302 under-specifies the landing state.**
  Admin: dropping overrides leaves bare `<h1>` vs page-standard `mb-1` on all 6 other h1s (grep [VERIFIED]) — fine (subtitle `mt-1` spaces it), but plan should say "strip to bare `<h1>`" so implementer does not invent `mb-1`. NewJob: dropping `text-lg` leaves `font-semibold text-strong mb-4` (600 matches global h3 600 [VERIFIED styles.css:69-72]) — plan should say keep the rest, not swap to `.newjob-section-title` (which uses 1.25rem margin vs current 1rem). One-sentence clarification prevents drift.
- **m4 — Favicon placement needs the head-pin guard in the task text.**
  INV P-02 says insert between `color-scheme` meta (L5) and init script (L6); plan says "before init script." `static.test.js:510-530` pins only init-before-module/headEnd [VERIFIED], so any head position passes — but the init-before-module order and `prime_theme` literal must not be disturbed by a well-meaning formatter. Suggested: name the exact insertion point (after L5, before L6) and "do not move the init script."

## 5. Assumption table
| Assumption | Status | Evidence |
|---|---|---|
| 24px meets WCAG 2.2 SC 2.5.8 AA exactly | Verified true (height); width unverified | Measured 24.0px INV §P-01; `.link` text width not measured |
| 24px floor is test-pinned (value, not just comment) | Verified true for `static.test.js`; false for `smoke.test.jsx` as value pin | `static.test.js:212-222` value pins [VERIFIED]; `smoke.test.jsx:220-223` class-only [VERIFIED] |
| `file:btn` renders `.btn` styles | Unverified, likely false (load-bearing, B1) | Tailwind v3 + component layer + empty plugins [VERIFIED]; build CSS not run per brief |
| NewJob/Admin headings verifiable via Playwright under Approach A | Verified false | Backend down + no seed/token (INV §F); plan defers backend-up |
| Invite `flex-wrap` zero-risk when short | Verified true (by CSS semantics + INV P-08) | `styles.css:310` [VERIFIED] |
| Audit `title={JSON.stringify(detail)}` is type-correct | Verified true | `detail Column(JSON)` [VERIFIED models.py:255]; guard `Object.keys(...).length` [VERIFIED AdminScreen.jsx:628] |
| `npm test` 154 baseline | Unverified | No suite run per brief/standing orders; count from plan only |
| Backend install is heavy / out of scope for fine-tune | Verified true (as scoping judgment) | `install.sh` uv + python 3.12 + torch-scale deps per AGENTS.md; INV B-concurs |

## 6. Parallelism and ownership check
Tasks are file-disjoint and safe to parallelize: T-301 (`index.html` + 1 static test), T-302a (`NewJob.jsx:660`), T-302b (`AdminScreen.jsx:670`), T-303 audit (`AdminScreen.jsx:628`), T-303 invite (`styles.css:310`) — no shared files except `tests/static.test.js` assertions (append-only, conflict-free if one agent owns that file) and `NewJob.jsx`/`AdminScreen.jsx` two-spot edits (same-file, sequence or single owner). T-303 file-button must be sequenced last pending B1 resolution (mechanism decision gates the edit). No shared config/migrations/lockfiles. Rollback: each spot is independently revertible; no ordering constraint beyond B1-first.

## 7. Test strategy gaps
What exists: Auth Playwright matrix (W0 done), static declaration/arithmetic guards, jsdom DOM/focus-`activeElement` tests. Gaps vs plan: (1) no tripwire for 5/6 fixes (M3); (2) no probe defined for "header/row heights unchanged" (no Playwright `getBoundingClientRect` checklist); (3) file-button focus/hover at 390 unmeasured (INV P-13/P-20) and unmeasured after change; (4) invite-wrap needs hostile-input check (32+ char code) per INV P-08; (5) `aria-invalid` Auth fix would need `auth.test.jsx` additions (deferred — see M2). Jsdom cannot close (1)-(4) (`test.css:false`, no layout) — Playwright or static string pins are the only options, and plan must name which. Reversal tests (which test fails if fix reverted): favicon → new static assertion; emoji/h1/title/wrap → new static assertions (currently none); file-button → build-CSS grep (after B1); heights → none.

## 8. Pre-mortem (top three)
1. **T-303 ships dead-button regression, undetected.** Copy applied, `npm test` green (no pin), Auth Playwright green (NewJob not rendered), file button silently unstyled. *Covered?* No — plan's verification cannot see it (B1/M1). Fix: build-CSS check + static pin.
2. **"Done" declared with data surfaces still unaudited; ResultLine/Compare/header defect surfaces a month later attributed to this fine-tune.** Invite/Error: plan closes keep items as documentation without screenshots, acceptance mentions NewJob/Admin Playwright which no one runs. *Covered?* Partially — Facts honestly excludes, but acceptance overshoot creates false confidence (M1). Fix: narrowed acceptance + named backend-up follow-up.
3. **Emoji/h1 drift recurs.** No pins; a later view edit re-adds `text-lg`/`text-2xl`. *Covered?* No (M3). Fix: static tripwires.

## 9. Second-order effects
- Favourable: favicon + type convergence slightly cheapen future views (one less precedent for overrides/emoji). Neutral: invite wrap + audit title are additive, no consumer depends on single-row invite or missing title. Risky: if `file:btn` pattern spreads, more pseudo-buttons become unstyled — B1 is a pattern-contagion risk, not a one-off. Deferred backend-up keeps data-view CSS hypotheses fossilized: future fine-tunes must re-derive the same uncertainty until a rendered pass lands (INV W1-T1 still owed). 24px acceptance locks the floor: a future 40px raise must still do the paired-test dance — no new cost, but the record should note the zero-margin fragility (any future height override reopens AA).

## 10. Questions for the orchestrator or user (blocking marked *)
1. *(Blocking, B1)* Is `file:btn` proven to generate CSS in this repo (build output)? If not, does ORCH want (a) CSS pseudo-element rule for both file inputs, (b) real-utility rebuild, or (c) T-303 file-button dropped from this wave?
2. *(Blocking, M1)* Is surface-batch-only acceptable with data views unaudited, and should acceptance be narrowed to Auth-Playwright + static/jsdom with a separately scheduled backend-up pass (owner/date)?
3. *(Non-blocking, M2)* Is Auth `aria-invalid` deferred to an a11y sweep by decision, or should it join this wave (it is the only deferral verifiable without backend)?
4. *(Non-blocking, m2)* Which 9th keep item did the plan mean?

## 11. What the plan gets right
The spine is honest: it carries W0's NOT-RENDERABLE exclusion verbatim, refuses to fix ResultLine/header/Compare/focus on hypothesis (INV's explicit rule), frames 24px as AA-exact + test-pinned rather than 40px-by-default, scopes write-set to 5 files with no token/`tailwind.config`/RunDetails touch, and keeps each commit independently revertible. The 6-fix batch (favicon/emoji/h1/title/wrap) is the right minimal set — only its file-button mechanism and acceptance wording need repair, not its scope.

## 12. Scratch files created
- `docs/agent-ops/20261109-playwright-design/reports/w1-review/PLAN-W1-PLAN-01.md` (this report; initial skeleton + full revision — same path, no other files).
- No other repo files created/modified. No builds/tests run.
