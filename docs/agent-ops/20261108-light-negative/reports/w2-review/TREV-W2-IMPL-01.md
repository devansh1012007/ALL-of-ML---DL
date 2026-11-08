<!-- ORCH-DIGEST:START -->
agent: W2-TREV-01 | scope: wave 2 / T-101 test review | verdict: APPROVE-WITH-CHANGES
tests_reviewed: 19 (theme.test.jsx) + 9 (static.test.js T-101 additive; 34 total in file) | fail-before/pass-after confirmed: 3 (scoped runs + 3x repeat green, ratio recompute) / reasoned: 4 (block deletion, near-white swap, no-toggle, unguarded storage/matchMedia) / not-possible: 0
findings: BLOCKER 0 | MAJOR 1 | MINOR 3 | NIT 2
flaky_suspects: none
missing_edge_cases: P1 0 | P2 3 | P3 3
mutation_survivors: 3 of 18 plausible (init-parity, applyTheme-raw, whitespace/matchMedia-throw pins)
changed_behavior_without_tests: index.html pre-paint init script; views/NewJob.jsx text-warn swap
confidence: high (blind pass + independent WCAG recompute + 3x stable scoped runs; full suite/build out of scope by brief)
<!-- ORCH-DIGEST:END -->

# Test quality review — W2-TREV-01

Blind pass first (theme.test.jsx full + static.test.js T-101 guards + components/theme.jsx), then implementation-report audit. Scope strictly read-only; scoped vitest only per brief.

## 0. Method (temporary worktree used? repeat counts, coverage tooling)

No worktree (read-only brief). Blind reading in brief order: STANDING-ORDERS, review-tests template, W2-IMPL-01 brief (test requirements §3.7), then theme.test.jsx (268 lines), static.test.js T-101 sections (lines 320-492), theme.jsx, styles.css, helpers.jsx teardown, App/NewJob/index.html spot checks. Only after blind pass read W2-IMPL-01-T-101.md claims (§7/§11).

Scoped runs recorded verbatim (branch frontend-ui-round2, HEAD 29eace8):
- [RAN cd frontend; npx vitest run tests/theme.test.jsx] -> 19/19 passed (242ms) [VERIFIED]
- [RAN npx vitest run tests/static.test.js] -> 34/34 passed (15ms) [VERIFIED]
- Repeat: theme.test.jsx twice more -> 19/19 (182ms, 187ms); static.test.js once more -> 34/34. No failures across 3x. [RAN]
- Independent WCAG recompute via node from styles.css light literals: faint/raised 4.85, accent/canvas 6.41, accent-ink/accent 6.70, badge ok/canvas-composite 5.18, confusion strong@0.52 7.05, near-white fails ~1.0-1.18. Matches guard thresholds; guards are live math, not presence theater. [RAN]
- No coverage tooling available/used (no coverage config in frontend); assessment is by line/branch reasoning against theme.jsx + styles.css. Full suite/build NOT run (ORCH gate owns per brief).

COMMS last line read: docs/agent-ops/20261108-light-negative/COMMS.md (Log header only, no entries).

## 1. Per test/suite assessment

