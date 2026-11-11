<!-- ORCH-DIGEST:START -->
agent: W0-INV-02 | domain: frontend-negative-diff + tech-debt | status: DONE
items: 2 verified EXISTS (N1 negative-diff, D1 dual counts) / 0 ALREADY-FIXED / 0 NOT-REPRODUCIBLE / 0 PARTIAL / 0 MISCLASSIFIED
proposed_tasks: 2 (SURFACE 2, DEEP 0)
top_risks: negative diff falsely renders "Took 0 s" (honesty) | light-mode vs N1 overlap on RunDetails.jsx (conditional C1) | tech-debt genealogy stays ambiguous if not reworded
cross_domain_conflicts: C1 conditional — N1 (T-102) vs light-mode (T-101) both potentially touch frontend/views/RunDetails.jsx; serialize or keep light-mode to styles/tailwind only
out_of_plan_discoveries: 0
confidence: high (code paths, backend serialization, and single-file test run verified; production reachability of negative rows [ASSUMED] from code only)
last_comms_line_read: 2026-11-08T19:03Z (COMMS.md header + empty Log at read time; no lines)
<!-- ORCH-DIGEST:END -->

# Investigation report — W0-INV-02 — frontend-negative-diff + tech-debt

## 0. Scope and method

**Scope:** Two user-directed items at HEAD `85acdda` on branch `frontend-ui-round2`:
- (a) N1 — Negative-diff duration (`finished_at < started_at`) clamps to `"Took 0 s"` via `Math.max(0,·)` in `frontend/views/RunDetails.jsx`. Mission A-010 recommends hide-the-chip (null sentinel); this investigation evaluates hide vs warn and gives the exact change + tests. Prior analysis at `docs/agent-ops/20261108-p3-wave/reports/w0-investigation/INV-frontend-P3.md` §"Edge cases" already found this leaf — **re-verified, not copied** (see §1 below for independent checks: mixed garbage, clamped-negative, `wall_seconds` alternatives).
- (b) D1 — `docs/tech-debt.md:17` carries both `115/115` header history and `117/117` gate counts; propose exact minimal reword, keeping A1/B2/E citations verbatim and lines 18-22 untouched.

**Required reading read (in order):** `docs/agent-ops/20261108-light-negative/templates/STANDING-ORDERS.md`, `00-mission.md`, `01-work-ledger.md`, `templates/report-investigation.md`, `frontend/views/RunDetails.jsx` (full, 329 lines), `frontend/tests/runs.test.jsx` (full spot-checks + P3 describe 571-622 + `completedRun`/`completedDetail` helpers), `frontend/format.js` (full), `docs/tech-debt.md` (full), `docs/agent-ops/20261108-p3-wave/reports/w0-investigation/INV-frontend-P3.md` (full).

**Commands run (scoped only):**
- [RAN `git log --oneline -8` -> `85acdda` HEAD, then `b384e17`, `6a39460`, `6409d0e`, `0053765`, `69fe44e`, `f292a9c`, `2502fd9` (115/115 commit)]
- [RAN `git branch --show-current` -> `frontend-ui-round2`]
- [RAN `cd frontend; npx vitest run tests/runs.test.jsx` -> `1 file passed, 14 tests passed` (5.09s) — P3 NaN-guard + zero tests included; full suite NOT run per scope]
- Greps: `Took|Math\.max\(0|durationMs|seconds` over `frontend/` (59 matches — only 1 duration site, see §1); `new Date\(.*finished|new Date\(.*started` over `frontend/` (1 match); `data-theme|color-scheme|light` over `frontend/` (styles + meta only, no `data-theme` yet); `started_at|finished_at|wall_seconds` over `backend/app/` (38 matches).

**Not done:** full frontend suite / build NOT run; no `.venv` backend pytest (out of scope, frontend-only diff); no source edits — this report is the only file written. Reversal reasoned from code, not executed via mutation (write-set protected).

**Line-number note:** brief cites `RunDetails.jsx:214-222` for the guard and `:238` for the chip — [VERIFIED frontend/views/RunDetails.jsx:214-222] guard block (comment + `durationMs` + `seconds`) and [VERIFIED frontend/views/RunDetails.jsx:238] chip `{seconds !== null && <span>Took {seconds} s</span>}`. Matches exactly at HEAD.

