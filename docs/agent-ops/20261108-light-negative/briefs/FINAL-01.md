# Brief — FINAL-01 (final integration reviewer) · run 20261108-light-negative

## 1. Role and mission
You are a FRESH reviewer with NO prior context. Audit the complete combined change on branch frontend-ui-round2 for this run (base 85acdda → HEAD, excluding docs/agent-ops). In scope: T-102 negative-diff hide-chip (`ca5d950`), T-103 tech-debt reword (`9c73971`), T-101 light mode (`21f65c13` + `94963e6`). The question: is each of the three truly closed — code+tests+docs — and is anything else broken? You wrote none of it.

## 2. Required reading
1. docs/agent-ops/20261108-light-negative/templates/STANDING-ORDERS.md (binding)
2. docs/agent-ops/20261108-light-negative/templates/review-code.md (report template — ORCH-DIGEST first)
3. docs/agent-ops/20261108-light-negative/00-mission.md (scope + baseline 117/117, gate 154/154)

Do NOT read per-task reports (INV-*, *-impl, REV-*, TREV-*) — form findings from the diff + code first. Open them only for the final claims check. Skip planner-review/spec detail; judge the shipped diff.

## 3. Task and acceptance criteria
Diff: `git diff 85acdda..HEAD -- . ':!docs/agent-ops'` plus `git show ca5d950`, `git show 21f65c13`. Spot-verify:
1. NEGATIVE-DIFF: finished<started → chip hidden; zero → "Took 0 s" unaffected; no sibling duration site.
2. LIGHT MODE: 14 light triples == design (recompute 3-4 ratios yourself, e.g. faint/raised, warn/canvas, accent-ink/accent); dark :root byte-identical to 85acdda (`git diff 85acdda..HEAD -- frontend/styles.css` shows only the added light block); init script head-first + guarded; toggle reachable in both shells, outside <nav>; hostile values can't reach DOM; sign-out doesn't clear prime_theme; RunDetails + tailwind.config untouched.
3. DOCS: tech-debt:17 genealogy counts unambiguous; probe line honest.
Verdict APPROVE | APPROVE-WITH-CHANGES | REJECT with file:line evidence + top risks. Explicitly state whether you'd let the branch be pushed. Write to: docs/agent-ops/20261108-light-negative/reports/final/FINAL-01.md. Read-only; do NOT edit/commit.

## 4. Ownership
READ-ONLY. Scoped checks (single-file vitest at most, greps/`git show`); never full suite/build.

## 5. Deliverables
Report first (append as you work; ORCH-DIGEST first). Final ≤8 lines: STATUS | agent | report path | verdict | findings counts | push decision | blockers.
