<!-- ORCH-DIGEST:START -->
agent: W0-INV-02 | domain: docs-PR | status: DONE
items: 3 EXISTS / 7 ALREADY-FIXED / 0 NOT-REPRODUCIBLE / 0 PARTIAL / 0 MISCLASSIFIED
proposed_tasks: 1 (SURFACE 1, DEEP 0)
top_risks: local 2 commits ahead of origin; tech-debt line17 stale P3 note; plan doc P3 section stale
cross_domain_conflicts: none
out_of_plan_discoveries: 2
confidence: high (git + code + gh verified; test counts UNKNOWN by brief constraint)
last_comms_line_read: 2026-11-08 (COMMS.md log empty, last line 33)
<!-- ORCH-DIGEST:END -->

# Investigation report — W0-INV-02 — docs-PR

## 0. Scope and method
Investigator: W0-INV-02, wave-orchestrator run 20261108-p3-wave. READ-ONLY; only this report file written.
Branch claimed: `frontend-ui-round2`, HEAD `69fe44e`.
Files read: STANDING-ORDERS.md, 00-mission.md, 01-work-ledger.md, report-investigation.md, docs/tech-debt.md (full 22 lines), docs/plans/2026-11-08-frontend-deferred-followups.md (full 113 lines), frontend/views/RunDetails.jsx (full 329 lines), COMMS.md (read at start, no START lines yet, last_read line 33).
Commands run: [RAN git log --oneline -8 -> 69fe44e, f292a9c, 2502fd9, 6c72d75...], [RAN git rev-parse HEAD -> 69fe44e448ae9af2e2b355d67aafa986b17abbce], [RAN git branch --show-current -> frontend-ui-round2], [RAN git status -sb -> ahead 2, untracked docs/agent-ops/.../reports/], [RAN git log origin/frontend-ui-round2..HEAD -> f292a9c + 69fe44e], [RAN git ls-remote origin frontend-ui-round2 -> 2502fd9daf764dd8694f07ddb6b9f6ad7b9112d3], [RAN git show --stat for 092e800, c2dd5db, 64c99f8, 87a6f08, 736339a, 6c72d75, 2502fd9, f292a9c, 69fe44e -> stats below], [RAN git show f292a9c diff -> RunDetails invariant + 2 tests], [RAN gh pr view 2 --json title,state,url,headRefName -> OPEN, title "Frontend UI round 2 redesign"], [RAN gh pr view 2 commits list -> last oid 2502fd9, body still "104 tests green... Not merging yet"], grep "Took" / "Invalid Date" in frontend/.
Not verified by brief constraint: `npm test` 117/117, `npm run build` green, backend pytest. Status claims "117" come from 00-mission.md:20 baseline expectation ("117/117 expected at f292a9c (115 at 2502fd9 + 2 P3 tests)"), not from a run here. Recorded as [UNKNOWN] for counts; code/test existence is [VERIFIED].

## 1. Per item

