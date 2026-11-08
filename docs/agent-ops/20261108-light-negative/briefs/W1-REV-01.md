# Brief — W1-REV-01 (code reviewer) · wave 1 · run 20261108-light-negative

## 1. Role and mission
You independently audit Wave 1 (two commits): T-102 negative-diff hide-chip (`ca5d950`, RunDetails.jsx + tests) and T-103 tech-debt reword (`9c73971`, docs). You wrote neither. Failure mode to hunt: an honesty fix that hides too much (or cheats by special-casing the negative test input), or a reword that silently changes a citation. Reviewer ≠ author.

## 2. Required reading
1. docs/agent-ops/20261108-light-negative/templates/STANDING-ORDERS.md (binding)
2. docs/agent-ops/20261108-light-negative/templates/review-code.md (your report template — ORCH-DIGEST first)
3. docs/agent-ops/20261108-light-negative/briefs/W1-IMPL-01.md and W1-IMPL-02.md (acceptance criteria)
4. Blind pass FIRST: `git show ca5d950`, `git show 9c73971`, frontend/views/RunDetails.jsx, docs/tech-debt.md:14-22
5. THEN read: docs/agent-ops/20261108-light-negative/reports/w1-impl/W1-IMPL-01-T-102.md, W1-IMPL-02-T-103.md, INV-negative-counts.md (claims audit)

## 3. Task and acceptance criteria
Blind pass first (form findings before implementer reports). Then claims audit. Must cover:
- T-102: does `durationMs < 0` correctly hide negative diffs while preserving sub-second rounding (400ms → 0 → valid) and zero? Is Math.max kept (defense-in-depth, not removed)? Any other duration site needing the same guard (grep Took/duration)? Comment accurate?
- T-103: does the new line 17 match the intended genealogy text with all 4 citations byte-identical, and only line 17 changed (`git diff 9c73971^..9c73971 --stat`)?
- Band-aid hunt: special-casing negative test values? Optional chaining hacks? Suppressed lint?
- Edge: `-0`? `Infinity`? boundary -1ms? (reason them)
Verdict APPROVE | APPROVE-WITH-CHANGES | REJECT, BLOCKER/MAJOR/MINOR/NIT with file:line evidence + suggested fixes. Write to: docs/agent-ops/20261108-light-negative/reports/w1-review/REV-W1-IMPL-01.md. You are read-only; do NOT edit/commit source.

## 4. Ownership
READ-ONLY. Write only your report. Scoped greps/`git show` only — never full suite/build.

## 5. Deliverables
Report first (append as you work; ORCH-DIGEST first). Final message ≤8 lines: STATUS | agent | report path | verdict | findings counts | blockers.
