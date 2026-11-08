# Mission — 20261109-playwright-verify (orchestrator-owned)

## Goal (restated from user)
Playwright is provided again — close the four gaps an earlier report left NOT-RUN/DO-LATER/deferred:
1. **W1 rendered re-verify:** prove the `f53e4ba` fine-tune batch (favicon, type, audit title, invite wrap, Auth aria) actually renders clean in a real browser (Auth surface at 1280/390 × dark/light, console, aria association, contrast, overflow).
2. **R-W1-001 status-mapped aria:** stop marking both Auth fields invalid for every error — map by status (409 username-only; 429/network describedby-without-invalid; credential errors both).
3. **R-W1-002 invite overflow-wrap:** break unbreakable long invite codes at 390px.
4. **Deferred hypotheses:** ResultLine label clamp, header gap-x-8 crowding, Compare title-only hint — verify with Playwright if renderable, fix only with rendered evidence; if backend still blocks, document honestly.

## Constraints
- Branch `frontend-ui-round2` (PR #2 open, no merge without approval). HEAD `3f5b220`. Baseline 162/162 + build green (this session).
- Token architecture + 24px floors unchanged. Favicon `%20` NOT-WORTH-IT — do NOT churn.

## Acceptance
- Playwright after-screenshots + console evidence for Auth; status-mapped aria semantic correctness + tests; long-code 390 no-overflow proof; honest deferral record for anything still NOT-RENDERABLE. Full gate green; independent reviews APPROVE; push only.

## Assumptions
- A-200: Playwright MCP restored via `execute` → `tools.playwright.*` (search-verified this session).
- A-201: Backend still unavailable (no `.venv`/`backend/.env`) — data views still likely NOT-RENDERABLE; verify, don't assume.