| Test | Asserts behavior? | Fails without fix? | Deterministic/isolated? | Over-mocked? | Notes |
|---|---|---|---|---|---|
| resolution: stored light beats system dark | Yes — strict `toBe('light')` | Yes — inverted order returns dark | Yes — storage + stubMatchMedia(false) per test | No — real resolveTheme | allow-list priority pinned |
| resolution: stored dark beats system light | Yes | Yes — inverted order returns light | Yes | No | symmetric pin |
| resolution: absent + system light -> light | Yes | Yes — wrong default fails | Yes | No | |
| resolution: absent + system dark -> dark | Yes | Yes | Yes | No | |
| resolution: absent + matchMedia absent -> dark | Yes | Yes — unguarded `matchMedia(...)` throws TypeError, test expects dark+no throw | Yes — `delete window.matchMedia` + typeof guard asserted | No | jsdom lacks matchMedia; stub only where needed is correct |
| resolution: App mount applies stored light (attr+meta+storage+toggle label/aria) | Yes — dataset.theme, meta content, storage key, label "Switch to dark mode", aria-pressed true | Yes — pre-fix App never sets attribute; impl hand-revert showed 6 failures [claim audited, mechanism verified] | Yes — beforeEach clears+ensureMeta; afterEach cleans | No — real renderApp/App | integration, not unit theater |
| hostile xss / 10KB / unicode / empty / LIGHT (5 separate its) | Yes — resolveTheme dark + dataset==dark + dataset!=raw + script count unchanged + no `[data-hostile]` script | Yes — case-insensitive or raw-passthrough impl returns hostile/light; XSS dataset check fails | Yes | No | strong: 5 case variants incl. case ("LIGHT") and 10KB; see §3 for raw-applyTheme gap |
| hostile toggle integration (mount dark, click -> light, 0 scripts) | Yes — end-to-end recovery | Yes — mount would be hostile/light or crash | Yes | No | proves hostile does not wedge toggle |
| throw: resolveTheme dark when getItem throws (system light=true) | Yes — not.toThrow + dark | Yes — unguarded getItem throws before matchMedia; also strict-dark pin (fall-through-to-system would give light and fail) | Yes — stubThrowingStorage wrapper | No — stubGlobal seam necessary (jsdom Storage prototype not spyable; comment at theme.test.jsx:46-49 accurate) | key test design: light system isolates storage-guard |
| throw: applyTheme flips attr+meta when setItem throws | Yes — dataset light + meta light + not.toThrow | Yes — unguarded setItem throws after attribute set; expect-not-toThrow fails | Yes | No | pins "write throw still flips in-memory" |
| throw: toggle flips in-memory when setItem throws | Yes — click not.toThrow + attr/meta light | Yes — same as above via UI path | Yes — stub installed AFTER mount so mount write succeeds, click write is denied (correct sequencing) | No | |
| toggle header flips attr+meta+storage both directions | Yes — both clicks, label/action semantics (light->"Switch to dark"), aria-pressed false->true, `nav.contains(toggle)===false` | Yes — no toggle -> getByRole fails; split-brain (attr only) -> meta/storage asserts fail | Yes | No | most complete test in file; double-flip proves idempotent round-trip |
| toggle sign-in + persistence across remount | Yes — AuthView toggle, click->light+stored, teardown+remount keeps light attr+meta | Yes — no AuthView toggle -> getByRole fails; unstored -> remount dark | Yes — explicit teardown + ensureMeta before remount | No | persistence claim proven, not just existence |
| toggle sign-out does NOT clear prime_theme | Yes — after sign-out: key still light, dataset light, AuthView toggle "Switch to dark"/pressed | Yes — if logout cleared key, asserts fail | Yes | No | pins intentional non-clear (App logout only removes prime_token) |
| toggleTheme pure flip (incl DOM fallback) | Yes — dark->light, light->dark, dataset-light->dark | Yes — inverted flip fails | Yes | No | unit, no DOM mount needed |
| static T-101 structural (14 names + color-scheme light) | Yes — per-name `--name:` loop + block non-null + color-scheme | Yes — deleted block -> extract null -> assertion fails; missing name -> per-name fails | Yes — pure file read | No | genuine structural pin |
| static T-101 dark-invariance (14 :root == 85acdda literals + color-scheme dark) | Yes — `toEqual` per token on parsed triples, all 14 | Yes — any :root drift or missing token -> null/unequal fails | Yes | No | parse regex (`--name: \d+ \d+ \d+`) matches styles.css format; fail-closed on missing (null -> ratioOf throws) |
| static T-101 ratios (7 it: body, accent-dual, ok/warn/bad, boundaries, badge, confusion, washed) | Yes — live WCAG luminance from parsed light triples vs ≥4.5 / ≥3 thresholds; composites via alpha blend | Yes — near-white swap -> ~1.0 fails ≥4.5; deleted block -> parse crash (fail-closed) | Yes — no timers/DOM | No | genuinely computes: independent recompute confirmed (faint/raised 4.85 is the tight tripwire). See §3 |

Overall: 19 theme tests all assert observable behavior (resolved token, DOM triple agreement, storage value, label/aria, nav exclusion, script absence), not mocks of the unit under test. matchMedia/localStorage/fetch are the only stubs, all justified. No test merely asserts a toggle exists without flipping it — every toggle test clicks and asserts post-click state.

## 2. Coverage of changed lines/branches, error paths, boundaries

Against components/theme.jsx (77 lines):
- `resolveTheme` 3 branches: stored-hit [theme.test.jsx:89-99], system-hit [101-109], absent-no-matchMedia fallthrough [111-115], storage-throw early-dark [175-180]. `matchMedia` THROW branch (theme.jsx:27-29) has no dedicated test — P2 (see finding R-W2-02). No-whitespace-string branch (e.g. `" light "`) falls through via strict `===` but no test pins it — P2 (R-W2-03).
- `applyTheme` branches: light/dark normalization [34-36] only exercised with already-resolved tokens (hostile test passes `resolveTheme()` output, never raw hostile); meta-create-if-absent [39-43] exercised via ensureMeta/create path in jsdom; storage write + write-throw [45-51] covered both ways. Raw-garbage-to-applyTheme normalization unpinned — survivor (R-W2-04).
- `toggleTheme` pure flip + DOM-read fallback: both covered [262-267].
- `ThemeToggle` labels + aria-pressed: covered in light AND dark states [128-130, 207-219, 230-234, 257-259].

