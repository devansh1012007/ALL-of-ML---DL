<!-- ORCH-DIGEST:START -->
agent: W0-INV-02 | domain: code-level-design-audit | status: DONE
items: 18 verified EXISTS / 0 already-fixed / 0 not-reproducible / 1 partial / 1 misclassified
proposed_tasks: 12 (SURFACE 11, DEEP 1)
top_risks: 24px tap-target set is test-pinned and needs a product decision, not a CSS-only edit; data views NOT-RENDERABLE (backend down) so all 390/data-view claims are code-only until the backend-up Playwright pass; admin contrast + focus on data views unverified until rendered
cross_domain_conflicts: none
out_of_plan_discoveries: 4
confidence: high (token census + per-view inventory source-verified with grep counts and path:line; rendered layout NOT verified — no browser)
last_comms_line_read: [2026-11-08T16:07:02Z] W0-INV-01 -> ALL | DONE | T-201
<!-- ORCH-DIGEST:END -->

# Investigation report — W0-INV-02 — Code-level design audit (T-202)

## 0. Scope and method
Task: code-level audit of the design surface (tokens, components, a11y, responsive) to cross-check what Playwright will find rendered and to give the fine-tune wave an exact file:line fix map. Read in brief order: `templates/STANDING-ORDERS.md`, AGENTS.md frontend conventions, `00-mission.md`, `01-work-ledger.md`, `COMMS.md`, `templates/report-investigation.md`, `frontend/styles.css` (all 345 lines), `frontend/tailwind.config.js`, `frontend/index.html`, `frontend/App.jsx`, `frontend/components/theme.jsx`, `frontend/components/shared.jsx`, `frontend/components/metrics.jsx`, `frontend/views/{AuthView,ModelsCatalog,RunsDashboard,RunDetails,NewJob,PredictPanel,CompareRuns}.jsx`, `frontend/AdminScreen.jsx`, `frontend/tests/static.test.js` (all 538 lines), `docs/plans/2026-11-08-light-mode.md`, plus the full W0-INV-01 rendered-audit report for cross-checking.
Method: grep counts + path:line evidence only; no browser, no full suite/build. No source files edited. Branch verified `frontend-ui-round2`, HEAD `7ce8bed`.

Token census (this session, re-run — not trusted from prior work):
- [RAN grep `#[0-9a-fA-F]{3,8}\b` over frontend/] → 11 hits: only `styles.css:16-19` hex in token-definition comments (allowlisted per light spec §5.5) and `#101` test text in `tests/admin.test.jsx`. Zero hex in shipped JSX.
- [RAN grep `dark:`] → 0 hits.
- [RAN grep arbitrary color values `bg-|text-|border-|ring-` + `[#\d]`] → 0 hits. Sole `[...]` color utility is `RunsDashboard.jsx:98` `accent-[rgb(var(--accent))]` — token-indirected (allowed pattern; the checkbox accent resolves through the token in both themes).
- [RAN grep palette utilities `(bg|text|border|ring)-(slate|zinc|gray|red|amber|emerald|blue|…)-`] → 2 hits, both in `tests/static.test.js:534,536` as a *negative* guard (`not.toContain('text-orange-400')`). The pre-T-101 `text-orange-400` outlier at `NewJob.jsx:678` is gone (now `text-warn`; `NewJob.jsx:676-679` verified).
- [RAN grep `rgb\(|text-white|bg-white`] → 94 hits, all `rgb(var(--token))` indirection in `styles.css`/`metrics.jsx:270`/`tailwind.config.js:3`. Zero `bg-white`/`text-black`.
- Theme init: `index.html:6-26` meta + pre-paint init, `theme.jsx:10-62` `resolveTheme/applyTheme/toggleTheme`, `theme.jsx:70` `aria-pressed={isLight}` — all verified by read; parity pinned by `static.test.js:509-530`.
- Verdict: **token census verified clean.** No hardcoded hex, no `dark:`, no palette utilities, no arbitrary color values in shipped code. `tailwind.config.js:9-24` maps exactly the 14 token names (`canvas, surface, raised, rule, strong, ink, muted, faint, accent, accent-hover, accent-ink, ok, warn, bad`); `content` globs (L6) cover `index.html`, `App.jsx`, `AdminScreen.jsx`, `main.jsx`, `views/**`, `components/**`.

## 1. Per plan item (repeat the block)

