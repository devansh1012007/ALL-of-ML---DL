<!-- ORCH-DIGEST:START -->
agent: W2-REV-01 | scope: wave2/T-101 commit 21f65c13 | verdict: APPROVE-WITH-CHANGES
findings: BLOCKER 0 | MAJOR 0 | MINOR 1 | NIT 2
claims_audit: 16 / 2
band_aids_found: none
top_3_risks: probe screenshots described-only, none persisted in repo; 4.85:1 faint/raised margin is thin but tripwired; inline init script has no automated test (probe-only coverage)
optimizations: DO-NOW 0 | DO-LATER 0 | NOT-WORTH-IT 2
reversal_check: reasoned-only (scoped checks only per brief; full suite/build owned by ORCH gate)
confidence: high (<why: 14/14 triples compared verbatim, :root byte-identity proven by script, 8/8 sampled ratios recomputed matching design, §5.5 greps re-run independently>)
<!-- ORCH-DIGEST:END -->

# Code review — W2-REV-01 (W2-IMPL-01 / T-101 light mode)

## 0. Method
- Diff range: `git show 21f65c13` (code commit; 9 files, +597/-5). Current branch `frontend-ui-round2` verified `[RAN git branch --show-current -> frontend-ui-round2]`.
- Files read in context (blind pass FIRST, before design/spec/report): `frontend/styles.css`, `frontend/index.html`, `frontend/components/theme.jsx`, `frontend/App.jsx`, `frontend/views/AuthView.jsx`, `frontend/views/NewJob.jsx:678`, plus `git show` of `tests/theme.test.jsx` + `tests/static.test.js`.
- THEN read (claims audit phase): design record `reports/w2-impl/W2-DEEP-01-T-101.md` (D1-D7), spec `docs/plans/2026-11-08-light-mode.md` §§4-5, implementation report `reports/w2-impl/W2-IMPL-01-T-101.md`.
- Commands (all read-only/scoped): `git show`, `git diff 21f65c13^..21f65c13`, python re-computations and greps. No vitest/build run (brief §4: ORCH gate owns full suite/build). Test/build results below are therefore impl-reported, not reviewer-verified.
- Order followed: blind pass (§1) recorded before reading the implementer report; claims audit (§2) after.

## 1. Blind-pass findings (before reading implementer reports)
Recorded from the diff + shipped files only, before opening the design/impl reports:
1. `styles.css` adds exactly one block `[data-theme="light"]` with 14 triples + `color-scheme: light`; `git diff` shows the addition only (no `:root` hunk) — dark invariance looks structurally sound.
2. `index.html` head init: single `try/catch`, one resolution setting both `dataset.theme` and meta `content`; the `catch (_) {}` is total silence — noted as a possible error-swallowing risk, but the single-outer-try shape matches a pre-paint must-never-throw contract, and any divergence self-heals on React mount (App effect re-applies). Meta sits BEFORE the script (required for `querySelector` to find it); viewport meta moved below the script (harmless).
3. `theme.jsx` allow-lists everywhere: `resolveTheme` strict `===` checks, `applyTheme` coerces non-light to dark, constant-only `querySelector('meta[name="color-scheme"]')`, no `innerHTML`/selector writes in the diff. One wrinkle: `toggleTheme()` reads `documentElement.dataset.theme` when called without an argument — an impure fallback (App always passes state, so currently dead). NIT.
4. `App.jsx` theme state at `App` level, `useEffect` → `applyTheme` single writer; toggle at line 159 inside the `ml-auto` div (nav closes at line 148) — outside `<nav>` as required. Same `ThemeToggle` component in both shells, so identical labels/`aria-pressed` by construction.
5. `NewJob.jsx:678`: `text-orange-400` removed, both non-high branches now `text-warn` — makes the `medium ? ... : ...` ternary a dead branch (both arms identical). Logically fine (the point is "not high → warn"), stylistically redundant. NIT.
6. No `dark:`, no added hex, no `bg-white`/`text-black`/gradient utilities in the shipped additions (verified by grep in §2). `RunDetails.jsx`/`tailwind.config.js` absent from the stat.
7. No automated test covers the inline head-init script itself (jsdom never executes `index.html`); its coverage is probe-based. Accepted by design, but worth stating.
8. Test-seam note: `theme.test.jsx` replaces storage via `vi.stubGlobal` rather than `vi.spyOn` — the report later explains jsdom Storage methods are not shadowable, consistent with the code.

