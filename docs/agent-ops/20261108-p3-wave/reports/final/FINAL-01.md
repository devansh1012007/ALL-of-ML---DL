<!-- ORCH-DIGEST:START -->
agent: FINAL-01 | scope: run 20261108-p3-wave (P3 Took NaN s + docs-close) | verdict: APPROVE
findings: BLOCKER 0 | MAJOR 0 | MINOR 1 | NIT 2
claims_audit: 10 claims checked / 1 unsupported or false (immaterial report-stat only)
band_aids_found: none
top_3_risks: Progress-poll timing flake could false-red a future gate (pre-existing, not P3) | negative-diff clamp to Took 0 s is pre-existing display honesty, product call | tech-debt:17 dual counts (115/115 + 117/117) may confuse future readers
optimizations: DO-NOW 0 | DO-LATER 1 | NOT-WORTH-IT 2
reversal_check: reasoned-only (deterministic JS semantics; no mutation run per read-only scope)
confidence: high (diff + code + tests + docs verified directly; scoped vitest 14/14 run by me; 117/117 + build taken from gate-w1-1, not re-run)
<!-- ORCH-DIGEST:END -->

# Code review — FINAL-01 (final integration reviewer)

**Verdict: APPROVE. P3 "Took NaN s" is truly closed (code + tests + docs). I would let branch `frontend-ui-round2` be pushed.** The single MINOR is a pre-existing process miss (missing commit trailers) that cannot be retro-fixed without a forbidden amend and changes no behavior; it is not push-blocking. No BLOCKER and no MAJOR.

## 0. Method

Diff range reviewed: `git diff 2502fd9..HEAD -- . ':!docs/agent-ops'` plus `git show f292a9c` and `git show 6409d0e` [RAN]. Branch `frontend-ui-round2`, HEAD `6a39460` [RAN `git branch --show-current`], log `2502fd9..HEAD` = `f292a9c`, `69fe44e`, `0053765`, `6409d0e`, `6a39460`. Combined frontend/docs diff is 4 files, +63/-4: `frontend/views/RunDetails.jsx` (+8/-2 actual numstat), `frontend/tests/runs.test.jsx` (+53/-0), `docs/tech-debt.md` (1/1), `docs/plans/2026-11-08-frontend-deferred-followups.md` (1/1) [RAN `git show f292a9c --numstat`, `git show 6409d0e --numstat`].

Files read in full/context: `frontend/views/RunDetails.jsx` (all 329 lines), `frontend/format.js` (all 45), `frontend/tests/runs.test.jsx` (helpers `completedRun`/`completedDetail` at :22-46/:312-340, B2/E guards :520-569, P3 block :571-622), `docs/tech-debt.md:17`, `docs/plans/2026-11-08-frontend-deferred-followups.md:113`, `frontend/views/RunsDashboard.jsx:127-128`, `frontend/views/CompareRuns.jsx` (all 145), `frontend/AdminScreen.jsx:385` (grep context). Greps run: `Took|started_at|finished_at`, `new Date\(|Infinity|NaN|duration`, `formatWhen|timeAgo|wall_seconds|Took` across `frontend/`; stale-phrase greps over both docs files (zero hits for `future phase|New P3 backlog|not fixed here|P3 remainder`) [RAN via grep tool in PowerShell env].

Commands run by me: `npx vitest run tests/runs.test.jsx -t "P3 duration"` → 2 passed/12 skipped [RAN]; `npx vitest run tests/runs.test.jsx` → 14/14 passed, 5.18s test time, single-file scope only [RAN]. Full suite / build explicitly NOT run (brief forbids; gate owns them — `gates/gate-w1-1.md` shows 117/117 + build 1670 modules green at HEAD `6a39460`).

Order followed: **blind pass first** (diff + code + tests + docs, findings formed §1), **then** claims audit (§2, opening the w1-impl/w1-review reports only at that point). Prior per-task reports were not relied on for any finding in §1.

## 1. Blind-pass findings (before reading implementer reports)