Against static guards:
- Structural/dark-invariance: all 14 names + color-scheme both blocks. Boundary: regex requires `[data-theme="light"]` double-quote form; single-quote variant would fail extract (strict, acceptable). No test asserts `:root` has NO extra tokens — extra token drift survives (intentional? design pins "exactly 14"; guard pins presence, not absence of extras — MINOR, see R-W2-05).
- Ratios: body matrix 4 fg × 3 bg, accent dual, status × canvas/surface, rule/fill ≥3, badge α0.1 × 2, confusion α0.52+0.12 × 3, tags α0.15 × 2 + selection α0.35. `raised` as foreground (raised/canvas 1.18) correctly absent — accepted non-text exception; no in-file comment documents the exclusion (doc lives in design record/impl report). Test author should add one-line comment to prevent future "fix" (NIT R-W2-06).
- Boundaries/error paths: hostile set covers XSS (quote/script), 10KB (oversized), unicode-emoji ×64 (encoding), empty, case-variant — matches brief list exactly. What it lacks: whitespace-padded valid token, string "null", and very-long single-token (10KB covers length for invalid tokens but not for near-miss like 10KB+'light'? same strict-=== path, covered by class, P3).

Isolation hygiene verified: beforeEach clears localStorage + hash + dataset.theme + ensureMeta (meta reset to dark) [67-73]; afterEach teardownApp + removes prime_token AND prime_theme + deletes dataset.theme + unstubAllGlobals + restoreAllMocks + delete matchMedia [75-86]. helpers.jsx teardown removes only prime_token [1054-1063], so the extra prime_theme cleanup is necessary and present. No cross-file pollution: vitest file isolation + per-test stubs; 3x runs stable.

## 3. Mutation thinking

| Plausible bug (off-by-one, inverted condition, missing await, dropped error, wrong default, …) | Caught? | By which test |
|---|---|---|
| Inverted resolution order (system beats stored) | Caught | stored-beats-system both directions |
| Case-insensitive stored compare ("LIGHT"->light) | Caught | hostile "LIGHT" expects dark |
| Raw hostile passthrough (resolve returns raw / dataset=raw) | Caught | hostile dataset!=raw + resolve dark |
| matchMedia absent unguarded (throws) | Caught | absent+no-matchMedia expects dark |
| Storage READ unguarded (throws out of render) | Caught | throw-getItem test (system-light isolates guard) |
| Storage WRITE unguarded (throws, no in-memory flip) | Caught | throw-setItem apply + toggle tests |
| applyTheme forgets meta / forgets storage / split-brain | Caught | toggle triple-agreement asserts (both directions) |
| Toggle label inverted / aria-pressed inverted / toggle inside <nav> | Caught | label+aria asserts + `nav.contains===false` |
| Sign-out clears prime_theme (existing logout "fixed" wrongly) | Caught | sign-out persistence test |
| Light block deleted (all tokens) | Caught (fail-closed) | structural non-null + ratio parse crash on null block |
| One light value swapped to near-white (fg) | Caught | fg/canvas ratio ~1.0 <<4.5; confirmed by independent recompute (faint 250,250,250/raised = 1.18) |
| Dark :root drift by 1 LSB on any token | Caught | dark-invariance exact `toEqual` vs literals |
| Ratio threshold weakened (4.5->3.0) / presence-only check | Would survive | threshold literals in file; no threshold-pinning meta-test — accepts as human-read risk (NIT) |
| matchMedia THROWS (typeof ok, call throws) -> uncaught | NOT caught | fallthrough catch at theme.jsx:27-29 has no throw-stub test (R-W2-02) |
| applyTheme(raw hostile) assigns raw into dataset (no normalization) | NOT caught | hostile test only feeds resolved token to applyTheme (R-W2-04) |
| init script in index.html drifts (wrong key / missing guard / sets only attr) | NOT caught | no vitest executes index.html script; probe-only (R-W2-01, MAJOR) |
| NewJob reverts to text-orange-400 | NOT caught | no test pins tokenized warn (R-W2-01) |
| Whitespace-padded " light " wrongly trimmed to light | NOT caught | no whitespace test; strict-=== is correct-by-implementation but unpinned (R-W2-03) |