### P-01 (T-202 C-01/C-14) — 24px tap-target floor family (`.link`, `.nav-link`, `.breadcrumb a`, `.compare-check`, `.admin-icon-btn`, disclosures, Sign out)
- **Existence verdict:** EXISTS (measured by W0-INV-01 at 24.0px; confirmed in code here)
- **Evidence:** [VERIFIED styles.css:86] `summary.disclosure-summary { min-height: 1.5rem }`; [VERIFIED styles.css:111] `.btn { min-height: 2rem }` (32px — above floor); [VERIFIED styles.css:122] `.link { min-height: 1.5rem }`; [VERIFIED styles.css:131] `.nav-link { min-height: 1.5rem; padding: 0.375rem 0.625rem }`; [VERIFIED styles.css:144] `.breadcrumb a { min-height: 1.5rem }`; [VERIFIED styles.css:177] `.compare-check { min-width: 1.5rem; min-height: 1.5rem }`; [VERIFIED styles.css:229] `.compare-run-link { min-height: 1.5rem }`; [VERIFIED styles.css:326] `.admin-icon-btn { min-width: 1.5rem; min-height: 1.5rem }`; [VERIFIED App.jsx:160] Sign out `min-h-6` (24px). Test pins: [VERIFIED tests/static.test.js:211-223] "interactive classes declare a 24px floor" asserts all six `.css` rules + `min-h-6`; [VERIFIED W0-INV-01 §P-01] `tests/smoke.test.jsx:220` pins `.nav-link` 24px. W0-INV-01 rendered measurement: `.link` = 24.0px at 1280/390 × dark/light — exactly meets WCAG 2.2 SC 2.5.8 AA (24×24) with zero margin.
- **Root cause chain:** R5 round set a documented 24px floor (`styles.css:86,111,290` comments) as the WCAG-AA minimum; every interactive class declares exactly that floor, so rendered height sits *at* the standard, not above it. The floor is **explicitly test-pinned** — raising it requires editing `static.test.js` + `smoke.test.jsx` as a deliberate contract change.
- **Blast radius:** `.link` usages: `AuthView.jsx:86` (mode switch), `RunDetails.jsx:312` (HF URL). `.nav-link`: `App.jsx:143` header nav. `.admin-icon-btn`: `AdminScreen.jsx:178,189,200,221,561`. `.breadcrumb a`: Breadcrumb component `shared.jsx:91-105` (live links only). `.compare-check`: `RunsDashboard.jsx:98`. Sign out: `App.jsx:160`. Any change shifts header height (`App.jsx:135`), Runs row height (`RunsDashboard.jsx:91-100`), and admin action columns.
- **Fix options:** A) Accept 24px as the shipped WCAG-AA decision (no code; record it). B) Raise `.link`/`.nav-link`/`.breadcrumb a`/`.compare-check`/`.admin-icon-btn`/disclosure/Sign out to 2.5rem (40px) in `styles.css` (+ `min-h-10` in App.jsx) **and** update the pinning assertions as a deliberate contract change (needs ORCH/product sign-off — the tests are a feature, not an obstacle). **Recommended:** ORCH decides; investigator takes no position on the 40px bar (per W0-INV-01 §P-01 — concur).
- **Long-run test:** Source: rendered measurement (done, W0-INV-01). Load/Hostile/Operability: n/a (pure CSS floor). Reversal: if reverted, `static.test.js` "interactive classes declare a 24px floor" + `smoke.test.jsx:220` fail without the paired test update — the correct tripwire.
- **Classification:** SURFACE (rendering-only), but **contract-touching** (test-pinned) — needs an explicit decision, not a drive-by.
- **WRITE-SET (proposed):** `frontend/styles.css` + `frontend/App.jsx` (only under B) + `frontend/tests/static.test.js` + `frontend/tests/smoke.test.jsx` (only under B). **CONTRACT-SET:** the 24px floor pins. **DEPENDS-ON:** ORCH/product decision. **ENV-SET:** none.
- **Test plan:** boundary (24 vs 40px measured via Playwright `getBoundingClientRect`), malformed/hostile n/a, concurrency n/a, idempotency n/a, partial failure n/a, exhaustion n/a, authz n/a. Which must fail before the fix: new/updated floor assertions (static) + Playwright tap measurement (40px bar) fail on current 24px code.
- **Acceptance criteria (measurable):** A) doc record "24px accepted". B) Playwright measures every interactive class ≥40px at 1280 + 390; `npm test` green with paired test updates; header row screenshot shows growth.

### P-02 (T-202 C-02) — favicon 404 on every page load
- **Existence verdict:** EXISTS
- **Evidence:** [VERIFIED index.html:1-34] no `<link rel="icon">` anywhere in `<head>`; W0-INV-01 §P-02 measured `[ERROR] 404 /favicon.ico` as the sole console error on plain load. Cross-check in code: browser auto-requests `/favicon.ico` when no icon link exists — consistent.
- **Root cause chain:** nobody shipped a favicon; the 404 is a browser default request.
- **Blast radius:** global (every view, every load).
- **Fix options:** A) inline data-URI SVG `<link rel="icon">` in `index.html` (no new dep, no new file) — insert between `<meta name="color-scheme">` (L5) and the init `<script>` (L6) so head order/pins (`static.test.js:513-520` init-before-module) are undisturbed. B) ship a real `favicon.svg` asset + link. **Recommended:** A (trivial, zero-risk).
- **Long-run test:** Source/Load/Hostile/Operability: zero-risk one line; observe via console-clean Playwright load + static assertion. Reversal: none pins this today — add/extend a static assertion for the icon link so the 404 can't regress silently.
- **Classification:** SURFACE.
- **WRITE-SET (proposed):** `frontend/index.html` (+ one-line test in `frontend/tests/static.test.js`).
- **Acceptance:** Playwright console has no 404 on load (all surfaces); static assertion passes.

### P-03 (T-202 C-03) — NewJob `📊 Model Intelligence` emoji heading
- **Existence verdict:** EXISTS
- **Evidence:** [VERIFIED views/NewJob.jsx:660] `<h3 className="text-lg font-semibold text-strong mb-4">📊 Model Intelligence</h3>` — sole emoji in shipped JSX ([RAN grep `📊` over views/] → 1 hit, this line). Only `tests/newjob.test.jsx:29,144` mention "Model Intelligence" (comments/describe, not a glyph pin — [RAN grep tests/] → 2 hits, neither asserts the emoji). Global `h3` is `0.9375rem` ([VERIFIED styles.css:72]) but this heading overrides to `text-lg` (1.125rem).
- **Root cause chain:** pre-R3 leftover in Section C panel; never converted to design-system type. Additionally the heading carries **two** inconsistencies at once: the glyph and the `text-lg` override (every other section title uses `.newjob-section-title` / plain `h2`).
- **Blast radius:** NewJob Section C only.
- **Fix options:** A) remove glyph, keep "Model Intelligence" and drop `text-lg` to inherit global h3. B) swap glyph for a lucide icon (lucide-react is already a dep — used in AdminScreen). **Recommended:** A (zero-dep, design-system type scale).
- **Long-run test:** Source: grep. Load/Hostile/Operability: text-only, zero-risk. Reversal: no test pins the glyph today; `newjob.test.jsx:144` asserts shared layout classes for the panel, unrelated to the h3 glyph — rerun that suite after.
- **Classification:** SURFACE.
- **WRITE-SET (proposed):** `frontend/views/NewJob.jsx`.
- **Acceptance:** [RAN grep `📊` views/] → 0 hits; Playwright NewJob screenshot shows plain heading; `newjob.test.jsx` green.

