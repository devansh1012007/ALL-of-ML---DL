<!-- ORCH-DIGEST:START -->
agent: W1-TREV-01 | scope: wave1 T-004 test review | verdict: APPROVE
tests_reviewed: 2 | fail-before/pass-after confirmed: 0 / reasoned: 2 / not-possible: 0
findings: BLOCKER 0 | MAJOR 0 | MINOR 0 | NIT 0
flaky_suspects: tests/runs.test.jsx Progress-poll test (4.5s, known timing-sensitive, passed this run; not a P3 test)
missing_edge_cases: P1 0 | P2 0 | P3 1
mutation_survivors: 0 of 6 plausible bugs not caught
changed_behavior_without_tests: none (docs-only task; no behavior changed, no test owed)
confidence: high (blind pass + scoped run 14/14 [RAN] + reversal reasoned with node-confirmed NaN semantics [RAN] + wave diff verified empty for frontend [RAN])
<!-- ORCH-DIGEST:END -->

# Test quality review — TREV-W1-IMPL-04 (T-004 P3 docs-close)

## 0. Method
- Blind pass FIRST, before reading the implementer report: read `frontend/tests/runs.test.jsx:571-622` (P3 describe block) and `frontend/views/RunDetails.jsx:212-238` (code under test). [VERIFIED]
- Then: scoped test run `cd frontend; npx vitest run tests/runs.test.jsx` → 1 file passed, 14/14 tests passed (~8.1s). [RAN]
- Wave tamper check: `git diff 69fe44e..HEAD -- frontend/` → EMPTY (0 lines). [RAN] The full wave diff touches only ops scaffolding + exactly two one-line docs edits (tech-debt.md:17, deferred-followups.md:113); lines 18-22 of tech-debt.md are outside the hunk and byte-identical. [VERIFIED via git diff]
- Reversal reasoning (no temp-worktree mutation needed — reasoning is airtight and cheap to confirm; brief allows reason OR demonstrate): (a) node one-liner confirmed `new Date('garbage') - new Date('garbage')` → `NaN`, `Number.isNaN → true`, and pre-fix `Math.max(0, NaN)` ≠ null → "Took NaN s" renders. [RAN] (b) Zero-diff likewise confirmed 0, `0 !== null` → renders under both versions.
- Only AFTER the blind pass did I read the implementer report (W1-IMPL-04-T-004.md). Its claims check out (see §7).

## 1. Per test/suite assessment
| Test | Asserts behavior? | Fails without fix? | Deterministic/isolated? | Over-mocked? | Notes |
|---|---|---|---|---|---|
| `garbage started/finished hides the duration chip (no Took, no NaN)` (runs.test.jsx:573) | Yes — real rendered DOM: `queryByText(/took/i)` absent AND `document.body.textContent` has no `NaN` (defense in depth: chip text gone, not just reformatted) | YES (reasoned): pre-f292a9c, `'garbage'` strings are truthy so `durationMs = NaN`; pre-fix `Math.max(0, Math.round(NaN)) = NaN` and chip gated on `seconds !== null` → "Took NaN s" renders → both assertions fail | Yes: fixed seed data, real timers, cleanup + backend.restore in afterEach | No: `renderApp` drives the real `<App/>` against a fetch-level fake backend; the component under test is not mocked | Exactly targets the shipped bug; assertion is on absence of user-visible text, not internals |
| `valid zero duration still renders "Took 0 s"` (runs.test.jsx:597) | Yes — `getByText('Took 0 s')` present AND no `NaN` in body | Passes both pre/post (guard-rail, by design): zero diff → `seconds = 0` under both formulas; it fails only if someone "fixes" the render with a falsy check (`seconds && …`) | Yes: same harness; identical timestamps make duration exactly 0 regardless of rounding | No (same harness) | Protects the `0` boundary the invariant comment warns about (RunDetails.jsx:216). This is the correct second test for this fix |
| Suite health (14/14) | n/a | n/a | P3 tests isolated from each other; shared `backend` variable reset per test | n/a | One slow unrelated test (Progress-poll, 4.57s) — known flake, passed here. Not a finding against P3 |

