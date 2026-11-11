<!-- ORCH-DIGEST:START -->
agent: W0-INV-01 | domain: frontend/P3 | status: DONE
items: 1 EXISTS / 1 ALREADY-FIXED / 0 NOT-REPRODUCIBLE / 1 PARTIAL / 0 MISCLASSIFIED
proposed_tasks: 1 (SURFACE 1, DEEP 0)
top_risks: 117 total unverified locally (PARTIAL) | negative-diff clamps silently to "Took 0 s" | wall_seconds unused in view
cross_domain_conflicts: none
out_of_plan_discoveries: 0
confidence: high (fix+tests verified in code and single-file run; full-suite 117 inferred, not run per scope)
last_comms_line_read: 2026-11-08T04:41Z (COMMS.md header only; Log section empty at read time)
<!-- ORCH-DIGEST:END -->

# Investigation report — W0-INV-01 — frontend/P3

## 0. Scope and method

**Scope:** Verify the P3 claim — commit `f292a9c` "hide run duration on NaN timestamps (P3 Took NaN s)" fixed `frontend/views/RunDetails.jsx` (~214-232), added 2 tests in `frontend/tests/runs.test.jsx`, total 117 frontend tests. Also root-cause the bug, blast-radius sibling NaN/date surfaces, assess uncovered edge cases, and judge symptom-vs-root-cause.

**Files read (in required order):** `docs/agent-ops/20261108-p3-wave/templates/STANDING-ORDERS.md`, `AGENTS.md`, `docs/agent-ops/20261108-p3-wave/00-mission.md`, `01-work-ledger.md`, `templates/report-investigation.md`, then `frontend/views/RunDetails.jsx` (full, 329 lines), `frontend/tests/runs.test.jsx` (full, 622 lines), `frontend/format.js` (full, 45 lines).

**Commands run (scoped only):**
- [RAN `git log --oneline -12` -> `69fe44e` HEAD, `f292a9c` second, `2502fd9` third; branch `frontend-ui-round2`]
- [RAN `git show f292a9c --stat` -> 2 files: `frontend/tests/runs.test.jsx` +53, `frontend/views/RunDetails.jsx` +8/-2 (61 insertions, 2 deletions)]
- [RAN `git show f292a9c` (full diff) -> fix splits inline `seconds` into `durationMs` + NaN guard; adds `describe('run details: P3 duration NaN guard')` with 2 `it()` blocks]
- [RAN `git show f292a9c^:frontend/views/RunDetails.jsx` (pre-fix, lines 211-218) -> old inline computation confirmed]
- [RAN `git show 69fe44e --stat` -> ops scaffolding only, no source changes]
- [RAN `cd frontend; npx vitest run tests/runs.test.jsx` -> 1 file passed, 14 tests passed, 5.04s; includes both P3 tests]
- Greps: `Took|started_at|finished_at|durationMs|wall_seconds|Number.isFinite|new Date(` and `timeAgo|formatWhen|wall_seconds|Took|seconds` over `frontend/`; `wall_seconds|started_at|finished_at` over `backend/app/`

**Not done (per brief/scope):** full frontend suite (`npm test`) NOT run — 117 total therefore PARTIAL (see §1). Backend pytest NOT run (out of scope, frontend-only diff). No source files edited; this report is the only file written. No revert-mutation performed — reversal assessment is by code reasoning + the pre-fix diff.

**Note on AGENTS.md drift:** `AGENTS.md` says the SPA is a single `frontend/App.jsx` with views inside it [VERIFIED AGENTS.md:109]; in fact views were split to `frontend/views/RunDetails.jsx` in commit `37f2c08` (R6, per git log). The brief's path is correct for current HEAD; AGENTS.md frontend section is stale on this point. [FACT, not a P3 issue]

---

## 1. Per plan item

### P3 — "Took NaN s" guard in RunDetails duration chip — `f292a9c`

**Claim decomposition (brief-required classification):**

