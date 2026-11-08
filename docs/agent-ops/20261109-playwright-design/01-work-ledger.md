# Work ledger — 20261109-playwright-design (orchestrator-owned)

## Tasks
| Task | Domain | Class | Root cause (1 line) | Write-set | Depends | Wave | Agent | Status | Code commits | Report |
|---|---|---|---|---|---|---|---|---|---|---|
| T-201 | Playwright audit (all surfaces) | INVESTIGATION | Rendered-UI defects unknown without real browser | — (read-only + screenshots) | — | W0 | W0-INV-01 | DONE (PARTIAL: auth rendered clean, data NOT-RENDERABLE, backend down) | — | reports/w0-investigation/INV-playwright-audit.md |
| T-202 | Code-level design audit | INVESTIGATION | Hardcoded/outlier code paths vs rendered | — | — | W0 | W0-INV-02 | DONE (21 items, 12 fix candidates) | — | reports/w0-investigation/INV-code-design.md |
| T-203 | Fine-tune fixes | TBD at plan | From audit defects | TBD at plan | T-201+T-202 | W1+ | TBD | PENDING | — | — |

## Waves
### Wave 0 (investigation, read-only) — dispatching
- W0-INV-01: Playwright rendered audit (screenshots/snapshots/evaluate, desktop+mobile, dark+light).
- W0-INV-02: Code audit (tokens, hardcoded, a11y, component patterns) cross-check.
### Wave 1+ (plan-gated)
- Plan from audits → planner-reviewer → coder(s) → independent review → gate → final review.

## Out-of-plan / deferred
- Backend pytest + SR/NVDA: still manual/NOT-RUN (carried).
