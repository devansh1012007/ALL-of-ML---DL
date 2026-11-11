# Brief — W1-PLAN-01 (planner-reviewer) · run 20261109-playwright-design

## 1. Role and mission
You CRITIQUE the fine-tune plan (T-203) before implementation. Break it against the actual code + W0 reports. Read-only; never edit the plan.

## 2. Required reading
1. docs/agent-ops/20261109-playwright-design/templates/STANDING-ORDERS.md (binding)
2. docs/plans/2026-11-09-playwright-fine-tune.md (THE plan under review)
3. docs/agent-ops/20261109-playwright-design/reports/w0-investigation/INV-playwright-audit.md
4. docs/agent-ops/20261109-playwright-design/reports/w0-investigation/INV-code-design.md
5. Spot-verify code: frontend/index.html, frontend/views/NewJob.jsx:660 + :431, frontend/AdminScreen.jsx:670 + :628, frontend/styles.css:310, frontend/tests/static.test.js (floor pins)

## 3. Task and acceptance criteria
Classify each plan claim SUPPORTED/UNSUPPORTED/MISSING. Attack: (1) Is deferring data views honest or does it leave the user's ask half-done? (2) Is the 24px accept-vs-raise framing correct (WCAG AA 24 exactly, test-pinned)? (3) Are the 6 fixes truly independent/zero-risk? Any hidden coupling (e.g. file-button class change affecting focus, Admin h1 test pins, invite wrap layout)? (4) Missing candidates or over-scoped items? (5) Acceptance measurable?
Verdict APPROVE / APPROVE-WITH-CHANGES / REJECT with BLOCKER/MAJOR/MINOR + evidence. Write to docs/agent-ops/20261109-playwright-design/reports/w1-review/PLAN-W1-PLAN-01.md (ORCH-DIGEST first). Read-only; do NOT commit.

## 4. Deliverables
Final ≤8 lines: STATUS | agent | report path | verdict | counts | blockers.
