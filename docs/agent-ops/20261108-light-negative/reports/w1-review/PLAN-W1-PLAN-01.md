<!-- ORCH-DIGEST:START -->
agent: W1-PLAN-01 | scope: T-101 light-mode spec review (docs/plans/2026-11-08-light-mode.md) | verdict: APPROVE-WITH-CHANGES
findings: BLOCKER 0 | MAJOR 6 | MINOR 4 | NIT 0
claims_audit: ~24 spec claims checked / 0 contradicted by code / 6 incomplete (guards, pair enumeration, state ownership, init detail, wash inventory, static-guard strength)
band_aids_found: none (spec rejects per-component `dark:` churn correctly; no swallow-and-continue proposed)
top_3_risks: (1) light palette left to design record without pinned pair inventory/table format — reviewer cannot verify completeness; (2) pre-paint init script under-specified (placement, try/catch, matchMedia guard) — plausible literal implementations flash, throw, or crash jsdom; (3) static guards pin block existence, not contrast values — a token swap to all-white passes them
optimizations: DO-NOW 0 | DO-LATER 0 | NOT-WORTH-IT 0 (planner review; no code)
reversal_check: reasoned-only (guard-strength argument; no test run per brief)
confidence: high (all 6 attack surfaces verified against code; no browser/probe run by design)
<!-- ORCH-DIGEST:END -->

# Planner review — W1-PLAN-01 — light-mode spec (T-101, docs/plans/2026-11-08-light-mode.md)

## 0. Method

Read in brief order: brief W1-PLAN-01, STANDING-ORDERS, the spec in full, INV-light-mode (W0-INV-01), then verified every load-bearing spec claim against code: `frontend/index.html` (all 13 lines), `frontend/vite.config.js` (all 15), `frontend/App.jsx:1-187` (whole file), `frontend/components/shared.jsx:150-199`, `frontend/styles.css` (all 323 lines), `frontend/tailwind.config.js` (all 33), `frontend/views/AuthView.jsx` (all 89), `frontend/main.jsx` (all 10), `frontend/components/metrics.jsx:150-289`, `frontend/tests/helpers.jsx:1030-1063`, `frontend/tests/static.test.js:1-40` + scoped greps. Ran scoped greps only (palette census, arbitrary values, alpha washes, `dark:`/`data-theme`, storage teardown, smoke nav queries). Did NOT run vitest/build/browser (per brief; coder agents own execution). Did NOT edit source or the spec.

Branch: `frontend-ui-round2` (per brief; not re-verified with git — not needed for a doc review).

## 1. Blind pass (verdict in one paragraph)

Option A (`[data-theme="light"]` variable inversion on `<html>`, `:root` stays dark) is the correct call and the census proves the codebase is token-ready: the approach is faithful to the architecture, keeps `tailwind.config.js` untouched, keeps the blast radius off `RunDetails.jsx` (C1-safe), and is fully reversible. The spec's process shape — thresholds pinned here, exact triples in a design record, reviewer recomputes — is also defensible. But the spec stops one level short of mechanical: six gaps sit between "approved shape" and "safe to implement without surprises" — the pre-paint contract, the environment guards, toggle state ownership across the two shells, the contrast pair inventory, the alpha-wash inventory, and the strength of the static guards. None requires redesign; all require pinning. Verdict: **APPROVE-WITH-CHANGES**, 0 blockers, 6 majors, 4 minors. Implementation should proceed only after the majors are folded into the spec (or explicitly accepted in the impl report).

## 2. Claims audit (spec section → classification)