| Sub-claim | Verdict | Evidence |
|---|---|---|
| Fix present in `RunDetails.jsx` | **ALREADY-FIXED** | [VERIFIED frontend/views/RunDetails.jsx:214-222] guard + comment; [RAN git show f292a9c -> diff adds exactly this] |
| Chip renders only when `seconds !== null` (valid 0s preserved) | **ALREADY-FIXED** | [VERIFIED frontend/views/RunDetails.jsx:238] `{seconds !== null && <span>Took {seconds} s</span>}` — pre-existing line, unchanged by f292a9c [RAN git show f292a9c -> line 238 context unchanged] |
| 2 tests added in `runs.test.jsx` | **EXISTS** | [VERIFIED frontend/tests/runs.test.jsx:571-622] `describe('run details: P3 duration NaN guard')` with `it('garbage started/finished hides the duration chip…')` (:573) and `it('valid zero duration still renders "Took 0 s"')` (:597); [RAN git show f292a9c -> +53 lines, both blocks new] |
| 117 total tests | **PARTIAL** | Indirect only: `2502fd9` message claims 115/115 [RAN git log], f292a9c adds exactly 2 `it()` [RAN git show f292a9c], and [RAN npx vitest run tests/runs.test.jsx -> 14 passed] at HEAD. Full-suite 117/117 NOT re-run per "single-file runs OK" constraint — left for ORCH gate (T-003). Arithmetic 115+2=117 is consistent but not independently observed. |

No sub-claim is MISCLASSIFIED. There was never a NOT-REPRODUCIBLE element: the pre-fix code provably produced the symptom (see root cause).

**Evidence — the fix as landed:**
```jsx
// frontend/views/RunDetails.jsx:214-222 (HEAD)
const durationMs = run.started_at && run.finished_at
  ? new Date(run.finished_at) - new Date(run.started_at)
  : null;
const seconds = durationMs === null || Number.isNaN(durationMs)
  ? null
  : Math.max(0, Math.round(durationMs / 1000));
```
[VERIFIED frontend/views/RunDetails.jsx:217-222] Pre-fix (parent of f292a9c): `const seconds = run.started_at && run.finished_at ? Math.max(0, Math.round((new Date(run.finished_at) - new Date(run.started_at)) / 1000)) : null;` [RAN git show f292a9c^:frontend/views/RunDetails.jsx]. This is the only delta in source.

**Root cause chain:**

1. **Symptom:** Run details header renders literal "Took NaN s".
2. **Mechanism:** `run.started_at`/`run.finished_at` are truthy garbage strings (e.g. `'garbage'`). Guard `a && b` passes. `new Date('garbage')` → Invalid Date → `getTime()` NaN → subtraction yields `NaN` → `Math.round(NaN/1000)` is `NaN` → `Math.max(0, NaN)` is `NaN` (Math.max propagates NaN). `seconds` is `NaN`, and `NaN !== null` is true, so the chip `{seconds !== null && …}` renders `Took {NaN} s`. Every step in this chain is standard JS semantics [FACT]; the missing step was a finiteness check between computation and render.
3. **Origin:** The duration was computed inline in the view with raw `Date` subtraction and no validation, while sibling surfaces already guarded NaN via `format.js` (`timeAgo`/`formatWhen` return "—" on `Number.isNaN(d.getTime())` [VERIFIED frontend/format.js:28,43], landed in A1 `092e800`). The duration site was the one remaining raw-date-math consumer — the A1/E pattern simply hadn't been applied to it. Why earlier fixes didn't hold: they fixed *formatting* (display of a single timestamp), not *arithmetic on two timestamps*, so the NaN source (subtraction, not `toLocaleString`) survived untouched.
4. **Why garbage timestamps reach the view at all [ASSUMED]**: backend serializes `started_at`/`finished_at` via `.isoformat() if … else None` [VERIFIED backend/app/main.py:2330-2331], so real rows are ISO or null. Garbage strings arrive only via stale/corrupt rows, API drift, or test fixtures — the frontend test harness injects them directly. The view must not trust the wire format; the fix's distrust is correct. Garbage is not reachable through the current happy-path backend [ASSUMED — inferred from serialization code, not from a live request].

**Blast radius (sibling locations):**

- **"Took" chip / duration arithmetic:** exactly **1** production site. Grep `Took` over `frontend/` hits only `RunDetails.jsx:238` (+ test strings). No other `new Date(a) - new Date(b)` duration computation exists in `frontend/` source — the only other `new Date(` hits are inside `format.js` (:27, :42), already guarded, and test/helper timestamp *construction* (`format.test.js:11`, `helpers.jsx` — constructors, not diffs). **No unguarded sibling duration site found.**
- **Other NaN/unparseable date surfaces:** all render through `timeAgo`/`formatWhen` [VERIFIED frontend/format.js:25-45]. Callers: `RunDetails.jsx:237` (Started), `RunsDashboard.jsx:127-128`, `AdminScreen.jsx:164,385,586,626`, `shared.jsx:58` (quota reset) — all inherit the A1 NaN→"—" guard. Grep found **0** additional raw `.toLocaleString(`/`Invalid Date`-prone render sites.
- **`wall_seconds`:** the backend already returns a server-monotonic duration (`wall_seconds`, from `time.monotonic()` [VERIFIED backend/app/executor.py:147, backend/app/main.py:2332]) which the view **ignores** — it recomputes duration client-side from timestamps. Not a defect (consistent display), but relevant to the design discussion below.
- **Consumers/tests affected by the fix:** `RunDetails` header only. Contract impact: none — UI text only, no API/schema change [VERIFIED git show f292a9c -> no backend files]. Test surface: `runs.test.jsx` 12→14 tests in that file [RAN vitest -> 14 passed].

