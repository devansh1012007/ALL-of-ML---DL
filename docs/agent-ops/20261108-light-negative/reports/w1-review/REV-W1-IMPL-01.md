<!-- ORCH-DIGEST:START -->
agent: W1-REV-01 | scope: wave 1 / T-102 + T-103 | verdict: APPROVE
findings: BLOCKER 0 | MAJOR 0 | MINOR 0 | NIT 2
claims_audit: 24 claims checked / 0 unsupported or false
band_aids_found: none
top_3_risks: production negative-row reachability assumed (no live DB) — accepted per mission A-010 | hidden tests not re-run by reviewer (scoped git/grep only) | timeAgo future-clamp is similar shape but out of scope
optimizations: DO-NOW 0 | DO-LATER 1 | NOT-WORTH-IT 2
reversal_check: reasoned-only (no mutation executed - read-only)
confidence: high (both diffs byte-checked; two new tests inspected line-by-line; execution results are implementer-reported, not re-run)
<!-- ORCH-DIGEST:END -->

# Code review — W1-REV-01 (T-102 ca5d950 + T-103 9c73971)

## 0. Method
Diff range reviewed, files read in context, commands run. Order followed: blind pass first, then implementer report.

- Blind pass (before reading implementer reports): [RAN `git show ca5d950` -> RunDetails 1-line + comment + 2 tests] , [RAN `git show 9c73971` -> docs one-line reword] , [VERIFIED frontend/views/RunDetails.jsx:214-239] , [VERIFIED docs/tech-debt.md:14-22] , [VERIFIED frontend/tests/runs.test.jsx:571-672] , [VERIFIED frontend/format.js:24-38] , [RAN grep Took|durationMs|started_at|finished_at in frontend/views/ -> only RunDetails.jsx duration site] , [RAN `git diff 9c73971^..9c73971 --stat` -> 1 file, 1 ins/1 del] , [RAN `git diff -U0 -- docs/tech-debt.md` -> single hunk @@ -17 +17 @@] , branch [RAN `git branch --show-current` -> frontend-ui-round2].
- Then read: `W1-IMPL-01-T-102.md`, `W1-IMPL-02-T-103.md`, `INV-negative-counts.md` (spec), plus briefs W1-IMPL-01/02.
- Scoped checks only (git show/diff/grep/read + byte-compare scripts via PowerShell). No vitest/build/full suite run per brief §4 — see §9.

## 1. Blind-pass findings (before reading implementer reports)

### T-102 correctness — `durationMs < 0` check [VERIFIED frontend/views/RunDetails.jsx:218-223]
```jsx
const durationMs = run.started_at && run.finished_at
  ? new Date(run.finished_at) - new Date(run.started_at)
  : null;
const seconds = durationMs === null || Number.isNaN(durationMs) || durationMs < 0
  ? null
  : Math.max(0, Math.round(durationMs / 1000));
```
And chip `{seconds !== null && <span>Took {seconds} s</span>}` [VERIFIED :239]. Verdict: correct, fail-closed to hidden.
- Negative diff (`-60000`): `<0` → null → hidden. Previously `Math.max(0,round(-60))=0` → false "Took 0 s". Fixed at the display predicate (root), not at test inputs.
- Zero (`finished==started`): `0<0` false → `Math.max(0,0)=0` → renders. Render uses `!==null`, not falsiness, so true zero visible. Preserved.
- Sub-second positive (400ms): `400<0` false, `round(0.4)=0` → "Took 0 s" (legitimate rounding). Preserved, no honesty loss.
- `Math.max(0,·)` kept [VERIFIED :223] as brief required; now redundant for negatives but harmless defense-in-depth. Correctly not removed.
- Comment [VERIFIED :214-217] "parses to a non-negative diff; NaN … or finished<started must hide" — accurate, includes 0 as non-negative. No drift.
- Other duration sites: grep finds exactly ONE "Took" production site [VERIFIED frontend/views/ grep: only RunDetails.jsx:239; INV confirms]. `format.js:29` `timeAgo` also clamps with `Math.max(0,·)` but is relative-time ("just now" for future), different semantics — see NIT-02, not in T-102 scope.