1. **The guard is the right fix at the right level.** `RunDetails.jsx:217-222` splits diff from render: `durationMs` is `null` unless *both* timestamps are truthy, `seconds` is `null` iff `durationMs === null || Number.isNaN(durationMs)`, else `max(0, round(ms/1000))`; chip gated on `seconds !== null` at :238. Garbage-but-truthy strings (`"garbage"`) therefore hit the NaN branch and hide the chip; `null`/`undefined`/`""` hit the null branch and hide it; valid `0` (`finished == started` → `durationMs 0` → `seconds 0` → `0 !== null`) still renders "Took 0 s" [VERIFIED RunDetails.jsx:214-222,238]. The falsy-trap (guarding on `seconds` itself) is explicitly avoided and documented in the invariant comment :214-216. Root cause is addressed, not masked: no try/catch, no error swallowing, no test-specific special-casing, no flag.
2. **Pre-fix mechanism is exactly as described.** Pre-`f292a9c` formula `Math.max(0, Math.round((new Date(fin)-new Date(start))/1000))` with truthy garbage: `new Date("garbage")` is Invalid Date, subtraction → `NaN`, `Math.max(0,NaN)` → `NaN`, chip gate `NaN !== null` is true → renders "Took NaN s" [VERIFIED via `git show f292a9c` diff]. Deterministic; no environment dependence.
3. **Both tests are real and target the shipped bug.** Garbage test seeds `started_at/finished_at: "garbage"` (the exact hostile truthy-but-unparsable input) and asserts *both* `queryByText(/took/i)` absent *and* no `NaN` in `document.body.textContent` [VERIFIED runs.test.jsx:573-595]. Zero test seeds identical valid timestamps and asserts `getByText("Took 0 s")` present + no `NaN` [VERIFIED :597-621]. Both render the real `<App/>` via the shared `renderApp` harness (fetch-level fake backend; component under test not mocked), use fixed data and real timers, with proper teardown [VERIFIED :7-20]. The garbage test fails pre-fix deterministically (see §3 Reversal); the zero test is a guard-rail that passes both ways and fails only under an over-broad falsy "fix" — the correct pair for this invariant.
4. **No sibling NaN/`Invalid Date` surface left open by this change.** "Took" render site is unique in `frontend/` [VERIFIED grep single hit at RunDetails.jsx:238]. Runs list Started cell uses guarded `formatWhen/timeAgo` (`RunsDashboard.jsx:127-128` → `format.js:28,43` NaN guards) [VERIFIED]; RunDetails Started span uses the same helpers (`RunDetails.jsx:237`) [VERIFIED]; Admin queue timestamp uses `formatWhen` (`AdminScreen.jsx:385`) [VERIFIED]; `CompareRuns.jsx` computes no duration/timestamps (metrics table only) [VERIFIED full read]; `PredictPanel.jsx:112` `Number.isNaN` is a validation throw, not a render leak [VERIFIED grep]. Pre-existing `Math.max(0,…)` negative-diff clamp (finished < started → "Took 0 s") is unchanged pre-existing display behavior, not a NaN leak — noted as honesty nit, not a P3 remainder.
5. **Docs match the code.** `tech-debt.md:17` and plan F5 (`:113`) both now state P3 FIXED at `f292a9c`, null sentinel, valid 0s renders, +2 tests; stale sentences (`P3 remainder…future phase`, `New P3 backlog…not fixed here`) are fully replaced, not appended-over [VERIFIED diff + zero-hit greps]. A1/B2/E citations (`092e800`, `64c99f8`, `6c72d75`) and tech-debt lines 18-22 sit outside the diff hunks and are byte-identical [VERIFIED]. "117/117 at gate" is now gate-observed (gate-w1-1: 117/117 + build green at HEAD), so what was arithmetic at docs-commit time is verified at final-review time.
6. **Regression risk is minimal.** The change is a single-file display guard plus additive tests plus two one-line docs edits; no API/schema/store/state shape touched, no `frontend/format.js` or shared-helper contract changed, no other view touched. My scoped run of the full `runs.test.jsx` file (14/14, including the known slow Progress-poll test) shows no intra-file regression [RAN]. `wall_seconds` present in fixtures is ignored by the view before and after (recomputed from timestamps) — preserved semantics, not a new divergence.

Blind-pass verdict before reading reports: **closed, minimal, correct** — no BLOCKER/MAJOR; one process nit (commit trailers, visible from `git show` subjects).

## 2. Claims audit

Implementer docs: `reports/w1-impl/W1-IMPL-04-T-004.md`; reviewers: `reports/w1-review/REV-W1-IMPL-04.md`, `TREV-W1-IMPL-04.md`. Checked independently against diff/code/tests/gate.