**Edge cases the guard may miss — assessment:**

| Case | Behavior at HEAD | Verdict |
|---|---|---|
| Both timestamps null/undefined/`""` | `a && b` falsy → `durationMs null` → chip hidden | ✅ Handled (pre-existing) |
| Both garbage (the P3 case) | diff `NaN` → `Number.isNaN` → null → hidden | ✅ Handled (the fix) |
| **Mixed** garbage/valid (one side garbage) | `new Date(valid) - new Date(garbage)` → `NaN` → hidden | ✅ Handled by same guard — ledger's "info" deferral is over-cautious; the guard is generic over NaN regardless of which side produced it. No test, but reasoning is airtight. |
| Valid equal timestamps (0 duration) | `durationMs 0` → `seconds 0` → `0 !== null` → "Took 0 s" | ✅ Handled + tested |
| **Negative diff** (finished < started, clock skew) | `Math.max(0, …)` clamps to 0 → renders "Took 0 s" | ⚠️ Handled but *silently misleading*: a skewed/negative duration displays as a genuine 0s run. Pre-existing behavior (not introduced by f292a9c; `Math.max` was in the old code too). Real leaf, low severity — honest fix would hide the chip on negative diff. Deferred by ledger; agree it's optional. |
| Sub-second durations (e.g. 400ms) | `Math.round(0.4)` → 0 → "Took 0 s" | ✅ By design (whole-second display) |
| `Infinity`-producing inputs | Not possible from `Date` subtraction of valid dates (bounded ~±8.64e15 ms); `Number.isNaN` suffices. `Number.isFinite` would also work but adds nothing here. | ✅ No leaf |

So: no missed NaN leaf. The only genuine residual is negative-diff honesty (display choice, not a crash/leak).

**Tests — reversal analysis:**

