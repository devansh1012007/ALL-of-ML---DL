# Plan: Frontend deferred follow-ups (Round 2)

- Status: APPROVED (autonomous — standing instruction "work automatically, don't ask" recorded as approval; planner-reviewer Approve-with-changes folded)
- Tier: M (several files, single module boundary, new behavior with tests, no API/schema change)
- Repo state: branch `frontend-ui-round2`, commit `092e800`, date 2026-11-08
- Spec: `docs/tech-debt.md` Round 2 items; operator message in checkpoint
- Operator / agent: autonomous (no interactive gates; reviewer per phase + final review per AGENTS.md)
- Staleness rule: re-verify `frontend/format.js` / `frontend/views/*` before resuming; Phase A is shipped at `092e800`.

## A. Problem, goal, success criteria
- Problem: four small deferred items ship sub-par a11y/robustness: JS `"Invalid Date"` leak, mouse-only row click, Tab-only segmented control, untested RL env-id label.
- Why now: tech-debt Round 2 follow-up; Phase A already committed, B–D are the remainder.
- Goal: fix each in an atomic phase with failing-first tests + independent review (AGENTS.md §1–4); no behavior/API changes.
- Success criteria (observable):
  - `npm test` 106 → ≥111 (B1/B2/C/D new tests), `npm run build` green.
  - No `"Invalid Date"` string reachable from formatters (unit-tested).
  - Runs rows reachable by keyboard (link) with no mouse-only affordance.
  - Predict segmented navigable by arrow keys without breaking `getByRole('button')` queries.
  - RL env-id label pinned by a seed test incl. submit payload `env_id`.
- Non-goals: light theme, Chromium/SR probes, backend pytest (manual/NOT-RUN, accepted risk — see §L).
- Constraints: references/pinned copy preserved; tokens only; one component per change; endpoint `/api/v1/ml/...` unchanged.
- Reversibility: two-way (single frontend commits, no migrations); rollback = `git revert <sha>`.

## C. Architecture (part that matters)
- Entry: `frontend/App.jsx` (shell + hash router) → `frontend/views/*.jsx`; shared `frontend/components/shared.jsx`, `frontend/components/metrics.jsx`; formatters `frontend/format.js`.
- Data flow: fake backend `frontend/tests/helpers.jsx` seeds `state.models/runs/...`; components fetch via `apiFetch`.
- Invariants: every ML route needs token; runs list `{items,...}` envelope; formatter contract `null → "—"` (true zero stays zero); predict request shapes (`rows/texts/prompt/window_rows/node_ids/state/image`) frozen by `predict.test.jsx`.
- Conventions: R6 split DAG (`shared ← metrics ← views ← App`); static scan covers App+views+components; `scope="col"`, 24px AA targets, `role=group`+`aria-pressed` toggle semantics.

## D. Proposed design
- A (DONE): NaN-guard in `timeAgo`/`formatWhen` → `"—"`.
- B1: remove row `onClick` + `cursor-pointer` (`RunsDashboard.jsx:90`); link remains the keyboard path; remove dead `stopPropagation` (`td` + link `onClick` closers are dead once row click is gone — remove the `e.stopPropagation()` handlers only, keep the elements).
- B2: Started tooltip `title={formatWhen(run.created_at)}` (depends on A; now satisfied).
- C: keep `role="group"` + `aria-pressed`; container `onKeyDown` (bubbled from focused button) handles ArrowLeft/Right/Home/End with `preventDefault()`, refs `.focus()`, clamp at ends, select-on-arrow; Up/Down = Left/Right; RTL accepted as-is (no special-case).
- D: per-test RL seed (do NOT pollute `newJobSeed` default); label + `id` + submit payload assertion.

## E. Change list (atomic, ordered)