### P-04 (T-202 C-04) — Admin `h1` larger/bolder than the page-head standard
- **Existence verdict:** EXISTS
- **Evidence:** [VERIFIED AdminScreen.jsx:670] `<h1 className="text-2xl font-bold tracking-tight">Admin</h1>` (32px/700) vs [VERIFIED styles.css:70] `h1 { font-size: 1.5rem; font-weight: 600 }` (24px/600) inherited by every other page header (`.page-header`, e.g. `RunsDashboard.jsx:45-49`, `ModelsCatalog.jsx:59-61`, `CompareRuns.jsx:50-55`, `NewJob.jsx:342-347`, `RunDetails.jsx:232-234`). Admin also skips `.page-header` entirely ([VERIFIED AdminScreen.jsx:668-675] plain `<div>` + custom class stack) while every other view uses it.
- **Root cause chain:** AdminScreen authored ahead of the R2 page-header pattern; inline Tailwind overrides never collapsed to the shared `h1` defaults.
- **Blast radius:** admin only; breaks the type scale across 7 surfaces (one surface's title is 8px larger + 100 weight heavier).
- **Fix options:** A) drop `text-2xl font-bold tracking-tight`, inherit global h1. **Recommended:** A.
- **Long-run test:** Source: grep/computed style. Load/Hostile/Operability: one-line class removal. Reversal: add/extend a static assertion that AdminScreen h1 carries no size/weight override (optional).
- **Classification:** SURFACE.
- **WRITE-SET (proposed):** `frontend/AdminScreen.jsx`.
- **Acceptance:** Playwright measures Admin h1 at 24px/600 like all other page headers; screenshot parity across surfaces.

### P-05 (T-202 C-05) — `PredictPanel` h2 `whitespace-nowrap` ("Use this model")
- **Existence verdict:** EXISTS (harmless — no rendered defect found in code)
- **Evidence:** [VERIFIED views/PredictPanel.jsx:169-170] parent is `flex flex-wrap items-center justify-between gap-3` and the h2 carries `whitespace-nowrap`. At 390 the flex-wrap makes the heading its own wrapped row (flex item, not text wrapping), so the nowrap is redundant but not harmful. No other heading carries `whitespace-nowrap` ([RAN grep] → PredictPanel:170 only; the other nowrap hits are table cells `RunsDashboard.jsx:102,127` and the ResultLine baseline label `metrics.jsx:173`).
- **Root cause chain:** pre-flex-layout leftover.
- **Blast radius:** Predict panel header at 390 only.
- **Fix options:** A) no change (document as harmless). B) drop the class. **Recommended:** A (but Playwright must confirm the heading isn't clipped at 390 — INFERENCE, not measured).
- **Long-run test:** Source grep; Playwright 390 screenshot is the evidence. Load/Hostile/Operability/Reversal: n/a.
- **Classification:** SURFACE (informational).
- **WRITE-SET (proposed):** none (document-only) / `frontend/views/PredictPanel.jsx` if B chosen.
- **Acceptance:** Playwright 390: heading fully visible, no clip.

### P-06 (T-202 C-06) — ResultLine baseline label may overflow its scale at 390
- **Existence verdict:** EXISTS (risk, code-measured; pixels are INFERENCE until rendered)
- **Evidence:** [VERIFIED components/metrics.jsx:146] `tickLeft` clamped to 8–92%; [VERIFIED components/metrics.jsx:173] label `whitespace-nowrap -translate-x-1/2` ("baseline X"). Scale parent is ~342px at 390 (390 − 2×24px main padding `App.jsx:164` `px-5`); 8% = ~27px, half a ~90px label = ~45px ⇒ ~18px overhang beyond the card at the left extreme, and symmetric risk at 92% on the right. [INFERENCE on label pixel width — depends on the baseline number's digit count.]
- **Root cause chain:** clamp sized for desktop scale widths; at 390 the label is wide relative to the scale.
- **Blast radius:** RunDetails result panel at 390 only, when the baseline lands near a scale extreme.
- **Fix options:** A) widen the clamp (e.g. 12–88%) — one number change. B) at <640px render the label as a second row under the scale. **Recommended:** A (verify by screenshot; B only if A still overhangs with long numbers).
- **Long-run test:** Source: rendered screenshot at both extremes. Load/Hostile: a hostile/long baseline number (many digits) is exactly the trigger — test with a 5+-digit baseline. Operability: two-line JSX change. Reversal: none pinned today; screenshot is the tripwire.
- **Classification:** SURFACE.
- **WRITE-SET (proposed):** `frontend/components/metrics.jsx`.
- **Acceptance:** Playwright 390 screenshots at both scale extremes show the label fully inside the card; no page horizontal scrollbar.

### P-07 (T-202 C-07) — Runs table `whitespace-nowrap` + truncate inside a scroll shell (by design)
- **Existence verdict:** EXISTS ✓ (by design — no defect; W0-INV-01 §F concurred)
- **Evidence:** [VERIFIED views/RunsDashboard.jsx:74] wrapper `overflow-x-auto runs-table-wrap`; [VERIFIED styles.css:185] `.runs-table-wrap table { min-width: 34rem }`; [VERIFIED RunsDashboard.jsx:102] model cell `whitespace-nowrap`, [VERIFIED L112] dataset `truncate max-w-[14rem]`, [VERIFIED L127] started `whitespace-nowrap`. The nowrap cells live *inside* the scroll region, not the page. [VERIFIED tests/runs.test.jsx:416-420] documents "jsdom cannot measure it" and pins the wrapper class only.
- **Root cause chain:** n/a — intentional R5 scroll-shell pattern.
- **Blast radius:** none (verified pattern).
- **Fix options:** None. **Recommended:** document-only; keep.
- **Long-run test:** n/a (code-verified; Playwright confirms page-level scroll absence).
- **Classification:** SURFACE (informational).
- **WRITE-SET (proposed):** none.
- **Acceptance:** Playwright 390: page has no horizontal scrollbar; table scrolls internally.

