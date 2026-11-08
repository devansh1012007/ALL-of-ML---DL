<!-- ORCH-DIGEST:START -->
agent: W1-REV-01 | scope: W1 V-103+V-104 (12f46a0, b86d3a2) | verdict: APPROVE
findings: BLOCKER 0 | MAJOR 0 | MINOR 2 | NIT 2
claims_audit: 14 claims checked / 1 inaccurate (V103 §8 "error.status=502" wording; code correct)
band_aids_found: none
top_3_risks: V-104 rendered hostile overflow still unproven in a browser (static-only, F-04 accepted; follow-up owner named by W1-IMPL-02) | V-103 Playwright spot NOT-RUN (attrs-only change, vitest DOM evidence sufficient) | register-400 both-fields overlabel accepted per plan F-09
optimizations: DO-NOW 0 | DO-LATER 1 | NOT-WORTH-IT 2
reversal_check: reasoned-only (read-only; pre-fix failure derived from old attr expressions vs new negative assertions)
confidence: high (code + tests verified by independent run; rendered wrap proof absent by design)
<!-- ORCH-DIGEST:END -->

# Code review — W1-REV-01 (V-103 + V-104)

## 0. Method
Reviewed commits `12f46a0` (V-103) and `b86d3a2` (V-104) on branch `frontend-ui-round2` against `docs/plans/2026-11-09-playwright-verify.md` (§Resolved/§Phases) and briefs. Blind pass first (`git show` both commits, `AuthView.jsx`, `styles.css:310-311`, `AdminScreen.jsx:553-568`, `shared.jsx` apiFetch contract, `tailwind.config.js`, `static.test.js` header), then implementer reports (`W1-IMPL-01-V103.md`, `W1-IMPL-02-V104.md`). Commands run: `git show`/`git diff --stat`/`git diff --name-only` (both commits + cumulative `8244ec7..HEAD`), `grep` (invite-code/aria references), and `npx vitest run tests/auth.test.jsx tests/static.test.js` from `frontend/` → **59 passed (15 auth + 44 static), 3.09s**. No code edited.

## 1. Blind-pass findings (before reading implementer reports)
1. **Whitelist mapping correct.** `ariaFor` (`AuthView.jsx:8-12`): 409→username-only (`uIn` only), 400→both, else→describedby-only on both fields. 403 falls in else (describedby-only), matching the user-confirmed resolved rule. `err.status` consumed directly (no string parsing anywhere in the file); network `Error` from `shared.jsx:206-211` carries no `status` → `undefined` → else branch. `shared.jsx:219/239` confirm HTTP errors carry numeric `status`.
2. **Clear+gate disciplined.** `handleSubmit` clears both `error` and `errorStatus` (`:25-26`); all four attrs gated `error && <branch> ? … : undefined` (`:81-82, :93-94`) — never literal `false`, never dangling: every present `describedby` points at `auth-error`, which renders iff `error` is truthy (`:73`). Pre-error DOM unchanged.
3. **Wrap pair correct.** `.admin-invite-code-text { min-width: 0; overflow-wrap: anywhere; }` (`styles.css:311`) + wrapper `min-w-0` (`AdminScreen.jsx:555`) + class on the code div (`:556`). `anywhere` (not `break-all`) means breaks only when the line must break; flex-item min-content is defeated by the paired `min-width: 0`s. `tailwind.config.js:6` includes `./AdminScreen.jsx` in `content`, so `min-w-0` is generated (the stale AGENTS.md note listing only App.jsx/main/index is outdated — verified, not assumed).
4. **No forbidden files.** `12f46a0` touches only `AuthView.jsx` + `auth.test.jsx`; `b86d3a2` touches only `AdminScreen.jsx` + `styles.css` + `static.test.js`. Cumulative diff `8244ec7..HEAD` adds only the two implementer reports. `helpers.jsx`, `shared.jsx`, `tailwind.config.js` untouched.
5. Commit trailers (Task/Agent/Wave/Report) present on both code commits.

