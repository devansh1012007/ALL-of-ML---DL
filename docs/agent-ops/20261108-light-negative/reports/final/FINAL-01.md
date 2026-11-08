<!-- ORCH-DIGEST:START -->
agent: FINAL-01 | scope: final integration, all 3 items (T-101/T-102/T-103) | verdict: APPROVE
findings: BLOCKER 0 | MAJOR 0 | MINOR 1 | NIT 0
claims_audit: 9 claims checked / 0 unsupported or false
band_aids_found: none
top_3_risks: stale tech-debt:21 "Light mode deferred" line contradicts :22 probe line (doc-only, minor) | negative-diff production reachability still uninspected against live DB (pre-existing, honest in impl report) | backend pytest NOT-RUN (frontend-only diff, gates document it)
optimizations: DO-NOW 0 | DO-LATER 0 | NOT-WORTH-IT 1
reversal_check: done
confidence: high (blind recomputation + re-run of T-102 tests + token/dark invariant checks all matched claims)
<!-- ORCH-DIGEST:END -->

# Code review — FINAL-01

## 0. Method
Blind pass first: `git diff 85acdda..HEAD -- . ':!docs/agent-ops'` (12 files, +903/−9) plus `git show ca5d950` (T-102), `git show 21f65c13` (T-101; actual SHA 21f65c131…), `git show 9c73971` (T-103), `git show 94963e6` (T-101 test pins). Read in context: styles.css, index.html, App.jsx (nav region), theme.jsx, AuthView.jsx, RunDetails.jsx, NewJob.jsx (via diff), shared.jsx logout, tech-debt.md:10-23, light-mode spec §§4.9-5. One scoped test run (runs.test.jsx 16/16). No full suite/build (gate doc records 154/154). Implementer reports opened only after the blind pass, for the claims audit.

## 1. Blind-pass findings (before reading implementer reports)

1. **Negative-diff [VERIFIED frontend/views/RunDetails.jsx:221-223]** — `seconds` null when `durationMs === null || Number.isNaN(durationMs) || durationMs < 0`; else `Math.max(0, round(ms/1000))`. Zero diff (finished == started) still yields 0 → chip renders "Took 0 s". No sibling duration site: grep for `Took|elapsed|duration` across views finds only RunDetails.jsx:239 (`Took {seconds} s`, gated on `seconds !== null`). [VERIFIED]
2. **Light tokens [VERIFIED frontend/styles.css:37-53]** — exactly 14 triples (canvas…bad) + `color-scheme: light`. Dark `:root` byte-identical: [RAN python split on ':root {' compare of 85acdda vs HEAD → True]. Light triples match the spec's pinned design values (spec §4.9, light-mode.md:94-104).
   Contrast recomputed independently [RAN python WCAG luminance]: faint/raised **4.85:1** (matches spec-accepted 4.85, light-mode.md:104 — accepted exception, not a violation), warn/canvas **5.64:1** ≥4.5, accent-ink/accent **6.70:1** ≥4.5, muted/surface 8.20, ink/canvas 13.98, ok/canvas 5.99, bad/canvas 6.18. All body pairs ≥4.5.