### P-08 (T-202 C-08) — Admin invite-code row has no `flex-wrap`
- **Existence verdict:** EXISTS (risk, code-only)
- **Evidence:** [VERIFIED styles.css:310] `.admin-invite-code { display: flex; align-items: center; justify-content: space-between; gap: 1rem }` — no `flex-wrap`. Code text is `text-sm tabular-nums text-accent` ([VERIFIED AdminScreen.jsx:556]); copy button is `.admin-icon-btn` ([VERIFIED L561]). At 390 a long code squeezes the copy button ([INFERENCE] — code length unknown, backend-rendered).
- **Root cause chain:** invite tab written pre-390 pass; row never got the wrap treatment other admin rows have (`.admin-tabs` wraps at [VERIFIED styles.css:296], `.admin-invite-code` does not).
- **Blast radius:** Admin → Invites, only immediately after creating an invite (single row).
- **Fix options:** A) add `flex-wrap: wrap` to `.admin-invite-code`. **Recommended:** A (one declaration; safe when short — wrap only engages when needed).
- **Long-run test:** Source: CSS. Load/Hostile: a long hostile code string is the trigger — test with a synthetic 32+ char code. Operability: one-line CSS. Reversal: none pinned; screenshot is the tripwire.
- **Classification:** SURFACE.
- **WRITE-SET (proposed):** `frontend/styles.css`.
- **Acceptance:** Playwright 390 with a long fake invite code: no overlap, no page scroll; short codes render identically to today.

### P-09 (T-202 C-09) — Admin UsageBar pair inside the scroll table (by design)
- **Existence verdict:** EXISTS ✓ (by design — no defect)
- **Evidence:** [VERIFIED AdminScreen.jsx:166-168] two `<UsageBar>` in `flex gap-4`; [VERIFIED styles.css:311] `.admin-usage { min-width: 8.75rem }` → pair ≈ 280px + 16px gap; [VERIFIED styles.css:305-307] `.admin-table-wrap` owns the scroll with `table { min-width: 34rem }`.
- **Root cause chain:** n/a.
- **Blast radius:** none.
- **Fix options:** None. **Recommended:** document-only.
- **Long-run test:** n/a.
- **Classification:** SURFACE (informational).
- **WRITE-SET (proposed):** none.
- **Acceptance:** Playwright 390: usage bars scroll inside the table; page not overflowing.

### P-10 (T-202 C-10) — eval-scores 2-col + metrics-grid 1-col at 390 (by design)
- **Existence verdict:** EXISTS ✓ (verified pattern — no defect)
- **Evidence:** [VERIFIED styles.css:210-212] `.eval-scores` `repeat(2, 1fr)` base → 3 @640 → 4 @768; [VERIFIED styles.css:222-224] `.metrics-grid` 1-col base → 2 → 3. At 390 each eval tile is ~165px wide (342px content − 32px column gap); tile values are `text-lg tabular-nums` ([VERIFIED metrics.jsx:221]) — fits. Model catalog `model-name flex:0 1 14rem` + `model-desc flex:1 1 12rem` ([VERIFIED styles.css:167-168]) stack name to 100% below 640 ([VERIFIED styles.css:189]).
- **Root cause chain:** n/a.
- **Blast radius:** none.
- **Fix options:** None. **Recommended:** keep; Playwright screenshot confirms visual rhythm.
- **Long-run test:** n/a.
- **Classification:** SURFACE (informational).
- **WRITE-SET (proposed):** none.
- **Acceptance:** Playwright 390: no crushed tiles/metrics.

### P-11 (T-202 C-11) — Quota/admin `grid-cols-2` at 390 (by design, densest remaining surface)
- **Existence verdict:** EXISTS ✓ (verified pattern — no defect; noted as densest surface)
- **Evidence:** [VERIFIED AdminScreen.jsx:290] quota editor `grid grid-cols-2 md:grid-cols-3`, [VERIFIED L466] profiles `grid-cols-2 md:grid-cols-4`, [VERIFIED L681,688] summary `grid-cols-2 md:grid-cols-4`. [VERIFIED styles.css:98] `.field { width: 100% }` so inputs fill their ~165px columns. These are the *only* 2-col-base grids left in shipped JSX ([RAN grep `grid-cols-2`] → 4 hits, all AdminScreen) — every other view's grids degrade to 1-col base.
- **Root cause chain:** n/a.
- **Blast radius:** none.
- **Fix options:** None. **Recommended:** keep; Playwright density check on the quota editor labels at 390 [INFERENCE width, not measured].
- **Long-run test:** n/a.
- **Classification:** SURFACE (informational).
- **WRITE-SET (proposed):** none.
- **Acceptance:** Playwright 390: quota inputs fully visible, labels not cramped.

