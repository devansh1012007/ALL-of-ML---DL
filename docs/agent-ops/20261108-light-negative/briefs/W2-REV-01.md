# Brief — W2-REV-01 (code reviewer) · wave 2 · run 20261108-light-negative

## 1. Role and mission
You independently audit T-101 light-mode implementation (commit `21f65c13`) on branch frontend-ui-round2. The design (W2-DEEP-01 D1-D7) and spec (docs/plans/2026-11-08-light-mode.md) are your requirements — but blind-pass the diff FIRST, then claims-audit the implementation report. Budget is blind-first, then claims audit (16-claim style).
Failure mode to hunt: palette values not matching the design table, guards that silently absorb errors (try/catch that hides real failures), toggle state split-brain, hostile stored values reaching innerHTML/selectors, dark `:root` drift, tailwind config or RunDetails edits.

## 2. Required reading
1. docs/agent-ops/20261108-light-negative/templates/STANDING-ORDERS.md (binding)
2. docs/agent-ops/20261108-light-negative/templates/review-code.md (report template — ORCH-DIGEST first)
3. docs/agent-ops/20261108-light-negative/briefs/W2-IMPL-01.md (acceptance criteria)
4. Blind pass: `git show 21f65c13` (full diff), frontend/styles.css, frontend/index.html, frontend/components/theme.jsx, frontend/App.jsx, frontend/views/AuthView.jsx, frontend/views/NewJob.jsx:678 area
5. THEN read: design record (W2-DEEP-01 D1-D7 + checklist), spec docs/plans/2026-11-08-light-mode.md §§4-5, implementation report W2-IMPL-01-T-101.md

## 3. Task and acceptance criteria
Check: (a) 14 light triples == design D2 §2.1 exactly; :root unchanged (`git diff 21f65c13^..21f65c13 -- frontend/styles.css`). (b) head init: placement in <head>, one try/catch, sets attribute+meta from one resolution, guards matchMedia/storage. (c) theme.jsx: allow-list only, no innerHTML/selector writes, storage write in try/catch with in-memory flip, matchMedia guard, resolveTheme side-effect-free. (d) App state: state in App, applyTheme single writer, toggle OUTSIDE <nav>, identical labels/aria-pressed in both shells. (e) NewJob 678 text-warn, zero new hex/`dark:`/palette utilities in shipped files (run the spec §5.5 greps yourself on the diff). (f) RunDetails.jsx + tailwind.config.js untouched (`git diff ... -- <paths>` empty). (g) Probe record in tech-debt is honest (NOT-RUN vs OK?), no over-claim.
Verdict APPROVE | APPROVE-WITH-CHANGES | REJECT with BLOCKER/MAJOR/MINOR/NIT + file:line evidence. Write to: docs/agent-ops/20261108-light-negative/reports/w2-review/REV-W2-IMPL-01.md. Read-only; do NOT edit/commit.

## 4. Ownership
READ-ONLY. Scoped checks (`git show`, greps) only; never full suite/build (ORCH gate owns those).

## 5. Deliverables
Report first (append as you work; ORCH-DIGEST first). Final message ≤8 lines: STATUS | agent | report path | verdict | findings counts | blockers.