## 2. Claims audit
| Implementer claim | Verified? | Evidence / finding |
|---|---|---|
| V103: whitelist 409 username-only / 400 both / else describedby-only incl. 403 | ✅ | `AuthView.jsx:8-12`; 403/401/429/500/502 in else by construction; tests pin each branch |
| V103: `errorStatus` null=none, `undefined`=network; cleared on submit; no string parsing | ✅ | `:19, :26, :56`; `grep` shows no message parsing in AuthView |
| V103: describedby invariant (no dangling) on every branch | ✅ | gating on `error` (`:81-82, :93-94`); `checkDescribedByInvariant` in every test; 409 password attrs absent not dangling |
| V103: 15/15 auth tests pass; 7 discriminating fail pre-fix, 400 passes both ways | ✅ pass / pre-fix reasoned | Independently ran: 15 passed. Pre-fix failure reasoned-only (read-only): old attrs `error ? true : undefined` on both fields vs new `not.toHaveAttribute("aria-invalid")` assertions — must fail; 400 identical both versions |
| V103: helpers.jsx untouched; forbidden files untouched | ✅ | `git diff --name-only 8244ec7..HEAD` on helpers/shared/tailwind: empty |
| V103: Playwright spot NOT-RUN, honest | ✅ | Honest; vitest DOM evidence sufficient for attrs-only change |
| V103 §8: oversized HTML body → connectivity sentence "with error.status=502" | ⚠️ inaccurate wording (code correct) | `shared.jsx:234-239`: fallback sentence but `error.status = response.status` (whatever the server returned, e.g. 500), not hardcoded 502. Report-only inaccuracy — see R-W1-REV-002 |
| V103: `setErrorStatus(err.status)` direct vs `'status' in err` guard | ✅ | Safe: apiFetch always throws real `Error`; even a string throw yields `undefined` `.status` without throwing |
| V104: Wrap A pair (anywhere + min-w-0 wrapper) correct; `anywhere` over `break-all` | ✅ | `styles.css:311`, `AdminScreen.jsx:555-556`; `anywhere` also shrinks min-content (vs `break-word`), correct choice |
| V104: static pin non-vacuous (block-scoped, not bare `toContain('min-w-0')`) | ✅ | `static.test.js:613-615` slices at `admin-invite-code">` (unique to `:554`; the `:556` class is `admin-invite-code-text`, no false hit) and first 400 chars; self-checks fail pre-fix literals |
| V104: 44/44 static tests pass | ✅ | Independently ran: 44 passed |
| V104: Playwright hostile NOT-RUN, closed static-only per F-04 with named follow-up | ✅ | Honest; follow-up owner (future backend-up Playwright run) + concrete procedure named in §5 |
| V104: short-code layout unchanged | ⚠️ not measured (honestly flagged) | jsdom cannot measure layout; report marks `[UNKNOWN]` and defers — accepted per F-04, residual risk noted |
| Both: write-set discipline, trailers, no NEED/FINDING left dangling | ✅ | Diff stats confirm; trailers present on both commits |

**14 claims checked, 1 inaccurate (report wording only), 1 honestly-deferred measurement.**

## 3. Long-run test (independent answers)
- **Source:** Status contract re-verified against installed `shared.jsx:206-241` (network→bare `Error`, 401→`error.status=401`, HTTP→numeric `response.status`); invite-token shape and `anywhere` precedent consistent with codebase (`styles.css` existing sites). Nothing taken from memory.
- **Load:** One extra scalar + 3-branch pure function per render in AuthView; one static CSS rule. No I/O, loops, or concurrency surface. Concurrent submits write `error`/`errorStatus` together in one catch; retry clears both first — no torn/stale branch.
- **Hostile:** Unknown/future statuses (404/405/422/≥500) cannot over-claim invalid (else→describedby-only) by construction. `aria-describedby` value is the literal `'auth-error'` constant, never user input. 64/256-char invite tokens: wrap mechanism correct statically; rendered proof deferred to the named Playwright follow-up.
- **Operability:** No migration/config/env; rollback is per-file revert of the 5 code files. No new failure mode: pre-error DOM byte-identical.
- **Reversal:** Reasoned-only (read-only, no stash): reverting attrs to `error ? …` on both fields re-fails the 7 discriminating tests; deleting the CSS rule or either class re-fails the V-104 pin; the 400 guard-rail distinguishes fix from no-op.

## 4. Findings
### R-W1-REV-001 [MINOR] Error/aria state persists across login↔register mode toggle
- Location: `frontend/views/AuthView.jsx:62, :104` · Evidence: `setMode` toggle does not clear `error`/`errorStatus`; an error (and its aria mapping) survives the mode switch, so e.g. a register-409 username-only mapping renders in login mode until next submit. Pre-existing behavior (not introduced by this change; old code had identical persistence). · Why it matters: minor UX/AT confusion on a rare path. · Recommended fix (DO-LATER, not a blocker): clear both states in the mode-toggle handler; add a toggle-after-error test. Root-cause level: state lifecycle, not the whitelist.

### R-W1-REV-002 [MINOR] V103 report §8 overstates the 502 fallback
- Evidence: report says non-JSON error body yields the connectivity sentence "with `error.status=502`"; `shared.jsx:239` sets `error.status = response.status` (real status, e.g. 500). Code is correct; only the report sentence is wrong. · Recommended fix: one-line correction in the report if a docs touch occurs; no code change.