### P-12 (T-202 C-12) — No `aria-invalid` / `aria-describedby` / `aria-errormessage` anywhere
- **Existence verdict:** EXISTS (a11y gap, code-verified)
- **Evidence:** [RAN grep `aria-invalid|aria-errormessage|aria-describedby`] → 0 hits across `{App,AdminScreen}.jsx`, `views/**`, `components/**`. Errors render as adjacent `role="alert"`/plain notices: [VERIFIED views/AuthView.jsx:59] `<p role="alert" className="notice notice-bad mb-5">` (form-level, above the form — no per-field association at all); [VERIFIED views/NewJob.jsx:349-352] same pattern; [VERIFIED views/PredictPanel.jsx:241] same. Fields carry only `required` ([VERIFIED NewJob.jsx:389,454,469,498,509,535,554,647]) + `autoComplete` on Auth ([VERIFIED AuthView.jsx:64,73]). jsdom tests bypass native validation via `fireEvent` ([VERIFIED tests/newjob.test.jsx:161-163] "Submit through the form directly: the dataset <select required> would…"), so the missing association is invisible in the suite. Note: `static.test.js` pins label `htmlFor`/`id` linkage ([VERIFIED L232-238]) but not error association.
- **Root cause chain:** form-error association never implemented; the pattern is native `required` + server round-trip + form-level alert.
- **Blast radius:** every form (Auth, NewJob, Predict, Admin quota) — a11y gap, not a visual defect. Submit-time validation messages are announced via `role="alert"` (verified pattern), just not associated with the offending field.
- **Fix options:** A) add `aria-invalid` + `aria-describedby` on Auth fields first (highest-value: sign-in failure), then NewJob/Predict (needs deciding how to map field → its candidate error). B) document as accepted (alert is adjacent to the form). **Recommended:** A for Auth; rest deferred to a11y sweep.
- **Long-run test:** Source: grep + axe/Playwright. Load/Hostile: oversized/invalid input still surfaces the alert (behavior unchanged). Operability: attrs only, no logic change. Reversal: new assertion (aria-invalid present on failed field) fails if attrs removed.
- **Classification:** DEEP (a11y semantics + test contract; cross-cutting).
- **WRITE-SET (proposed):** `frontend/views/AuthView.jsx` (+ `frontend/tests/auth.test.jsx`).
- **Acceptance:** failed Auth submission exposes `aria-invalid="true"` + `aria-describedby` on the invalid field in the DOM; existing auth tests green.

### P-13 (T-202 C-13) — Divergent file-input button treatments
- **Existence verdict:** EXISTS
- **Evidence:** [VERIFIED views/NewJob.jsx:431] file input classes `file:mr-3 file:rounded-md file:border-0 file:bg-raised file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-ink hover:file:bg-rule` — bespoke token utilities; vs [VERIFIED views/PredictPanel.jsx:232] `file:mr-4 file:btn file:btn-quiet file:cursor-pointer` — design-system classes. Two file buttons, two designs. Neither carries `.field`. Focus appearance of the pseudo-button relies on the global `:focus-visible` rule ([VERIFIED styles.css:75] `input, select, textarea, button { font: inherit }` at L76 + `:focus-visible` at L75) — rendered focus on the pseudo-element is unverified ([INFERENCE] needs Playwright).
- **Root cause chain:** views authored independently; `::file-selector-button` styling never unified.
- **Blast radius:** NewJob CSV upload + Predict image input.
- **Fix options:** A) standardise on Predict's `file:btn file:btn-quiet` (reuse the system, one class swap in NewJob). **Recommended:** A.
- **Long-run test:** Source: grep. Load/Hostile n/a. Operability: class swap only. Reversal: none pinned; screenshot match is the evidence.
- **Classification:** SURFACE.
- **WRITE-SET (proposed):** `frontend/views/NewJob.jsx`.
- **Acceptance:** Playwright screenshots show both file buttons matching (size/style); focus ring visible on both at 390.

### P-14 (T-202 C-14) — Sign-out button outside the design system (part of the P-01 floor family)
- **Existence verdict:** EXISTS ✓ (absorbed into P-01; listed separately for the fix map)
- **Evidence:** [VERIFIED App.jsx:160] `<button ... className="min-h-6 inline-flex items-center hover:text-strong underline-offset-4 hover:underline">Sign out</button>` — no `.btn` class; pinned at [VERIFIED tests/static.test.js:222] `toContain('min-h-6')`. It is the only header control not using `.btn` (ThemeToggle uses `btn btn-quiet`, [VERIFIED components/theme.jsx:72]).
- **Root cause chain:** same R5 24px-floor decision as P-01; the button was deliberately kept "quiet" (text-like) rather than a bordered `.btn-quiet`.
- **Blast radius:** header cluster.
- **Fix options:** Folds into P-01 decision (A/B). Under B: `min-h-6` → `min-h-10` + paired static-test update. **Recommended:** resolve with P-01; do not split.
- **Long-run test:** Shared with P-01.
- **Classification:** SURFACE.
- **WRITE-SET (proposed):** `frontend/App.jsx` (+ `frontend/tests/static.test.js`, only under P-01/B).
- **Acceptance:** shared with P-01.

### P-15 (T-202 C-15) — Header 390 wrap cluster (`gap-x-8`)
- **Existence verdict:** EXISTS ✓ (pattern verified — rendered verdict pending, per W0-INV-01 §F)
- **Evidence:** [VERIFIED App.jsx:135] header inner `flex flex-wrap items-center gap-x-8 gap-y-2 py-3` (128px gap-x is wide for wrapped rows); [VERIFIED App.jsx:137] nav `flex flex-wrap gap-1`; [VERIFIED App.jsx:149] right cluster `ml-auto flex items-center gap-4`; [VERIFIED App.jsx:151] usage chip `hidden sm:inline` (storage chip disappears below 640 — by design). `main` padding `px-5 md:px-8 py-8 md:py-10` ([VERIFIED App.jsx:164]) vs Auth page `px-6 py-12` ([VERIFIED AuthView.jsx:50]) — two shell paddings (20px vs 24px gutters at 390; W0-INV-01 measured 24px on Auth, consistent with `px-6`).
- **Root cause chain:** n/a — wrap + hide-usage is the designed 390 behavior; the Auth shell is a separate `<main>` outside MainApp ([VERIFIED App.jsx:201-208], light spec §1 last bullet) so the two shells' padding is authored independently.
- **Blast radius:** header at 390 (logo/nav wrap to a second row).
- **Fix options:** None pre-render. **Recommended:** Playwright screenshot verdict; reduce `gap-x-8` only if the shot shows crowding ([INFERENCE] gap-x-8 reads wide on wrapped rows).
- **Long-run test:** n/a until measured.
- **Classification:** SURFACE (informational).
- **WRITE-SET (proposed):** none pending Playwright.
- **Acceptance:** Playwright 390 header shot (both themes): no overlap; Sign out + theme toggle reachable within the first two rows.

