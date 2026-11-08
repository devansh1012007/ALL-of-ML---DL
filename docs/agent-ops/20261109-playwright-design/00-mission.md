# Mission — 20261109-playwright-design (orchestrator-owned)

## Goal (restated from user)
Use Playwright MCP to audit the real rendered UI and fine-tune the design — evidence-driven polish (layout, spacing, contrast, responsive, focus, overflow, alignment), not ad-hoc aesthetic churn. Every change must cite Playwright evidence (screenshots/snapshots/evaluate) and map to file:line.

## Constraints
- Branch: `frontend-ui-round2` (PR #2 continuity, stays open, no merge without explicit approval).
- HEAD at start: `7ce8bed`. Baseline: 154/154 green (intermittent runs.test.jsx Progress-poll flake, pre-existing) + build 1670 green. Tree clean.
- Preserve token architecture (14-token dark/light), DO NOT revert light mode, Do NOT introduce new deps without justification.
- No full-suite parallelism; gates owned by ORCH.

## Acceptance criteria
1. Playwright audit artifact: screenshots + snapshots + evaluate probes for all major surfaces (Auth, Runs, RunDetails, NewJob, Predict, Models, Admin) at desktop (1280) + mobile (390), dark + light.
2. Concrete defect list with severity + file:line + Playwright evidence; fixes scoped to defects.
3. After fixes: full gate (npm test + build) green, independent code review APPROVE, final integration APPROVE, push (PR #2), merge still needs approval.

## Assumptions
- A-100: "Improve/fine-tune" means fixing real rendered-UI defects + polish gaps Playwright can measure (overflow, contrast, tap targets, focus, spacing inconsistencies), not a redesign.
- A-101: Playwright MCP available via `execute` → `tools.playwright.*` (search-verified).
- A-102: No backend changes expected (frontend-only fine-tune).

## Sample structure (preflight-created)
```
docs/agent-ops/20261109-playwright-design/
├── 00-mission.md, 01-work-ledger.md, COMMS.md, SUMMARY.md (last)
├── templates/ (copied from 20261108-light-negative)
├── briefs/, ownership/, gates/, screenshots/before/
└── reports/w0-investigation|w1-impl|w1-review|w2-impl|final/
```