---

## 1. Per plan item

### N1 — Negative-diff duration clamps to "Took 0 s" (RunDetails.jsx)

- **Existence verdict:** EXISTS
- **Evidence:**
  - Negative path today [VERIFIED frontend/views/RunDetails.jsx:217-222]:
    ```jsx
    const durationMs = run.started_at && run.finished_at
      ? new Date(run.finished_at) - new Date(run.started_at)
      : null;
    const seconds = durationMs === null || Number.isNaN(durationMs)
      ? null
      : Math.max(0, Math.round(durationMs / 1000));
    ```
    For `finished_at < started_at`: `durationMs` is a negative non-NaN number → passes both null/NaN checks → `Math.round(negative/1000)` negative → `Math.max(0, negative)` = `0` → `seconds = 0` → `0 !== null` → chip renders `"Took 0 s"` [VERIFIED frontend/views/RunDetails.jsx:238]. Concrete: `started 00:01:00Z, finished 00:00:00Z` → `-60 s` → `Max(0,-60)=0` → `"Took 0 s"`. The clamp is deterministic JS semantics — re-verified with fresh greps below, not inherited from the prior report.
  - Re-verified prior-report claims independently:
    - *Mixed garbage/valid:* `new Date(valid) - new Date('garbage')` → `NaN` → null → hidden. Guard is generic over NaN regardless of which side produced it. No test exists yet for mixed, but [VERIFIED frontend/views/RunDetails.jsx:220] `Number.isNaN(durationMs)` covers it; prior report's "over-cautious deferral" assessment confirmed by code reading.
    - *Clamped-negative:* prior report §Edge-cases row 4 flagged `Math.max` clamp → "silently misleading" — **confirmed** at HEAD: `Math.max` still present line 222, negative path untouched by P3 (`f292a9c` only added the NaN branch; negative row was never closed).
    - *`wall_seconds` alternative:* backend already serializes `wall_seconds` [VERIFIED backend/app/main.py:2332 `"wall_seconds": run.wall_seconds`] from server `time.monotonic()` [VERIFIED backend/app/executor.py:147] but the view **ignores** it and recomputes client-side — confirmed still true at HEAD (no `wall_seconds` reference in `RunDetails.jsx`; grep over `frontend/` shows `wall_seconds` only in `tests/helpers.jsx`, `compare.test.jsx`, `predict.test.jsx` fixtures).
  - Every other duration site in `frontend/` (fresh grep): `Math.max(0,` hits are `format.js:29` (`timeAgo` clamps future dates to "just now" — different semantics, correct), `metrics.jsx` chart bars, `helpers.jsx` id counters — **zero** other `new Date(a) - new Date(b)` duration computations. Only 1 production duration site exists. `Took` hits: only `RunDetails.jsx:238` + test strings.
  - Single-file gate green at HEAD: [RAN `cd frontend; npx vitest run tests/runs.test.jsx` -> 14 passed] — includes P3 garbage + zero tests, so baseline for N1 tests is established.
- **Root cause chain:** symptom → mechanism → origin:
  1. **Symptom:** a run whose `finished_at` precedes `started_at` displays `"Took 0 s"` — indistinguishable from a genuine instant run. The displayed number is asserted-false.
  2. **Mechanism:** `seconds` uses `Math.max(0, …)` as a floor. Unlike the NaN case (which `Math.max` propagates as NaN and P3 now intercepts), a negative number is *coerced* to 0. The chip's `seconds !== null` gate therefore cannot distinguish "unknown/negative" from "true zero". The honesty invariant "seconds is null unless both timestamps parse" [VERIFIED RunDetails.jsx:214-216 comment] is satisfied for NaN but not for negative: negative *parses* but is not a trustworthy duration.
  3. **Origin:** the floor was written as sub-second rounding defense (400 ms → `round(0.4)=0`) and as future-date insurance borrowed from `timeAgo` style, but no distinction was drawn between "small positive rounding to zero" (legit) and "negative diff" (data-integrity failure). P3 fixed the NaN half of the same expression; the negative half survived because the two share one line (`Math.max`) and only one branch was guarded.
  4. **Why earlier fixes didn't hold:** A1/E guarded *single-timestamp formatting* (`format.js`), P3 guarded *two-timestamp NaN*; negative diff is the third failure mode of the same expression (wrong-sign arithmetic, not unparseable dates) and no guard covers the sign. The data-integrity failure is silently normalized to a plausible value instead of being surfaced as unknown.