### P-16 (T-202 C-16/C-17) — Detail/metric/confusion wrapping guards verified in place
- **Existence verdict:** EXISTS ✓ (guards in place — no defect)
- **Evidence:** [VERIFIED styles.css:213] `.confusion-wrap { overflow-x: auto }`; [VERIFIED views/RunDetails.jsx:319] + [VERIFIED views/RunDetails.jsx:323] JSON `<pre class="field font-mono text-sm overflow-x-auto">`; [VERIFIED views/RunDetails.jsx:297] metric rows `flex justify-between gap-4`; [VERIFIED styles.css:216] `dd { overflow-wrap: anywhere }`; [VERIFIED styles.css:187-188] mobile `model-detail-grid` collapses to 1fr; [VERIFIED styles.css:186-195] runs-table cell tightening below sm. `pre`/truncate discipline is uniform.
- **Root cause chain:** n/a.
- **Blast radius:** none.
- **Fix options:** None. **Recommended:** keep; Playwright confirms.
- **Long-run test:** n/a.
- **Classification:** SURFACE (informational).
- **WRITE-SET (proposed):** none.
- **Acceptance:** Playwright 390: metric rows + confusion cells + JSON blocks don't push page width.

### P-17 (T-202 C-18) — Audit detail `truncate` without tooltip
- **Existence verdict:** EXISTS
- **Evidence:** [VERIFIED AdminScreen.jsx:628-630] `{event.detail && ... <div className="text-xs text-faint truncate">{JSON.stringify(event.detail)}</div>}` — no `title=` attribute. (Contrast: `RunsDashboard.jsx:127` date cell carries `title={formatWhen(...)}` — same repo, tooltip provided there.)
- **Root cause chain:** truncation added for layout without an exposure fallback.
- **Blast radius:** Admin audit rows only.
- **Fix options:** A) add `title={JSON.stringify(event.detail)}` (native tooltip, zero layout change). **Recommended:** A.
- **Long-run test:** Source: grep. Load/Hostile: a long hostile `detail` is exactly where truncation loses data — title preserves it. Operability: one-line JSX. Reversal: none pinned.
- **Classification:** SURFACE.
- **WRITE-SET (proposed):** `frontend/AdminScreen.jsx`.
- **Acceptance:** Playwright 390: hovering/focusing a long audit row shows the full JSON via title.

### P-18 (T-202 C-19) — NewJob `max-w-6xl` vs shell `max-w-page`
- **Existence verdict:** EXISTS ✓ (no overflow; outer cap wins)
- **Evidence:** [VERIFIED views/NewJob.jsx:341] `newjob-page max-w-6xl` (1152px) inside [VERIFIED App.jsx:164] `main max-w-page` where [VERIFIED tailwind.config.js:29] `maxWidth.page = 68rem` (1088px). Inner cap is wider than outer → outer wins; no overflow. Two container names for the same shell width.
- **Root cause chain:** NewJob authored with its own container name.
- **Blast radius:** NewJob content width only (desktop); naming inconsistency, not a visual defect.
- **Fix options:** A) document (no-op). B) change to `max-w-page` for naming consistency (visual no-op). **Recommended:** A (zero-risk; B only if the fine-tune wave touches the line anyway).
- **Long-run test:** n/a.
- **Classification:** SURFACE (informational).
- **WRITE-SET (proposed):** none.
- **Acceptance:** Playwright desktop shot confirms NewJob ≈ Runs width (both capped by `max-w-page`).

### P-19 (T-202 C-20) — Hover-only / touch-unavailable affordances (Compare hint, file-button hover)
- **Existence verdict:** EXISTS (risk, code-only; deferred to rendered audit)
- **Evidence:** [VERIFIED views/RunsDashboard.jsx:53-54] Compare `disabled={selected.length < 2}` with the *only* explanation in `title="Tick two to four completed runs"` — `title` is unavailable to touch users and unreliable for keyboard/AT. File-button hover `hover:file:bg-rule` ([VERIFIED NewJob.jsx:431]) is desktop-only feedback (the static affordance exists, so this is milder). [INFERENCE: disabled-Compare discoverability without hover is the sharper risk, on Runs — the most-visited surface.]
- **Root cause chain:** desktop-first affordances; no visible equivalent for the Compare constraint.
- **Blast radius:** Runs header (Compare) + NewJob upload at 390 touch.
- **Fix options:** A) visible hint under the header actions ("Tick 2–4 completed runs") + keep title. B) document as accepted. **Recommended:** defer verdict to T-202's sibling Playwright pass (W0-INV-01 follow-up with backend up); do not add code on hypothesis alone.
- **Long-run test:** n/a until measured.
- **Classification:** SURFACE.
- **WRITE-SET (proposed):** `frontend/views/RunsDashboard.jsx` (deferred).
- **Acceptance:** deferred to Playwright finding on touch discoverability.

