# Playwright fine-tune plan (2026-11-09)

**Status:** draft (planner review pending). **Owner:** run `20261109-playwright-design` (T-203).
**Why:** user asked to use Playwright MCP to improve/fine-tune the design. W0 proved auth is already clean rendered (contrast 6.7–16.3:1, zero overflow 1280/390, visible focus, `role=alert` error) — this plan fixes ONLY the concrete defects the audits found, no redesign.

## Facts (from W0 — verify, don't trust memory)
- Auth rendered: 7 screenshots, clean except favicon 404 (P-02, NIT) and 24px `.link` targets (P-01, test-pinned R5 floor, WCAG 2.2 2.5.8 AA exact).
- Code census clean: 0 hex in shipped JSX, 0 `dark:`, 0 palette utilities, token map = 14 names. No backend → Runs/RunDetails/NewJob/Predict/Models/Admin NOT-RENDERABLE (honest exclusion).
- Candidates (INV-code-design P-03..P-21): favicon, 📊 emoji+h3, Admin h1 32px/700 vs 24/600 standard, file-button divergence, audit truncate w/o title, invite flex-wrap, aria-invalid gap, ResultLine clamp, header gap-x-8, Compare title-only hint — plus 9 verified-keep items (no change).

## Approach comparison
- **A: Surface batch only (recommended).** Fix the 6 zero-decision 1–2-line defects (favicon, emoji, Admin h1, file buttons, audit title, invite wrap) + record the 24px decision as accepted (or raise to 40px only with paired test edits + ORCH/product sign-off). Data-view hypotheses (ResultLine clamp, header wrap, Compare hint, focus-walk) deferred until a backend-up pass is feasible (no `.venv`/`backend/.env` in this env; install is heavy and out of scope for a fine-tune).
- **B: Full audit first (backend install + 7-surface matrix).** Rejected for now: requires `scripts/install.sh` (uv + python 3.12 + torch-scale deps) and a seed/admin user; blast radius >> fine-tune value; W0 already banked auth evidence. Revisit only if user provides backend env.
- **C: 40px tap-target raise immediately.** Rejected as default: changes header/row/table heights and rewrites `static.test.js`/`smoke.test.jsx` pins — a product contract change needing sign-off, not a silent fine-tune.

## Decisions (planner-reviewed, user-confirmed 2026-11-09)
- **File-buttons: DROPPED from this wave (user choice, safest).** Planner B1 claimed `file:btn` dead (Tailwind v3 custom class + component layer) — build check (ORCH, 2026-11-09: `dist/assets/*.css` contains `.file\:btn::file-selector-button{...}`) proves it IS live, so B1 is overruled on mechanism. No copy either way this wave; Predict stays as-is, NewJob bespoke stays as-is. A future unification needs rendered focus proof at 390px.
- **Scope: Auth Playwright + static/jsdom acceptance only (user choice).** Data-view rendered parity (NewJob/Admin) deferred to a named backend-up follow-up (no `.venv`/`backend/.env`; install out of scope). Acceptance below is split by surface.
- **Auth aria-invalid: INCLUDED (user choice).** P-12 is code-certain (0 hits), Auth renderable now — DEEP fix in this wave with `auth.test.jsx` additions.
- **24px floors: ACCEPTED (user choice).** Height measured 24.0px = WCAG 2.2 SC 2.5.8 AA exact (`static.test.js:212-222` is the value pin; `smoke.test.jsx:220-223` is class-only + comment). `.link` width text-driven >24 (height measured; width [UNVERIFIED rendered width]). Zero-margin fragility noted; no code.

## Atomic phases
1. **T-301 favicon (SURFACE):** `index.html` inline data-URI SVG `<link rel="icon">` inserted after `<meta name="color-scheme">` (L5), before init `<script>` (L6) — do not move the init script. + static assertion (icon link present).
2. **T-302 type consistency (SURFACE):** `NewJob.jsx:660` drop 📊 + `text-lg`, keep `font-semibold text-strong mb-4` (inherit global h3 0.9375rem/600 — NOT `.newjob-section-title`); `AdminScreen.jsx:670` strip to bare `<h1>` (do NOT invent `mb-1`). Static pins: no 📊 in shipped JSX + NewJob h3 no `text-lg`; Admin h1 no `text-2xl`/`font-bold`.
3. **T-303 control consistency, REDUCED (SURFACE):** `AdminScreen.jsx:628-630` add `title={JSON.stringify(event.detail)}` (+ static pin: audit truncate carries `title=`); `styles.css:310` `.admin-invite-code` add `flex-wrap: wrap` (+ static pin). File-button pair DROPPED (see Decisions).
4. **T-304 Auth aria (DEEP):** `AuthView.jsx` add `aria-invalid` + `aria-describedby` on fields for failed submissions (Auth first only; NewJob/Predict deferred to a11y sweep) + `auth.test.jsx` additions (assertion fails if attrs removed). Playwright error-state already proven (W0 P-06).
5. **T-305 deferred (document-only):** ResultLine clamp / header gap-x-8 / Compare title-only hint / data-view focus-walk stay code-only hypotheses until backend-up pass (owner: future run with backend env). Verified-keep (8 items: P-05/P-07/P-09/P-10/P-11/P-16/P-18/P-21) closed as documentation.

## Acceptance (measurable, split by surface)
- **Auth (Playwright):** console clean (no favicon 404), error state shows `aria-invalid`/`aria-describedby` association, both themes still contrast-clean.
- **NewJob/Admin (static/jsdom, rendered parity deferred):** `npm test` full green (154 baseline) + `npm run build` green; greps: 0 emoji in shipped JSX, 0 palette utilities, icon link present; header/row heights unchanged (no floor/token edits); `newjob.test.jsx` + `admin.test.jsx` green.

## Blast radius / rollback
Write-set: `index.html`, `views/NewJob.jsx` (2 spots), `AdminScreen.jsx` (2 spots), `styles.css` (1 declaration), `tests/static.test.js` (+1–2 assertions). No `tailwind.config.js`, no `RunDetails`, no token changes. Revert = 4 small commits, each independently revertible.
