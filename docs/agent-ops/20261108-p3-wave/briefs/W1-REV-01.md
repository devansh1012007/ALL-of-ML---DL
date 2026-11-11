# Brief — W1-REV-01 (code reviewer) · wave 1 · run 20261108-p3-wave

## 1. Role and mission
You independently audit T-004 docs-close (commit 6409d0e) on branch frontend-ui-round2: is the P3-fixed claim accurate against the code, is the scope clean (docs only, no collateral damage), and are the stale sentences fully removed? You are the agent that did NOT write this change. Failure mode to hunt: docs that claim a code state that isn't true, or silent edits beyond the two P3 sentences.

## 2. Required reading
1. docs/agent-ops/20261108-p3-wave/templates/STANDING-ORDERS.md (binding)
2. docs/agent-ops/20261108-p3-wave/templates/review-code.md (your report template — mirror ORCH-DIGEST)
3. docs/agent-ops/20261108-p3-wave/briefs/W1-IMPL-04.md (the implementer's brief — acceptance criteria)
4. docs/agent-ops/20261108-p3-wave/reports/w0-investigation/INV-frontend-P3.md and INV-docs-PR.md (read AFTER your blind pass)
5. docs/agent-ops/20261108-p3-wave/reports/w1-impl/W1-IMPL-04-T-004.md (implementer report — claims audit AFTER blind pass)

## 3. Task and acceptance criteria
Blind pass FIRST: run `git show 6409d0e` and read docs/tech-debt.md:14-22 + docs/plans/2026-11-08-frontend-deferred-followups.md:107-113 + frontend/views/RunDetails.jsx:214-238 + frontend/tests/runs.test.jsx:571-619. Form your own findings BEFORE reading implementer/investigation reports.
Then claims audit: verify every material claim in W1-IMPL-04 report against the diff/code. Report any violated acceptance criterion (either file still claims P3 unfixed; lines 18-22 of tech-debt changed; commit touched code/tests).
Return verdict APPROVE | APPROVE-WITH-CHANGES | REJECT with severity-rated findings (BLOCKER/MAJOR/MINOR/NIT), file:line evidence, and recommended fix. Note: the implementer disclosed missing Task/Agent/Wave/Report trailers on 6409d0e — judge its severity (docs commit, amend forbidden by standing orders).

## 4. Ownership
READ-ONLY on source. Write ONLY: docs/agent-ops/20261108-p3-wave/reports/w1-review/REV-W1-IMPL-04.md. Do NOT edit source. Do NOT commit (orchestrator commits reviews at wave close).

## 5. Scope note
Single-task wave; no parallel implementers. Your domain cluster: docs-claims accuracy (tech-debt vs plan vs RunDetails code).

## 6. Deliverables
Write report first (append as you work; ORCH-DIGEST block first). Final message ≤8 lines: STATUS | agent | report path | verdict | findings counts | blockers. Run only scoped checks if any (e.g. grep); never run the full suite or build — the ORCH gate owns that.