Mutation survivors: 3 substantive (+ threshold-weakening as process risk). Rest of matrix survives strongly with small margins (faint/raised 4.85, badge-warn/surface 4.68) — guards are deliberately near the threshold tripwire, which is good.

Reversal answers (brief §3, reasoned + traced):
- Light block deleted -> static.test.js FAILS: structural `expect(block).not.toBeNull()` fails; ratio describe also crashes in `parseTriples(null)` at collect time (fail-closed, not a pass). Verified by code trace; not executed (read-only).
- One value near-white -> ratio FAILS: WCAG ratio ~1.0 vs 4.5 threshold; independently recomputed [RAN node -> 1.00/1.18].
- Toggle removed from App -> theme.test.jsx FAILS: `getByRole button /switch to (light|dark) mode/` not found + `dataset.theme` undefined; impl hand-revert reported exactly 6 such failures (claims audit: mechanism matches, count plausible).
- resolveTheme unguarded matchMedia/storage -> theme.test.jsx FAILS: absent-matchMedia test throws TypeError; throw-getItem test `not.toThrow()` fails. Both pinned.

Long-run test (STANDING-ORDERS §8):
- Source: client-only O(1) writes per toggle (attribute+meta+storage), no network/timers/listeners [VERIFIED theme.jsx:34-53].
- Load 100x/concurrency: idempotent same-token writes; no accumulation; double-flip test proves round-trip. No race (single-threaded DOM writes).
- Hostile input: allow-list (`=== 'light'/'dark'` only) + resolved-token property assignment, never innerHTML/HTML parsing [VERIFIED theme.jsx:19,37; grep zero per impl §6, theme.jsx clean]. 10KB/unicode/XSS handled as opaque fallthrough; cost O(1) (no regex on stored value).
- Operability: triple agreement (dataset/meta/storage) is the observable; rollback = revert 3 mechanisms, keys inert. Deviation: if storage write is denied mid-toggle, in-memory and storage diverge until reload — tested and intended (test pins in-memory flip), but no test pins reload-after-denied-write behavior (falls back to default/system). P3.
- Reversal: see table above; suite fails without fix for every pinned mechanism.

## 4. Flakiness evidence (repeated runs) and test-suite health (slow, order-dependent, shared state)

- [RAN theme x3, static x2] -> all green, stable durations (theme ~180-240ms, static ~15ms). No flake observed. [VERIFIED]
- No sleeps/retries/timeouts; real timers (`vi.useRealTimers` in both hooks prevents fake-timer bleed); fetch fake via helpers (no real network). No wall-clock dependence (no Date assertions).
- Shared-state risk: meta element persists across tests in-file (ensureMeta creates once); beforeEach resets content to dark so no leakage. localStorage cleared per test; dataset.theme deleted per test; matchMedia deleted in afterEach so tests that don't stub start from jsdom default — deterministic, but order-dependent if a test ever fails to clean (afterEach runs even on failure, so safe).
- Suite health: theme.test.jsx 19 tests in ~200ms — fast, no polling wait (toggle is synchronous DOM+storage, no fetch dependency for assertions). Not run: full suite/build (gate-owned). Known pre-existing runs.test.jsx Progress-poll flake cited in impl brief does not affect this file (no polling assertions here).

## 5. Findings (R-W<N>-nnn, severity, location, evidence, recommended fix)

R-W2-01 | MAJOR | frontend/index.html:6-26 (pre-paint init) + frontend/views/NewJob.jsx:678 (`text-warn`) | No automated test covers the init script parity (key `prime_theme`, allow-list, matchMedia guard, single-resolution, both writes) or the NewJob tokenization. The init script duplicates theme.jsx logic as a second source of truth; drift (e.g. missing matchMedia guard -> throw leaves page unthemed but React later corrects, causing flash; wrong key -> stored pref ignored on first paint) would pass all 53 scoped tests and only the manual probe would catch it. Evidence: theme.test.jsx/static.test.js contain zero index.html/NewJob references [VERIFIED by grep this review]. Recommended fix (scoped, no prod change): add a static.test.js guard that reads index.html and asserts: script precedes module entry, references `prime_theme`, contains allow-list check, `typeof window.matchMedia` guard, sets `dataset.theme` + meta content from one `resolved` var, single outer try/catch; and asserts NewJob.jsx contains `text-warn` and not `text-orange-400`. Alternatively execute the init script body in jsdom as a unit. Blocker? No — spec §5 accepts the production-build probe for no-flash, and impl probe recorded first-paint checks; but as test reviewer this is the single largest unpinned surface.