| ID | File and symbol | WHAT | HOW | WHY not alternative | Depends on | Verified by | Risk | Revert |
|---|---|---|---|---|---|---|---|---|
| A1 | `frontend/format.js::timeAgo/formatWhen` | DONE: NaN → `"—"` | `092e800` | — | none | format.test.js garbage ×2 | low | revert `092e800` |
| B1 | `frontend/views/RunsDashboard.jsx::RunsDashboard` tr | Remove `onClick`+`cursor-pointer`; drop dead `stopPropagation` | delete row handler; remove `e.stopPropagation` closures | stretched-link breaks nested checkbox; `tabIndex`+Enter = duplicate stop | A1 (tooltip not needed) | runs.test.jsx hash assertions (below) | Med (mouse convenience removed — accepted D-B1) | revert commit | DONE `c2dd5db` (APPROVE) |
| B2 | `frontend/views/RunsDashboard.jsx` Started `td` | Tooltip via `formatWhen` | `import {formatWhen}` + `title={formatWhen(run.created_at)}` | one fix per phase (planner-reviewer MAJOR-1) | A1 | runs.test.jsx garbage `created_at` → `title="—"` | low | revert commit | DONE `64c99f8` (combined APPROVE) |
| C1 | `frontend/views/PredictPanel.jsx::PredictPanel` segmented | Arrow/Home/End + select-on-arrow | `useRef` ×2, `handleSegmentedKeyDown`, Clamp, ↑/↓ alias | `radio`/`radiogroup` = semantic change + breaks `getByRole('button')` (plan-review note: test cost, not strawman) | none | predict.test.jsx arrows + Tab + non-arrow no-op | low | revert commit | DONE `87a6f08` (combined APPROVE) |
| D1 | `frontend/tests/newjob.test.jsx` new describe | Per-test RL seed + label/id + submit `env_id` | `models:[Random_Forest, Q-Learning]` only in this test; `getByLabelText(/gymnasium environment id/i)`; `id="newjob-env-id"`; train call body `env_id` | polluting default seed breaks all NewJob tests (reviewer MAJOR-5) | none | new test (red first: no seed → unable to find label) | low | revert commit | DONE `736339a` (combined APPROVE) |
| E | `frontend/views/RunDetails.jsx` + `frontend/components/shared.jsx` | Close 2 residual raw-date leaks (final-review P2) | `title={formatWhen(...)}`; quota `resets at ${formatWhen(...)}` | shared→format one-way, cycle-free; single sentinel path | A1 | runs + format tests red→green (115) | low | revert commit | DONE `6c72d75` (APPROVE) |

Trace tags: `PLAN:deferred-followups:A1|B1|B2|C1|D1`.
Ordering: A1 shipped → B2 can land any time; B1 needs user-visible decision (autonomous D-B1); C1 and D1 disjoint; all four write-sets disjoint (format / Runs / Predict / newjob test).

## F. Files affected
| File | Change | IDs | Who else depends |
|---|---|---|---|
| `frontend/format.js` | modify (done) | A1 | all date callers (Runs/Admin) |
| `frontend/tests/format.test.js` | modify (done) | A1 | — |
| `frontend/views/RunsDashboard.jsx` | modify | B1, B2 | runs.test.jsx (R5 comment), static guards |
| `frontend/tests/runs.test.jsx` | modify | B1, B2 | — |
| `frontend/views/PredictPanel.jsx` | modify | C1 | predict.test.jsx `getByRole('button')` queries (must stay valid) |
| `frontend/tests/predict.test.jsx` | modify | C1 | — |
| `frontend/tests/newjob.test.jsx` | modify | D1 | helpers default models untouched |

## G. Alternatives and decisions

| ID | Decision | Options | Chosen | Why | Rejected | Mind-changer |
|---|---|---|---|---|---|---|
| D-A | Invalid date → what | literal / crash / `"—"` | `"—"` | only unknown sentinel in formatter contract | literal = JS leak; crash = loss of whole panel | backend contract change |
| D-B1 | Runs row | remove click / stretched-link / key-handler | REMOVE (autonomous, see risk) | link is already correct keyboard path; stretched-link conflicts with nested checkbox; key-handler adds duplicate tab stop + SR ambiguity | keep mouse affordance with stretched-link (reviewer recommendation) if operator disagrees | operator reversal |
| D-B2 | tooltip | `formatWhen` / leave raw | `formatWhen` | reuses A1 guard, one path | — | — |
| D-C | segmented semantics | keep group+pressed+arrows / `radio` roving | keep + arrows | 2-option toggle pressed semantics are honest; `radio` changes SR name + breaks queries for no benefit at n=2 | radio (APG purist) | SR pass flagging it |
| D-D | RL seed | per-test / default | per-test | default pollutes every NewJob test | default (simpler) | shared fixture refactor |
| D-E | residual leaks | formatWhen both / leave quota sentence raw | formatWhen both | single sentinel path; format.js standalone so shared→format is acyclic | partial (RunDetails only) | — |

