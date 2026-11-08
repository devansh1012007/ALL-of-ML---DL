<!-- ORCH-DIGEST:START -->
agent: W1-REV-01 | scope: wave 1 / T-004 (6409d0e) | verdict: APPROVE
findings: BLOCKER 0 | MAJOR 0 | MINOR 1 | NIT 2
claims_audit: 17 claims checked / 1 unsupported
band_aids_found: none
top_3_risks: 117/117 count is gate-observed, not re-run here (PARTIAL) | two counts on tech-debt:17 may confuse future readers | missing commit trailers weaken traceability (mitigated by report SHA)
optimizations: DO-NOW 0 | DO-LATER 1 | NOT-WORTH-IT 1
reversal_check: reasoned-only (docs-only change; code reversal pinned by pre-existing garbage test per INV-frontend-P3 reasoning)
confidence: high (diff, code, tests, and greps verified directly; 117/117 explicitly not verified)
<!-- ORCH-DIGEST:END -->

# Code review — W1-REV-01 (T-004 docs-close, commit 6409d0e)

## 0. Method
Reviewed commit `6409d0ea397aa3f6872719451411967fe4c73989` on branch `frontend-ui-round2`
[RAN `git branch --show-current` -> `frontend-ui-round2`]. Order followed per brief §3:

1. **Blind pass first** — `git show 6409d0e` (full diff + `--stat` + `--numstat`), then read
   `docs/tech-debt.md:14-22`, `docs/plans/2026-11-08-frontend-deferred-followups.md:107-113`,
   `frontend/views/RunDetails.jsx:214-238`, `frontend/tests/runs.test.jsx:571-619`, plus scoped
   greps over both docs files and `docs/`. Findings (§1) were formed before opening any
   implementer/investigation report.
2. **Required reading** — STANDING-ORDERS, review-code template, W1-IMPL-04 brief, then
   investigation reports INV-frontend-P3 and INV-docs-PR, then the implementer report
   W1-IMPL-04-T-004 for the claims audit (§2).
3. **Scoped checks only** — `git show`, `grep`, `read`. Full test suite / build NOT run
   (brief §6; ORCH gate owns that). The single-file `runs.test.jsx` suite was NOT re-run by me
   either; the implementer's 14/14 claim is corroborated by INV-frontend-P3's independent run
   (see §2, claim 13).

COMMS.md read at start: Log section empty, last line 33 [VERIFIED COMMS.md:33].

## 1. Blind-pass findings (before reading implementer reports)

1. **Scope is exactly clean.** `git show 6409d0e --stat` touches only two files, one line each:
   `docs/tech-debt.md` (1+/1-) and `docs/plans/2026-11-08-frontend-deferred-followups.md`
   (1+/1-) [RAN `git show 6409d0e --numstat` -> 1/1 per file]. No code, test, or frontend file
   in the diff. No collateral edits, no drive-by cleanup, no whitespace churn outside the two
   P3 sentences.
2. **Both stale sentences are fully removed, and the replacements match the code.**
   - `docs/tech-debt.md:17`: trailing `P3 remainder: … "Took NaN s" (not a date leak; future
     phase).` is replaced by `P3 "Took NaN s" (FIXED 2026-11-08, f292a9c): … hides on NaN diff
     (null sentinel; valid 0s still renders); +2 tests (117/117 at gate).`
     [VERIFIED tech-debt.md:17]. This is accurate against `RunDetails.jsx:214-222,238`:
     `durationMs` is `null` when either timestamp is falsy, `seconds` is `null` when
     `Number.isNaN(durationMs)`, and the chip renders only under `seconds !== null`
     [VERIFIED RunDetails.jsx:217-222,238]. A valid 0 (`finished == started`) yields
     `durationMs 0` -> `seconds 0` -> renders `Took 0 s`, so "valid 0s still renders" is true.
   - `docs/plans/...-followups.md:113` (F5): `New P3 backlog: … (not fixed here).` is replaced
     by `P3 FIXED f292a9c (2026-11-08): … hides on NaN diff (null sentinel; valid 0s still
     renders "Took 0 s"); +2 tests in runs.test.jsx (garbage-hide, zero-render).`
     [VERIFIED followups.md:113]. Both test names map to real tests:
     `runs.test.jsx:573` (garbage hides chip, asserts no `/took/i` and no `NaN`) and `:597`
     (zero renders `Took 0 s`) [VERIFIED runs.test.jsx:571-622].