### P-20 (T-202 C-21) — Focus visibility beyond Auth unverified (data views)
- **Existence verdict:** PARTIAL (Auth verified rendered; data views unverified — MISCLASSIFIED if treated as settled)
- **Evidence:** [VERIFIED styles.css:75] global `:focus-visible { outline: 2px solid rgb(var(--accent)); outline-offset: 2px; border-radius: 3px }`; [VERIFIED styles.css:107] `.field:focus { outline: none; box-shadow: 0 0 0 3px rgb(var(--accent) / 0.2) }` replaces the outline for fields. Static guard pins only declarations ([VERIFIED tests/static.test.js:225-229]). W0-INV-01 §P-05 rendered-verified the ring on Auth (inputs: shadow ring; buttons: `outline: solid 2px`). All other controls — `.btn-quiet`/`.btn-danger` (e.g. `RunsDashboard.jsx:55`, `RunDetails.jsx:244,249`), `.nav-link` (`App.jsx:143`), `.link`, `.admin-icon-btn`, file inputs (`NewJob.jsx:431`, `PredictPanel.jsx:232`), compare checkbox (`RunsDashboard.jsx:98`) — rely on the same global rule but are **unmeasured rendered**. jsdom `focus()` only asserts `document.activeElement` ([VERIFIED tests/runs.test.jsx:438-441]) — it cannot assert ring visibility.
- **Root cause chain:** R5 static guard pins rule presence (`:focus-visible` + `.field:focus` box-shadow), not rendered visibility per control.
- **Blast radius:** every interactive control on data views (Runs, RunDetails, NewJob, Predict, Models, Admin).
- **Fix options:** None pre-render. **Recommended:** Playwright Tab-walk every surface at 390 + 1280, both themes; fix only what the walk shows. Note the known exception: light theme `--raised` on `--canvas` is 1.18:1 by design (spec §4.9, fill-not-boundary) — the focus *outline* token (`accent` on canvas) is separately pinned ≥3:1 ([VERIFIED tests/static.test.js:449-454] `rule/canvas`, `accent/raised fill` ratio guards), so the focus ring itself is contrast-covered by math; only its rendered presence per control is unproven.
- **Long-run test:** Source: Tab-walk protocol. Load/Hostile/Operability n/a. Reversal: n/a until measured. (Also note `ring-canvas` on the ResultLine dot, [VERIFIED metrics.jsx:177] — reads as an invisible white gap in light; spec §4.9 records this as cosmetic/accepted, "record it, don't fix it with a token change" — [VERIFIED docs/plans/2026-11-08-light-mode.md:118-121].)
- **Classification:** DEEP (requires rendered measurement; cannot be settled from source).
- **WRITE-SET (proposed):** TBD from Playwright findings.
- **Acceptance:** Playwright Tab-walk protocol recorded per surface; every focused control shows ≥2px outline or 3px shadow ring in both themes at 390 + 1280.

### P-21 (T-202 C-22) — Light-mode non-text exceptions already pinned (raised/canvas, ring-canvas, accent-ink)
- **Existence verdict:** EXISTS ✓ (design-recorded exceptions — no fix)
- **Evidence:** `--raised` on `--canvas` 1.18:1 is an accepted fill exception (spec §4.9, [VERIFIED docs/plans/2026-11-08-light-mode.md:101-104]; guard comment [VERIFIED tests/static.test.js:416] "raised/canvas is excluded by design D2 §2.4a"). `--accent-ink` is white (255 255 255) in the light block ([VERIFIED styles.css:48]) vs dark ink `10 18 32` ([VERIFIED styles.css:26]) — the only compliant value ([VERIFIED light-mode.md:94-98]). `ring-canvas` cosmetic gap — see P-20. Static ratio guards cover the full P-04/P-05 inventory ([VERIFIED tests/static.test.js:417-507]: body tokens × canvas/surface/raised, accent/ink dual, ok/warn/bad, badges, confusion composites, tags/selection).
- **Root cause chain:** by design (dark-on-accent vs accent-on-white are mutually exclusive constraints — light-mode.md:95-98).
- **Blast radius:** none.
- **Fix options:** None. **Recommended:** keep; Playwright light screenshots ratify.
- **Long-run test:** Static ratio guards are the reversal tripwire (they fail if any light triple is edited blindly).
- **Classification:** SURFACE (informational).
- **WRITE-SET (proposed):** none.
- **Acceptance:** Playwright light shots match the token math; no new exception introduced by the fine-tune wave.

## 2. Duplicates / shared root causes across items
- P-01 + P-14 share the R5 24px-floor root cause — one decision settles both; do not split the fix or the test update.
- P-07/P-09/P-16/P-18 share the "scroll shell / shell container owns overflow" idiom — zero fixes; they are why Playwright must check *page-level* scroll, not component-level, at 390.
- P-04/P-13 share "pre-R3 views never collapsed to the shared pattern" (Admin h1 + file buttons).
- P-09/P-16/P-18/P-21 are verified-keep items: ship them as close-out documentation, not code.

## 3. Out-of-plan discoveries
1. Auth shell and app shell use different paddings: `px-6 py-12` ([VERIFIED AuthView.jsx:50]) vs `px-5 md:px-8 py-8 md:py-10` ([VERIFIED App.jsx:164]) — 24px vs 20px gutters at 390. W0-INV-01 measured 24px on Auth (consistent). Product may want one shell rhythm; flagging as polish, not defect.
2. `static.test.js` floor pins are string scans, not measurements — the suite would pass with a floor that never renders (e.g. `display:none` on the control). jsdom cannot close this; Playwright measurement is the only real floor test. (This is the "jsdom misses" test gap, §8 below.)
3. `accent-[rgb(var(--accent))]` ([VERIFIED RunsDashboard.jsx:98]) is the sole arbitrary-value color utility — token-indirected and compliant, but a naive future arbitrary-value grep would flag it. Worth an allowlist comment for grep hygiene (mine: no change needed).
4. `vite.config.js` `test.css: false` ([VERIFIED docs/plans/2026-11-08-light-mode.md:20] + `tests/static.test.js` ratio math) means jsdom never loads `styles.css` — no test asserts a computed color; contrast is pinned by *arithmetic on triples*, not by rendered pixels. Alpha compositing over real content (badges over tables, confusion cells over rows) is therefore verified by math, not by pixels.

## 4. Assumptions and unknowns
1. [ASSUMED] NewJob 390 layout is as the CSS implies (intelligence grid 1-col base [VERIFIED styles.css:277], preset grid 1-col [VERIFIED L265], pairs stack [VERIFIED L252]) — unverified rendered; Playwright must confirm Sections C/D don't push page width.
2. [UNKNOWN] Whether any data view has real rendered defects at 390 (overflow/tap/contrast/focus) — cannot be determined from source; W0-INV-01's backend-up follow-up matrix (7 surfaces × 2 widths × 2 themes) is the only evidence. This report deliberately claims none.
3. [ASSUMED] `📊` renders on all target fonts (emoji font present) — if a font lacks it, a tofu box appears in the NewJob heading. Playwright screenshot settles it; P-03 removes the question entirely.
4. [UNKNOWN] Rendered contrast of hover-only states (`hover:bg-surface/60` at [VERIFIED styles.css:119], `hover:bg-surface/60` at [VERIFIED ModelsCatalog.jsx:93]) — static guards cover washes, not hover composites over arbitrary content.
5. [ASSUMED] P-06's ~18px overhang math (label ≈90px) — depends on the rendered baseline digit count; Playwright with a real run settles it.