- **Backend reachability (clock skew vs corrupt rows)** [VERIFIED backend/app/main.py:588-590, 1766, 2077, 2330-2332]:
  - `started_at` is written once at claim time (`main.py:1766` `started_at=now`) and `finished_at` at `_finish_run` (`main.py:2077` `finished_at=_now()`); both call `_now()` = `datetime.now(timezone.utc)` — same timezone-aware UTC clock, so a *single* healthy process never produces a negative diff.
  - Reachable paths (all [ASSUMED] outside this investigation's scope since no live DB seed was run):
    - **Clock skew / NTP step:** claim and finish may execute in different processes/hosts (worker pool); a backwards NTP step or inter-host skew between the two `_now()` calls yields a negative diff. Long-running trainings make this non-hypothetical over hours/days.
    - **Corrupt/stale rows:** manual DB edits, timezone-naive legacy rows, migration of old versions with different timestamp semantics.
    - **Test fixtures / wire drift:** frontend test harness injects arbitrary strings (the P3 tests prove the view cannot trust the wire).
  - Serialization itself is faithful (`.isoformat() if … else None` both sides, `main.py:2330-2331`) — the view must still distrust it, consistent with the P3 rationale.
- **Blast radius:** single render site. Grep counts: `Took` = 1 production site; `new Date(finished) - new Date(started)` = 1 site; `seconds` duration variable only in `RunDetails.jsx:220,238` + `format.js` local (unrelated `timeAgo`). Consumers/tests: `RunDetails` header only; no API/schema change (timestamps already serialized). Test surface: `runs.test.jsx` P3 describe `571-622` (+ `completedRun` `:22-46`, `completedDetail` `:312-340` helpers drive the new cases via `runDetails[1]` override, same pattern as P3 tests).
- **Fix options:**
  - **Option A (RECOMMENDED — hide chip, null sentinel, per mission A-010):** extend the null condition to include negative diffs. The chip hides; no new UI, no copy, no announcement; extends the existing P3 invariant from "parses" to "parses and is non-negative" (i.e. trustworthy). Reversible in one line. Risk: conceals data corruption from the user — accepted because (i) the user cannot repair server timestamps from Run Details, (ii) a false "0 s" is strictly worse than silence, (iii) the prior NaN fix established silence as the unknown-sentinel convention, (iv) backend logs/DB retain the corrupt values for operators.
  - **Option B (warn chip — rejected):** e.g. `role="status"` "Duration unavailable (clock skew)". Pros: surfaces corruption. Cons: invents UX + copy (needs content-owner per tech-debt copy-ownership item, [VERIFIED docs/tech-debt.md:10]); needs screen-reader announcement semantics (the `RunEvents` phase-announcement dedup pattern shows the team is careful here); needs a threshold (is −1 s skew a warning?); still shows a "Took"-like assertion, weakening the negative test's "no Took text" invariant; disproportionate for a low-severity honesty nit on unreachable-in-happy-path data. Rejected as over-engineering; revisit only if operators report real negative rows.
  - **Option C (show negative / remove clamp — rejected):** render `"Took -60 s"`. Displays impossible physics; swaps a small lie for a bigger one. Rejected.
  - **Option D (use `wall_seconds` — rejected as product change, see §1 `wall_seconds` note):** server-monotonic and skew-immune, but changes display semantics (null for queued/interrupted runs, integer column [VERIFIED backend/app/models.py:140]), contradicts the timestamp-derived display elsewhere, and needs fallback logic. Not a bug fix; needs product decision.
  - **Long-run test:** Source — wire drift/manual rows (tests inject via harness). Load (100× concurrency) — one subtraction per render; poll re-render cost unchanged. Hostile input — negative/huge/garbage timestamps → hidden chip, no injection surface (timestamps never rendered raw; `formatWhen` shows "—"). Operability — pure display; rollback = revert one line; no migration/config. Reversal — negative-diff test fails on current code (chip renders), passes after fix; zero test passes on both (guard-rail); mixed test passes on both (already NaN-covered).
- **Exact 1-2-line change (Option A):**
  ```jsx
  // frontend/views/RunDetails.jsx:220 (replace condition)
  // BEFORE:
  const seconds = durationMs === null || Number.isNaN(durationMs)
  // AFTER:
  const seconds = durationMs === null || Number.isNaN(durationMs) || durationMs < 0
  ```
  plus update the invariant comment `RunDetails.jsx:214-216` to add negative, e.g.:
  ```jsx
  // INVARIANT: seconds is null unless both timestamps parse to a non-negative
  // diff; NaN (garbage-but-truthy dates) or finished<started must hide the chip.
  ```
  Keep `Math.max(0, …)` on line 222 as defense-in-depth (now redundant for negatives but harmless; removing it is optional churn — do NOT remove in the same change). Net diff: 1 logical line + 2 comment lines.
- **Classification:** SURFACE — single-file display guard, no contract/schema/state change, no cross-domain effect; matches ledger T-102 `SURFACE` [VERIFIED 01-work-ledger.md:14].
- **WRITE-SET:** `frontend/views/RunDetails.jsx`, `frontend/tests/runs.test.jsx` (same set as P3 `f292a9c`, no overlap with hotspots `format.js`/`tailwind.config.js`/`styles.css`). **CONTRACT-SET:** none. **DEPENDS-ON:** none. **ENV-SET:** jsdom/Vitest only.
- **Test plan (3 cases, same `renderApp` + `runDetails` override pattern as `runs.test.jsx:571-622`):**
  1. **Negative-diff (must FAIL before fix, PASS after):** `started_at: '2026-11-08T00:01:00Z', finished_at: '2026-11-08T00:00:00Z'` (−60 s) via `completedDetail` spread → `expect(screen.queryByText(/took/i)).not.toBeInTheDocument()` + `not.toMatch(/NaN/)`. Before fix: chip renders `"Took 0 s"` → fails. ✅ genuine reversal coverage.
  2. **Mixed garbage/valid (control, passes both):** `started_at: 'garbage', finished_at: '2026-11-08T00:01:00Z'` → no "Took" text. Proves NaN guard genericity; guards against a fix that only special-cases both-garbage.
  3. **Zero regression (exists, keep):** `started == finished` → `"Took 0 s"` rendered [VERIFIED runs.test.jsx:597-621]. Guards against an over-broad `if (!seconds)` hiding true zero. Must stay green.
  Boundary extra (optional): −1 s vs −60 s both hidden (no threshold logic — any `< 0` hides).
- **Conflicts/ordering:** ⚠️ **C1 conditional** — mission A-011 light mode is "CSS-variable token inversion keyed off data-theme + toggle" [VERIFIED 00-mission.md:27]. Current tree has `color-scheme:dark` only (`styles.css:30`, `index.html:6`) and **no** `data-theme` anywhere [VERIFIED grep] — light mode has not landed yet. If T-101 implementer stays inside `styles.css`/`tailwind.config.js` (+ toggle in `App.jsx`), there is **no** conflict with N1. If the token inversion renames component classes across views (e.g. `text-muted`, `tabular-nums` in `RunDetails.jsx`), the two diffs overlap in `RunDetails.jsx` — distinct lines (N1: 214-238 vs class strings scattered), so git auto-merge would *likely* succeed but review would be muddied. **Recommended ordering:** land N1 (W1, T-102) first, then light mode (W2, T-101) rebases over it; or constrain light mode to styles/tailwind and forbid JSX class churn. Do NOT run N1 and a class-renaming light mode in parallel without a merge plan.
- **Acceptance criteria (measurable):**
  1. Negative diff → no "Took" text in DOM. (New test 1 must fail pre-fix.)
  2. Mixed garbage → no "Took" text. (New test 2.)
  3. `started == finished` → "Took 0 s" still rendered. (Existing zero test stays green.)
  4. `npx vitest run tests/runs.test.jsx` green (14 → 16 with 2 new tests).

### D1 — tech-debt:17 dual counts (docs/tech-debt.md)

- **Existence verdict:** EXISTS
- **Evidence — verbatim line 17** [VERIFIED docs/tech-debt.md:17]:
  > `- **Invalid date renders "Invalid Date" (FIXED 2026-11-08, ` + "`frontend-ui-round2`" + ` 115/115).** ` + "`format.js`" + ` NaN-guard (A1 ` + "`092e800`" + `), Runs tooltip B2 (` + "`64c99f8`" + `), RunDetails + quota-text residual leaks Phase E (` + "`6c72d75`" + `). No ` + "`"Invalid Date"`" + ` string reachable from any UI surface (grep-verified). P3 "Took NaN s" (FIXED 2026-11-08, f292a9c): RunDetails.jsx duration chip hides on NaN diff (null sentinel; valid 0s still renders); +2 tests (117/117 at gate).`
  
  The header asserts `115/115` (commit `2502fd9` era) while the trailing P3 clause adds `+2 tests (117/117 at gate)` — a reader cannot tell whether `115/115` is stale or whether `117/117` supersedes it without reading the commit history. Genealogy is arithmetic-only (`115 + 2 = 117`), never spelled out. This is the exact deferred NIT from the prior review.
- **Root cause:** two dated counts were appended to one bullet at different commits (`2502fd9` wrote 115/115; `6409d0e`/`f292a9c` era appended the P3 clause) without updating the header. Neither count is wrong at its own point in time; the line is ambiguous because neither is qualified by its commit.
- **Blast radius:** documentation only. Word count of line 17: header carries the stale total; no code, test, or script parses this line. No callers/consumers. Neighbour lines (Round-1 entries 5-12, fix bullets 18-22) are independent.
- **Fix options:**
  - **Option A (RECOMMENDED — genealogy into header, drop trailing count clause):** change only the header parenthetical and remove the duplicated `117/117` from the tail. Minimal, one-line diff, keeps FIXED structure and all three citations (`092e800`/`64c99f8`/`6c72d75`) byte-identical.
  - **Option B (keep both clauses, qualify each):** header `115/115 at 2502fd9`, tail `117/117 at gate`. Rejected: still reads as two competing totals on one line; the geneaology is better stated once.
  - **Option C (split into two bullets):** rejected: needlessly restructures the entry, touches line count, risks neighbouring-line drift.
- **Exact replacement text (Option A — the whole line 17 becomes):**
  ```
  - **Invalid date renders "Invalid Date" (FIXED 2026-11-08, `frontend-ui-round2` 115/115 at 2502fd9; +2 P3 tests → 117/117 at gate).** `format.js` NaN-guard (A1 `092e800`), Runs tooltip B2 (`64c99f8`), RunDetails + quota-text residual leaks Phase E (`6c72d75`). No `"Invalid Date"` string reachable from any UI surface (grep-verified). P3 "Took NaN s" (FIXED 2026-11-08, f292a9c): RunDetails.jsx duration chip hides on NaN diff (null sentinel; valid 0s still renders).
  ```
  Diff vs current line 17: header `115/115)` → `115/115 at 2502fd9; +2 P3 tests → 117/117 at gate)`; tail `; +2 tests (117/117 at gate).` → `.` (counts now live once, in the header). Citations `092e800`, `64c99f8`, `6c72d75`, `f292a9c` and all FIXED dates untouched.
- **Byte-identity check for forbidden zone (lines 18-22):** after the edit, run:
  ```powershell
  git diff -U0 docs/tech-debt.md  # expect exactly one hunk, @@ ... -17 +17 @@
  git diff docs/tech-debt.md | Select-String -Pattern '^[-+].*(Runs row click|Predict segmented|RL model|Light mode|Backend pytest)'
  # expect: no matches (empty output)
  ```
  Equivalent single-command gate: `git diff --stat docs/tech-debt.md` should show `1 insertion(+), 1 deletion(-)` and `git show HEAD:docs/tech-debt.md | Select-Object -Skip 17 -First 5` vs working `Select-Object -Skip 17 -First 5` must be byte-identical for lines 18-22.
- **Long-run test:** Source — future readers misreading `115/115` as current total. Load — n/a (static doc). Hostile input — n/a. Operability — n/a (revert = one line). Reversal — if reverted, the ambiguity returns; no test guards prose, so acceptance is human diff review, not a test.
- **Classification:** SURFACE — docs-only one-line reword. **WRITE-SET:** `docs/tech-debt.md` only. **CONTRACT-SET:** none. **DEPENDS-ON:** none. **ENV-SET:** none.
- **Test plan:** no automated test; verification = `git diff -U0` shows one hunk at line 17 + the 5 lines above are empty. Eyeball that A1/B2/E citations (`092e800`/`64c99f8`/`6c72d75`) are byte-identical (paste-check).
- **Conflicts/ordering:** none — `docs/tech-debt.md` is a hotspot (single-writer per 00-mission) but only D1 touches it this wave; N1/light-mode do not. Independent of N1; may land in any order.
- **Acceptance criteria (measurable):**
  1. Line 17 reads `115/115 at 2502fd9; +2 P3 tests → 117/117 at gate` in the header.
  2. No `117/117` remains duplicated in the tail clause.
  3. Lines 18-22 byte-identical to HEAD (`git diff -U0` = one hunk).

---

## 2. Duplicates / shared root causes across items

Both items share the "one stale/partial guard leaves a sibling case" pattern with P3: N1 is the sign-half of the same `Math.max` expression P3 guarded on the NaN-half; D1 is the prose shadow of the same commit chain (`2502fd9` → `f292a9c` → `6409d0e`). They are otherwise independent — different files, different test surfaces, no shared contract. N1's remedy (extend null sentinel) and D1's remedy (spell out genealogy) both preserve the established "unknown/old state named, never silently normalized" convention.

## 3. Out-of-plan discoveries

None new. Carried facts (not added to scope):
- `wall_seconds` (server-monotonic) is serialized but unused by the view — a product decision (§1 Option D), not a defect.
- AGENTS.md still describes the SPA as single-file `App.jsx` while views live in `frontend/views/` (noted in prior report, unchanged here).

## 4. Assumptions and unknowns

- **[ASSUMED]** Negative rows are not reachable through the current backend happy path (single `_now()` UTC clock, `main.py:588-590,1766,2077`); reachability requires multi-host skew, NTP steps, or corrupt rows. Would need live DB inspection to confirm — not done (read-only, no shared-DB runs).
- **[ASSUMED]** N1 warn-chip copy would need content-owner approval (tech-debt copy-ownership item) — inferred from process, not from a copy ticket.
- **[UNKNOWN]** Whether any production rows actually contain `finished_at < started_at` — requires DB access, out of scope.
- **Facts vs assumptions:** code paths, grep counts, backend serialization, and the 14-test baseline are [VERIFIED]; only production reachability and the A-010 warn-chip cost assessment are [ASSUMED].

## 5. Recommended task breakdown and ordering

| # | Task | Class | Files | Why this order |
|---|---|---|---|---|
| 1 | T-102 (N1) hide-chip + 2 tests | SURFACE | `RunDetails.jsx`, `runs.test.jsx` | **First.** 1-line logic change; lands before any light-mode JSX churn so T-101 rebases cleanly. No hotspot contention. |
| 2 | T-103 (D1) tech-debt reword | SURFACE | `docs/tech-debt.md` | Any time. Docs-only, independent; may land in parallel with T-102 (zero overlap). |
| 3 | T-101 (light mode) spec → impl | TBD (likely DEEP) | `styles.css`, `tailwind.config.js`, `App.jsx`, … | **Last / W2.** Depends on spec + planner review per mission; must not touch `RunDetails.jsx` class strings without rebasing over T-102 (C1). |

*No DEEP work identified for N1 or D1. Suggested ORCH gate after T-102/T-103: `cd frontend; npx vitest run tests/runs.test.jsx` (expect 16/16) + `git diff -U0 docs/tech-debt.md` one-hunk check.*