### T-103 correctness — line 17 reword [VERIFIED docs/tech-debt.md:17]
Old: `(FIXED …, `frontend-ui-round2` 115/115).` … tail `…still renders); +2 tests (117/117 at gate).`
New: `(FIXED …, `frontend-ui-round2` 115/115 at 2502fd9; +2 P3 tests → 117/117 at gate).` … tail `…still renders).`
[RAN `git diff --stat` -> 1 ins/1 del] [RAN `git diff -U0` -> only -17/+17] [RAN PowerShell substring compare -> middle segment `092e800`/`64c99f8`/`6c72d75`/`f292a9c` byte-equal True, tail-contains-`117/117` False]. Verdict: exact intended genealogy text; all 4 citations byte-identical; only line 17 changed; lines 18-22 untouched. (Note: brief says "all 4 citations" — that is 092e800, 64c99f8, 6c72d75, f292a9c; INV line 118 uses the same four. Header's `2502fd9` is a commit qualifier, correctly not counted as a citation.)

### Band-aid sweep (blind)
- No special-casing of the negative test values: predicate is generic `durationMs < 0` for any negative number; no literal `00:01:00Z`/`-60000` in production code.
- No optional-chaining hack, no `eslint-disable`/`@ts-` suppression, no blanket try/catch, no sleep in ca5d950 (diff grep clean; pre-existing `run.metrics?.` at :212 is unrelated context).
- No test weakening: zero test untouched (see §2), existing P3 tests only appended to.

Blind conclusion: no blocker/major; formal findings NIT-01/02 only (below).

## 2. Claims audit
Implementer-report [RAN …] execution results were *not* re-run by this reviewer (scoped git/grep only per brief §4). Code/diff claims were re-checked independently. "REPORTED-RAN" = implementer executed it; I inspected the artefacts it would produce, not the process output.

| Implementer claim | Verified? | Evidence / finding |
|---|---|---|
| T-102: only 2 files changed | ✅ Yes | [RAN `git show --name-only ca5d950`] -> `runs.test.jsx` + `RunDetails.jsx` only; [RAN `git diff --stat ca5d950^..ca5d950`] -> 2 files, 54 ins/3 del |
| T-102: negative diff hides chip, no Took/NaN | ✅ Yes (design) | [VERIFIED RunDetails.jsx:221-223]: `durationMs<0`→null→`:239` hidden; test at [VERIFIED runs.test.jsx:623-646] asserts `/took/i` absent + no NaN. Execution outcome REPORTED-RAN (see below) not re-run by reviewer |
| T-102: mixed garbage/valid hides chip | ✅ Yes (design) | [VERIFIED :221]: one garbage→NaN→`isNaN`→null; test [VERIFIED :648-671]. Generic over either side (subtraction symmetric); only `started=garbage` exercised — see NIT-01 |
| T-102: zero duration still renders "Took 0 s", zero test unmodified | ✅ Yes | [RAN compare parent vs new test file `:596-621`] -> zero test byte-identical; [VERIFIED :597-621]. Production: `0<0`=false + `!==null` gate preserves. Diff appends after `:619`, does not touch zero block |
| T-102: 16/16 scoped vitest pass | ⚠️ Reported-only | REPORTED-RAN `cd frontend; npx vitest run tests/runs.test.jsx -> 16/16` (W1-IMPL-01 §7). I did NOT re-run (brief: grep/git-show only, never full suite/build). Count 14+2 is consistent with file (4 P3 tests + earlier). Cannot independently confirm green without execution — see §9 |
| T-102: pre-fix negative test fails (reversal proof) | ⚠️ Reported-only | REPORTED-RAN pre-fix `1 failed/15 passed`, failure `found <span>Took 0 s</span>` at `:644`. Plausible from code (pre-fix Math.max coerces -60→0 [VERIFIED :223 parent]); not re-executed by reviewer |
| T-102: mixed test passes pre-fix as control | ✅ Yes (design-consistent) | Pre-fix `isNaN` already hid NaN [VERIFIED parent :220]; REPORTED-RAN consistent. No code change needed for mixed |
| T-102: `Math.max` kept | ✅ Yes | [VERIFIED RunDetails.jsx:223] `Math.max(0, Math.round(...))` retained |
| T-102: comment reword accurate | ✅ Yes | [VERIFIED :214-217] "non-negative diff … finished<started" matches code `isNaN \|\| <0` |
| T-102: generic sign check (no band-aid) | ✅ Yes | `durationMs<0` generic; no eslint-disable, no literal-date match (blind §1) |
| T-102: single duration site, no wall_seconds touch | ✅ Yes | [RAN grep `wall_seconds\|Took` in frontend/views/] -> only RunDetails chip; diff touches no backend/wall_seconds |
| T-102: root cause = display honesty, not parsing | ✅ Yes | Agree: negative parses (not NaN) yet Math.max normalizes to false 0; invariant now "parses AND non-negative" |
| T-102: no ownership violation / no deferred deps | ✅ Yes | Write-set exactly RunDetails + runs.test + report; no NEED needed |
| T-102: production reachability uncertain (assumed) | ✅ Yes — honest | Report §15 flags no live-DB inspection. INV §4 concurs [ASSUMED]. Reviewer accepts as appropriately stated unknown |
| T-103: exactly one hunk, line 17 only | ✅ Yes | [RAN `git diff -U0 9c73971^..9c73971`] -> `@@ -17 +17 @@` only; `--stat` 1 ins/1 del |
| T-103: header literal + no tail `117/117` | ✅ Yes | [VERIFIED tech-debt.md:17] header contains `115/115 at 2502fd9; +2 P3 tests → 117/117 at gate`; [RAN substring check] tail after `P3 "Took` contains no `117/117` |
| T-103: 4 citations byte-identical | ✅ Yes | [RAN substring compare] middle segment containing `092e800`,`64c99f8`,`6c72d75`,`f292a9c` equal OLD vs NEW (True); P3 tail segment `f292a9c` intact |
| T-103: lines 18-22 byte-identical | ✅ Yes | Single `-17/+17` hunk proves; lens (`Runs row click … Backend pytest`) untouched in diff |
| T-103: docs-only, no code/test/docs touched | ✅ Yes | [RAN `git show --name-only 9c73971`] -> `docs/tech-debt.md` only |
| T-103: verbatim line matches INV, no BLOCKED | ✅ Yes | New line equals INV §D1 line 118 [VERIFIED INV-negative-counts.md:118] verbatim (visual compare via `git show …:17`; citations + arrow `→` match) |
| T-103: NOT-RUN tests justified (docs) | ✅ Yes | Agree: prose has no executable effect; diff-gate is the acceptance (brief W1-IMPL-02 §7). No test run needed |
| T-103: no forbidden-zone/terms added | ✅ Yes | New line adds no light-mode note, no light-mode/lines 18-22 rewrites; only genealogy text | 

24 claims checked / 0 unsupported-or-false. Two T-102 execution claims are marked ⚠️ Reported-only, **not** false — they are simply un-re-runnable within reviewer scope (statements are internally consistent with the diff; blast radius is only the displayed chip).

## 3. Long-run test (independent answers)

- **Source / data corruption:** Negative diffs arise from clock skew/NTP steps, corrupt/legacy rows, or wire drift (INV §N1 backend-reachability [ASSUMED]; same `_now()` single-clock happy path means production prevalence is low/unknown). The fix makes the display predicate fail-closed: any negative, any NaN, any missing side → chip hidden, never a fabricated number. Hardware/clock behaviour cannot produce a false "Took 0 s" any more; zero renders only for a genuine non-negative round-to-zero.
- **Load (100×, concurrency, partial failure):** One extra numeric comparison per render of RunDetails; no I/O, no state, no queue interaction. Poll re-renders pay the same two `new Date` subtractions as before. No new failure mode. T-103: static prose, zero runtime cost.
- **Hostile input:** Negative/huge/garbage/missing timestamps are all handled: garbage → NaN → hidden; negative → hidden; missing → null → hidden; huge positive → passes predicate and renders a large integer (unchanged, honestly a large duration — timestamps are never rendered raw, `formatWhen` returns "—" for garbage, so no injection surface enters the chip). Injection/oversized-payload concerns are outside this one-line display guard and unchanged by it.
- **Operability:** Pure display + docs; rollback = revert `ca5d950`/`9c73971` one-liners. No migration, no config, no secret. Corrupt timestamps remain visible in DB/logs for operators (hide-chip does not delete data). Observability unchanged: chip absence is itself signalled by the null sentinel convention already used for NaN.
- **Reversal:** Reverting `|| durationMs < 0` restores `Math.max(0,round(-60))=0`, so the new negative-diff test (asserts no `/took/i`) would fail while zero/mixed stay green — genuine reversal coverage for N1 (reasoned from code semantics; implementer REPORTED-RAN confirms pre-fix failure with the exact bug text). Reverting 9c73971 restores dual-count ambiguity; no test guards prose, diff-gate is the reversal check.

## 4. Findings

### R-W1-001 [NIT] Mixed test exercises only `started=garbage`, not `finished=garbage`
- Location: `frontend/tests/runs.test.jsx:648-671` · Evidence: the test sets `started_at:'garbage'`, `finished_at` valid; subtraction is symmetric so both sides yield NaN through the same `Number.isNaN(durationMs)` branch · Why it matters: minimal — one direction already proves NaN genericity (the pre-existing both-garbage test covers the other logical corner), so this is a coverage nicety, not a correctness gap · Recommended fix: no change required to approve; optionally add/film the symmetric direction only if touching the file next.

### R-W1-002 [NIT] `format.js timeAgo` still clamps future dates to "just now" (same honesty shape, out of scope)
- Location: `frontend/format.js:29` (`Math.max(0, Math.round((Date.now()-d.getTime())/1000))`) · Evidence: future timestamp → `seconds=0` → "just now" · Why it matters: n/a for this wave — `timeAgo` is relative-time ("just now" for a slightly-future/created-in-future row is the documented canonical behaviour, and T-102's mandate was the "Took" duration chip, where the grep proves no other site exists). Noted only so a future honesty pass can consciously decide whether a future `created_at` should hide/`—` instead. · Recommended fix: none this wave; DO-LATER discussion only (see §7).

No BLOCKER/MAJOR/MINOR found on either task.

## 5. Attempts to break it
Reasoned (read-only; no test execution, no mutation of source). Predicate: `durationMs===null || isNaN || <0 → null else max(0,round(/1000))`.

| Input (finished − started) | durationMs | Outcome | Honest? |
|---|---|---|---|
| −60 s (spec negative) | −60000 | hidden | ✅ Was false "Took 0 s" |
| −1 ms (boundary) | −1 | hidden (`-1<0`) | ✅ Tiny skew hides rather than lies 0 |
| −999 ms | −999 | hidden | ✅ No threshold games — any negative hides (by design) |
| 0 ms (zero) | 0 | "Took 0 s" | ✅ True zero |
| −0 | −0 (`-0<0`=false) | "Took 0 s" | ✅ True zero; also unreachable — subtracting equal Dates yields +0 |
| 400 ms (sub-second) | 400 | "Took 0 s" | ✅ Legit rounding, preserved |
| 999 ms | 999 | "Took 0 s" (`round(0.999)=1`? actually `round(0.999)=1` → "Took 1 s" — still honest rounding) | ✅ |
| garbage/valid → NaN | NaN (`NaN<0`=false but `isNaN` catches) | hidden | ✅ Order `isNaN`+`<0` handles NaN correctly |
| valid/garbage → NaN | NaN | hidden | ✅ Symmetric |
| missing one side | null | hidden | ✅ Pre-existing |
| Infinity | n/a | — | ✅ Unreachable: `Date−Date` bounded by ±max Date ~8.64e15; unparseable sides give NaN. If `Infinity` ever occurred, `max(0,round(Infinity))` would render "Infinity" — cannot occur from these inputs, so no guard needed |
| huge positive (e.g. 10 days) | +864000000 | "Took 864000 s" | ✅ Honest, unchanged, out of scope |

What I did *not* do: execute vitest (out of reviewer scoped-checks scope) and jack in test fixtures to mutate `durationMs`; all break-attempts above are arithmetic reasoning against the exact predicate at [VERIFIED RunDetails.jsx:218-223]. The predicate survives every hostile input in the table by construction (null/NaN/negative → hidden; everything else → clamped round).

## 6. Dimension checklist
| Dimension | Verdict | Notes |
|---|---|---|
| Correctness | ✅ Pass | Negative hides; zero/sub-second preserved; NaN ordering correct; citations byte-exact |
| Root cause vs symptom | ✅ Pass | Nulls the computed duration (unknown) instead of clamping to a false 0; no test-input special-casing |
| Regression / compat | ✅ Pass | Zero test byte-identical and green per design; only one render site changes; no API/shape change |
| Concurrency / idempotency | ✅ Pass | Pure render-time predicate; no state, no retry, no race surface |
| Error handling | ✅ Pass | Fail-closed to hidden for null/NaN/negative; garbage never rendered raw |
| Security / abuse | ✅ Pass | No new input, no secrets/PII; timestamps bounded, no ReDoS/traversal risk introduced |
| Performance / scalability | ✅ Pass | One extra comparison per render |
| Migration / rollback | ✅ Pass | Revert one line each; no migration |
| Observability | ✅ Pass | Convention preserved: null sentinel = unknown (established by P3 NaN fix) |
| Maintainability / conventions | ✅ Pass | Comment updated with code; same test harness pattern as P3 block; no new deps; `Math.max` retained as documented defense-in-depth |
| Docs impact | ✅ Pass | T-103 genealogy unambiguous once; lines 18-22 untouched; no stale duplicates |

## 7. Optimization and simplification opportunities
| # | Location | Evidence | Impact | Effort | Risk | Verdict |
|---|---|---|---|---|---|---|
| O-1 | `frontend/format.js:29` future-clamp | `timeAgo` renders "just now" for future dates | Low (relative-time semantic, not a duration lie) | Small | Changing affects many views | DO LATER (separate honesty pass, conscious product call) |
| O-2 | Remove now-redundant `Math.max(0,·)` | Negatives filtered before it | ~0 (pure tidiness) | Trivial | Loses defense-in-depth | NOT WORTH IT — brief explicitly forbids removal in same change |
| O-3 | Split/reshape `isNaN … \|\| <0` ordering | `NaN<0` is false, so order matters only for NaN | None (current order correct) | Trivial | Churn | NOT WORTH IT |

## 8. Cross-agent / cross-task interactions observed
- `W1-IMPL-01 (ca5d950)` and `W1-IMPL-02 (9c73971)` are disjoint (RunDetails/tests vs tech-debt) — no file overlap, no merge interaction observed.
- C1 ordering (INV §N1/§5): T-102 landed before any light-mode JSX churn (T-101), satisfying the "land N1 first" recommendation; no conflict observed in this diff window.
- `docs/tech-debt.md` single-writer (T-103) respected; no other writer touched it in the two commits.
- `frontend-ui-round2` branch discipline confirmed [RAN `git branch --show-current`].

## 9. What I could not verify
- Test execution: I did **not** re-run `npx vitest run tests/runs.test.jsx` (brief §4: scoped greps/`git show` only — never full suite/build). The 16/16 pass and pre-fix 1-fail reversal are therefore implementer-REPORTED-RAN, cross-checked against the diff and code semantics but not independently executed. [UNKNOWN] whether a re-run would be green in this environment (e.g. Progress-poll flake); ORCH gate owns the authoritative run.
- Production negative-row reachability: [ASSUMED] clock-skew/corrupt-row paths only; no live-DB inspection (both INV §4 and W1-IMPL-01 §15 state this honestly). Cannot quantify live prevalence — and the fix does not depend on prevalence (hide-chip is correct whether rows are rare or real).
- Wall-seconds/alternative product options: reviewed only as INV Options B/C/D summaries; not independently re-derived beyond confirming the brief's "do not touch wall_seconds" boundary was respected in the diff.
- Reversal by mutation: reasoned-only (I am read-only; reverting source to watch tests fail would violate my write-set). Arithmetic reasoning + implementer pre-fix run cover this adequately.

---

**Verdict: APPROVE** — both tasks meet their measurable acceptance criteria with no BLOCKER/MAJOR/MINOR; the two NITs are non-blocking notes (test symmetry + out-of-scope timeAgo shape). The implementers did not cheat: the predicate is generic, `Math.max` retained, zero preserved, tests behaviour-focused (negative test would genuinely fail pre-fix; mixed test proves NaN genericity), and the docs reword moves counts into the header verbatim while keeping every citation byte-identical and every neighbouring line untouched.