3. **Init script [VERIFIED frontend/index.html:6-26]** — inside `<head>` before body/module script, single outer try/catch, sets `dataset.theme` + meta `color-scheme` from ONE resolution; allow-lists stored value, defaults dark. Guarded (localStorage/matchMedia throws → dark, no crash). Head-first ✓.
4. **Toggle placement [VERIFIED frontend/App.jsx:137-161]** — `ThemeToggle` at :159, inside the `ml-auto` div OUTSIDE `<nav>` (nav closes :148) → no accessible-name collision with Runs/Models/New run/Admin. AuthView: diff shows toggle inside `.auth-card` above `<h1>` in the signed-out shell [VERIFIED frontend/views/AuthView.jsx].
5. **Hostile values [VERIFIED frontend/components/theme.jsx]** — `resolveTheme` allow-lists `light|dark`, returns a resolved token never the raw string; `applyTheme` coerces anything non-`light` to `dark` before any DOM write. Stored XSS/10KB/unicode can never reach `dataset`/meta. Storage-throw caught in both resolve and apply.
6. **Sign-out [VERIFIED frontend/components/shared.jsx:175-176]** — `logout` removes only `prime_token`; `prime_theme` never cleared. ✓
7. **RunDetails/tailwind untouched by T-101** — `git show 21f65c13 --stat`: 9 files (tech-debt, App, theme.jsx, index.html, styles.css, static/theme tests, AuthView, NewJob); no RunDetails, no tailwind.config. `git diff 85acdda..HEAD -- frontend/tailwind.config.js` empty. ✓ (RunDetails changes in the combined diff belong to T-102.)
8. **T-103 genealogy [VERIFIED docs/tech-debt.md:17]** — "115/115 at 2502fd9; +2 P3 tests → 117/117 at gate" reads unambiguously; single historical line, no dual-count confusion.
9. **Probe line [VERIFIED docs/tech-debt.md:22]** — honestly scoped: "empty-backend states where deterministic", deploy/dev flash out of scope per P-07, accepted exceptions named. No overclaim.
10. **[MINOR docs/tech-debt.md:21]** — the pre-existing "Light mode deferred. Tokens remain dark-only…" bullet is now stale: tokens are no longer dark-only, yet the bullet still reads as current state and is contradicted two lines later by the :22 probe line. Read in the "Round 2 … 104 tests" section it is arguably historical, but nothing marks it superseded. Cosmetic doc inconsistency, not a behavioral issue.

## 2. Claims audit
| Implementer claim | Verified? | Evidence / finding |
|---|---|---|
| T-102: 2 new tests, scoped 16/16, zero-duration still renders (W1-IMPL-01) | YES | [RAN `npx vitest run tests/runs.test.jsx` → 16 passed (16)] — includes negative-diff, mixed-garbage, and zero cases; diff matches report's 2-file scope |
| T-102: production reachability assumed from code only (honest caveat) | HONEST | Caveat stands; no live DB inspected (consistent with briefing). Not a blocker: fix is a pure presentation guard |
| T-101: dark `:root` byte-identical, 14 light triples verbatim | YES | [RAN python byte-compare → True]; triples match spec §4.9 |
| T-101: warn 5.64:1 on canvas, no warn-strong needed (W2-IMPL-01 intro/§4) | YES | Independent recompute: 5.64 ✓ |
| T-101: toggle outside nav, both shells, action-describing labels | YES | App.jsx:159 outside nav; AuthView toggle in auth-card; theme.jsx label logic |
| T-101: logout deliberately does not clear prime_theme | YES | shared.jsx:175-176 |
| T-101: NewJob :678 → text-warn, tailwind untouched, no new token | YES | Diff confirms; applies to the `text-orange-400` outlier branch (medium already text-warn) |
| T-101: hostile storage / storage-throw / resolution-order tests present | YES | theme.test.jsx + 94963e6 pins reviewed; scoped run green per gate 154/154 (not re-run in full — see §9) |
| T-103: line 17 genealogy unambiguous (W1-IMPL-02) | YES | tech-debt.md:17 |

## 3. Long-run test (independent answers)
- **Source**: all three fixes are presentation/doc-layer, no data model, migration, or API contract change. No new failure mode at source.
- **Load**: no new fetches, listeners, or loops; theme state is two setState/useEffect writes per toggle. Zero-diff chip behavior unchanged under load (pure computation of existing fields).
- **Hostile**: localStorage hostile values are allow-listed before DOM reachability (theme.jsx); negative/huge/garbage timestamps collapse to hidden chip rather than rendered garbage (RunDetails.jsx:218-223 handles NaN, negative, and null uniformly). No injection surface added — `dataset.theme` and meta content receive only the two literals.
- **Operability**: theme init is synchronous head script (no flash, no async dependency); rollback = remove one CSS block + one script (dark default is `:root`, so absence of `data-theme` is itself the safe state). Chip-hide is reversible by deleting the `< 0` disjunct.
- **Reversal**: removing `|| durationMs < 0` makes the new negative-diff test fail with "found Took 0 s" (pre-fix failure documented in W1-IMPL-01 §2). Removing the `[data-theme="light"]` block fails the static ratio/structure guards in static.test.js. Both regressions are test-covered — done, not reasoned-only.