- Garbage test (`runs.test.jsx:573`): asserts no `/took/i` text and no `NaN` in body. Under revert (old inline formula), `seconds = NaN`, chip renders "Took NaN s" → **test fails**. ✅ Genuine reversal coverage.
- Zero test (`runs.test.jsx:597`): asserts "Took 0 s" renders. Under revert, old formula also yields 0 → test **passes on both versions** — it is a *guard against overcorrection* (a naive `if (!seconds)` fix would hide it), not a bug-reproduction test. Correct design; it protects the fix's boundary.
- [RAN `npx vitest run tests/runs.test.jsx` -> 14/14 passed, 5.04s] at HEAD, including both P3 tests. The timing-sensitive Progress-poll test (:157, noted flaky in 00-mission) passed this run but is unrelated to P3.
- Reversal was reasoned, not executed (no mutation run; brief allows single-file runs but a temp revert would touch files outside this agent's write-set). The pre-fix code path above makes the garbage-test failure deterministic [FACT by code reading].

**Design — root-cause or symptom?**

The remedy fixes the *display invariant* ("seconds is null unless both timestamps parse") at the exact site where the invariant was violated, following the established A1/E convention in `format.js`. It does not add a shared helper — arguably consistent, since a duration formatter would be the only consumer.

Two alternatives, for the record:

- **Option A (landed): local NaN guard.** Pros: minimal, matches existing convention, zero contract change, proven by 2 tests. Cons: the next duration computation elsewhere would repeat the pattern; relies on `Math.max` clamping for negative diffs.
- **Option B (not taken): use backend `wall_seconds`.** Pros: server-monotonic, immune to client clock skew and timestamp corruption; single source of truth. Cons: `wall_seconds` is null for queued/interrupted runs and is an integer column [VERIFIED backend/app/models.py:140]; would need fallback logic anyway; larger change touching the render contract; contradicts the timestamp-derived display the UI already presents elsewhere. Rejected reasonably — B is a product decision, not a bug fix.

**Verdict:** root-cause-adequate for a SURFACE display bug. The *cause* ("view trusted unvalidated wire strings in arithmetic") is addressed at the trust boundary (computation→render), not papered over downstream. No blanket try/catch, no special-casing — the guard is generic over all NaN sources.

**Long-run test:**
- **Source:** N/A beyond what tests cover. [ASSUMED] Wire-format drift (e.g. backend switching date format) is the realistic source; both timestamps garbage → hidden chip, no leak.
- **Load (100×):** Trivial arithmetic per render; no added cost. Poll-driven re-render re-runs the same cheap computation. ✅
- **Hostile input:** Garbage/oversized strings in timestamp fields → `Date` parse fails → NaN → hidden. No injection surface (timestamps never rendered raw; `formatWhen` renders "—"). ✅
- **Operability:** N/A — pure display; no migration, no config, rollback = revert one commit. ✅
- **Reversal:** Which test fails if reverted? The garbage test (:573) fails deterministically; zero test (:597) passes (guard-rail). See above. ✅

**Classification:** **SURFACE** — single-file display guard, no contract/schema/state change, no cross-domain effect. Matches ledger T-001 classification. Criteria hit: localized, reversible, no invariant beyond the render site.

**WRITE-SET (for a hypothetical follow-up, not needed for this fix):** `frontend/views/RunDetails.jsx`, `frontend/tests/runs.test.jsx`. **CONTRACT-SET:** none. **DEPENDS-ON:** none. **ENV-SET:** jsdom/Vitest only.

**Test plan (residual, optional):** mixed garbage/valid case (1 test, proves genericity); negative-diff case (decide: hide vs clamp — product call). Both already deferred as nice-to-have in `01-work-ledger.md:29,40`; I concur with deferral — neither is reachable through the current backend serialization and neither leaks NaN.

**Conflicts/ordering:** None. `frontend/format.js` is a hotspot per `00-mission.md:25` but f292a9c does **not** touch it. No overlap with other agents' write-sets in this wave (W1 ownership: T-001 owned exactly these 2 files [VERIFIED 01-work-ledger.md:18]).

**Acceptance criteria (measurable) — all met at HEAD:**
1. Garbage timestamps → no "Took", no "NaN" in DOM. ✅ [RAN vitest -> P3 garbage test passes]
2. Valid 0s → "Took 0 s" rendered. ✅ [RAN vitest -> P3 zero test passes]
3. Single-file suite green. ✅ [RAN npx vitest run tests/runs.test.jsx -> 14/14]
4. Full-suite 117/117. ⏳ PARTIAL — awaiting ORCH gate T-003; arithmetic (115+2) and single-file result support it but it was not observed here.

---

## 2. Duplicates / shared root causes across items

Single plan item (P3) in scope. The shared root cause with A1/E (`092e800`, `6c72d75`) — "unvalidated date strings reaching render" — is now closed at every identified surface: formatters (A1), tooltips (B2/E), duration arithmetic (P3). Grep shows no remaining raw date-math render site. No duplicates.

## 3. Out-of-plan discoveries

None. One documentation drift noted in §0 (AGENTS.md single-file SPA description vs `views/` split) — recorded as fact, not added to scope.

## 4. Assumptions and unknowns

- **[ASSUMED]** Garbage timestamps are not reachable via the current backend happy path (serialization is `.isoformat() or None`); P3 is a defensive fix for corrupt/stale rows or wire drift. Would need a live seed or DB inspection to confirm reachability — not done (read-only investigation, no shared-DB runs per standing orders).
- **[ASSUMED]** 115/115 at `2502fd9` (from commit message; not re-run). Hence 117 total is PARTIAL, pending T-003 gate.
- **[UNKNOWN]** Whether any production rows actually contain garbage `started_at`/`finished_at` — requires DB access, out of scope.
- **Facts vs assumptions discipline:** everything in "Evidence", "Root cause chain" (JS semantics + code paths), "Blast radius" (grep counts), and "Tests" (reversal reasoning over the actual pre-fix diff) is verified against code/command output. Only reachability-in-production and the 117 total are flagged ASSUMED/PARTIAL.

## 5. Recommended task breakdown and ordering

**No new task required for P3 — the fix is landed, minimal, tested, and reviewed (ledger T-001 DONE, T-002 APPROVE).** Recommended remaining work, in order:

1. **T-003 ORCH gate** (already planned): full `npm test` + `npm run build` at `f292a9c`/`69fe44e` to convert the PARTIAL 117 claim to verified. Re-run once if the known flaky Progress-poll test trips (per 00-mission pre-mortem).
2. **Optional SURFACE follow-up (1 task, only if the team wants the info items closed):** add mixed garbage/valid + negative-diff tests in `runs.test.jsx`; if negative-diff should hide rather than clamp, one-line change in `RunDetails.jsx` (`durationMs < 0 → null`). Independent of gate; may be deferred indefinitely with no user-visible risk.
3. Do **not** pursue Option B (`wall_seconds`) without a product decision — it changes display semantics, not a bug.

*No DEEP work identified. No conflicts, no ordering constraints, no hotspot contention.*