### P3 — Took-NaN duration chip (RunDetails.jsx)
- **Existence verdict:** ALREADY-FIXED (code) / STALE (docs)
- **Evidence:** [VERIFIED frontend/views/RunDetails.jsx:214-238] `durationMs = ... new Date(...) - new Date(...)`; `seconds = durationMs===null || Number.isNaN(durationMs) ? null : Math.max(0, Math.round(durationMs/1000))`; chip gated by `seconds !== null` → garbage dates hide chip, valid 0 still renders `Took 0 s`. [RAN git show f292a9c -> 2 files, 61 insertions: RunDetails.jsx guard + runs.test.jsx 2 tests line 571-619]. Grep "Took": production single site RunDetails.jsx:238; rest are tests/comments. Grep "Invalid Date": only in tests/comments, no production literal. [VERIFIED docs/tech-debt.md:17] line still reads `P3 remainder: RunDetails.jsx:214-216 garbage started_at/finished_at -> "Took NaN s" (not a date leak; future phase)` — now false against HEAD code. [VERIFIED docs/plans/2026-11-08-frontend-deferred-followups.md:113] F5 says `New P3 backlog: RunDetails.jsx:214-216 garbage ... not fixed here` — also stale, never edited since `2502fd9`.
- **Root cause chain:** Pre-f292a9c `Math.round((new Date(fin)-new Date(start))/1000)` spread with `Math.max(0,NaN)=NaN` -> template rendered `Took NaN s`. Fix separates parse diff from null, NaN→null→hide. Matches 00-mission A-001 remedy; 01-ledger T-001 records DONE f292a9c + T-002 APPROVE.
- **Blast radius:** Grep "Took" = 8 hits (2 prod-related). No API/backend touch. Consumers = RunDetails only. Tests pin both branches (garbage-hide, zero-render).
- **Fix options:** Docs-only: update tech-debt line17 + plan doc F5 to mark P3 FIXED at f292a9c. **Recommended:** that (code already correct). Alternative "code change" rejected — would be churn/regression risk.
- **Long-run test:** Source: evidence is git-log codified (f292a9c). Load: N/A (pure fn). Hostile: garbage strings covered by test. Operability: docs fix rollback = revert docs commit. Reversal: removing NaN guard makes P3 garbage test fail (proves test strength).
- **Classification:** SURFACE (docs + one-file guard already landed).
- **WRITE-SET:** docs/tech-debt.md, docs/plans/2026-11-08-frontend-deferred-followups.md (docs-close; either ORCH or docs agent owns hotspots per 00-mission:25 — coordinate single-writer).
- **Test plan:** N/A for docs edit; gate re-run of runs.test.jsx P3 describe confirms 2 tests exist.
- **Conflicts:** Hotspot both docs (00-mission:25). Avoid parallel edit.
- **Acceptance criteria:** line17 no longer says "future phase"/"remainder" for P3; both docs cite f292a9c + 117 count note (or "115+2"); light-mode/probes/backend-pytest lines unchanged.

### A1 — Invalid Date NaN guard (format.js)
- **Existence verdict:** ALREADY-FIXED
- **Evidence:** [RAN git show --stat 092e800 -> format.js 11 lines + format.test.js 10 lines]. [VERIFIED docs/tech-debt.md:17] cites A1 092e800, "115/115". Plan §E line41 + §D line31 mark DONE at 092e800. Grep "Invalid Date" frontend/ = 9 hits all tests/comments. Consistent.
- **Root cause:** `new Date(garbage).toString()` leaked. Guard null→"—" contract.
- **Blast radius:** formatTimeAgo/formatWhen all callers; plan §F row1.
- **Fix options:** none needed. **Recommended:** leave as FIXED claim.
- **Long-run test:** Source: 092e800. Load: N/A. Hostile: garbage-string tests. Operability: revert 092e800. Reversal: removing guard re-fails format.test.js.
- **Classification:** SURFACE. **WRITE-SET:** none. **CONTRACT-SET:** formatter null→"—". **DEPENDS-ON:** none. **ENV-SET:** jsdom.
- **Test plan:** existing format.test.js. **Conflicts:** none. **Acceptance:** already satisfied.

### B1 — Runs row link-based (remove tr onClick)
- **Existence verdict:** ALREADY-FIXED
- **Evidence:** [RAN git show c2dd5db -> RunsDashboard.jsx 5 lines + runs.test.jsx 78 lines]. [VERIFIED docs/tech-debt.md:18] cites c2dd5db. Plan §E line42 DONE + §G D-B1 decision REMOVE.
- **Root cause:** mouse-only tr onClick excluded keyboard. Link is keyboard path.
- **Blast radius:** RunsDashboard only; checkbox/compare tests.
- **Fix options:** none. **Recommended:** keep FIXED. Reversal option (stretched-link) is owner choice per ledger, not this run.
- **Long-run test:** Reversal: re-adding tr onClick fails hash-click test.
- **Classification:** SURFACE. **WRITE-SET:** none. **Conflicts:** none (D-B1 risk accepted).
- **Acceptance:** already satisfied.

