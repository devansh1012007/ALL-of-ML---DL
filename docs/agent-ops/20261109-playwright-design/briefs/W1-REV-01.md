# Brief — W1-REV-01 (code reviewer) · wave 1 · run 20261109-playwright-design

## 1. Role and mission
Independent audit of W1 code commit f53e4ba (T-301..T-304). Blind pass first, then claims audit vs W1-IMPL-01 report. You wrote none of it.

## 2. Required reading
1. docs/agent-ops/20261109-playwright-design/templates/STANDING-ORDERS.md (binding)
2. docs/agent-ops/20261109-playwright-design/templates/review-code.md (ORCH-DIGEST first)
3. Blind: git show f53e4ba, frontend/index.html, frontend/views/NewJob.jsx:660, frontend/AdminScreen.jsx:670+:628, frontend/styles.css:310, frontend/views/AuthView.jsx
4. Then: docs/plans/2026-11-09-playwright-fine-tune.md (Decisions), W1-IMPL-01-T301-T304.md

## 3. Task and acceptance criteria
Check: favicon data-URI well-formed + position (after color-scheme meta, before init script, init unmoved); type strips exact (NewJob keeps font-semibold text-strong mb-4; Admin bare h1 no mb-1 invention); audit title type-correct (detail JSON, guard preserved); invite flex-wrap placement; Auth aria wiring (error-truthy only, id unique, both fields vs per-field appropriateness — scrutinize coder §15); forbidden files untouched (git diff f53e4ba^..f53e4ba --name-only = 7 files); no token/floor/config edits; band-aid hunt.
Verdict APPROVE/APPROVE-WITH-CHANGES/REJECT with severity + file:line. Write to docs/agent-ops/20261109-playwright-design/reports/w1-review/REV-W1-IMPL-01.md. Read-only; no commit.

## 4. Deliverables
Final ≤8 lines: STATUS | agent | report path | verdict | counts | blockers.