## 4. Findings
### R-FINAL-001 [MINOR] Stale "Light mode deferred" bullet contradicts new probe line
- Location: `docs/tech-debt.md:21` vs `:22` · Evidence: :21 still asserts "Tokens remain dark-only; color-scheme:dark retained" while :22 records a completed light-mode probe with tokens shipped · Why it matters: a cold reader gets two contradictory statements about current state · Recommended fix: mark :21 as superseded by :22 (e.g. prefix "SUPERSEDED 2026-11-08 by T-101" or delete). Root-cause level: one-line doc edit in a future touch; not push-blocking.

## 5. Attempts to break it
- Hostile stored values (`<script>…`, 10KB string, unicode, `light ` padded, `Object.prototype` keys): allow-list means only exact `light|dark` hits; everything else → dark. Cannot reach DOM as raw strings.
- localStorage throws (sandbox/private mode): caught at getItem (resolveTheme) and setItem (applyTheme) — app falls back to dark, renders normally.
- matchMedia missing/throws: guarded by typeof + try/catch → dark.
- `started_at`/`finished_at` = garbage, one-side garbage, empty, or reversed: all collapse to null → chip hidden, no "NaN", no "Took 0 s" lie.
- Toggle spam / StrictMode double-effect: `applyTheme` idempotent; single writer path.
- Negative diff of −1 ms: hidden (not rounded to 0) — correct per "untrustworthy duration" invariant.

## 6. Dimension checklist
Correctness ✓ (all three spot-check groups verified against code) · root cause vs symptom ✓ (hide-chip is the honest presentation fix at the invariant site, not a display patch) · regression/compat ✓ (dark :root byte-identical; zero-duration behavior preserved; no contract changes; NewJob warn change is the spec-sanctioned swap) · concurrency/idempotency ✓ (theme apply idempotent; no shared-state mutation) · error handling ✓ (one-outer-try/catch init, storage throws contained) · security/abuse ✓ (allow-list before DOM) · performance/scalability ✓ (no new work per render) · migration/rollback ✓ (none needed; revert instructions in §3) · observability ✓ (probe recorded; chip-hide has no silent side effect) · maintainability/conventions ✓ (single-writer applyTheme; invariant comments at both sites) · docs impact ✓ except R-FINAL-001 (minor).

## 7. Optimization and simplification opportunities
| # | Location | Evidence | Impact | Effort | Risk | Verdict |
|---|---|---|---|---|---|---|
| 1 | tech-debt:21 | Contradicted by :22 | Prevents reader confusion only | 1 line | None | NOT WORTH IT as a blocking change; fold into next doc touch |

## 8. Cross-agent / cross-task interactions observed
T-101 and T-102 touch disjoint surfaces (theme subsystem vs RunDetails duration) — no interaction, no ordering hazard. T-103 is a one-line doc edit. 94963e6 (W2-IMPR-01) closes W2 review findings with additive-only tests, no production change. Spec amendment ddf0b25 and planner-review fold 1b8d26a are doc-only and precede the implementation commits.

## 9. What I could not verify
- Full suite/build: not re-run per brief (gate record: 154/154 at docs/agent-ops/20261108-light-negative/gates/gate-w2-1.md). One scoped file re-run (runs.test.jsx 16/16) matched impl claims.
- Live-browser probe assertions (tech-debt:22): taken as recorded; jsdom re-run does not re-prove production-build rendering.
- Production reachability of negative-diff rows: assumed from code (no live DB), as the impl report honestly states.

## 10. Push decision
**Yes — push the branch.** All three items are truly closed: T-102 (code + 2 tests + code+test verification re-run), T-101 (code + theme/static tests + spec + probe record, dark invariant byte-verified, contrasts recomputed), T-103 (doc reword verified unambiguous). The sole finding is a minor stale doc bullet (R-FINAL-001) that should be fixed in a later doc touch but does not block. Merge into main / PR #2 remains subject to the mission's separate explicit approval, which this verdict does not grant.