3. **Lines 18-22 of tech-debt are untouched.** The diff hunk for tech-debt covers only line 17
   [RAN `git show 6409d0e` -> single hunk @@ -14,7]. Parent vs HEAD lines 18-22 (B1 `c2dd5db`,
   C1 `87a6f08`, D1 `736339a`, light-mode deferred, backend-pytest NOT-RUN) are identical
   [VERIFIED via `git show 6409d0e^:docs/tech-debt.md` lines 18-22 vs current file].
4. **Acceptance greps pass.** Grep `future phase|remainder|not fixed here|New P3 backlog` over
   `docs/tech-debt.md` -> zero hits for P3 (the only "Took NaN" hit is the new FIXED title on
   line 17). Over the plan -> one `remainder` hit at line 12, `B–D are the remainder`, which
   is about phases B–D, not P3, and is outside the two P3 sentences [VERIFIED followups.md:12].
   No remaining text in either file claims P3 is unfixed.
5. **A1/B2/E citations on tech-debt:17 are preserved verbatim** (`092e800`, `64c99f8`,
   `6c72d75`, "No `"Invalid Date"` string reachable… (grep-verified)") [VERIFIED diff]. The
   `115/115` header on line 17 is historical (A1/B2/E state at `2502fd9`); the new clause
   carries its own `117/117 at gate` note. Slightly dense but not false — and the brief
   mandated keeping citations verbatim (see NIT-2).
6. **Commit-message trailers are missing.** `git show 6409d0e --format=%B` shows only the
   subject `docs: mark P3 Took NaN s FIXED at f292a9c (T-004)` — no `Task:`/`Agent:`/`Wave:`/
   `Report:` trailers required by STANDING-ORDERS §15. Content, paths, and branch are correct.
   This is a process miss, not a content defect; `--amend` is forbidden (§13), so it cannot be
   retro-fixed. Rated MINOR (R-W1-001), not a blocker.
7. **"117/117 at gate" is the weakest claim in the new docs text and is not verifiable here.**
   Arithmetic supports it (115 at `2502fd9` + exactly 2 new `it()` blocks in `f292a9c`
   [RAN `git show f292a9c --numstat` -> 53/0 tests, 8/2 view]), and both investigators flag
   the full-suite count as PARTIAL pending the ORCH gate. The wording "at gate" attributes the
   count to the gate rather than to this docs commit, which is the honest hedge. Not a false
   claim; explicitly recorded under "could not verify" (§9).

Blind-pass verdict before reading reports: change is correct, minimal, and complete against the
brief's acceptance criteria, with one MINOR process finding (trailers) and no content findings.

## 2. Claims audit

Implementer report: `docs/agent-ops/20261108-p3-wave/reports/w1-impl/W1-IMPL-04-T-004.md`.

