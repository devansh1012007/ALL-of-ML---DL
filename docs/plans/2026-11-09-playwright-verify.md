# Playwright verify + DO-LATER fixes (2026-11-09)

**Status:** draft (planner review pending). **Owner:** run `20261109-playwright-verify` (V-103/V-104).
**Goal:** (1) close the W1 rendered NOT-RUN with real Playwright evidence (V-101 DONE: Auth CLEAN, deferred NOT-RENDERABLE honest). (2) status-mapped Auth aria (R-W1-001). (3) invite overflow-wrap (R-W1-002). (4) honest closure on ResultLine/header/Compare hypotheses.

## Facts (W0 verified)
- **Rendered (V-101):** Auth CLEAN 1280/390 × dark/light — console 0 errors on load (favicon fixed), overflow 0, contrast ≥6.7, theme+focus clean; error state shows both-fields aria (V-103 input, not regression). 7 contact sheets in `screenshots/after/`. Deferred NOT-RENDERABLE: `#/runs` still renders AuthView behind `token ? <MainApp/> : <AuthView/>` (App.jsx:197-207); backend 8010 down. Side findings: `.result-headline-row` already flex-wraps (clamp hypothesis likely misclassified); `.compare-run-link` has NO `title=` (title-only hypothesis has no source basis).
- **Aria (V-102):** `err.status` available (shared.jsx:239) — no string parsing needed. Backend Auth vocabulary: register 400/403/409/429; login 400 (credentials, not 401). State shape: `error` + `errorStatus` (`null`=none, `undefined`=network, else status).
- **Wrap (V-102):** invite codes `secrets.token_urlsafe(12)` → 16 chars `[A-Za-z0-9_-]`; fit today, hostile 64+ overflows via flex min-content. Precedent: `overflow-wrap: anywhere` (2 sites), `min-width: 0`.

## Approaches
- **Aria A (revised whitelist):** `errorStatus` scalar + first-branch helper `ariaFor(status)`: `409→username-only`; `400→both`; else → describedby-only (covers 403/404/405/422/401/429/network/`>=500`). Minimal diff, no `shared.jsx`/backend change. vs B single-object state (churn), vs C message parsing (brittle, forbidden).
- **Wrap A (unchanged):** `.admin-invite-code-text{min-width:0;overflow-wrap:anywhere}` + `min-w-0` on wrapper (precedent-paired) vs B parent-only vs C `break-all` (rejected).
- **Deferred closures (unchanged):** ResultLine/header/Compare stay document-only (no backend, no evidence = no fix). Favicon `%20` closed (rendered proof: console clean).

## Resolved by planner + user (2026-11-09)
- **Whitelist rule (F-01, user-confirmed 403→describedby-only):** 409→username-only; 400→both; **everything else** (403, 404, 405, 422, 401, 429, network/`undefined`, ≥500) → describedby-only. Only 400 has affirmative invalid evidence.
- **Clear+gate (F-02):** `errorStatus` initial `null`; `handleSubmit` clears both; every attr `error && <branch> ? … : undefined` (never literal `false`); invariant test: every present `describedby` resolves to `#auth-error`.
- **409 via register (F-03):** discriminating test through register mode (`fail: {'/api/v1/register': {status:409}}`); `/token`-409 synthetic labelled defensive only.
- **V-104 closure (F-04):** coder attempts Playwright route-mock hostile (390, 64+256 chars); if NOT-RUN, closes as static-only + follow-up owner named.
- **Acceptance (F-05):** discriminating branches (409-neg, 429, network, 502/500) fail pre-fix; 400/401 guard-rails pass both ways. Edit `auth.test.jsx:201-232` in place, preserve :184-199 guard + :196-198 self-check.
- **401 defensive (F-06):** describedby-only bucket, labelled defensive (near-unreachable: AuthView mounts only without token).
- **`ariaFor` placement (F-08):** pure helper inside AuthView (test-through-DOM); attrs omitted (`undefined`) when N/A, never `"false"`.
- **400-conflation known (F-09):** register-400 covers short-password/reserved-name — both still overlabels subcases; accepted without string parsing.

## Phases
1. **V-103 (DEEP-test):** AuthView + auth.test — branches: 409 (username-only, password-negative), 429 (describedby-only), network (describedby-only, replaces old both-fields test), 400 (both, guard-rail), 401/502 defensive. Playwright spot-check: 429/network describedby-only.
2. **V-104 (SURFACE):** styles + AdminScreen classNames + static pin; Playwright hostile 390 if seedable, else static + short-code unchanged proof.

## Blast radius / rollback
V-103: AuthView+auth.test only; apiFetch contract consumed. V-104: styles+AdminScreen+static; no height change for short codes. Revert: per-file.

## Acceptance
- V-101: 7 after-screenshots + console 0 on load (done). V-103: scoped auth green; each branch fails pre-fix; Playwright describedby-only spot. V-104: static pin + 16-char heights unchanged.