## 2. Claims audit
| # | Implementer claim | Verified? | Evidence / finding |
|---|---|---|---|
| 1 | Light block = exactly the 14 D2 §2.1 triples + `color-scheme: light` | YES | `[VERIFIED frontend/styles.css:37-53]` vs design §2.1 table, token-by-token: 248 250 252 / 241 245 249 / 226 232 240 / 120 138 165 / 15 23 42 / 30 41 59 / 60 74 95 / 86 100 124 / 29 78 216 / 30 64 175 / 255 255 255 / 4 110 80 / 165 73 10 / 185 28 28. Reviewer recomputed 8 ratios from shipped triples: faint/raised 4.85, warn/canvas 5.64, accent-ink/accent 6.70, accent/canvas 6.41, rule/canvas 3.36, ok/canvas 5.99, strong/canvas 17.06, raised/canvas 1.18 — 8/8 MATCH design §2.2 (rounded to 2dp). |
| 2 | `:root` 14 dark triples byte-identical to 85acdda | YES | `[RAN python: git show parent vs child :root block -> ROOT_BYTE_IDENTICAL True]`; `git diff` numstat for styles.css is +22/-0 (pure addition). |
| 3 | Head init: in `<head>`, one outer try/catch, sets attribute+meta from one resolution, matchMedia/storage guarded | YES | `[VERIFIED frontend/index.html:5-26]`: meta at :5, one `try{...}catch(_){}` at :10-25, `typeof window.matchMedia === 'function'` at :16, storage read inside try at :11, both writes from `resolved` at :21-24. Also before the module entry (:32). Satisfies spec §4.4. |
| 4 | `theme.jsx`: allow-list only, no innerHTML/selector sinks, storage write in try/catch with in-memory flip, matchMedia guard, `resolveTheme` side-effect-free | YES | `[VERIFIED frontend/components/theme.jsx:10-77]`: strict `===` at :19, typeof guard :22, read-try :12-18, coerced write path :36-44, storage-try :45-51, `resolveTheme` performs reads only (no writes). Grep of the full diff: `innerHTML` 0 occurrences. |
| 5 | State in `App`; `applyTheme` single writer; toggle outside `<nav>`; identical labels/aria in both shells | YES | `[VERIFIED frontend/App.jsx:182-192]` state + effect; `:159` toggle in `ml-auto` cluster, nav closed at :148; `[VERIFIED frontend/views/AuthView.jsx:54]` same component; labels "Switch to light/dark mode" + `aria-pressed` iff light in `theme.jsx:64-77`. |
| 6 | `NewJob.jsx:678` → `text-warn`; zero new hex/`dark:`/palette utilities in shipped files | YES | `[VERIFIED frontend/views/NewJob.jsx:678]` exact line; `[RAN python grep over frontend/**/*.jsx,*.js (tests excluded): dark: [] files, hex [] files, palette-ish only prose 'to-' in AuthView/NewJob/dist]`. Spec §5.5 greps re-run independently: clean (prose `to-` confirmed as English false positives, matching impl §6). |
| 7 | `RunDetails.jsx` + `tailwind.config.js` untouched | YES | `[RAN git diff 21f65c13^..21f65c13 -- frontend/views/RunDetails.jsx frontend/tailwind.config.js -> empty]`; numstat = 9 files, exactly write-set + tech-debt. |
| 8 | `theme.test.jsx`: 19 tests (resolution/hostile/throw/toggle) + afterEach cleanup | YES (by source; NOT-RUN by reviewer) | Source contains 15 `it(` calls, one looped over 5 hostile values = 19 executed: resolution 6, hostile 5+1, throw 3, toggle 4. afterEach removes `prime_theme` + `dataset.theme`. Test bodies read and consistent with the guards (e.g. storage-throw-with-system-light proves a real guard). |
| 9 | `static.test.js`: structural + dark-invariance + ratio guards (incl. accent-ink dual, badge composites), raised/canvas excluded | YES with count nit | Titled tests #26-34 = 9 new its (structural 1, invariance 1, ratios 7); file total 34 — matches "34 total" but impl writes "+8" (R-W2-002). Ratio set covers accent-ink on accent+accent-hover, badge `token/0.1` over canvas AND surface, confusion α0.12/0.52 min+max, newjob-tag α0.15, `::selection` α0.35. `raised`/canvas correctly excluded, rule/canvas ≥3 asserted instead. |
| 10 | Full `npm test` 147 green + `npm run build` green (×2, identical hashes) | NOT independently verified | Impl-reported with commands/results (§11). Reviewer ran no suite/build per brief §4 (ORCH gate). No reason found to doubt: guards assert on parsed CSS text that the reviewer independently parsed and recomputed. |
| 11 | Pre-fix proof: 6 failed / 13 passed with App toggle+apply hand-removed | PLAUSIBLE, not re-run | The 6 failing tests are exactly the App-integration tests; pre-fix tree had no `data-theme`/toggle (verified "no theme" baseline in report §2, consistent with parent source having no theme code). |
| 12 | Probe (production build, preview :3100, headless Chrome / Playwright): all 7 views × 2 widths × 2 themes, focus outline measured, no-flash at DOMContentLoaded | RECORD present, evidence NOT persisted | Tech-debt line added, historical deferral kept (`git show` diff confirms additive only). The described outcomes are specific and internally consistent (measured `rgb(29,78,216)` focus matches shipped accent exactly), and impl §14 honestly caveats empty-backend probing. But no screenshot/probe artifact exists anywhere in the repo (`git status` shows none), so visual-parity (spec §5.1) cannot be independently confirmed — R-W2-001. |
| 13 | Grep claims: `dark:` 0, hex 0, `to-` prose-only, `innerHTML` 0, no storage/change listeners | YES | `dark:`/`hex`/`innerHTML` re-run by reviewer: clean. `to-` hits re-located to prose only (no gradient utility). No `addEventListener` for storage/change in the diff (spec P-09). |
| 14 | No `--warn-strong`, no tailwind darkMode, no system/cross-tab listeners | YES | Diff contains none of these; `tailwind.config.js` untouched so no `warn-strong` mapping exists. |
| 15 | Reversal tripwires (delete light block / drift `:root` / remove toggle → guards fail) | Reasoned YES | Read the guard code: structural asserts each of 14 names, invariance asserts literal triples, ratios recompute luminance live; theme integration tests query the toggle by role. Each deletion path maps to a failing assertion. |
| 16 | "Independent review pending" (impl §15) | CLOSED | This review is the independent review. |