| Implementer claim | Verified? | Evidence / finding |
|---|---|---|
| 1. Pre-edit tech-debt:17 ended `P3 remainder: … future phase).` | ✅ Yes | [RAN `git show 6409d0e^:docs/tech-debt.md` -> line 17 matches verbatim] |
| 2. Pre-edit plan:113 F5 ended `New P3 backlog: … not fixed here).` | ✅ Yes | [RAN `git show 6409d0e^:docs/plans/...` -> line 113 matches verbatim] |
| 3. `f292a9c` = RunDetails.jsx "+10/-2", runs.test.jsx +53 | ❌ False (immaterial) | [RAN `git show f292a9c --numstat` -> RunDetails 8/2, tests 53/0]. "+10" counts total changed lines, not insertions; off by the deletion count. Report-text typo only; does not affect the docs change. See NIT-1. |
| 4. Head code: `durationMs` split, `Number.isNaN -> null`, chip gated `seconds !== null` (:214-222,238) | ✅ Yes | [VERIFIED RunDetails.jsx:214-222,238] on current HEAD |
| 5. Pre-fix formula + NaN mechanism (`Math.max(0,NaN)=NaN`, `NaN!==null` renders) | ✅ Yes | Matches INV-frontend-P3 root-cause chain; standard JS semantics; consistent with `git show f292a9c` diff |
| 6. Two P3 tests exist at :573 and :597 | ✅ Yes | [VERIFIED runs.test.jsx:571-622] names and assertions as quoted |
| 7. Log/head sequence: f292a9c in history, docs last touched at 2502fd9 (stale because pre-fix) | ✅ Yes | [RAN `git log --oneline -4` -> 6a39460, 6409d0e, 0053765, 69fe44e]; f292a9c ancestry confirmed by investigators |
| 8. Branch `frontend-ui-round2` verified before commits | ✅ Yes | [RAN `git branch --show-current` -> `frontend-ui-round2`] |
| 9. tech-debt:9 "P3 low test-strength notes" is a different (Round-1) P3, left untouched | ✅ Yes | [VERIFIED tech-debt.md:9] still present; not in the 6409d0e diff |
| 10. Plan line 12 "B–D are the remainder" is non-P3, out of scope | ✅ Yes | [VERIFIED followups.md:12] — my grep confirms exactly this single `remainder` hit |
| 11. Diff stat: 2 files, 2 insertions, 2 deletions; only the two P3 sentences | ✅ Yes | [RAN `git show 6409d0e --numstat` -> 1/1 + 1/1]; single hunk per file |
| 12. Lines 18-22 byte-identical; A1/B2/E citations verbatim | ✅ Yes | [VERIFIED diff hunks + parent/HEAD comparison] (§1.3, §1.5) |
| 13. Scoped run `runs.test.jsx` 14/14, incl. both P3 tests; Progress-poll passed | ⚠️ Supported, not re-run by me | Implementer reports duration 7.42s; INV-frontend-P3 independently ran the same file -> 14/14 [INV-frontend-P3.md:26,94]. Two independent runs agree. I did not re-run (scoped-check budget; flake risk unneeded). |
| 14. Post-edit greps: zero P3 hits for `future phase|not fixed|remainder` in tech-debt; plan only line 12 | ✅ Yes | Independently reproduced with `grep` (§1.4) |
| 15. "117/117 at gate" rests on ORCH baseline + arithmetic, NOT run by implementer; flagged as least-confident | ✅ Yes (honest PARTIAL) | Disclosed in report digest, §7, §14, §15; matches INV PARTIAL rating [INV-frontend-P3.md:46,127]. Wording "at gate" is a fair attribution. Gate T-003 must confirm (§9). |
| 16. Missing Task/Agent/Wave/Report trailers on 6409d0e; amend forbidden; disclosed | ✅ Yes | [RAN `git show 6409d0e --format=%B` -> subject only, no trailers]. Disclosure accurate; severity judged in R-W1-001. |
| 17. "Append" vs "replace" on F5: append would retain "(not fixed here)" and fail acceptance #1 | ✅ Yes (sound interpretation) | [VERIFIED followups.md:113] — replaced sentence contains no stale phrase; appending after it would. Only self-consistent reading. |

Claims checked: 17. Unsupported/false: 1 (claim 3, immaterial report-text stat). Partial by
design and disclosed: claims 13 and 15.

No violated acceptance criterion: (a) no text in either file claims P3 unfixed ✅,
(b) lines 18-22 byte-identical ✅, (c) commit touches only the two docs files ✅.

## 3. Long-run test (independent answers)

- **Source:** Docs drift is the source. This commit addresses it at the right level: the new
  wording cites the fixing SHA (`f292a9c`) and date, so future staleness is detectable via
  `git log` without re-reading code. I agree with the implementer's drift-level framing.
- **Load (100x):** N/A — docs-only. No runtime, render, or I/O path touched; zero performance
  surface change.
- **Hostile input:** N/A — no input surface. The underlying code case (garbage timestamp
  strings) is already pinned by the landed garbage-hide test; this commit neither weakens nor
  strengthens it.
- **Operability:** Rollback is `git revert 6409d0e` (single docs commit, no migration, no
  data) [VERIFIED --numstat]. Observability: the acceptance greps are re-runnable by anyone
  (`future phase`, `not fixed here`, `remainder` over the two files). The missing trailers
  reduce log-level traceability slightly, mitigated by the SHA recorded in the implementer
  report (§17), this review, and the ledger.
