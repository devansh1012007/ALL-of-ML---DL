# Work ledger — 20261109-playwright-verify (orchestrator-owned)

## Tasks
| Task | Domain | Class | Root cause | Write-set | Wave | Agent | Status | Code | Report |
|---|---|---|---|---|---|---|---|---|---|
| V-101 | W1 rendered re-verify (Auth matrix) | INVESTIGATION | `f53e4ba` never proved in a real browser | — (read-only + screenshots) | W0 | W0-INV-01 | PENDING | — | reports/w0-investigation/INV-rendered-verify.md |
| V-102 | Aria + overflow code audit | INVESTIGATION | Status mapping shape + wrap point unknown from report alone | — | W0 | W0-INV-02 | PENDING | — | reports/w0-investigation/INV-aria-wrap.md |
| V-103 | Status-mapped aria | TBD | Both-fields broad (409/429/network) | AuthView.jsx + auth.test | W1 | TBD | PENDING | — | — |
| V-104 | Invite overflow-wrap | TBD | Unbreakable code overflows 390 | styles.css (+AdminScreen?) + static pin | W1 | TBD | PENDING | — | — |

## Waves
### Wave 0 — dispatching (W0-INV-01 rendered, W0-INV-02 code)
### Wave 1+ — plan-gated (V-103/V-104, then gate + final review)
## Deferred / carried
- ResultLine/header/Compare: verify-or-document (V-101 probe; fix only with evidence).
- Favicon `%20`: NOT-WORTH-IT, no churn.
- Backend pytest + SR: still manual/NOT-RUN.
