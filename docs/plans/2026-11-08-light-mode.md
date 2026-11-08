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
   `"light"` (explicit light) and `"dark"` (both render today's dark palette; the toggle writes
   `"dark"` explicitly so devtools state is unambiguous). Absence (initial page load before init
   runs, or storage denied) renders dark; absence means "no stored choice" — the system
   preference decides, not "system-was-dark".
2. **Preference resolution (priority order, one-shot at load):**
   `localStorage[prime_theme]` ∈ {"light","dark"} → if absent, `matchMedia("(prefers-color-scheme: light)")`
   → else dark. Any other stored value (garbage/XSS payload) is IGNORED → falls through to
   system. The stored value is only ever assigned to `dataset.theme` (an allow-listed property),
   never to `innerHTML` — no injection vector.
   - **Environment guards (P-02):** `resolveTheme()` checks `typeof window.matchMedia === 'function'`
     and wraps the `localStorage` READ in `try/catch` (access itself can throw in some contexts);
     any environment absence or throw falls through to dark — never a crash, never an uncaught
     exception out of a render path. `theme.test.jsx` stubs `matchMedia` per test (both light-
     and dark-preferring) because jsdom does not implement it.
   - **No live sync (P-09):** resolution happens once at load. No `matchMedia` listener
     (mid-session system switches are intentionally ignored) and no cross-tab `storage` listener
     (a second tab picks up the new value on its next reload; last-write-wins).
3. **Storage key:** `prime_theme`. Values `"light"`/`"dark"`. **Sign-out must NOT clear it**
   (per-browser preference, unlike `prime_token`).
4. **Pre-paint init (P-01):** an inline script in `index.html`, placed in the **`<head>` before
   the stylesheet/module entries**, fully `try/catch`-guarded (storage read, `matchMedia` call,
   meta update — silent fall-through to dark on any throw, never an uncaught error), that reads
   the resolved preference once and sets BOTH `documentElement.dataset.theme` and the meta
   color-scheme `content` from that single resolution. React then treats
   `documentElement.dataset.theme` as the source of truth on mount (no double-apply, idempotent,
   StrictMode/HMR-safe; the init runs once at load, so neither needs handling).
5. **Meta color-scheme:** the init script sets it from the resolved theme (`light`/`dark`);
   the toggle updates it on flip so scrollbars/native controls follow.