| # | Implementer claim | Verified? | Evidence / finding |
|---|---|---|---|
| 1 | P3 guard hides chip on NaN diff (null sentinel), preserves valid 0s | ✅ Yes | [VERIFIED RunDetails.jsx:214-222,238]; [RAN scoped P3 tests 2 passed, file 14/14] |
| 2 | 2 P3 tests exist at `runs.test.jsx:573` (garbage-hide) and `:597` (zero-render), exact assertions as quoted | ✅ Yes | [VERIFIED runs.test.jsx:571-622]; fixture spread via `completedDetail` confirmed :312-340 |
| 3 | Pre-fix mechanism (`Math.max(0,NaN)=NaN`, `NaN!==null` renders "Took NaN s") | ✅ Yes | [VERIFIED `git show f292a9c` diff]; standard JS Date semantics, matches TREV node check |
| 4 | Both docs' stale P3 sentences removed; replacements match code/tests | ✅ Yes | [VERIFIED diff 6409d0e + zero-hit greps]; test-name mapping `garbage-hide`/`zero-render` accurate |
| 5 | Lines 18-22 of tech-debt byte-identical; A1/B2/E citations verbatim; only 2 one-line docs changes | ✅ Yes | [VERIFIED `git show 6409d0e --numstat` 1/1+1/1; hunks single-line] |
| 6 | Scoped `runs.test.jsx` 14/14 pass (Progress-poll passed, no flake) | ✅ Yes | [RAN `npx vitest run tests/runs.test.jsx` → 14/14, 5.18s]; implementer 7.42s + INV/TREV independent runs agree |
| 7 | "117/117 at gate" (115 + 2, gate-observed) | ✅ Yes (now gate-verified) | [VERIFIED gates/gate-w1-1.md: 117/117 + build green at HEAD 6a39460]; arithmetic 115+2 corroborates; implementer disclosed it as NOT-RUN-by-them (honest) |
| 8 | No sibling leak; mixed garbage same branch; negative-diff clamp pre-existing | ✅ Yes | [VERIFIED sibling greps §1.4]; [ASSUMED from code trace] mixed→NaN→hide; clamp at :222 pre-dates fix |
| 9 | Missing Task/Agent/Wave/Report trailers on `6409d0e`, disclosed; amend forbidden | ✅ Yes | [RAN `git show 6409d0e --format=%B` → subject only]; same for `6a39460` (subject only) — see R-FINAL-001 |
| 10 | `f292a9c` stat "RunDetails +10/-2" | ❌ False (immaterial) | [RAN `git show f292a9c --numstat` → 8/2; "+10" sums ins+del]. Report-text typo, zero effect on docs/code verdict |

Claims checked: 10. Unsupported/false: 1 (claim 10, immaterial). All load-bearing claims verified.

## 3. Long-run test (independent answers)

- **Source:** Original source was unvalidated timestamps flowing through naive arithmetic into user-visible text (`Math.max(0, NaN)` = `NaN` renders as "NaN"). Fix addresses it at the invariant: `seconds` is `null` unless the diff is a real number, gated on `!== null`. Docs source was second-order drift (docs frozen at `2502fd9`, code moved at `f292a9c`); fix cites fixing SHA + date, so future staleness is `git log`-detectable. Both addressed at cause level.
- **Load (100×):** Pure O(1) render arithmetic, unchanged cost. No I/O, polling, or concurrency surface touched (`RunDetails` fetch/poll logic at :116-146 untouched). No unbounded loops/queues introduced.
- **Hostile input:** Garbage strings (both-side and single-side) → NaN → hidden [VERIFIED code trace]; missing/`null`/`undefined`/`""` → null → hidden; empty-string is falsy so takes the null branch (same observable outcome: chip hidden) [VERIFIED :217]. Sub-second truncation via `round` preserved; negative diff clamps to 0 (pre-existing). No injection/traversal surface — values are only formatted into a number slot (`Took {seconds} s` with `seconds` a number or null). `Infinity` cannot arise: both valid Dates are within ±8.64e15 ms of epoch, their difference is finite; JSON cannot transport `Infinity` anyway (becomes `null`).
- **Operability:** Rollback is `git revert f292a9c` (code+tests) and/or `git revert 6409d0e` (docs), no migration/data. Observability is good: two regression tests + re-runnable stale-phrase greps; invariant comment at :214-216 states the contract for future editors.
- **Reversal:** Which test fails if the fix is reverted? **Garbage-hide fails deterministically** under the pre-`f292a9c` formula ("Took NaN s" renders, `NaN` in body → both assertions fail); **zero-render passes both ways** by design (it pins the `0` boundary against a falsy overcorrection). Reasoned-only (no mutation run; read-only scope) but airtight on deterministic Date arithmetic — same mechanism the TREV reviewer node-confirmed. For the docs commit itself, reversal fails no test by nature (no executable effect); stale wording returns, detectable by grep.

## 4. Findings

