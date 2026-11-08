<!-- ORCH-DIGEST:START -->
agent: W1-TREV-01 | scope: W1 T-301..T-304 (f53e4ba) | verdict: APPROVE
tests_reviewed: 8 | fail-before/pass-after confirmed: 8 pass-after by run, 7 fail-before reasoned (arithmetic + in-test self-check literals) / reasoned: 7 / not-possible: 0
findings: BLOCKER 0 | MAJOR 0 | MINOR 2 | NIT 1
flaky_suspects: none
missing_edge_cases: P1 0 | P2 1 | P3 2
mutation_survivors: 0 of 7 plausible bugs (1 brittleness survivor noted, not an escape)
changed_behavior_without_tests: none
confidence: high (scoped run green 51/51 reproduced; pins targeted; no mocking of unit under test)
<!-- ORCH-DIGEST:END -->

# Test quality review — W1-TREV-01 (W1-IMPL-01 T-301..T-304, commit f53e4ba)

## 0. Method
Blind read: `frontend/tests/static.test.js` (full 603 lines, new block L540-603), `frontend/tests/auth.test.jsx` (full 233 lines, new block L184-233), `frontend/views/AuthView.jsx` (full) — before reading impl report §7/§11. Then cross-checked impl claims (§7: pre-fix 7 failed/44 passed; §11 commands) and plan acceptance (`docs/plans/2026-11-09-playwright-fine-tune.md` L29-31). One scoped run per brief/STANDING-ORDERS §16: [RAN `cd frontend; npx vitest run tests/static.test.js tests/auth.test.jsx` -> 2 files passed, 51 passed (43 static + 8 auth), 9.92s]. Question tool NOT needed; no full suite, no worktree (read-only brief), no repeat-count runs. Reversal was reasoned (reverting source would violate read-only mandate); see §4 arithmetic. `git show --name-only f53e4ba` = exactly the 7 claimed files [VERIFIED], consistent with impl §5.

