<!-- ORCH-DIGEST:START -->
agent: W1-TREV-01 | scope: wave1/T-102 (ca5d950) | verdict: APPROVE
tests_reviewed: 2 new + 2 existing P3 + helpers completedRun/completedDetail
fail-before/pass-after confirmed: 1 / reasoned: 2 / not-possible: 0
findings: BLOCKER 0 | MAJOR 0 | MINOR 0 | NIT 1
flaky_suspects: pre-existing Progress-poll test only (passed in my run, 4.57s); new P3 tests: none
missing_edge_cases: P1 0 | P2 0 | P3 3
mutation_survivors: 1 of 5 plausible bugs not caught (positive-duration mutant; no test asserts "Took 60 s")
changed_behavior_without_tests: none
confidence: high (blind pass + own 16/16 run + independent pre-fix trace agreeing with implementer's executed pre-fix failure)
<!-- ORCH-DIGEST:END -->

# Test quality review — W1-TREV-01 (T-102, ca5d950)

## 0. Method (temporary worktree used? repeat counts, coverage tooling)
- Blind pass, implementer report deliberately not read first: `frontend/tests/runs.test.jsx` (whole file; P3 block 571-672, new tests 623-671, helpers `completedRun` 22-46, `completedDetail` 312-340) and `frontend/views/RunDetails.jsx:214-239` [VERIFIED frontend/tests/runs.test.jsx:571-672, frontend/views/RunDetails.jsx:214-239].
- Helpers checked: `renderApp` renders the real `<App/>` against a fetch-level fake backend and does not mock the component under test [VERIFIED frontend/tests/helpers.jsx:1037-1052, helpers.jsx:9-15]; P3 tests seed via `runDetails` override, exactly the established pattern.
- One scoped run only, per brief: [RAN `cd frontend; npx vitest run tests/runs.test.jsx` -> `Test Files 1 passed (1)`, `Tests 16 passed (16)`, duration 6.75s; Progress-poll test 4573ms]. Expectation 16/16 met. No repeat runs (brief: ONE scoped run), no coverage tooling, no temp worktree — reversal done by independent code trace + implementer's executed pre-fix evidence (read after blind pass, §below).
- Diff check: [RAN `git diff 9e0730e..HEAD -- frontend/` -> only `frontend/tests/runs.test.jsx` (+50, 0 deletions) and `frontend/views/RunDetails.jsx` (condition + comment; line 220 `|| durationMs < 0`)]. Existing garbage/zero P3 tests appear only as unchanged context; additions start after the zero test at old line 619. Byte-unchanged confirmed: the test-file diff has zero deleted lines. Branch: [RAN `git branch --show-current` -> `frontend-ui-round2`].
- Implementer report read last: `reports/w1-impl/W1-IMPL-01-T-102.md` — its §2/§7 claim a pre-fix run "1 failed | 15 passed" with the negative test finding `<span class="tabular-nums">Took 0 s</span>` at runs.test.jsx:644, and post-fix 16/16. This matches my trace exactly (see §1 reversal analysis); I did not re-execute the pre-fix state (would require reverting code, forbidden read-only).

## 1. Per test/suite assessment
| Test | Asserts behavior? | Fails without fix? | Deterministic/isolated? | Over-mocked? | Notes |
|---|---|---|---|---|---|
| `negative diff hides the duration chip` (new, :623-646) | Yes — rendered-DOM absence: `queryByText(/took/i)` not in document + no `NaN` in body text. No internals asserted. | **Yes, by trace + implementer's execution.** Pre-fix code [VERIFIED `git show 9e0730e:frontend/views/RunDetails.jsx`]: `seconds = durationMs===null \|\| isNaN ? null : Math.max(0, round(diff/1000))`. For started 00:01 / finished 00:00, diff = −60000ms → not null/NaN → `Math.max(0,−60)=0` → chip `seconds!==null` renders "Took 0 s" → `expect(...).not.toBeInTheDocument()` FAILS. Exactly the reported bug text. | Yes — fixed ISO `…Z` timestamps (UTC, timezone-independent), `renderApp` real timers (`vi.useRealTimers()` beforeEach, :8), fresh seed per test, `afterEach` cleanup+restore (:13-20). Gated on `findByRole(heading)` so the page provably rendered before asserting absence — the test cannot pass by the page failing to load. | No — fetch-level fake backend is the shared harness; `RunDetails`/`App` are real. | Positive control in suite: zero test proves the same component *does* render "Took 0 s" when seconds=0, so absence here is caused by the null sentinel, not by the chip being unrenderable. Not a vacuous absence. |
| `mixed garbage/valid timestamps hides the duration chip` (new, :648-671) | Yes — same DOM absence + no `NaN`. | No — passes pre- and post-fix, **by design** (control). `new Date('garbage')` → Invalid Date → diff NaN → pre-existing P3 `Number.isNaN` guard hides it. Its value: proves the guard is generic over either side (subtraction is symmetric in NaN), not a both-garbage special case. | Yes — same determinism as above. | No. | Symmetric sibling (valid/garbage) would exercise the identical NaN path; arithmetic is side-agnostic. P3 nit only. |
| `garbage started/finished hides…` (existing P3, :573-595) | Yes. | Unchanged (byte-identical). Would fail if NaN guard regressed. | Yes. | No. | Untouched — verified via zero-deletion diff. |
| `valid zero duration still renders "Took 0 s"` (existing P3, :597-621) | Yes — positive presence (`getByText('Took 0 s')`) + no `NaN`. | N/A (guard-rail, passes both). Catches an over-broad falsy fix (`if (!seconds) hide`) and the `<= 0` mutant. | Yes — single `ts` reused for both fields. | No. | Untouched — verified. This is the suite's anti-vacuity anchor for the two absence tests. |

## 2. Coverage of changed lines/branches, error paths, boundaries
Changed lines: condition `durationMs < 0` (RunDetails.jsx:221) — hit by negative test (true branch) and by zero test (false branch, diff 0); comment only otherwise. `Number.isNaN` branch — hit by garbage + mixed. `null` branch — hit by neither new test (timestamps are truthy strings); pre-existing uncovered-by-P3 path, unchanged by T-102. Positive diff branch (`Math.max(0, round(·))` with seconds>0) — **no P3 test asserts a positive "Took N s"** (grep: the only "Took" assertions in the suite are zero + absences; R3b detail test uses the +60s fixture but asserts no duration text). Boundary: exactly −60s covered; sub-second negatives (−1ms…−999ms) and −1s not covered, but the implementation is a sign test with no threshold, so one representative negative is the right granularity — brief's "no threshold logic needed" holds.

## 3. Mutation thinking
| Plausible bug (off-by-one, inverted condition, missing await, dropped error, wrong default, …) | Caught? | By which test |
|---|---|---|
| Remove `durationMs < 0` (revert T-102) | **Yes** | negative test (renders "Took 0 s") — executed pre-fix by implementer, traced by me |
| Remove `Number.isNaN` check | Yes | garbage test + mixed test ("Took NaN s") |
| `durationMs <= 0` (hide true zero) | Yes | zero test |
| Falsy check `if (!seconds) hide` | Yes | zero test (0 is falsy) |
| Remove `durationMs === null` check | **No (P3 suite)** | no P3 test uses null/empty timestamps; mutant renders "Took 0 s" for missing timestamps. Pre-existing gap, not introduced by T-102. |
| Hide all nonzero durations (`seconds = durationMs===0 ? 0 : null`) | **No** | all 4 P3 tests pass under this mutant (garbage/negative/mixed hidden, zero shown) while normal +60s display breaks. No positive-duration assertion anywhere in the suite. The one survivor. |
| Inverted `< 0` → `> 0` | Yes | zero test still passes but negative test… `>0` hides positives and shows negatives→clamped 0: negative test catches (chip renders), garbage unchanged. Caught. |
| Threshold `< -60000` (strict) | No (artificial) | −60s fixture is exactly at boundary; rejected as an implausible mutant — the spec is an unthresholded sign check. |

## 4. Flakiness evidence (repeated runs) and test-suite health (slow, order-dependent, shared state)
One run only (per brief): 16/16, 6.75s total; the suite's known timing-sensitive Progress-poll test took 4573ms of the 5065ms test time and passed. New P3 tests are pure render-and-assert with fixed data and no timers/polling of their own — no flake mechanism identified. No order dependence: each test re-seeds via `renderApp` and `afterEach` fully cleans up (cleanup, backend restore, localStorage/hash reset, real timers). No shared mutable state between the P3 tests beyond the module-level `backend` handle, which is reassigned per test and restored in `afterEach`.

## 5. Findings (R-W<N>-nnn, severity, location, evidence, recommended fix)
- R-W1-001 (NIT): `frontend/tests/runs.test.jsx` P3 block — mixed test covers only garbage/valid, not valid/garbage. Evidence: :657-658. The NaN path is symmetric, so this is coverage aesthetics, not a functional gap. Recommended fix (optional, not required for approval): none — do not churn the suite for a symmetric case.
- No BLOCKER/MAJOR/MINOR findings. The two new tests assert rendered DOM, match the established harness pattern, are deterministic, and the negative test genuinely fails pre-fix (see §1). The fix under test is one condition; the tests pin exactly its branch and its guard-rails.

## 6. Missing edge cases and tests (prioritized)
P1 (must add): none.
P2 (should add): none — spec said "add exactly 2 tests"; both demanded cases exist and pass.
P3 (nice to have):
1. Positive duration renders `Took 60 s` (fixture `completedDetail` defaults started 00:00/finished 00:01 already imply it). Kills the §3 survivor mutant (hide-all-nonzero). Sketch: copy the zero test with `started_at: '2026-11-08T00:00:00Z', finished_at: '2026-11-08T00:01:00Z'`, assert `getByText('Took 60 s')`. Belongs in the same P3 describe.
2. Null timestamps (`started_at: null`) hide the chip — covers the `durationMs === null` branch in the P3 block (currently only covered implicitly elsewhere, if at all). Sketch: same as mixed with `started_at: null`.
3. Sub-second/−1s negative (`finished_at` 1s before `started_at`) hides the chip — documents the unthresholded sign rule. Sketch: negative test with `started_at: '2026-11-08T00:00:01Z'`, finished 00:00.

## 7. What I could not verify
- Did not re-execute pre-fix failure myself (read-only; would require reverting RunDetails.jsx in a temp worktree). Rely on: (a) my independent trace of `git show 9e0730e` code, (b) implementer's executed pre-fix run (1 failed/15 passed, exact bug text) in `reports/w1-impl/W1-IMPL-01-T-102.md` §2/§7. Both agree.
- No repeat runs → flakiness assessment is single-run plus mechanism analysis, not statistics.
- Full frontend suite not run (scoped-only rule; ORCH gate owns it).
- Production reachability of negative-diff rows (DB state) — out of scope for a test review; display logic is the testable contract.

## Long-run test (standing orders §8)
Source: corrupt/skewed timestamps via harness injection — chip hides, never renders raw values. Load/partial failure: no new I/O; one comparison per render. Hostile input: garbage strings, negative, missing → null sentinel hides; no injection surface. Operability: pure display, revert one line. Reversal: reverting `|| durationMs < 0` fails exactly the negative test (proven above); zero + mixed stay green as guard-rails.