### B2 — Runs Started tooltip via formatWhen
- **Existence verdict:** ALREADY-FIXED
- **Evidence:** [RAN git show 64c99f8 -> RunsDashboard.jsx 4 lines + runs.test 27 lines]. [VERIFIED docs/tech-debt.md:17] cites B2 64c99f8. Plan §E line43 DONE.
- **Root cause:** raw date tooltip leaked Invalid Date on garbage created_at.
- **Blast radius:** Runs Started td title. **Fix options:** none. **Recommended:** keep FIXED.
- **Long-run test:** reversal restores raw title -> garbage test fails.
- **Classification:** SURFACE. **WRITE-SET:** none.
- **Acceptance:** already satisfied.

### C1 — Predict segmented arrow keys
- **Existence verdict:** ALREADY-FIXED
- **Evidence:** [RAN git show 87a6f08 -> PredictPanel.jsx 31 lines + predict.test.jsx 58 lines]. [VERIFIED docs/tech-debt.md:19] cites 87a6f08. Plan §E line44 DONE, §G D-C keep group+pressed.
- **Root cause:** Tab-only 2-option segmented control. Fix: Arrow/Home/End clamp select-on-arrow.
- **Blast radius:** PredictPanel only; getByRole('button') preserved.
- **Fix options:** none. **Recommended:** keep FIXED.
- **Long-run test:** reversal breaks arrow test.
- **Classification:** SURFACE. **WRITE-SET:** none.
- **Acceptance:** already satisfied.

### D1 — RL env-id label test
- **Existence verdict:** ALREADY-FIXED
- **Evidence:** [RAN git show 736339a -> newjob.test.jsx 86 lines, 1 file]. [VERIFIED docs/tech-debt.md:20] cites 736339a. Plan §E line45 DONE. Note: test-only commit (no App.jsx change) matches plan "per-test seed only".
- **Root cause:** label/id + submit env_id unpinned. Fix: seed RL model in test.
- **Blast radius:** newjob.test only; default seed untouched.
- **Fix options:** none. **Recommended:** keep FIXED.
- **Long-run test:** reversal (remove seed) -> label not found.
- **Classification:** SURFACE. **WRITE-SET:** none.
- **Acceptance:** already satisfied.

### E — Residual Invalid Date leaks (RunDetails + quota)
- **Existence verdict:** ALREADY-FIXED
- **Evidence:** [RAN git show 6c72d75 -> shared.jsx, format.test, runs.test, RunDetails.jsx]. [VERIFIED docs/tech-debt.md:17] cites Phase E 6c72d75. Plan §E line46 + §M F5 DONE, note 115/115.
- **Root cause:** final-review P2 two raw-date sites missed by A1/B2. Fix: formatWhen both.
- **Blast radius:** RunDetails Started title + shared quota "resets at".
- **Fix options:** none. **Recommended:** keep FIXED.
- **Long-run test:** reversal -> runs garbage title test fails.
- **Classification:** SURFACE. **WRITE-SET:** none.
- **Acceptance:** already satisfied.

### Light mode / browser+SR probes / backend pytest (accepted risk)
- **Existence verdict:** EXISTS (still-open, correctly classified as deferred)
- **Evidence:** [VERIFIED docs/tech-debt.md:6-7,12,16,21,22] light-mode dark-only, probes manual, backend pytest NOT-RUN (no venv). [VERIFIED docs/plans/...:20,82,98-102] Non-goals + R-P ACCEPTED; [VERIFIED 00-mission.md:6] Out of scope: light mode, Chromium/SR probes, backend pytest (manual/NOT-RUN, accepted risk); ledger:39 carries same. [ASSUMED] Correct to leave untouched in this docs-close — no code changed for them, no evidence they were run.
- **Root cause:** deferred by design (token inversion hypothesis, jsdom limits, no venv).
- **Blast radius:** docs + acceptance wording only if carelessly edited.
- **Fix options:** minimal docs close must NOT touch these lines. **Recommended:** leave verbatim.
- **Long-run test:** N/A. **Classification:** SURFACE. **WRITE-SET:** none for this task.
- **Acceptance:** no such lines altered in docs-close diff.

## 2. Duplicates / shared root causes
- A1/B2/E/P3 share one pattern: raw `new Date()` diff/string without NaN guard. Single sentinel (`formatWhen`) + explicit NaN→null is the unified lesson. Docs should now reflect all five as FIXED; only note left is probes/light/pytest.
- No duplicate tasks proposed.