- **Reversal:** Which test fails if the fix is reverted? For the *docs* commit: none —
  docs have no executable effect; reverting restores only the stale wording (detectable by the
  same greps). For the *code* fix the docs now describe: the garbage-hide test
  (`runs.test.jsx:573`) fails deterministically under the pre-`f292a9c` formula while the
  zero test (`:597`) passes both ways as an overcorrection guard [INV-frontend-P3.md:92-93,
  independently reasoned, not mutation-run]. Reversal coverage for the described behavior is
  therefore genuine; for this commit itself it is reasoned-only by nature.

## 4. Findings

### R-W1-001 [MINOR] Commit 6409d0e lacks required Task/Agent/Wave/Report trailers
- Location: commit `6409d0e` message (no `path:line` in source; evidence below).
- Evidence: [RAN `git show 6409d0e --format=%B`] -> body contains only the subject line;
  STANDING-ORDERS §15 requires `Task:`, `Agent:`, `Wave:`, `Report:` trailers, and the
  implementer brief §8 restated them. Implementer self-disclosed in report §11/§12
  [W1-IMPL-04-T-004.md:182-187,190-194].
- Why it matters: log-level traceability (who/what/wave/report) is the mechanism that lets the
  next reader connect a docs claim to its task and report without reading the whole run.
- Recommended fix: **no amend** (§13 forbids `--amend`; the content is correct and complete).
  ORCH should record the miss in the wave ledger / PR description (SHA `6409d0e` already
  recorded in the implementer report §17 and this review) and enforce trailers on the report
  commit `6a39460` and all later commits. Not a merge blocker: this is a docs-only commit
  with full SHA traceability elsewhere.

### R-W1-002 [NIT] Implementer report misstates f292a9c file stat as "+10/-2"
- Location: `docs/agent-ops/20261108-p3-wave/reports/w1-impl/W1-IMPL-04-T-004.md:43`.
- Evidence: [RAN `git show f292a9c --numstat` -> RunDetails.jsx 8 insertions, 2 deletions].
  The report's "+10/-2" appears to count total changed lines as insertions.
- Why it matters: negligible — describes a prior commit, not this change; all other stats in
  the report (6409d0e 2/2, tests +53) are exact.
- Recommended fix: none required in this wave (report files are historical records; correcting
  them now would add churn). Noted for accuracy of the audit trail.

### R-W1-003 [NIT] Two test counts (115/115, 117/117) now share tech-debt:17
- Location: `docs/tech-debt.md:17`.
- Evidence: line carries the historical `115/115` header for A1/B2/E and the new
  `+2 tests (117/117 at gate)` clause. Implementer flagged this themselves
  [W1-IMPL-04-T-004.md:212-215]; the brief mandated verbatim citation retention.
- Why it matters: a future reader could misread which count applies to which fix batch.
- Recommended fix (DO-LATER, not this commit): when tech-debt:17 is next touched, reword to
  make the genealogy explicit, e.g. "115/115 at 2502fd9; +2 P3 tests -> 117/117 at gate".
  Changing it now would violate the brief's verbatim-preservation instruction for zero user
  impact.

No BLOCKER or MAJOR findings. No band-aid patterns (nothing to band-aid: docs-only change,
no code). Out-of-scope observations from the investigations (PR #2 body staleness,
AGENTS.md single-file SPA drift, negative-diff clamp) are correctly left untouched —
touching them would exceed the write-set; I concur with the implementer on all three.

## 5. Attempts to break it

Reasoned adversarial checks against the new docs claims and the code they describe:

1. **"Hides on NaN diff" vs negative diff:** a run with `finished_at < started_at` (clock
   skew) computes a negative `durationMs`, `Math.max(0, …)` clamps it to `0`, and the chip
   renders `Took 0 s` [VERIFIED RunDetails.jsx:222]. Docs do not claim negative-diff
   handling — no inaccuracy. The clamp is pre-existing (present before `f292a9c`) and
   INV-frontend-P3 already deferred it as a product call [INV-frontend-P3.md:84].
2. **Mixed garbage/valid timestamps:** one side garbage -> subtraction NaN -> hidden. Docs'
   "hides on NaN diff" covers it generically; no contrary claim made. Not test-pinned, but
   the code path is identical to the both-garbage case (same `Number.isNaN` branch).
3. **One timestamp null/missing:** falsy guard -> `durationMs null` -> hidden. Docs say
   "null sentinel" — accurate.
4. **Zero-duration falsy trap:** if the code had used `if (!seconds)`, valid 0s would hide.
   It uses `seconds !== null` [VERIFIED RunDetails.jsx:238] and the zero test pins it.
   Docs' "valid 0s still renders" is true at HEAD.