## 2. Coverage of changed lines/branches, error paths, boundaries
- Guard `RunDetails.jsx:220-222`: `durationMs === null` (missing timestamps) and `Number.isNaN(durationMs)` (garbage) both → `null` → chip hidden at :238. The garbage test exercises the NaN branch directly. [VERIFIED]
- The null branch (missing one/both timestamps) is covered by the pre-existing suite (detail tests render runs without the chip breaking — no NaN text, no crash). Pre-existing, not owed by this wave.
- Boundary `0`: zero-render test. [VERIFIED] Rounding/negative-diff clamp (`Math.max(0,…)`) unchanged pre-existing behavior; implementer correctly left it.
- Docs change itself: no executable surface; grep-asserted acceptance (stale phrases gone for P3) verified independently via `git diff` [RAN]. No test owed for a docs-only change — correct per brief/investigation.

## 3. Mutation thinking
| Plausible bug | Caught? | By which test |
|---|---|---|
| NaN guard removed (revert to pre-f292a9c formula) | YES — garbage test fails deterministically ("Took NaN s" renders, `NaN` in body) | garbage-hide (reasoned + node-confirmed semantics) |
| Guard inverted (`!Number.isNaN(durationMs)`) | YES — valid durations would hide (chip absent) and garbage would render NaN | garbage-hide + zero-render |
| Render gate changed to falsy (`seconds && …`) | YES — "Took 0 s" disappears (0 is falsy) | zero-render |
| Guard dropped but chip gated on `Number.isNaN(seconds)` instead | equivalent — would also pass; fine | — (not a bug) |
| Garbage test data weakened to empty strings (falsy) | Would pass trivially — test would stop exercising the truthy-garbage path | Not present: seed uses `'garbage'` for BOTH fields — the exact hostile input. Mutant-resistant |
| `seconds` rounded before NaN check | still NaN → still caught if guard removed | garbage-hide |

Mutation survivors: 0 of 6.

## 4. Flakiness evidence and test-suite health
- Single scoped run: 14/14 pass; Progress-poll test took 4.57s of the 5.08s test time. [RAN] This is the documented timing-sensitive test (brief §6, implementer §7) — passed, no re-run needed, but its runtime makes the suite slow and it is the known flake source for the ORCH full-gate run. Not a P3 concern; flagged, not a finding.
- No order dependence observed; P3 describe block runs after the detail/E suites with clean teardown between each test (afterEach restores backend, clears localStorage + hash, resets timers). [VERIFIED runs.test.jsx:7-20]

## 5. Findings
None. No BLOCKER/MAJOR/MINOR/NIT.
- In particular: T-004 changed no tests and degraded none — `git diff 69fe44e..HEAD -- frontend/` is EMPTY. [RAN] The "+2 tests" docs claim is accurate: f292a9c added exactly these two `it()` blocks (+53 lines in runs.test.jsx), and both exist at HEAD at the cited locations. [VERIFIED]
- The "117/117 at gate" wording: full suite NOT-RUN by me (brief forbids; ORCH gate T-003 owns it). My scoped 14/14 + arithmetic (115 + 2, no intervening test commits per `git show f292a9c --stat`) corroborate but do not independently prove 117. This is correctly disclosed by the implementer (§15) and is ORCH's to close — noted in §7, not a finding against the test side.

## 6. Missing edge cases and tests (prioritized)
P1 (must add): none. P2 (should add): none.
P3 (nice to have, NOT owed by this task):
- One-side garbage (`started_at` valid, `finished_at` garbage, and vice versa): same `Number.isNaN` branch; a 3rd test would permute the input table. Cheap to add someday; its absence does not weaken the shipped fix (both-side garbage already kills the bug), and T-004 is docs-only so nothing is owed. Where: `runs.test.jsx` P3 describe; sketch = clone of the garbage test with one field kept from `completedDetail` defaults, assert same chip-hidden + no-NaN.

## 7. What I could not verify
- Full-suite 117/117 count and `npm run build` — explicitly out of scope for this reviewer (ORCH gate). Scoped run only. [RAN single file]
- Production data: whether real rows contain garbage timestamps — needs DB access, out of scope; doesn't affect the test-side verdict.
- Implementer report comparison (post-blind-pass): its scoped-run result (14/14), f292a9c description, and diff claims all match my independent evidence; its one disclosed process miss (missing commit trailers on 6409d0e) is a process issue outside test quality and does not affect this verdict.