### R-FINAL-001 [MINOR] Commits `6409d0e` and `6a39460` lack required Task/Agent/Wave/Report trailers

- Location: commit messages of `6409d0e` ("docs: mark P3 Took NaN s FIXED at f292a9c (T-004)") and `6a39460` ("docs(ops): W1-IMPL-04 T-004 implementation report (code commit 6409d0e)"); evidence: [RAN `git show --format=%B` → subject lines only, no trailers], STANDING-ORDERS §15 requires `Task:/Agent:/Wave:/Report:`.
- Why it matters: weakens log-level traceability (which task/agent/wave/report produced a commit) — mild, because SHAs + subjects + ledger/report chain already give full traceability.
- Recommended fix: **none on this branch** — `--amend` is forbidden (§13), content is correct, implementer self-disclosed, ledger records it. ORCH should enforce trailers on all subsequent commits. **Not push-blocking.**

### R-FINAL-002 [NIT] Dual test counts share `docs/tech-debt.md:17` (115/115 + 117/117)

- Location: `docs/tech-debt.md:17`. Evidence: historical `115/115` header (A1/B2/E at `2502fd9`) + new `+2 tests (117/117 at gate)` clause in one line [VERIFIED read].
- Why it matters: a future reader could misassign counts to fix batches. Brief-mandated verbatim citation retention, so this is a wording-density residual, not an error — both counts are true of their respective moments.
- Recommended fix: DO-LATER (next touch of the line): make genealogy explicit ("115/115 at 2502fd9; +2 P3 tests → 117/117 at gate"). Do not churn now.

### R-FINAL-003 [NIT] P3 tests don't pin mixed garbage/valid or negative-diff; `document.body.textContent` /NaN/ assertion is broad

- Location: `frontend/tests/runs.test.jsx:571-622`, code `RunDetails.jsx:220-222`. Evidence: only both-garbage and zero cases tested; mixed→same `Number.isNaN` branch holds by trace but is unpinned; negative diff clamps to "Took 0 s" (pre-existing, product call); `not.toMatch(/NaN/)` over the whole body would false-fail if any future fixture metric rendered the literal substring "NaN" (defense-in-depth that slightly overreaches — but it is also what catches a reformatted leak).
- Why it matters: small residual test-strength gap, identical to what prior reviewers deferred as nice-to-have; correctness of the shipped guard is unaffected (generic branch, no per-input special-casing that could diverge).
- Recommended fix: DO-LATER: add one mixed-garbage test (one field from `completedDetail` defaults, one `"garbage"`, same chip-hidden + no-NaN assertions). No negative-diff test unless product decides honesty over clamp.

No BLOCKER, no MAJOR. No band-aid patterns found (no error swallowing, blanket try/catch, sleep/retry, hardcoded test inputs, weakened tests, type suppression, TODO-instead-of-fix, or unit-under-test mocking; `renderApp` mocks transport, not the component — correct layer).

## 5. Attempts to break it

Concrete inputs/interleavings tried (code trace) or run (tests):

1. **Both garbage** (`"garbage"`/`"garbage"`) → `"garbage"` truthy → diff `NaN` → hidden [RAN garbage test: passed; [ASSUMED] pre-fix fail confirmed by formula trace]. ✅
2. **Single-side garbage** (valid/`"garbage"` and vice versa) → subtraction `NaN` → hidden [ASSUMED by trace; unpinned test — R-FINAL-003]. The other timestamp is irrelevant to the `Number.isNaN` branch, so behavior is identical to case 1 by construction.
3. **Missing/null/empty** (one or both undefined/null/`""`) → falsy guard → `durationMs null` → hidden [ASSUMED by trace; pre-existing suite renders missing-timestamp runs without crash]. ✅ behaves as invariant states.
4. **Zero** (identical valid instants) → `0` → `seconds 0` → renders "Took 0 s" [RAN zero test: passed]. ✅ falsy trap avoided by `!== null`.
5. **Negative diff** (`finished < started`) → `Math.max(0,…)` → renders "Took 0 s" [ASSUMED by trace]. Pre-existing honest-display question, not a NaN leak; no docs claim contradicts it.
6. **Falsy short-circuit mutation** (gate changed to `seconds && …`) → zero test would fail (chip disappears) [ASSUMED; standard React falsiness]. Mutation killed by the zero test by design.
7. **Inverted/removed guard** → garbage test fails (case 1) or valid chips vanish [ASSUMED; garbage+zero pair brackets both directions].
8. **Docs contradiction hunt**: re-read both edited lines fully + grep stale phrases → zero live P3-unfixed claims; `115/115`/`113/113` figures describe Phase E history, not P3 [RAN]. ✅