6. **Toggle placement + state ownership (P-03):** theme state lives in **`App`** (the sole common
   ancestor of `MainApp` and `AuthView`). Both `ThemeToggle` instances — header button in
   `App.jsx` (right-side cluster next to "Sign out", OUTSIDE the `<nav>` element — smoke tests
   query nav by role/name) and the SAME toggle on the AuthView sign-in card (theme must be
   reachable pre-login) — render from that state; all writes (attribute + meta + `prime_theme`)
   go through the one `applyTheme()` path (no split-brain between React state and the DOM
   attribute). The two shells never co-render, so duplicate accessible names are out of scope.
   One component (`components/theme.jsx` — new file; tailwind `content` globs already cover
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
   themes. ~~(expect it stays dark-on-blue)~~ **[RESOLVED at design (W2-DEEP-01, §2.4b):**
   accent-ink is WHITE in the light block (255 255 255). The two constraints are mutually
   exclusive (dark ink on accent ≥4.5 forces accent luminance ≥0.211; accent-as-text ≥4.5 on
   white canvas forces accent luminance ≤0.183 — an empty interval), so white ink is the only
   compliant value. Dark block keeps `10 18 32`.]** `--warn`/`--bad`/`--ok` on `--canvas` ≥4.5:1 in light
   (warn needs darkening — #E4B95F on white is ~1.9:1 today); alpha washes must be evaluated
   composited over light canvas, not on raw tokens. No mechanical 255−x invert.
   - **[ACCEPTED EXCEPTION (W2-DEEP-01, §2.4a):** `--raised` on `--canvas` is 1.18:1 — a FILL
     surface, never a boundary. Every raised consumer is bordered by `--rule` (rule/canvas
     3.36:1) or a fill track (accent fill 5.44:1 on raised). Mitigated by the boundary contract;
     do not darken raised to chase 3:1 (would break faint text 4.85:1 on raised).]**
   - **Pinned pair inventory (P-04):** the design record's table MUST cover, per theme:
     body tokens (strong/ink/muted/faint) × (canvas, surface, raised); accent-as-text on
     canvas + surface; **accent-ink on accent AND on accent-hover** (`.btn-primary` hover,
     styles.css:94-95); ok/warn/bad × canvas + surface; `--rule` on `--canvas`; `--raised` on
     `--canvas`; focus outline on `--canvas`. Table columns: `token`, `dark value`,
     `light value`, `pair checked`, `ratio`. The `--accent` dual-role tension (link text needs
     ≥4.5:1 on white; fill for `.btn-primary`/`Bar`/ResultLine needs to read as solid against
     `--raised` tracks) must be shown in both roles.
   - **Pinned alpha-wash inventory (P-05):** the design record MUST list every composited pair
     (token/alpha, background token, resulting color, resulting ratio where text sits on it) for
     at minimum: confusion-matrix cells at alpha min AND max (accent vs warn distinction on
     white — off-diagonal warn cells vs diagonal accent cells, metrics.jsx:270, plus the
     `bg-accent/25` CV band metrics.jsx:164); admin badges ok/warn/bad washes (styles.css:298-301);
     `.newjob-tag` (styles.css:258-262); `::selection` (accent/0.35, :51); `.field:focus` ring
     (accent/0.2, :85). Distinguishability (accent vs warn cells) must be shown, not just text
     ratios. Non-text note to record: `ring-canvas` around the ResultLine dot will read as an
     invisible white gap in light (cosmetic; acceptable) — record it, don't fix it with a token change.
10. **Test structure:** `frontend/tests/theme.test.jsx` (new) — one `describe` per concern:
    resolution order (stored/system/default; `matchMedia` stubbed per test — P-02), hostile
    stored values (XSS, 10KB, unicode), localStorage-throw fallback (theme flips in-memory, no
    crash), toggle side effects (attribute + meta + storage, sign-out does not clear), afterEach
    removes `prime_theme`. The design record (edge: toggle accessible label — action-describing,
    e.g. "Switch to light mode" — and no collision with nav link names "Runs"/"Models"/"New
    run"/"Admin") must land BEFORE `theme.test.jsx` is written (P-10).
    `frontend/tests/static.test.js` — ADDITIVE guards:
    - Structural: `[data-theme="light"]` block exists, all 14 token names defined in it, sets
      `color-scheme: light` (existing rule: pin structure, not values).
    - **Ratio guards (P-06):** parse the 14 light triples from styles.css, compute relative
      luminance + pairwise ratios for the full P-04 inventory, assert each meets the §4.9
      thresholds (values stay free; ratios are pinned — a value edit that destroys contrast fails).
    - **Dark-value invariance (P-06):** assert the 14 `:root` triples equal today's literals
      (85acdda), making acceptance #4 automated.
11. **Probe checklist (manual Chromium, recorded in tech-debt — NOT claimable by jsdom) (P-07):**
    run against the **production build** (`npm run build` + `vite preview`) — the dev-only
    unstyled flash (CSS injected via `main.jsx`) is out of scope and must not fail the
    "no dark flash for stored-light on throttled reload" check. Checklist: all 7 views + Admin
    at 390px + desktop in both themes; keyboard focus visible; toggle persistence across reload.
    Any component-level fix beyond token values (expected: none) requires a spec amendment.

## 5. Acceptance criteria (measurable)

1. Light theme renders every surface with identical layout (probe screenshots).
2. Palette contrast table in the design record meets §4.9 ratios — reviewer recomputes.
3. Toggle flips attribute + meta + storage in one interaction; persists across reload; first
   paint matches stored/system (no flash for stored-light).
4. Dark default at 85acdda is byte-identical (14 token values unchanged) when system is dark.
   (Enforceable form: the 14 `:root` token assignments are textually unchanged from 85acdda;
   implemented as the P-06 dark-value assertion in static.test.js.)
5. `npm test` (full) + `npm run build` green; shipped-file greps show zero hits outside
   comments/tests. Literal commands:
   `grep -rnE 'dark:' frontend/ --include='*.jsx' --include='*.js'` → no matches;
   `grep -rnE '#[0-9a-fA-F]{3,8}\b' frontend/ --include='*.jsx'` → no matches
   (styles.css token-definition comments at frontend/styles.css:16-19 are allowlisted hex);
   `grep -rnE 'bg-white|text-black|from-|via-|to-' frontend/ --include='*.jsx'` → no matches.
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