### R-W1-REV-003 [NIT] `ariaFor(errorStatus)` with initial `null` returns the else branch
- Location: `:21`. Harmless because every attr is additionally gated on `error`; only a reader might misread `null` as network. The code comment (`:6-7`) documents the mapping; acceptable as-is.

### R-W1-REV-004 [NIT] V-104 pin's 400-char slice is fail-safe-brittle
- `static.test.js:613-615`: if >400 chars are ever inserted between the invite-code div and its classes, the pin fails loudly (does not false-pass). Acceptable; flagged only so a future failure is debugged in the right direction.

## 5. Attempts to break it
- **Status sweep:** reasoned over every value `apiFetch` can throw — `undefined` (network → else), 400/401/403/404/405/409/422/429/500/502 (each pinned or covered by else) — no status can claim invalid without affirmative whitelist evidence. ✅ holds
- **Operator precedence** `error && uIn ? true : undefined` parses as `(error && uIn) ? …` — no precedence bug. ✅
- **409 password-negative:** absent attrs (not `false`, not dangling describedby) — invariant helper proves resolution; test pins both absences. ✅
- **Pin vacuity:** `indexOf('admin-invite-code">')` matches line 554 only (line 556 is `admin-invite-code-text`); slicing is real. ✅
- **TOCTOU/stale status:** cleared at every submit; success path leaves both null. ✅
- **401 path:** harness-forced `/token` 401 goes through `shared.jsx:213-221` (logout + `error.status=401`) → describedby-only; green in independent run (15/15). ✅

## 6. Dimension checklist
- Correctness: ✅ — whitelist, clear+gate, wrap pair all match the resolved plan exactly.
- Root cause vs symptom: ✅ — status persisted at the source (apiFetch contract consumed, not changed); flex min-content defeated at the flex item, not patched over.
- Regression/compat: ✅ — pre-error DOM, alert text/role/id, 400 behavior all byte-identical; pre-submit guard + self-check preserved.
- Concurrency/idempotency: ✅ — paired writes in one catch; submit clears both.
- Error handling: ✅ — network `undefined` preserved (no `?? null` conflation).
- Security/abuse: ✅ — no input surface, no string parsing, literal constant describedby target; status-independent else bucket is fail-safe.
- Performance/scalability: ✅ — O(1) render work, static CSS; zero runtime cost.
- Migration/rollback: ✅ — no schema/config; per-file revert.
- Observability: ✅ — alert discourse unchanged; no silent swallows.
- Maintainability/conventions: ✅ — single pure helper inside AuthView (F-08), test-through-DOM, existing class-naming precedent followed.
- Docs impact: ✅ — plan resolved rules faithfully implemented; only report wording R-W1-REV-002 to correct.

## 7. Optimization and simplification opportunities
| # | Location | Evidence | Impact | Effort | Risk | Verdict |
|---|---|---|---|---|---|---|
| 1 | Mode toggle clears error (`AuthView.jsx:104`) | R-W1-REV-001; 1-line state clear + test | Low (rare path) | Low | Low | DO LATER |
| 2 | Unify 502/500/429 tests into one parameterized else-test | 3 near-identical tests, ~45 lines | Low (file size) | Low | Would weaken per-status evidence | NOT WORTH IT |
| 3 | Export `ariaFor` for unit test | F-08 mandates test-through-DOM; DOM tests already discriminate | None | — | — | NOT WORTH IT |

## 8. Cross-agent / cross-task interactions observed
No conflicts: V-103 files (`AuthView.jsx`, `auth.test.jsx`) and V-104 files (`AdminScreen.jsx`, `styles.css`, `static.test.js`) are disjoint; no shared symbols beyond the unchanged `shared.jsx` contract. No other wave artifacts in the working tree are affected. (`git status` outside the reviewed diff shows only untracked briefs/templates and `.playwright-mcp/` residue; COMMS.md modified outside this review's scope.)

## 9. What I could not verify
- **Pre-fix test failures (7 failed/8 passed):** reasoned-only — read-only mandate forbade stashing/rewriting `AuthView.jsx` to re-run. The derivation is sound (old both-fields attrs vs new negative assertions), but it was not re-executed.
- **Rendered V-104 behavior** (64/256-char overflow at 390px, short-code height invariance): jsdom cannot measure layout; Playwright NOT-RUN is honestly reported by W1-IMPL-02 with a named follow-up owner and procedure. This is the principal residual risk.
- **Playwright V-103 spot-check (429/network describedby-only):** NOT-RUN (no preview server); accepted given the attrs-only change and DOM-level evidence.