Claims checked: 16. Unsupported-or-false: 2 (claim 9's "+8" is off by one — trivially false; claim 12's visual evidence is described-only — unsupported by persisted artifact).

## 3. Long-run test (independent answers)
- **Source:** Pure client write path: 1 attribute + 1 meta + 1 storage write per toggle; no timers, listeners, or network. `theme.jsx:34-53` is the only writer.
- **Load (100×):** Still O(1) per toggle (3 small writes + state-driven re-render of the button only). No accumulation, no history/queue. StrictMode double-effect is idempotent (assigns the same token). Concurrency: two tabs are last-write-wins on reload — accepted per spec P-09, no live sync by design. Partial failure: storage denied → in-memory + attribute/meta flip persists until reload (by design, tested).
- **Hostile input:** `prime_theme` is attacker-visible. Strict `===` allow-list → resolved token (never raw string) → `dataset.theme` property assignment; meta selector is a constant; no HTML-parsing sink anywhere. Hostile mount is sanitized because App's effect overwrites the stored garbage with the resolved token. 10KB payload has zero parsing path (only compared for equality then dropped).
- **Operability:** Devtools-inspectable triple agreement (`dataset.theme` == meta `content` == `prime_theme`), asserted in tests. Rollback = revert 3 mechanisms (light block + init + toggle/state); leftover `prime_theme` keys go inert. No flag/migration. No logging/metrics — nothing to alert on for a pure client preference.
- **Reversal:** Which test fails if the fix is reverted? (a) Delete light block → structural + ratio guards fail (missing tokens). (b) Change any `:root` value → dark-invariance fails. (c) Remove `ThemeToggle`/apply path → 6 App-integration theme tests fail (impl's pre-fix proof, code-consistent). (d) Weaken `faint` above 86 100 124 → faint/raised ratio guard fails (4.85 margin is the tripwire). Verified by reading the guards; full reversal experiment not run per brief scope.

## 4. Findings
### R-W2-001 [MINOR] Probe screenshots described but not persisted — spec §5.1 visual parity not independently verifiable
- Location: `docs/tech-debt.md:22` (probe line), spec §5.1.
- Evidence: Implementer reports eyeballing screenshots (light/dark × 390/1280 × 7 views, focus outline). No screenshot file or probe script exists in the repo (`git status`/`ls-files` show none; `git show --stat 21f65c13` lists 9 files, none is a probe artifact). The probe's measurable claims (canvas rgb values, focus `rgb(29,78,216)`, dataset/meta agreement) are all consistent with the shipped code, and impl §14 honestly notes empty-backend limits — so this is an evidence-persistence gap, not a suspected fabrication.
- Why it matters: Spec §5.1 phrases the evidence as "probe screenshots". A future reviewer cannot re-confirm layout parity from the repo alone.
- Recommended fix (root-cause level): Attach the probe screenshots (or a compressed contact sheet) to the ORCH run folder / commit them with the docs, OR have ORCH explicitly record acceptance of described-only probe evidence for T-101. Code unchanged either way.

### R-W2-002 [NIT] Implementation report miscounts new static guards (+8 claimed, +9 actual)
- Location: `reports/w2-impl/W2-IMPL-01-T-101.md:6,87` vs `[VERIFIED frontend/tests/static.test.js]` titled tests #26-34.
- Evidence: Reviewer's parse of the test titles gives 9 new `it`s (structural 1 + invariance 1 + ratios 7); the "34 total" figure is correct. The error is conservative (more coverage than claimed) and has no engineering consequence.
- Why it matters: Claims-audit hygiene only; noted because the review's job is to catch exactly this class of discrepancy.
- Recommended fix: Correct the count in a docs follow-up if convenient. NOT-WORTH-IT as a standalone commit.

### R-W2-003 [NIT] `NewJob.jsx:678` ternary is now a dead branch (both arms `text-warn`)
- Location: `frontend/views/NewJob.jsx:678`.
- Evidence: `scalability === 'medium' ? 'text-warn' : 'text-warn'` — both arms identical after the mandated token swap.
- Why it matters: Readability only; the mapping (high→ok, else→warn) is exactly what design D5 prescribed, and collapsing it would be a deviation for style's sake. Retained for fidelity to the design.
- Recommended fix: None required. If a future pass touches this line, collapse to `high ? 'text-ok' : 'text-warn'`. NOT-WORTH-IT now.

Notes (not findings): `toggleTheme()`'s DOM-read fallback (`theme.jsx:57-60`) is impure but unreachable from the shipped call site (App always passes prev-state); the init script's silent catch is spec-mandated (§4.4) and self-healing via App's effect; `resolveTheme()` returning dark directly on storage-read throw (skipping system-light) matches the design D4 pin ("any throw → fall-through to dark"); meta-before-script ordering is the correct reading of §4.4, not a violation.

## 5. Attempts to break it
Reasoned traces (scoped checks only; no suite/build run):
- Hostile stored values `"><script>alert(1)</script>`, 10KB, unicode, `""`, `"LIGHT"` → all fail both `===` checks → fall to system/dark; `dataset.theme` only ever receives the resolved token; no element/script creation path. Would pass as designed.
- `localStorage.getItem` throws → `resolveTheme` returns dark without crashing (`theme.jsx:12-18`). `setItem` throws → attribute+meta already written, exception caught (`:45-51`) → flip survives in-memory. MatchMedia absent/throwing → dark.
- Missing meta node → `applyTheme` creates one (`:38-43`). Init script path: meta is always present in shipped HTML, so the only theoretical divergence (dataset set, meta query throws) cannot occur in production and would self-heal on App's first effect.
- Rapid re-clicking / double toggle → `toggleTheme(prev)` chains from state only; effect applies the final state idempotently. No split-brain: React state is the sole input to the single apply path.
- Sign-out → `shared.jsx` has zero mentions of `prime_theme` (grep: 0 hits); `logout` still removes only `prime_token`. Preference survives by construction, and a theme test pins it.
- Tampered `dataset.theme = "light"` before React mounts → App trusts it as source of truth (allow-listed on read at `App.jsx:183-185`) — this is the designed contract (§4.4), bounded to two tokens.

## 6. Dimension checklist
- Correctness — PASS: palette exact, resolution order stored→system→dark, toggle writes all three channels, labels/aria correct, sign-out preserves preference.
- Root cause vs symptom — PASS: builds the missing subsystem (tokens + init + state) rather than patching a symptom; NewJob outlier tokenized at its source.
- Regression/compat — PASS: `:root` byte-identical (proven), tailwind untouched, RunDetails untouched, toggle outside `<nav>` (smoke-safe), `App` public surface unchanged for the harness.
- Concurrency/idempotency — PASS: idempotent apply (StrictMode/HMR-safe), LWW across tabs by design (P-09), no listeners/races.
- Error handling — PASS (with noted shape): storage/matchMedia guards are scoped per-operation, not blanket; the one total catch (init) is spec-pinned and self-heals. No banned band-aids (no sleeps/retries/type suppressions/test weakening found).
- Security/abuse — PASS: allow-list + property-assignment-only sinks, constant selector, no injection vector; 10KB/hostile inputs have no sink. Storage key holds no auth data.
- Performance/scalability — PASS: O(1) per flip, zero view re-render, +22 lines CSS.
- Migration/rollback — PASS: additive only; default at-rest is today's dark; rollback = revert three mechanisms, stored keys inert.
- Observability — PASS: triple-agreement asserted in tests; no logs needed for a pure client preference.
- Maintainability/conventions — PASS: single-helper ownership (`components/theme.jsx`), existing `.btn`/`.btn-quiet` classes reused, AGENTS.md frontend conventions respected (no router/library churn). Two NITs (§4).
- Docs impact — PASS: token comment in `styles.css:33-36`, tech-debt probe line added with history preserved, impl report documents deviations honestly (meta ordering, spyOn seam).

## 7. Optimization and simplification opportunities
| # | Location | Evidence | Impact | Effort | Risk | Verdict |
|---|---|---|---|---|---|---|
| 1 | `NewJob.jsx:678` | Both ternary arms `text-warn` | Readability only | 1 min | Deviation-from-design noise | NOT-WORTH-IT |
| 2 | `theme.jsx:57-60` DOM-read fallback | `toggleTheme()` pure-flip when passed state; DOM read unreachable in shipped code | None in prod path | Small | Untested-path surface | NOT-WORTH-IT |

## 8. Cross-agent / cross-task interactions observed
- `frontend/views/RunDetails.jsx` untouched (`git diff` empty) — confirmed no collision with T-102 territory (C1). `tailwind.config.js` untouched — no contract conflict with future warn tokens.
- `docs/tech-debt.md` W2 touch is a single additive line; the historical "Light mode deferred" line is preserved (spec §5.7). No other agent's lines modified.
- No conflicts with core (backend untouched; no backend pytest claim made — correctly marked NOT-RUN in impl §7).

## 9. What I could not verify
- Full `npm test` (147-test claim) and `npm run build` status — reviewer did not run suite/build per brief §4; ORCH gate must confirm green. Reason for confidence anyway: every guard asserts on CSS text the reviewer independently parsed and re-computed.
- Browser probe outcomes (28/28 rows, screenshots, no-flash at DOMContentLoaded) — no artifacts in repo (R-W2-001). All measurable sub-claims are consistent with the shipped code, and focus/contrast math (accent 29 78 216, focus ratio 6.41) checks out.
- Pre-fix proof (6 failed/13 passed) — not re-run; code-consistent.
- Full 27-pair D2 inventory recomputation — reviewer recomputed 8 representative pairs (all MATCH); the remaining pairs are asserted live by `static.test.js` ratio guards (reviewer-read but not executed).
- Assistive-technology pass (noted as out of scope by impl). No claim made, none checked.