| Spec section | Class | Evidence |
|---|---|---|
| §1: 14 tokens `styles.css:15-31`, `color-scheme: dark` at :30 | SUPPORTED | [VERIFIED frontend/styles.css:15-31] exact triples match INV §1; values are space-separated RGB, matching `token()` in tailwind.config.js |
| §1: `tailwind.config.js` maps every token, utilities resolve through vars | SUPPORTED | [VERIFIED frontend/tailwind.config.js:3-24] `token(name) => rgb(var(--name) / <alpha-value>)` for all 14 names; no `darkMode` key (defaults to unused media strategy) |
| §1: census 93 `var(--)` / 94 `rgb(...)`, zero hardcoded hex in shipped rules | SUPPORTED | Direct re-greps agree: zero `dark:`, zero `bg-white`/`text-black`, zero `from-/via-/to-` gradient utilities, zero `bg-[#…]`/`text-[…]`/`shadow-*` in shipped JSX/CSS; hex hits are only token-documentation comments (`styles.css:16-19`) — spec §5.5 correctly scopes greps "outside comments/tests" |
| §1: sole outlier `NewJob.jsx:678` `text-orange-400` | SUPPORTED | [RAN grep text-(palette)-N] → exactly 1 match, `NewJob.jsx:678` [VERIFIED] |
| §1: two `color-scheme: dark` pins (`styles.css:30`, `index.html:6`) | SUPPORTED | [VERIFIED frontend/index.html:6] + [VERIFIED frontend/styles.css:30] |
| §1: no `data-theme`/`prefers-color-scheme`/`prime_theme` anywhere; state is `{currentView, activeParams, me}` + `prime_token` only | SUPPORTED | [RAN grep dark:\|data-theme\|prime_theme\|prefers-color-scheme] → 0 matches; [VERIFIED frontend/App.jsx:66-71], [VERIFIED frontend/components/shared.jsx:161-179] |
| §1: `vite.config.js` `test.css: false` → jsdom can't assert computed colors | SUPPORTED | [VERIFIED frontend/vite.config.js:10-14]; static guards read source text [VERIFIED frontend/tests/static.test.js:1-9], confirming the harness limitation |
| §1: test hygiene trap — per-file `window.localStorage.clear()`, `teardownApp` removes only `prime_token` | SUPPORTED | [VERIFIED frontend/tests/helpers.jsx:1044,1054-1063] + [RAN grep localStorage.clear() in tests/] → every test file clears in beforeEach/afterEach; leakage would only occur *within* one file — spec §4.10's afterEach-removes-`prime_theme` is the right minimal fix (correctly avoids touching `helpers.jsx`) |
| §1: "AuthView renders its own `<main>` outside MainApp (`App.jsx:175-187`)" | SUPPORTED | [VERIFIED frontend/views/AuthView.jsx:48-89] own `<main>`; [VERIFIED frontend/App.jsx:178-185] `token ? <MainApp/> : <AuthView/>` mutually exclusive |
| §2: goals (toggle every surface incl. sign-in; persisted; no flash; system default; contrast-valid, not invert) | SUPPORTED (as targets) | Consistent with code constraints; "every surface" claim depends on §4.6 both-shells decision holding — it does (see §3.2 below) |
| §3/§6: Option A chosen, B/C/D rejected with reasons | SUPPORTED | Option B rejection is decisive: ~119 `text-*` + ~17 bg/border sites per INV, and the token architecture (`tailwind.config.js:1-3` comment) plus static R4 guard ("tokens only, no ad-hoc hex" [VERIFIED frontend/tests/static.test.js:161]) make per-component variants a regression, not an improvement. C/D rejections sound. |
| §4.1: canonical attribute `documentElement.dataset.theme`, explicit `"dark"` on toggle-to-dark | SUPPORTED | Coherent with resolution order; MISSING corollary (mid-session `prefers-color-scheme` change is not tracked — say so explicitly). Wording nit: "absence = system-was-dark initial" is misleading; absence means "no stored choice" regardless of system. See MINOR P-08. |
| §4.2: resolution order incl. garbage-value fallthrough, allow-list only | PARTIALLY SUPPORTED / MISSING (guards) | The allow-list design is right and XSS-safe (`dataset.theme` assignment is not `innerHTML`); but the spec never pins existence guards for `matchMedia`/`localStorage` — see MAJOR P-02. jsdom does not implement `matchMedia`, so an unguarded `window.matchMedia(...)` crashes the test harness itself. |
| §4.3: `prime_theme` key, sign-out must NOT clear | SUPPORTED | Matches `shared.jsx:175-179` (`logout` removes only `prime_token`); note `logout` is a `useCallback` with no deps — the theme key survives by default, the pin is belt-and-braces and correct |
| §4.4: inline pre-paint init script | SUPPORTED (shape) / MISSING (contract) | Direction right; detail missing (head placement, try/catch, meta) — see MAJOR P-01 and MINOR P-07 |
| §4.5: meta color-scheme updated by init + toggle | SUPPORTED | [VERIFIED frontend/index.html:6] static `content="dark"` + init-script update is the only mechanism; must be pinned reachable from the same init (see P-01) |
| §4.6: header toggle OUTSIDE `<nav>` + same toggle on AuthView; `components/theme.jsx` needs no config change | SUPPORTED (placement) / MISSING (state owner) | Outside-nav confirmed safe: smoke queries scope to `getByRole('navigation', {name:/^main$/i})` [VERIFIED frontend/tests/smoke.test.jsx:210-229]; `content` globs cover `components/**` [VERIFIED frontend/tailwind.config.js:6]. State ownership across shells not pinned — see MAJOR P-03 |
| §4.7: `<button aria-pressed>`, label describes the ACTION, ≥3:1 focus | SUPPORTED | Consistent with existing `:focus-visible` (accent outline [VERIFIED frontend/styles.css:53]) — 3:1 ratio must be folded into the design-record pair list (see P-04); label deferral to design record is fine provided the record lands before tests are written (trivial ordering, noted in P-10) |
| §4.8: `NewJob.jsx:678` → `text-warn`, optional `--warn-strong` + one-line config mapping | SUPPORTED | Minimal-fix shape is right; the conditional config edit is properly recorded. Note: `text-warn` only fixes the light theme if the light `--warn` actually reaches ≥4.5:1 on white (spec already requires it, design record must prove it — see P-04) |
| §4.9: contrast thresholds (4.5:1 body, 3:1 large/focus, accent-ink-on-accent 4.5:1, warn/bad/ok 4.5:1) | SUPPORTED (thresholds) / MISSING (inventory) | Thresholds are the right bars. But the spec enumerates no concrete pair list and no design-record table format — see MAJOR P-04. Also missing: `--accent-ink` on `--accent-hover` (btn-primary hover state, [VERIFIED frontend/styles.css:94-95]) and non-text contrast for `--rule`/`--raised`. |
| §4.10: `theme.test.jsx` concerns + `static.test.js` additive guards (selector + 14 names + color-scheme: light) | SUPPORTED (test *concerns*) / MISSING (guard *strength*) | Resolution/hostile/throw/toggle-side-effect coverage matches the real failure modes. But existence guards don't survive value regression — see MAJOR P-06 |
| §4.11: probe checklist (7 views + Admin, 390px + desktop, keyboard focus, no-flash throttled reload) | SUPPORTED | Honestly scoped to manual Chromium (jsdom can't), spec explicitly marks it NOT claimable by jsdom. Gap: probe environment (dev vs build) not pinned — see MINOR P-07 |
| §5: acceptance criteria 1-7 | SUPPORTED with wording issues | #4 "byte-identical dark default" is literally false (styles.css bytes change when the light block lands); the enforceable claim is `:root` triple-equality — see MINOR P-08. #5's grep acceptance needs literal commands — P-08 |
| §7: write-set, rollback, top risks; RunDetails excluded | SUPPORTED | Rollback (revert block + toggle + init) is genuinely byte-equivalent to today's dark. C1-safe: RunDetails not touched, disjoint from T-102 |

**No spec claim was contradicted by the code.** The spec is honest about what INV verified vs what it didn't. Option A really is the right call; the tech-debt "do not invert ad-hoc" constraint is honored by pinning thresholds here and triples in a design record.

## 3. Attack surfaces (brief §3)

### 3.1 Is the inline init script in `index.html` actually pre-paint in this Vite setup? What else could FOUC?

**Mostly yes, with two unspecified details that let a literal implementation flash or throw.**

- Build mode: Vite emits the bundled CSS as a separate `<link rel="stylesheet">` in `<head>` (render-blocking) and preserves inline scripts in `index.html`. A parser-blocking inline script in `<head>` runs during parsing, before first contentful paint. In this mode FOUC is prevented by the render-blocking CSS regardless of the script — so the acceptance test "no dark flash for stored-light on throttled reload" passes in the built app.
- Dev mode: `main.jsx:4` imports `./styles.css`, and Vite dev injects CSS via JS. Paint *can* occur before the module graph loads. The inline script still sets `data-theme` early, but the background color comes from CSS that hasn't arrived — the flash would be the browser's default white, not dark. Current dev behavior already has this unstyled-flash characteristic (no inline critical style exists today), so the spec's acceptance would be flaky-by-environment unless the probe mode is pinned. See MINOR P-07.
- StrictMode double-render (`main.jsx:6-10`): harmless. `applyTheme` (attribute + meta set) is idempotent; the spec's §4.4 "React treats `dataset.theme` as source of truth, no double-apply" already closes this. No extra StrictMode FOUC vector.
- HMR: init script runs once at load; hot updates preserve the DOM attribute. No re-init problem.
- **Unspecified**: (a) exact placement — the spec says "in `index.html` (before first paint)" but never pins `<head>` vs end-of-body; end-of-body still precedes the deferred module script, yet progressive rendering can paint before a body-end script in theory. Pin `<head>` before the CSS link and there is no ambiguity. (b) the init script must wrap `localStorage`/`matchMedia` access in `try/catch` — a throw in a head script aborts the rest of the script (no DOM damage, but the theme silently stays dark for stored-light users, exactly the flash the script exists to prevent). The spec pins try/catch only for the React-side `theme.jsx` (test §4.10), not for the init script. → MAJOR P-01.

### 3.2 Toggle in both shells vs header-only vs AuthView-only — which does the spec pin? Is requiring BOTH over-engineering? Minimal-risk placement?

The spec pins **both**: header button (outside `<nav>`) + same `ThemeToggle` on the AuthView card (§4.6). This is the right call, not over-engineering:

- §2's goal is "visible on every surface (incl. sign-in)" — a header-only toggle strands the sign-in screen dark-only, because AuthView renders its own `<main>` outside MainApp [VERIFIED frontend/views/AuthView.jsx:48-89 + frontend/App.jsx:178-185]. An AuthView-only toggle is even worse (no toggle at all once authenticated).
- The cost of both is one shared component with two render sites (`ThemeToggle` in `components/theme.jsx`) — not duplicated logic. The two shells are mutually exclusive [VERIFIED frontend/App.jsx:182], so there is no duplicate-accessible-name conflict, and both mount fresh — labels re-derive from `documentElement` on mount.
- Placement test-safety is confirmed: smoke tests scope nav queries to the `navigation` role [VERIFIED frontend/tests/smoke.test.jsx:210-229], so a header button in the `ml-auto` cluster (`App.jsx:148-159`) outside `<nav>` cannot break them.

What the spec does **not** pin is where React state lives: `App` (the only parent of both shells), `MainApp`, or inside `ThemeToggle` itself. Each yields a different failure surface (stale `aria-pressed`/label if state is scoped to one shell while the DOM twin is mutated directly; remount churn if state sits above both but `ThemeToggle` additionally mirrors `documentElement`). The minimal-risk shape — theme state lifted to `App`, `ThemeToggle` rendered from it in both shells, `documentElement` as the persistent truth — should be one sentence in the spec. → MAJOR P-03.

### 3.3 Does any component break if token VALUES change even while class names stay? (alpha-wash compositing)

Yes — three real risks the generic statement in §4.9 ("evaluate washes composited") must be forced into an explicit inventory, because the actual sites behave differently on white:

1. **ConfusionMatrix** (`metrics.jsx:270`, spot-checked): inline `rgb(var(--accent)/alpha)` with alpha `0.12 + (count/top)*0.4` (range 0.12–0.52 after the `count===0 ? 0` clamp). On white, low-alpha cells read near-white (dark `text-strong`/`text-ink` on top — passes); high-alpha cells read mid-blue (dark text on light blue — passes). The subtle failure is *distinction*, not contrast: `--warn` cells at 0.12 alpha over white vs `--accent` cells at 0.12 alpha — both are faint tints of different hues, and off-diagonal (warn, "where it gets confused") vs diagonal (accent, correct) must stay distinguishable. Token-only fix exists (darken warn improves this), but a design record that never lists this site cannot be checked for it.
2. **Badges and washes with a fixed band**: `admin-badge` family (`styles.css:298-301`: ok/warn/bad text on `/0.1` wash with `/0.3–0.4` border), `.newjob-tag` (`:258-262`: accent text on `/0.15` + `/0.5` border), `.newjob-mode-note` (`:242`), `.field:focus` shadow (`:85` accent/0.2), `::selection` (`:51` accent/0.35), `bg-accent/25` CV band (`metrics.jsx:164`), Ask-on-canvas hover washes (`hover:bg-surface/60`, AdminScreen:155, ModelsCatalog:93). In dark these light-darken; on white, a `/0.1` wash *lightens toward white* — the wash becomes nearly invisible, leaving text-on-canvas as the only signal. That's fine for badges *if* `--ok/--warn/--bad` on white pass 4.5:1 (required), but `accent`-tinted surfaces on white need their own composited check (accent text on accent/0.15 over white ≈ accent text on near-white ≈ fine iff accent-on-canvas passes — the design record must show that chain, not assume it).
3. **Non-text surfaces with no contrast budget in §4.9**: `ring-canvas` around the ResultLine value dot (`metrics.jsx:177` — ring color *is* canvas, so in light it's white around an accent/warn dot on white — invisible gap, dot appears larger; cosmetic, acceptable, but say so), `bg-rule` baseline line (`:161`), `bg-raised` Bar track (`:239`), `--rule` hairlines everywhere. WCAG 1.4.11-style non-text 3:1 for meaningful UI boundaries is a reasonable bar for `--rule` on `--canvas` and `--raised` on `--canvas`, but the spec assigns no budget to either — a mechanically-inverted `--rule` could go near-white and erase every hairline. → MAJOR P-05 (wash inventory), MAJOR P-04 (non-text pairs).

`Bar`/`ResultLine` fills themselves (`bg-accent`/`bg-faint`/`bg-raised`) are token-driven and survive; the accent-vs-warn-on-white distinction is a palette-math property, already flagged by INV and required by §4.9's warn/bad/ok-on-canvas rule — provided the design record enumerates it.

### 3.4 Is `text-orange-400` the ONLY hardcoded outlier? Census completeness.

**Confirmed sole outlier.** Independent greps over `frontend/`:

- [RAN grep `text-(palette)-N` / `bg-(palette)-` / `border-(palette)-`] → exactly 1 hit: `NewJob.jsx:678` `text-orange-400`.
- [RAN grep `bg-[#…]` / `text-[…]` / `shadow-*`] → 0 hits in shipped files (the only `shadow` occurrences are the CSS `box-shadow` property in `styles.css:85`, token-colored).
- [RAN grep `bg-white|text-black|from-|via-|to-|darkMode`] → 0 hits in shipped files (only `electron-to-chromium` in package-lock).
- No gradients, no `bg-white`, no arbitrary color values; `accent-[rgb(var(--accent))]` (RunsDashboard) and both inline-style token references (`metrics.jsx:270`) are variable-indirected and invert-safe.

The census is complete. The spec's "zero hits outside comments/tests" guard for acceptance #5 needs literal commands though — styles.css token-definition comments contain hex (`styles.css:16-19`), so the implementer must know to strip comments or allowlist those lines. → MINOR P-08.

### 3.5 Light palette left to the design record — acceptable, or must the spec carry the 14 values NOW?

**Acceptable shape, unacceptable under-specification.** Carrying 14 triples (plus ~8 composited washes) inside the planning spec would duplicate a second spec; a separate design record with reviewer-recomputed math is the right division of labor. But the spec must make that review *checkable*. Right now the reviewer receives §4.9 thresholds and prose, from which they must guess: which token×surface pairs were checked, in what table format, how washes were composited, and which dual roles each token serves. Two things would make it mechanical without bloating the spec:

1. **Pinned pair inventory + table columns** (see §3.3 + P-04): body text tokens (strong/ink/muted/faint) × (canvas, surface, raised); accent-as-text on canvas + surface; accent-ink on accent *and* accent-hover; ok/warn/bad × canvas + surface; rule × canvas; raised × canvas. The `--accent` dual-role tension must be named: one token is simultaneously link text (needs ≥4.5:1 on white) and fill for `.btn-primary`/`Bar`/ResultLine (needs to read as a solid against `--raised` tracks on white). Both are satisfiable by a mid-dark blue, but only if the record shows accent in both roles.
2. **Automated contrast check in `static.test.js`** (see P-06): parse the 14 light triples from styles.css in the test, compute relative luminance + ratios, assert ≥ thresholds. That converts "reviewer recomputes" from manual homework into a regression guard — jsdom can't paint, but it can do arithmetic. This directly answers "what evidence proves the palette is right without a browser": the computed table + a test that fails if any value drifts below threshold, with the manual probe covering layout/visibility only.

Feasibility: every required ratio is achievable in a light palette (dark-ink-on-mid-blue stays ≥4.5:1 for accent-ink; a darkened warn hits 4.5:1 on white; faint/muted at ~5:1 need dark gray-blues, not light ones). Nothing in the thresholds is impossible — but "feasible" ≠ "proven," and the proof obligation must be pinned. → MAJOR P-04, MAJOR P-06.

### 3.6 Static-test strategy: does "selector exists + 14 tokens + color-scheme" prevent regression, or test implementation detail?

It tests *implementation detail* — and only half of it. The guards in §4.10 would pass if all 14 light values were white, or if the accent/warn distinction collapsed entirely. They prevent one specific regression (someone deleting the light block or a token) while being blind to the actual risk class of this feature (a value edit that silently destroys contrast).

Stronger but still browser-free — and consistent with the spec's own "don't pin exact RGB" principle:

- Parse the light block's 14 triples in `static.test.js` (regex over styles.css, matching existing guard style: `expect(stylesSource).toMatch(...)`), compute pairwise ratios for the pinned inventory, assert ≥ thresholds. Values stay untinned; *ratios* are pinned.
- Separately assert the dark `:root` block's 14 triples equal today's literals (acceptance #4 made automatic — currently a hand-waved sentence in §5.4).

This keeps the spec's "structure, not exact triples" rule while making the regression it cares about (unreviewed value edits) actually fail. → MAJOR P-06.

## 4. Spec-section verdicts

| Spec section | Verdict |
|---|---|
| §1 Facts (verified) | PASS — faithful to code, numbers check out, honest about jsdom limits |
| §2 Goals/non-goals | PASS — achievable; token-only constraint is honored by census |
| §3 Approach (Option A) | PASS — correct vs alternatives, all rejections well-founded |
| §4 design decisions | CONDITIONAL — see MAJORS P-01…P-06 below |
| §5 acceptance criteria | CONDITIONAL — #4 needs rewording, #5 needs literal commands (P-08) |
| §6 alternatives rejected | PASS — B/C/D rejections are decisive and internally consistent |
| §7 blast radius/rollback | PASS — honest, C1-safe, rollback truly restores byte-equivalence |

## 5. Findings (each with resolution requirement)

### P-01 [MAJOR] Pre-paint init contract under-specified (placement + fault safety)

- **Location:** spec §4.4, §4.5 · **Evidence:** `frontend/index.html:1-13` has no script and a static `content="dark"` meta at :6; `frontend/main.jsx:4` pulls styles.css via JS in dev, bundled `<link>` in build. The spec pins neither head placement nor failure behavior.
- **Why it matters:** End-of-body script placement risks early paint in dev; an un-guarded `localStorage` access in a head script throws silently and leaves stored-light users flashing dark — the exact defect this script exists to prevent. A spec test covers storage-throw only on the React side (§4.10), not the init script.
- **Resolution required:** Pin in §4.4: (1) script lives in `<head>` before the stylesheet link/module script; (2) fully `try/catch`-guarded (storage read, `matchMedia` call, meta update) with silent fall-through to dark; (3) it sets `data-theme` *and* the meta `content` from one resolution. Explicitly state StrictMode/HMR need no handling because the script runs once and React treats the attribute as truth (already implied by §4.4 — make it explicit).

### P-02 [MAJOR] Missing environment guards for `matchMedia` / `localStorage` + test stub pin

- **Location:** spec §4.2, §4.10 · **Evidence:** jsdom does not implement `window.matchMedia`; `resolveTheme()` per §4.2 unconditionally consults `matchMedia("(prefers-color-scheme: light)")`. No guard or stub requirement is pinned anywhere.
- **Why it matters:** An unguarded call crashes not just the theme but the test render (jsdom) and older browsers; an unstubbed test suite makes "resolution order" tests environment-dependent.
- **Resolution required:** Pin `typeof window.matchMedia === 'function'` and safe `localStorage` access (access can itself throw in some contexts) inside `resolveTheme()` — fall-through to dark on any environment absence; and pin that `theme.test.jsx` stubs `matchMedia` per test (both light- and dark-preferring), since the spec's resolution-order tests are otherwise unimplementable. The garbage-value XSS tests remain valid.

### P-03 [MAJOR] Toggle state ownership across the two shells not pinned

- **Location:** spec §4.6 (exports `resolveTheme/applyTheme/toggleTheme/ThemeToggle` without a state model) · **Evidence:** `App.jsx:175-186` is the sole common ancestor of `MainApp` (header) and `AuthView` (card). A `ThemeToggle` that mirrors `documentElement` without parent state will greet the next mount correctly but can hold a stale `aria-pressed`/label after programmatic flips; state scoped to `MainApp` leaves AuthView reliant on unmounted-state magic.
- **Why it matters:** This is the one genuinely new piece of React state in the app; "the component exports these functions" is not an architecture.
- **Resolution required:** One sentence pinning: state lives in `App`, both `ThemeToggle` instances render from it, `documentElement.dataset.theme` + meta + `prime_theme` are written through the same `applyTheme` path (no split-brain between React state and DOM attribute). Note the two shells never co-render, so duplicate-name and keyboard-trap concerns are out of scope.

### P-04 [MAJOR] Design record lacks a pinned pair inventory and table format

- **Location:** spec §4.9 · **Evidence:** threshold list names only generic "text/background pairs" plus three special cases; never enumerates which of the (14 tokens × 3 surfaces) combinations the record must show, never names the accidental omissions: `--accent-ink` on `--accent-hover`, `--rule` on `--canvas`, `--raised` on `--canvas`, or the dual-role tension of `--accent` (text vs fill). "Reviewer recomputes" (§5.2) is unverifiable against freeform prose.
- **Why it matters:** Without an inventory, the light palette can pass every listed ratio and still ship invisible hairlines, an illegible primary-button hover, or an accent that fails as link text — precisely the failure mode tech-debt warned about ("may need component fixes… do not invert ad-hoc") [INV §1].
- **Resolution required:** Pin the minimum pair inventory (body tokens strong/ink/muted/faint × canvas/surface/raised; accent-text on canvas+surface; accent-ink on accent + accent-hover; ok/warn/bad × canvas+surface; rule × canvas; raised × canvas; focus outline × canvas) and the table columns (`token`, `dark value`, `light value`, `pair checked`, `ratio`). Thresholds stay as written. The 14 triples themselves remain in the design record.

### P-05 [MAJOR] Alpha-wash inventory absent (composited check named but not enumerable)

- **Location:** spec §4.9 (last clause) · **Evidence (spot-checked, all token-indirected):** ConfusionMatrix inline alpha 0–0.52 (`metrics.jsx:270`); `bg-accent/25` CV band (`metrics.jsx:164`); admin badges `/0.1–0.4` (`styles.css:298-301`); `.newjob-tag` `/0.15 + /0.5` (`:258-262`); `.field:focus` accent/0.2 (`:85`); `::selection` accent/0.35 (`:51`); hover washes `hover:bg-surface/60` etc. Light washes over white lighten toward white — the verification direction reverses vs dark.
- **Why it matters:** A design record satisfying §4.9 generically ("washes evaluated composited") can skip the exact sites where light-theme degradation concentrates (badge tints vanishing, confusion diagonal-vs-off-diagonal distinguishability on white).
- **Resolution required:** Require the design record to list every composited pair (token/alpha, background token, resulting color, resulting text ratio where text sits on it) for at minimum: confusion cells at alpha min/max, badge washes (ok/warn/bad), `.newjob-tag`, selection, field-focus ring. Distinguishability (accent vs warn cells) must be shown, not just text ratios.

### P-06 [MAJOR] Static guards pin existence, not behavior; dark-value invariance is only asserted in prose

- **Location:** spec §4.10 (final sentence), §5.2/§5.4 · **Evidence:** `static.test.js` is a text-reading harness [VERIFIED frontend/tests/static.test.js:1-9] — it *can* do arithmetic but the spec only requires it to check presence of 14 names. Acceptance #4 ("byte-identical dark default") is a manual assertion; nothing fails if a later commit "tunes" `:root`.
- **Why it matters:** The feature's true regression class is value edits, not block deletion; the pinned guards can't see them, so drift accumulates silently. The spec explicitly admits this ("those are pinned *by the contrast computation in the design record*") — a document, not a test.
- **Resolution required:** Extend §4.10's static guards to (1) parse the 14 light triples from styles.css and assert every P-04 pair meets the §4.9 thresholds (values free, ratios pinned — consistent with the existing rule); (2) assert the 14 dark `:root` triples equal today's literals, making §5.4 automated. If the orchestrator prefers manual review over ratio tests, that preference must be recorded as an explicit acceptance, not left implicit.

### P-07 [MINOR] Probe environment not pinned (dev flash vs build)

- **Location:** spec §4.11, §5.3 · **Evidence:** dev injects CSS via `main.jsx` module; build uses render-blocking `<link>`. "No flash on throttled reload" is only assertable one way.
- **Why it matters:** A probe run against `npm run dev` can show a white flash for dark users (pre-existing dev characteristic) and fail the acceptance for environmental reasons; conversely a dev-only probe can't distinguish.
- **Resolution:** Pin the probe to the production build (`npm run build` + `vite preview`), and either (a) accept the dev-only unstyled flash as out of scope, or (b) require an inline critical `<style>` (body background keyed off `data-theme`) — at the cost of duplicating one token value in index.html, which must then be a deliberate, recorded exception to "tokens live in CSS only." Either choice is fine; silence is not.

### P-08 [MINOR] Acceptance §5.4/§5.5 wording is not executable as written

- **Location:** spec §5 (#4, #5) · **Evidence:** (a) "byte-identical (14 token values unchanged)" — the CSS file bytes change when the light block is added; only the `:root` triple set is invariant. (b) §5.5's "shipped-file greps show zero hits" — hex comments exist at `styles.css:16-19` by design, so the literal grep as worded fails on a clean tree.
- **Resolution:** Reword #4 to "the 14 `:root` token assignments are textually unchanged from 85acdda" (and prefer P-06's automated assertion); give the exact grep commands for #5 with comments stripped or lines 16-19 allowlisted. Same reword for §4.1's "absence = system-was-dark initial" → "absence = no stored choice (system decides)".

### P-09 [MINOR] Two scope silences: live system-preference changes and cross-tab sync

- **Location:** spec §4.2 (resolution "priority order" implies a one-shot resolution, but never says so) · **Evidence:** `toggleTheme` writes one tab's DOM + storage; other tabs stay stale until reload; mid-session OS theme switches are ignored.
- **Why it matters:** A reasonable implementer might add a `matchMedia` listener and a `storage` listener — more surface, more tests, no requirement behind them. Conversely a reviewer might ding the absence.
- **Resolution:** State explicitly: resolution happens once at load; no system-preference listener and no cross-tab `storage` listener (last-write-wins on reload is acceptable). This matches the spec's "instant flip" non-goal ethos and keeps the test surface bounded.

### P-10 [MINOR] Toggle label deferred without an ordering note + accessible-name hygiene

- **Location:** spec §4.7 ("pinned by the design record") · **Evidence:** `theme.test.jsx` will need `getByRole('button', {name: …})` queries (same style as smoke tests), so the label must be fixed before tests are written; smoke queries already demonstrate name-based lookups are this repo's convention [VERIFIED frontend/tests/smoke.test.jsx:30,210].
- **Why it matters:** Minor sequencing/clarity only — the action-describing-label requirement is correct and complete as written.
- **Resolution:** Add a one-line note that the design record must land before `theme.test.jsx` (label source of truth), and that the toggle's accessible name must not collide with existing nav link names ("Runs"/"Models"/"New run"/"Admin") — no new queries would break, but a sloppy label could.

## 6. Attempts to break the plan (reasoned; no execution per brief)

| Attempted break | Outcome |
|---|---|
| Assume Option A forces a `tailwind.config.js` edit (new token or `darkMode`) | **Fails** — token names are the contract and don't change; `components/theme.jsx` is inside existing content globs [VERIFIED frontend/tailwind.config.js:6]. Only the conditional `--warn-strong` in §4.8 touches config, properly flagged |
| Assume C1 (RunDetails) conflict with T-102 | **Fails** — light mode needs zero RunDetails edits (§7 write-set excludes it); the two tasks share a file only if the *probe* later demands a token tweak, already governed by the remediation clause |
| Store garbage/XSS in `prime_theme`, check injection | **Plan holds** — exact `=== "light"/"dark"` allow-listing (§4.2) means the value never reaches `innerHTML`; tests pinned (§4.10) |
| Throwing `localStorage`, jsdom without `matchMedia` | **Plan breaks here** — guards unpinned (P-02); the spec's own test plan would crash on its first test run until someone adds a guard the spec doesn't mention |
| Flip tokens only, keep class names, eyeball badges/confusion on white | **Plan under-determines** — failures are in compositing/distinction, not class lookup (P-04/P-05); a "passes §4.9 generically" record can still ship washed-out badges |
| Re-run the census hunting for missed hardcoded colors (arbitrary values, shadows, gradients, white/black) | **Plan holds** — exactly one outlier (NewJob:678); `shadow-*`/arbitrary-color/`dark:` all zero in shipped files |
| Delete the light block after implementation; ask which tests fail | **Plan partially holds** — structural static guard + toggle DOM test + hostile-value test fail (good); but a *value* edit (e.g., 14 values set to near-white) passes all new tests — reversal detection is incomplete (P-06) |
| Two-shell toggle with naive state | **Plan under-determines** — mount-fresh semantics rescue labels in the common path, but the spec never says state lives in `App` (P-03) |

## 7. Long-run test (independent answers)

- **Source:** Spec is faithful to the code (24 claims checked, 0 contradicted). Option A + token-only scope is not a band-aid: the root cause of the current state is the deferred-by-design palette, and the plan supplies the missing subsystem (palette + state + init) at the right layer. Rejections of B/C/D are principled, not process recitation.
- **Load (100x / concurrency / partial failure):** N/A for the UI itself (pure client; one localStorage key; no network). Concurrency concern is limited to two tabs + `toggleTheme` — last-write-wins, storage is the arbiter; spec's silence on cross-tab sync should be made explicit (P-09) rather than left to emerge.
- **Hostile input:** Covered well by design (§4.2 allow-list + §4.10 hostile tests) *except* the environment-absence case (P-02) — hostile isn't only a 10KB payload, it's a browser that refuses storage entirely.
- **Operability:** Rollback story is genuinely clean (revert 3 mechanisms → identical dark); observability is `documentElement.dataset.theme` + meta — both devtools-inspectable. Degradation path (storage denied → system default) is pinned for React but not for the init script (P-01).
- **Reversal:** Existence guards catch block deletion but not value corruption; the ratio-computing guard (P-06) is the missing test that *would* fail on the plausible bad edit. Until then, the plan relies on human review for its central invariant.

## 8. Dimension checklist

Correctness ✓ shape right, details missing · root-cause-vs-symptom ✓ (spec itself, not symptom patching) · regression/compat ✓ (dark default + C1 + smoke-safe placement all hold; P-06 is the one soft spot) · concurrency/idempotency ✓ (idempotent apply, P-09 silence aside) · error handling ✗ P-01/P-02 · security/abuse ✓ (allow-list + tests; storage vectors correctly analyzed) · performance/scalability ✓ n/a (no network, no render cost) · migration/rollback ✓ · observability ✓ (probe + attribute/meta inspectability, P-07 mode aside) · maintainability/conventions ✓ (new file in covered glob, token-only invariant preserved) · docs impact ✓ (design record + tech-debt probe entry correctly scoped)

## 9. What I could not verify

- No browser/Chromium probe (by design — the question is whether the *spec* is checkable, and §4.11's probe honesty is itself a passed check).
- Did not execute vitest, the grep census tools' full-suite equivalents, or `npm run build` (brief forbids; the census greps above were re-run directly via the grep tool and agree with INV).
- Exact census numbers (93/94) were re-derived only directionally via targeted greps, not by recounting every universe; the zero-hardcoded-colors conclusion was verified directly and is the load-bearing fact.
- Whether Vite's build output in this repo keeps the inline `<head>` script untouched (standard Vite behavior [ASSUMED from docs, not executed]) — cheap to confirm in W2 by inspecting `dist/index.html` after build; P-01's head-placement pin is robust either way.
- The design record does not exist yet, so palette feasibility of every ratio is judged as achievable-by-construction, not demonstrated.

## 10. Bottom line for the orchestrator

The spec makes the right call (Option A), is honest about the code, and keeps the wave plan C1-safe. It should **not** enter implementation until the six MAJORS are folded in or explicitly accepted: (1) init-script placement + try/catch, (2) matchMedia/localStorage guards + jsdom stub, (3) toggle state in `App`, (4) pinned contrast pair inventory + table format, (5) enumerated alpha-wash sites with composited ratios, (6) ratio-computing static guard + automated dark-value invariance. With those pinned, implementation becomes mechanical and the acceptance criteria become checkable in jsdom + one build-mode probe.