No input produces a "Took NaN s", "Took Infinity s", or crash in the fixed code. No doc statement contradicts HEAD code.

## 6. Dimension checklist

- **Correctness:** PASS — guard + gate + docs all true of HEAD; scoped 14/14 [RAN].
- **Root cause vs symptom:** PASS — null-sentinel invariant at render boundary + paper-trail correction; no code churn for docs-only drift.
- **Regression/compat:** PASS — additive tests, single-file display guard; no API/schema/contract change; `wall_seconds` non-use preserved (pre-existing semantics).
- **Concurrency/idempotency:** PASS (trivially) — pure render derivation; no shared state, no poll/timer change.
- **Error handling:** PASS — explicit `null` for unparseable/missing, no exception/exception-swallow introduced.
- **Security/abuse:** PASS — no secrets/PII, no new input surface; garbage strings neutralized, not echoed.
- **Performance/scalability:** PASS — O(1) arithmetic.
- **Migration/rollback:** PASS — `git revert` revertible, no migration.
- **Observability:** PASS (MINOR note R-FINAL-001 trailers) — tests + greps re-runnable.
- **Maintainability/conventions:** PASS — invariant comment at the guard, existing `describe` conventions followed, no drive-by cleanup.
- **Docs impact:** PASS — this wave *is* the docs correction; code, tests, and both docs now agree; "117/117 at gate" is gate-verified.

## 7. Optimization and simplification opportunities

| # | Location | Evidence | Impact | Effort | Risk | Verdict |
|---|---|---|---|---|---|---|
| 1 | Mixed-garbage test (R-FINAL-003) | §4 | Pins the shared NaN branch against future input-table drift | Small (clone garbage test, one field default) | Low | DO LATER (nice-to-have, not owed) |
| 2 | Negative-diff honesty (hide chip vs clamp 0s) | §4 | Display honesty under clock skew | Small code + product decision | Product call needed; changes visible behavior | NOT WORTH IT for this run (correctly deferred/pre-existing) |
| 3 | Consume backend `wall_seconds` instead of recomputing from timestamps | fixtures carry `wall_seconds` (runs.test.jsx:44, helpers.jsx:664), view ignores it | Removes duplicated duration authority | Cross-layer (frontend + backend contract) | Medium — wider than P3 scope, semantics change | NOT WORTH IT for this run (preserved pre-existing behavior; needs its own spec) |

## 8. Cross-agent / cross-task interactions observed

- Write-sets were disjoint: T-001 (`f292a9c`) owned code+tests, T-004 (`6409d0e`) owned the two docs — verified by numstats with zero overlap [RAN]. No parallel-edit conflict, no hotspot violation (`frontend/format.js` untouched in this diff).
- `6409d0e` correctly follows `f292a9c` (docs-after-code) and `6a39460` only adds the implementer report — wave frontend diff `69fe44e..HEAD` is empty, so no agent touched frontend after the fix [RAN, 0 diff lines]. No cross-task regression surface.
- ORCH gate (`gate-w1-1.md`, 117/117 + build green at HEAD) is the owner of the full-suite count; this review corroborates (scoped 14/14 + arithmetic) without duplicating it. Ledger T-004/T-003/T-002 dispositions are consistent with my findings; R-W1-001 is carried as R-FINAL-001 with the same ACCEPT disposition.

## 9. What I could not verify

- **Full suite (117/117) and `npm run build` at HEAD** — explicitly NOT run by me (brief: gate owns them; scoped-only budget). Taken from `gates/gate-w1-1.md` (117/117, 1670 modules, green at `6a39460`). My own evidence is scoped `runs.test.jsx` 14/14 [RAN].
- **Backend pytest** — NOT-RUN (frontend-only diff; accepted risk per mission). No backend files in scope, so nothing to regress there.
- **Chromium visual / screen-reader probes** — not run (jsdom-only verification, carried in tech-debt as accepted risk; outside this brief).
- **Production data reality** — whether real rows contain garbage timestamps: needs DB access, out of scope, and irrelevant to verdict (fix is defensive + test-pinned either way).
- **Mutation execution** — reversal is deterministic-reasoned, not demonstrated in a temp worktree (read-only scope, standard JS Date semantics); TREV additionally node-confirmed the NaN mechanism.
- PR #2 description/body and `AGENTS.md` drift notes flagged in investigations — outside this diff's scope of truth; left to ORCH, correctly not touched.