5. **Re-read F5 for hidden stale language:** full line 113 inspected — the only P3 sentence
   now says FIXED; `113/113`/`115/115` figures describe Phase E history, not P3. Clean.
6. **Cross-file contradiction:** grepped `docs/` for `New P3 backlog|future phase` — remaining
   hits are in run scaffolding (briefs/investigations/ledger describing the past), the
   implementer report quoting pre-edit text, and the new FIXED line itself. No live doc
   still presents P3 as open.

No input, interleaving, or doc re-reading produces a false statement in the edited files.

## 6. Dimension checklist

- **Correctness:** PASS — both new sentences are true of HEAD code/tests; acceptance greps
  pass; lines 18-22 and A1/B2/E citations intact.
- **Root cause vs symptom:** PASS — the root cause was docs drift (docs frozen at `2502fd9`
  while code moved to `f292a9c`); the fix corrects the record without touching correct code.
  A code change here would have been the band-aid (churn with regression risk).
- **Regression/compat:** PASS — docs-only; `--numstat` proves no code/test file changed.
- **Concurrency/idempotency:** N/A — no runtime behavior; git history is the state.
- **Error handling:** N/A for this commit (no executable code). The described code's NaN
  handling is explicit null, not exception-swallowing.
- **Security/abuse:** PASS — no secrets/PII in diff; no input surface added.
- **Performance/scalability:** PASS — zero runtime delta.
- **Migration/rollback:** PASS — rollback = `git revert 6409d0e`; no schema/data.
- **Observability:** MINOR note — missing trailers (R-W1-001); re-runnable acceptance greps
  otherwise good.
- **Maintainability/conventions:** PASS — follows brief's prescribed wording and repo
  `docs:` subject convention; commit SHA citation in docs aids future verification.
- **Docs impact:** PASS — this commit *is* the docs correction; both target files now match
  HEAD code.

## 7. Optimization and simplification opportunities

| # | Location | Evidence | Impact | Effort | Risk | Verdict |
|---|---|---|---|---|---|---|
| 1 | tech-debt.md:17 dual counts | §4 R-W1-003 | Reader clarity only | Trivial (one clause) | Low — but conflicts with verbatim-preservation now | DO LATER (next touch of the line) |
| 2 | Negative-diff honesty (hide vs clamp `Took 0 s`) | RunDetails.jsx:222 `Math.max(0, …)`; INV-frontend-P3.md:84 | Low-severity display honesty; pre-existing, not introduced here | Small code change + tests | Product decision needed; out of T-004 scope | NOT WORTH IT for this run (correctly deferred) |

## 8. Cross-agent / cross-task interactions observed

- Single-task wave: no parallel implementers. W1-CODER-001 (`f292a9c`) owned RunDetails.jsx +
  runs.test.jsx; W1-IMPL-04 owned only the two docs + report — write-sets disjoint, verified
  by the 6409d0e `--numstat` showing no overlap.
- The report commit `6a39460` ("W1-IMPL-04 T-004 implementation report (code commit 6409d0e)")
  landed after the implementer report was written, closing the report's "pending" line (claim
  §17). It is outside my review target (6409d0e) but I note its subject correctly references
  the code commit; I did not audit its trailers.
- ORCH gate T-003 (full `npm test` + build) remains the owner of verifying the 117/117 count
  that tech-debt now states. This review does not substitute for that gate.

## 9. What I could not verify

- **117/117 full-suite count and build green** — NOT run (brief forbids full suite/build;
  gate-owned). Evidence is arithmetic (115 + 2) plus two independent single-file 14/14 runs
  (implementer + INV-frontend-P3). The docs wording "at gate" is consistent with this status.
- **Scoped `runs.test.jsx` 14/14** — not re-run by me (deliberate: two independent runs on
  record; re-running adds flake risk without new information). Marked supported-without-rerun.
- **Whether any production rows contain garbage `started_at`/`finished_at`** — requires DB
  access, out of scope; irrelevant to the truth of the docs edit (the fix is defensive and
  test-pinned regardless).
- **[UNKNOWN] at review time:** whether the report commit `6a39460` carries the §15 trailers
  that `6409d0e` lacks — outside the review target; ORCH to confirm at wave close.