## 3. Out-of-plan discoveries
1. `git status` shows untracked `docs/agent-ops/20261108-p3-wave/reports/` (this investigation's dir). Not a source change; ensure the run doesn't accidentally commit it as ops-scaffold or ignore rules drop it. In commit scoping, avoid `git add -A` (STANDING-ORDERS:13).
2. PR #2 body stale (still "104 tests green ... Not merging yet") even at origin `2502fd9`. After the 2 un-pushed commits land, PR description needs rewrite (tests 115→117, P3 f292a9c, probes/pytest still manual). Body not auto-updated by git push.

## 4. Assumptions and unknowns
- [ASSUMED] Single-writer for docs hotspots (00-mission:25) means ORCH/docs agent coordinates tech-debt + plan edits; this investigator did not edit them.
- [UNKNOWN] Exact test totals 117/117 + build green at `69fe44e` — not run per brief; baseline expectation from 00-mission:20 must be re-verified at gate T-003 before any PR claim of 117.
- [UNKNOWN] whether a gate run already observed the flaky Progress-poll test (00-mission:22) — no gate report read in scope.
- [KNOWN] PR #2 state [VERIFIED via gh]: OPEN, headRefName `frontend-ui-round2`, title "Frontend UI round 2 redesign", url https://github.com/devansh1012007/ALL-of-ML---DL/pull/2; commits on PR top at `2502fd9` (f292a9c/69fe44e NOT in PR — network path worked, not assumed).

## 5. Recommended task breakdown and ordering
- **T-DOCS-CLOSE (SURFACE, 1 task, only remaining code-docs item):** Edit `docs/tech-debt.md:17` — replace the trailing P3-remainder sentence with FIXED-at-`f292a9c` wording, e.g.: `P3 "Took NaN s" guard (FIXED 2026-11-08, f292a9c): RunDetails.jsx duration chip hides on NaN diff (null sentinel, valid 0s still renders); +2 tests (117/117 at gate).` Keep A1/B2/E citations; do not alter lines 18-22 (B1/C1/D1 FIXED wording already correct; light-mode/probes/backend-pytest stay manual/NOT-RUN accepted risk). Mirror a one-line P3-FIXED note in `docs/plans/2026-11-08-frontend-deferred-followups.md:113` (append `P3 FIXED f292a9c` clause; no re-plan). Single-writer hotspot — one agent only. No code/tests change in this task.
- **After docs-close + gate (T-003) passes, then PR #2 push (orchestrator/user action):** Push `frontend-ui-round2` (today: `f292a9c` + `69fe44e` + docs-close commit) to origin; expected origin move `2502fd9 -> new HEAD`. Update PR #2 description: title unchanged; body = PR #1 scope already described + deferred-followups summary (A1/B1/B2/C1/D1/E/P3 with SHAs, 117/117, build green) + explicit "Not merging yet — needs approval; light-mode/probes/backend pytest NOT-RUN accepted risk". Explicitly do NOT merge without approval.
- Order: docs-close → gate T-003 (npm test 117/117 + build) → push+PR-desc. Push before gate would publish unverified counts.
- Push-readiness today: branch `frontend-ui-round2` is ahead 2 of `origin/frontend-ui-round2` (`2502fd9`); `git ls-remote` confirms same origin tip. No network blocker other than push permission (not tested here). Re-verify at push time.

## Git evidence summary (brief's claim adjudicated)
- [RAN git log -8 -> 69fe44e, f292a9c, 2502fd9, 6c72d75, 736339a, 64c99f8, 87a6f08, c2dd5db]; 092e800 at depth 9. All 7 follow-up commits + 2 new present locally.
- [RAN git rev-parse HEAD -> 69fe44e448...]; branch frontend-ui-round2 [VERIFIED].
- [RAN git ls-remote -> 2502fd9 refs/heads/frontend-ui-round2; git status -sb -> ahead 2]. f292a9c + 69fe44e are pushed? No — NOT pushed; origin tip remains 2502fd9 (VERIFIED, not UNKNOWN).
- [RAN git show f292a9c -> RunDetails + runs.test only; 69fe44e -> 15 ops-scaffold files]. No source drift between them.