## 1. Per test/suite assessment
| Test | Asserts behavior? | Fails without fix? | Deterministic/isolated? | Over-mocked? | Notes |
|---|---|---|---|---|---|
| static T-301 icon+order (L541-555) | Yes: `<link rel="icon"`, `data:image/svg+xml`, order color-scheme < icon < prime_theme init | Yes: all 3 `toContain`/order asserts fail on pre-fix html (no icon link) | Yes: sync fs read, no timers | No | Order pin (not just presence) matches brief T-301 placement; `initIdx` pinned via `prime_theme` string [VERIFIED static.test.js:543-552]. In-test self-check L554. |
| static T-302 no-emoji (L559-564) | Yes: neither `combinedAppSource` nor Admin `source` contains U+1F4CA | Yes: pre-fix NewJob.jsx:660 contained 📊 | Yes: sync string scan | No | Union coverage is correct: scanned files = App.jsx+views/**+components/** [VERIFIED static.test.js:38-45], Admin scanned separately as `source`; both checked. Self-check L563. |
| static T-302 NewJob h3 (L566-574) | Yes: matched `<h3 ...>Model Intelligence</h3>` must not contain `text-lg` or 📊, must contain `font-semibold text-strong mb-4` | Yes: pre-fix line had `text-lg ... 📊` | Yes: sync regex on file text | No | **Targeted, not whole-file:** regex extracts the element first, asserts on `h3[0]` — a legit `text-lg` on a div elsewhere cannot trip it [VERIFIED L567-571]. This was the brief's explicit check; passed. Self-check L573. |
| static T-302 Admin h1 (L576-585) | Yes: `toContain('<h1>Admin</h1>')` + matched h1 element excludes `text-2xl`/`font-bold`/`tracking-tight` | Yes: pre-fix `text-2xl font-bold tracking-tight` fails both pins | Yes: sync | No | Targeted via `match(/<h1[^>]*>Admin<\/h1>/)` on element, not file. Self-check L584 (`includes('<h1>Admin</h1>') === false` for old line). |
| static T-303 audit title (L589-595) | Yes: matched truncate div (`className="text-xs text-faint truncate"`) must contain `title={JSON.stringify(event.detail)}` | Yes: pre-fix div had no `title=` | Yes: sync | No | Targeted element regex — a `title=` on a different div would not satisfy it. Self-check L594. |
| static T-303 invite wrap (L597-602) | Yes: `/\.admin-invite-code\s*\{[^}]*flex-wrap:\s*wrap/` on styles | Yes: pre-fix rule lacked flex-wrap (self-check constructs pre-fix literal L600-601) | Yes: sync | No | Selector-scoped regex; used pervasively in this file (same style as L189-190, L215-220) — consistent convention. |
| auth T-304 pre-submit clean (auth.test.jsx:185-199) | Yes: before submit, neither field has `aria-invalid=true` nor `aria-describedby` | N/A by design (negative pin): passes pre-fix too — it pins "no regression into initial render", not the fix | Yes: `renderApp`, sync fireEvent, no timers (see §4) | No | Complements failed-submit pin; guards the `undefined` omission behavior in AuthView.jsx:67-68,79-80 [VERIFIED]. Self-check L197-198 (bare input has no attr). |
| auth T-304 failed-submit (auth.test.jsx:201-232) | Yes — all three brief criteria verbatim: `aria-invalid="true"` on **both** fields (L225), `aria-describedby` equals alert's id (L226), `document.getElementById(describedby) === alert` (L228) | Yes: removing attrs from AuthView makes L225-226 fail (unrendered attr ≠ 'true'); removing `id="auth-error"` fails L220 (`toBeTruthy`) | Yes: `findByRole('alert')` is query-wait, not a timer/sleep; `vi.useRealTimers()` [VERIFIED L8] | No | Real `<AuthView/>` rendered via `renderApp`; only `fetch` is faked at the network boundary (helpers.jsx), which is the correct seam. No vi.mock of the component. See §4. |

## 2. Coverage of changed lines/branches, error paths, boundaries
- T-301: presence + placement (order) covered; full data-URI payload not asserted — appropriate (presence is the contract; exact SVG bytes would be brittle). No rendered-browser check in this review's scope (impl §7 honestly marked Playwright NOT-RUN; jsdom+static+build is the agreed acceptance for this surface per plan L31).
- T-302: all three claims pinned independently (emoji / h3 scale / h1 scale) — a partial revert fails exactly one test. Boundary: global h3/h1 scales themselves are pre-existing T-101 territory, unchanged here; not re-pinned, correctly.
- T-303: title and wrap each pinned; `title={JSON.stringify(event.detail)}` literal matches AuthView/AdminScreen wiring [VERIFIED AdminScreen per impl §5; `grep file:btn` side-check not in scope]. Empty-detail branch (guard `Object.keys...length`) is pre-existing code — unchanged, correctly untested by new tests.
- T-304: both branches of the `error ? ... : undefined` ternary covered (clean test = undefined branch, failed-submit = true branch) [VERIFIED AuthView.jsx:67-68,79-80]. Both input fields covered (loop over username+password). Register-mode branch of AuthView (minLength/autocomplete/hint) is pre-existing; aria attrs are shared code, so login-mode coverage exercises the same lines. Error-text variants (409/429/network) funnel through the same `error` state → same attrs; single network-failure trigger is sufficient for the attr contract.
- No changed behavior lacks a test: all 7 changed files' behavioral deltas are pinned; `git show --name-only` matches impl's file list.

## 3. Mutation thinking
| Plausible bug | Caught? | By which test |
|---|---|---|
| Icon link present but added after init script (order regression) | Yes | T-301 `iconIdx < initIdx` (L552) |
| Emoji dropped but `text-lg` kept on h3 (or vice versa) | Yes | T-302 h3: independent `not.toContain('text-lg')` and `not.toContain(emoji)` asserts |
| Admin h1 bare but gains a new `text-...` override | Partially | T-302 h1 pins the three known overrides; a *new* override class (e.g. `text-xl`) would not be caught — accepted: pin matches the known defect, not an exhaustive allow-list. NIT below. |
| `title=` added to wrong div / wrap added to wrong selector | Yes | T-303 element/selector-scoped regexes |
| `aria-describedby` points at a non-existent id | Yes | failed-submit L226 equality + L228 `getElementById === alert` |
| Only username marked invalid (over-narrowing) | Yes | Loop asserts both fields (L224-229) |
| `aria-invalid="false"` rendered on error | Yes | `toHaveAttribute('aria-invalid','true')` |
| Attrs leak into initial render (e.g. `aria-invalid={false}` always rendered) | Yes | Pre-submit clean test (L192-195) |
| Alert `id` removed but attrs kept | Yes | L220 `toBeTruthy` on alert id; L228 would also fail |
| h3 regex breakage if JSX reformats to single quotes / multiline | N/A (escape, not bug-catch) | `[^>]*` tolerant of attribute order but not single quotes — see MINOR `TREV-W1-IMPL-01-01` |

Mutation survivors: 0 true escapes of the 8 plausible bugs above. One brittleness item (single-quote JSX would fail the h3/h1/truncate regexes) is a false-negative risk on future refactors, not a survivor that lets a bug through.

## 4. Flakiness evidence (repeated runs) and test-suite health
- One scoped run green: 51/51 [RAN]. No repeats (no flakiness signal; scope rule). Static suite: pure sync fs reads, sorted `readJsxFiles` traversal [VERIFIED static.test.js:22-36] — deterministic ordering, no clock. Auth suite: `beforeEach`/`afterEach` clear localStorage + hash + `cleanup()` + `backend.restore()` [VERIFIED auth.test.jsx:7-20]; `vi.useRealTimers()` both ends (L8, L19) — no fake-timer hangs. `submitLogin` uses `fireEvent` (sync) and `findByRole` (polling wait bounded by Testing Library defaults, not a hand-rolled sleep) — no timer/sleep/retry masking [STANDING-ORDERS §7 clean]. No shared state between the 8 new tests beyond module-level source strings (immutable). Suite health: 43 static + 8 auth in 9.92s wall (mostly environment setup) — no slowness concern. Order-dependence: none observed.
- Reversal reasonableness (impl §7 "7 failed, 44 passed"): arithmetic checks out — current total is 51 = 43 static + 8 auth [RAN]. Baseline before the 8 additions must therefore be 44 = 37 old static + 7 old auth. Pre-fix failures claimed: 6 static new + 1 auth (failed-submit) = 7; the pre-submit clean test passes pre-fix vacuously, so exactly 7 of 8 new tests fail pre-fix and all 44 old tests pass — internally consistent. Each in-test self-check literal (pre-fix strings constructed inline, e.g. static.test.js:573,584,594,601; auth.test.jsx:197-198) independently demonstrates its pin fails on the old form. Classified as *reasoned*, not demonstrated (read-only brief), hence the digest split "pass-after confirmed by run / fail-before reasoned".

## 5. Findings
- No BLOCKER/MAJOR. Two MINOR + one NIT, none blocking:
  - `TREV-W1-IMPL-01-01` (MINOR, brittleness) `frontend/tests/static.test.js:567,578,590` — h3/h1/truncate regexes assume double-quoted `className="...">` on one line. A future refactor to single quotes or multiline JSX would fail these pins spuriously. Recommended: no change now (tests match current code style, which is uniformly double-quoted); if it ever trips, widen to `[^>]` already-helpful — e.g. match `<h3[^>]*>` then assert on the slice. Not actionable this wave.
  - `TREV-W1-IMPL-01-02` (MINOR, coverage gap, P2) — register-mode failed submit not exercised; attrs are mode-independent shared code (AuthView.jsx:67-68 applies regardless of `registering`), so risk is minimal. Optional follow-up sketch: duplicate failed-submit test with `fireEvent.click(getByRole('button',{name:/create an account/i}))` first, then submit, assert same attrs. Deferrable.
  - `TREV-W1-IMPL-01-03` (NIT) `frontend/tests/static.test.js:576-585` — Admin h1 pin forbids the 3 known overrides but not arbitrary new ones; `toContain('<h1>Admin</h1>')` already enforces bareness strictly (any class attr breaks it), so this is belt-and-braces — no defect.

## 6. Missing edge cases and tests (prioritized)
- P1: none. All T-301..T-304 deltas are pinned with reversal tripwires.
- P2: register-mode failed-submit attr pin (see finding -02). Scenario: register with `fail: {'/api/v1/register': {status:409, detail:'Username already taken...'}}` → same aria-invalid/describedby assertions. Where: `frontend/tests/auth.test.jsx`, new `it` in the T-304 describe. Sketch: render app, click "Create an account" toggle, fill fields, submit, `findByRole('alert')`, reuse L222-229 loop verbatim.
- P3: (a) error→success transition clears attrs: after a failed submit, fix backend and resubmit successfully → fields no longer `aria-invalid=true`. (b) `sessionNotice` (role=status) does not trigger aria-invalid: render with a session notice, assert no attrs. Both are pure consequences of `error ? ... : undefined` [VERIFIED AuthView.jsx:67-68] and lower-risk than P2; nice-to-have hardening only.
- Categories considered and correctly out of scope: unicode/oversized/hostile input (no input handling changed), concurrency (no async change), authz (no token change), clock/timezone (none), backward compat (additive attrs only; `undefined` omission keeps initial DOM identical — pre-submit test pins this).

## 7. What I could not verify
- Actual pre-fix failure run (7 failed/44 passed): read-only brief forbids reverting source; verified by arithmetic + in-test self-check literals only (reasoned, §4). Would require a scratch worktree revert of `f53e4ba`'s source files — deliberately not done.
- Rendered-browser behavior (favicon 404 gone in real browser, AT announcement of the describedby association, dark/light contrast): no Playwright MCP in this review session (matching impl §7's honest NOT-RUN); jsdom + static ratio guards (T-101, still green in this run) are the accepted proxy per plan L31.
- Full suite (154→162) and build: out of scope per STANDING-ORDERS §16 scoped-run rule; impl's full-run numbers (§7/§11) are plausible but unverified by me.
- The both-fields semantic choice (409 marks password too): a product/a11y judgment flagged by impl §15; the test faithfully pins the implemented behavior (`for both fields`), so there is no test/impl mismatch. Whether the semantics should narrow is for ORCH/product, not a test defect.