R-W2-02 | MINOR (P2) | frontend/components/theme.jsx:22-29 vs tests/theme.test.jsx (no matchMedia-throw test) | `matchMedia` throw path (typeof ok but call throws -> catch -> dark) is implemented but untested. Absent-matchMedia is tested [111-115]; throwing-matchMedia is a different branch. Recommended fix: one test stubbing `window.matchMedia = () => { throw new Error('mq denied') }` with absent storage, expect dark + not.toThrow.

R-W2-03 | MINOR (P2) | tests/theme.test.jsx:134-140 hostile array | Whitespace-padded valid tokens (`" light "`, `"dark "`) and literal string `"null"` are not in the hostile matrix. Implementation is strict `===` so they correctly fall through, but the pin is missing; a future "helpful trim" would silently change behavior. Recommended fix: add `['padded light',' light ']` and `['string null','null']` entries (same fallthrough asserts).

R-W2-04 | MINOR (P2) | tests/theme.test.jsx:143-157 hostile loop | Hostile tests never feed the RAW hostile value to `applyTheme`; they feed `resolveTheme()` output. A regression that removes applyTheme's normalization (`theme === 'light' ? ...`) while keeping resolveTheme correct would survive (App always passes resolved tokens today, so production impact is latent defense-in-depth, not current bug). Recommended fix: add one test `applyTheme('"><script>…')` expecting dataset `dark` + no new script.

R-W2-05 | NIT | tests/static.test.js:374-399 dark-invariance | Guard pins presence + exact values of the 14 names but not absence of a 15th rogue token in `:root` or `[data-theme="light"]`. "Exactly 14" from the brief could be enforced by counting `--*:` declarations in each block == 14. Non-blocking (extra token would need a consumer to matter).

R-W2-06 | NIT | tests/static.test.js:402-492 ratio section | raised/canvas 1.18 non-text exception is correctly excluded but not documented in-file; a future reader may "fix" the missing assertion. Add a one-line comment referencing the design D2 §2.4a exception. Also impl report count says "+8" guards while the file actually adds 9 `it`s (structural 1 + invariance 1 + ratios 7) — doc-count error only; test run confirms 34 total [VERIFIED].

No BLOCKER. Nothing here weakens the core fail-before/pass-after claim.

## 6. Missing edge cases and tests (prioritized)

P1 (must add): none — all brief §3 pinned behaviors (resolution order, hostile set, storage throw, toggle triple agreement + sign-out survival, ratio/structure/invariance) are covered.

P2 (should add):
- P2-1 Init parity static guard (R-W2-01): input table index.html text (valid init / missing guard / wrong key / meta-after-script order); expected single-resolution + dual-write + try/catch. Sketch above in R-W2-01.
- P2-2 matchMedia-throws test (R-W2-02): stub throwing matchMedia, absent storage -> dark, not.toThrow.
- P2-3 Whitespace/"null" hostile entries (R-W2-03): `" light "` / `"null"` -> dark.

P3 (nice to have):
- P3-1 applyTheme-raw normalization test (R-W2-04).
- P3-2 Exactly-14 token count guard (R-W2-05); threshold-weakening meta-pin (optional).
- P3-3 Reload-after-denied-write: after setItem throws + successful in-memory flip, remount resolves system/default (storage still empty) — documents the intended divergence window.
- P3-4 NewJob `text-warn` pin (folded into P2-1 static guard; standalone P3 if ORCH splits it).

## 7. What I could not verify

- Full suite / production build / browser probe (scoped-only brief; ORCH gate owns). In particular no-flash first-paint, track width at 390px, and 7-view parity rely on impl probe record (W2-IMPL-01 §11), not independently re-run here.
- "Fail-before" by re-running theme/static tests against pre-fix tree (read-only + no destructive revert); reversal is reasoned from code traces + independently recomputed ratios + impl hand-revert report (6 failures, consistent with getByRole/dataset assertions). Counts as reasoned, not demonstrated.
- jsdom-storage-shim claim (`vi.spyOn` cannot shadow Storage) taken from impl notes + test comment; stubGlobal seam verified working by green throw tests [RAN], but the spyOn failure itself not re-demonstrated.
- Backend pytest untouched (frontend-only change; not run).

---
Verdict rationale: APPROVE-WITH-CHANGES (no BLOCKER; one MAJOR coverage gap for init-script parity + NewJob pin, plus three P2 alignment tests). The test side itself is behavior-proving, deterministic, isolated, and genuinely computes contrast — the core failure modes named in the brief (presence-only ratio theater, toggle-exists-but-never-flips) are avoided and reversal-confirmed. Recommend adding the P2 items in a follow-up without delaying merge of the verified theme/static guards; if ORCH requires P1, it may promote R-W2-01 static guard to pre-merge (cheap, additive-only).