## 5. Recommended task breakdown and ordering
1. **W1-T1 (backlog audit, first):** backend-up Playwright pass per W0-INV-01 §5 — probe set identical to its §0 matrix, all 7 surfaces × {390,1280} × {dark,light}. WRITE-SET: audit report + screenshots. Settles P-05/P-06/P-15/P-19/P-20 hypotheses.
2. **W1-T2 (decision):** P-01/P-14 24px vs 40px. Do not let an agent change the floor without the paired `static.test.js`/`smoke.test.jsx` update and ORCH sign-off.
3. **W1-T3 (surface batch, no decision needed):** P-02 (favicon) + P-03 (emoji/h3) + P-04 (Admin h1) + P-08 (flex-wrap) + P-13 (file buttons) + P-17 (audit title). Each 1–2 lines, independent, low-risk; can land as one commit series. SURFACE, mostly NIT.
4. **W1-T4 (deep, optional):** P-12 Auth `aria-invalid`/`aria-describedby` — needs test additions; schedule after T1 confirms nothing higher-priority surfaced. DEEP.
5. **Close-out (document-only):** P-05/P-07/P-09/P-10/P-11/P-16/P-18/P-21 verified-keep; Playwright screenshots ratify them.

## Method note / scratch files
- Per-view token/class inventory (from reads this session):
  - **App shell** (`App.jsx`, `shared.jsx`, `theme.jsx`): `page-header` + `nav-link` + `breadcrumb` + `btn/btn-quiet`; tokens `canvas/surface/raised/rule/strong/ink/muted/faint/accent`; `aria-current` on nav ([VERIFIED App.jsx:142]), `aria-label="Main"` ([VERIFIED L137]), Breadcrumb `aria-label="Breadcrumb"` + `aria-current="page"` ([VERIFIED shared.jsx:91,99]); `role="alert"` ErrorBoundary ([VERIFIED App.jsx:45]).
  - **AuthView**: `auth-card/auth-brand/auth-form/field/btn/btn-primary/link/notice`; `role="status"` session notice + `role="alert"` error ([VERIFIED L58-59]); `htmlFor` labels ([VERIFIED L62,70]); autocomplete hints.
  - **RunsDashboard**: `runs-page/page-header/btn/btn-primary/btn-quiet/runs-empty/runs-table-wrap/th/td/compare-check/link`; `scope="col"` ×6 ([VERIFIED L78-83]); `aria-label` on checkboxes ([VERIFIED L94]); `role="alert"` error ([VERIFIED L64]).
  - **RunDetails**: `run-details-page/Breadcrumb/panel/result-panel/eval-panel/confusion-panel/prep-panel/metrics-panel/training-panel/disclosure-summary/disclosure-marker/btn-danger/btn-quiet/link`; `role="status"` sr-only announcements ([VERIFIED L87] phase, [VERIFIED L256] cancel note); `aria-label="Progress"` ([VERIFIED L84]); `role="img"` ResultLine scale ([VERIFIED metrics.jsx:160]).
  - **NewJob**: `newjob-page/newjob-form/panel/newjob-field-label/newjob-mode-btn[aria-pressed]/newjob-preset-card[aria-pressed]/newjob-intelligence/newjob-tag/newjob-submit-row/field`; `role="group"` + `aria-label` ([VERIFIED L361]), `aria-labelledby` preset group ([VERIFIED L618]); `htmlFor` on all single controls ([VERIFIED L338-339] invariant comment + newjob.test.jsx:70-99 label suite).
  - **PredictPanel**: `panel/predict-panel/predict-segmented[role=group]/predict-segmented-btn[aria-pressed]/predict-form-grid/predict-actions/predict-result`; arrow-key segmented behavior ([VERIFIED L26-46]); single `role="status"` sr-only summary ([VERIFIED L266]); `aria-label="Rows as JSON"` ([VERIFIED L206]).
  - **ModelsCatalog**: `catalog-page/catalog-search[field]/catalog-list/model-row/disclosure-summary/model-summary/model-name/model-desc/model-detail-grid`; search `aria-label` ([VERIFIED L70]); `role="alert"` error ([VERIFIED L75]); worktree `group-open:line-clamp-none` on descriptions ([VERIFIED L96]).
  - **AdminScreen**: `admin-page/admin-tabs/admin-tab[aria-current]/admin-table-wrap/admin-card/admin-summary/admin-usage/admin-badge/admin-icon-btn/admin-form-label/notice/btn*;` icon buttons carry `title` + `aria-label` ([VERIFIED AdminScreen.jsx:180,191,202,223,563]); `aria-current="page"` tabs ([VERIFIED L49]); `scope="col"` 16 across tables ([VERIFIED L101-106,365-370,575-578] + static count test).
- Test-gap summary (jsdom misses vs Playwright): jsdom (`test.css:false`) never loads `styles.css` → no computed colors, no layout (`scrollWidth`/`clientWidth`), no rendered overflow/wrap/truncate, no ring visibility, no 390/1280 viewports, no hover/disabled rendering, no `prefers-reduced-motion`, no pre-paint init timing. `static.test.js` pins *declarations and arithmetic* (ratios, floors-as-strings, class presence); `*.test.jsx` pin DOM structure, roles, order, and `activeElement` — never pixels. Playwright uniquely covers: rendered contrast, page-level overflow, tap-target measurement, Tab-walk focus visibility, hover/composite states, console errors, theme pre-paint.
- Scratch files created: none. No tests or build run (per brief: scoped greps/reads only). One read-only shell command run: `git branch --show-current; git log --oneline -5` → `frontend-ui-round2` / `7ce8bed`.