## H. Tests and validation
- Baseline (re-verified by planner-reviewer): `npm test` 104/104 at `7b9458d`; 106/106 at `092e800` (A1 red `Invalid Date` → green).
- Existing guarantees: format null/false contract, runs envelope, predict request shapes (8 kinds), static guards (negative margins, `scope=col`, split coverage).
- New tests:
  - T-B1: `fireEvent.click(tr)` → `location.hash` unchanged; model link click → `#/run-details/7`; checkbox still toggles + Compare enabled; update R5 "mouse-only" comment.
  - T-B2: `created_at:"garbage"` seeded run → `td[title]="—"`, cell `"—"`.
  - T-C: focus One row → ArrowRight → Several pressed+focused+rows-JSON visible; ArrowLeft back; Home/End; Tab reaches both (`Tab` order via DOM); non-arrow key no-op (`aria-pressed` unchanged); `document.activeElement` moves.
  - T-D: seed `[Random_Forest (classification), Q-Learning (reinforcement-learning, params {})]` per-test; `getByLabelText(/gymnasium environment id/i)` exists + `id="newjob-env-id"`; absent for Random_Forest default; type `CartPole-v1` → Start → train body `env_id==="CartPole-v1"`.
- Per-phase: investigation subagent first, failing-first red run, full `npm test` + `npm run build`, independent reviewer APPROVE (no critical/major), manual dev-server check (`cd frontend; npm run dev` + spot-check the touched view), then commit.
- Backend pytest: still NOT-RUN (no `.venv`, frontend-only diff); Chromium/SR probes: still manual — NOT-RUN accepted risk (§L).

## I. Edge cases (from this code)
| Case | Where | Expected | Handled by |
|---|---|---|---|
| garbage date string | format.js | `"—"` (not `"Invalid Date"`) | A1 ✓ |
| `timeAgo(0)` → falsy guard | format.js:26 | `"—"` (accepted deviation; `new Date(0)` never a real run date) | documented, out of scope |
| RTL arrow direction | PredictPanel | acceptable as-is (documented) | C1 note |
| arrow at ends (clamp vs wrap) | PredictPanel | clamp (no wrap surprise at 2 options) | C1 spec |
| RL model-details missing `test_results` | NewJob:658 | Model Intelligence panel hidden (no crash) | existing guard |

## K. Rollout / rollback / observability
- Rollout: frontend-only, no flags/migrations; phases commit independently on `frontend-ui-round2` (PR #2; do not merge without user approval).
- Rollback: `git revert <phase-sha>` per phase; risk = none (no data).
- Observability: tests are the signal; dev-server spot check per phase.

## L. Risks, assumptions, open questions
| ID | Type | Notes | Likelihood×impact | Mitigation / verify | Status |
|---|---|---|---|---|---|
| R-B | risk | B1 removes whole-row mouse click (reviewer BLOCKER-2) | Med × Med | D-B1 autonomous decision; link remains; owner may revert to stretched-link | ACCEPTED (autonomous) |
| R-P | risk | probes/pytest still manual | Low × Med | carry in `tech-debt.md`; do not claim SR/visual verification | ACCEPTED |
| A-Q | assumption | Q-Learning catalog category is `reinforcement-learning` | — | verify from `backend/app/model_training.py` before seeding; if absent, seed name must match real catalog | VERIFY in D1 |

Pre-mortem top causes: B1 dead `stopPropagation` removal breaks checkbox toggle (test proves); C1 `e.currentTarget` vs `e.target` ref mixup (test proves focus); D1 seed pollution breaks other tests (per-test seed avoids).

## M. Decision log
- F1: Phase A re-baselined DONE at `092e800` (planner-reviewer BLOCKER-1).
- F2: B split B1/B2 (MAJOR-1); B1 vs stretched-link = autonomous D-B1 (BLOCKER-2) — flagged as residual risk, reversible.
- F3: C keeps group+pressed; clamp + preventDefault + ↑/↓ alias (MAJOR-3/4).
- F4: D per-test seed + submit `env_id` assertion (MAJOR-5); catalog spelling to verify.
- Pre-mortem / red-team: covered by planner-reviewer; cold-read = reviewer report `ses_e44d4c4b4ffeZ7o07tjDa1DYCc`.
- F5 (final review P2): Phase E closes residual leaks at RunDetails + shared quota text (`6c72d75`, independent APPROVE). Final combined APPROVE (113/113; E re-runs green 115/115 with one unrelated timing flake noted — runs.test.jsx:196 Progress poll, pre-existing). P3 FIXED f292a9c (2026-11-08): RunDetails.jsx duration chip hides on NaN diff (null sentinel; valid 0s still renders "Took 0 s"); +2 tests in runs.test.jsx (garbage-hide, zero-render).
