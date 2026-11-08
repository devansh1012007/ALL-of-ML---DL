# Light mode spec — frontend theme (2026-11-08)

**Status:** draft (planner review pending). **Owner:** wave run `20261108-light-negative` (T-101).
**Why this spec exists:** tech-debt deferred light mode as "separate spec; do not invert ad-hoc".
This document is that spec. It pins the design BEFORE code. The implementation agent proposes
the exact palette values (with computed contrast) in a design record; the reviewer verifies the
math before anyone merges.

## 1. Facts (verified by W0-INV-01 — see report)

- 14 RGB tokens in `frontend/styles.css:15-31` (`:root`), `color-scheme: dark` at `:30`.
  `frontend/tailwind.config.js:3-24` maps every token into Tailwind (`token(name)`), so all
  utilities (`bg-accent/15`, `text-muted`, `border-rule/60`…) resolve through the vars.
- Token census: 93 `var(--)` and 94 `rgb(...)` hits — ALL token-indirected. Zero hardcoded hex
  in shipped CSS/JSX, zero `dark:` variants, zero gradients, zero `bg-white`/`text-black`.
- Sole outlier: `frontend/views/NewJob.jsx:678` uses `text-orange-400` (Tailwind default #fb923c).
- Two `color-scheme: dark` pins: `styles.css:30` and `frontend/index.html:6` meta.
- NO theme state today: no `data-theme`, no `prefers-color-scheme` query, no `prime_theme` key.
  `App.jsx` state is `{currentView, activeParams, me}` only; `shared.jsx` owns `prime_token` only.
- `vite.config.js` sets `test.css: false` — jsdom never loads styles.css, so no existing test
  asserts a computed color. Static guards pin class *names*, not values.
- Test hygiene trap: per-file `window.localStorage.clear()` resets between tests, and
  `teardownApp` removes only `prime_token` — a `prime_theme` key set by a theme test could leak
  into later tests in the same file if tests don't clean up.
- AuthView renders its own `<main>` outside MainApp (`App.jsx:175-187`): theme state in MainApp
  alone leaves the sign-in screen dark-only.

## 2. Goals / non-goals

Goals: one-click light/dark toggle visible on every surface (incl. sign-in); persisted per
browser; first paint already in the chosen theme (no dark flash); system preference as default;
visual parity of layout across themes; contrast-valid palette (not a mechanical invert).
Non-goals: per-view themes; animated transitions (theme flip is instant); SSR/pre-render; any
backend/API change. No component redesign — tokens only, plus the one NewJob outlier.

## 3. Approach (approved shape — details in §4)

CSS-variable inversion via `[data-theme="light"]` on `<html>`. `:root` keeps today's dark
palette (default/no-JS/at-rest = dark = current behavior). The light block overrides the SAME
14 token names + `color-scheme: light`. `tailwind.config.js` is NOT touched (token names are
the contract; values live in CSS).

## 4. Design decisions pinned here

1. **Canonical attribute:** `document.documentElement.dataset.theme`. Only two legal values:
   `"light"` (explicit light) and absent/`"dark"` (both render today's dark palette — spec pins
   the implementation to write `"dark"` explicitly on toggle-to-dark so devtools state is
   unambiguous; absence = system-was-dark initial).
2. **Preference resolution (priority order):**
   `localStorage[prime_theme]` ∈ {"light","dark"} → if absent, `matchMedia("(prefers-color-scheme: light)")`
   → else dark. Any other stored value (garbage/XSS payload) is IGNORED → falls through to
   system. The stored value is only ever assigned to `dataset.theme` (an allow-listed property),
   never to `innerHTML` — no injection vector.
3. **Storage key:** `prime_theme`. Values `"light"`/`"dark"`. **Sign-out must NOT clear it**
   (per-browser preference, unlike `prime_token`).
4. **Pre-paint init:** an inline script in `index.html` (before first paint) reads the resolved
   preference and sets `data-theme` + updates the meta color-scheme. React then treats
   `documentElement.dataset.theme` as the source of truth on mount (no double-apply, idempotent,
   StrictMode-safe).
5. **Meta color-scheme:** `index.html` meta starts at the resolved theme (`light`/`dark`) via
   the same init script; the toggle updates it on flip so scrollbars/native controls follow.
6. **Toggle placement:** a single header button in `App.jsx` (right-side cluster next to
   "Sign out", OUTSIDE the `<nav>` element — smoke tests query nav by role/name) + the SAME
   toggle rendered on the AuthView sign-in card (theme must be reachable pre-login). One
   component (`components/theme.jsx` — new file; tailwind `content` globs already cover
   `components/**`, no config change) exports: `resolveTheme()`, `applyTheme()`,
   `toggleTheme()`, and a `ThemeToggle` button.
7. **Toggle semantics:** plain `<button aria-pressed>`; accessible label pinned by the design
   record (e.g. "Switch to light mode" when dark, "Switch to dark mode" when light) — the label
   must describe the ACTION, not the current state. Keyboard-focusable; focus indicator visible
   in both themes (≥3:1).
8. **NewJob outlier:** `NewJob.jsx:678` `text-orange-400` → a token (proposed: `text-warn`; if
   the palette needs it, a new `--warn-strong` token MAY be added — only then does
   `tailwind.config.js` need a one-line `token("warn-strong")` mapping, recorded as a contract
   change in the impl report).
9. **Light palette requirements (design record computes values):** every text/background pair
   ≥4.5:1 (body) / ≥3:1 (large/headings, focus); `--accent-ink` on `--accent` ≥4.5:1 in BOTH
   themes (expect it stays dark-on-blue); `--warn`/`--bad`/`--ok` on `--canvas` ≥4.5:1 in light
   (warn needs darkening — #E4B95F on white is ~1.9:1 today); alpha washes (e.g. `bg-accent/15`)
   must be evaluated composited over light canvas, not on raw tokens. No mechanical 255−x invert.
10. **Test structure:** `frontend/tests/theme.test.jsx` (new) — one `describe` per concern:
    resolution order (stored/system/default), hostile stored values (XSS, 10KB, unicode),
    localStorage-throw fallback (theme flips in-memory, no crash), toggle side effects
    (attribute + meta + storage, sign-out does not clear), afterEach removes `prime_theme`.
    `frontend/tests/static.test.js` — ADDITIVE guards only: `[data-theme="light"]` block exists,
    all 14 token names defined in it, sets `color-scheme: light`. Guards pin structure, NOT
    exact RGB triples (those are pinned by the contrast computation in the design record).
11. **Probe checklist (manual Chromium, recorded in tech-debt — NOT claimable by jsdom):**
    all 7 views + Admin at 390px + desktop in both themes; keyboard focus visible; toggle
    persistence across reload; no dark flash for stored-light on throttled reload. Any
    component-level fix beyond token values (expected: none) requires a spec amendment.

## 5. Acceptance criteria (measurable)

1. Light theme renders every surface with identical layout (probe screenshots).
2. Palette contrast table in the design record meets §4.9 ratios — reviewer recomputes.
3. Toggle flips attribute + meta + storage in one interaction; persists across reload; first
   paint matches stored/system (no flash for stored-light).
4. Dark default at 85acdda is byte-identical (14 token values unchanged) when system is dark.
5. `npm test` (full) + `npm run build` green; shipped-file greps for hex/`dark:`/palette
   utilities show zero hits outside comments/tests.
6. Hostile-value + localStorage-throw tests pass.
7. Probe outcome recorded in `docs/tech-debt.md` (add a light-mode entry; do not delete the
   historical deferral lines).

## 6. Alternatives considered and rejected

- **B: Tailwind `darkMode: 'class'` + `dark:` variants per component.** Rejected: ~119 text-* +
  ~17 bg/border sites across 8 files would churn without benefit and contradicts the token
  architecture (R4 guard bans bespoke bg strings). INV-01 §"Option B".
- **C: System-preference-only (`@media`).** Rejected as sole mechanism: no user control, tests
  can't assert deterministically. Retained only as the DEFAULT source (§4.2).
- **D: Static asset swap (light stylesheet).** Rejected: doubles the file, FOUC risk identical,
  no contract benefit over CSS variables.

## 7. Blast radius / rollback / risks

Write-set: `styles.css`, `index.html`, `App.jsx`, `AuthView.jsx`, new `components/theme.jsx`,
`views/NewJob.jsx:678`, `tests/theme.test.jsx`, `tests/static.test.js` (additive), plus
`docs/tech-debt.md` (probe record, W2 only) and this spec. NOT in write-set: `tailwind.config.js`
(unless §4.8's warn-strong is adopted), `RunDetails.jsx`, and all other views (token-only).
Rollback: revert the light block + toggle + init script = today's dark behavior identical.
Top risks: (1) light palette fails contrast without probe evidence — mitigated by computed
table + probe; (2) FOUC if init is React-only — mitigated by §4.4 inline script; (3) theme
state leaks across jsdom tests — mitigated by afterEach cleanup + teardown parity.
