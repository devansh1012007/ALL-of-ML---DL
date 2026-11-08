# Work ledger — 20261108-light-negative (orchestrator-owned; source of truth for resume)

## Plan coverage
| Plan item | Summary | Disposition |
|---|---|---|
| L1 Light mode | dark-only tokens → invert + toggle | PENDING investigation + spec/plan |
| N1 Negative-diff | hide chip on negative diff | PENDING investigation |
| D1 tech-debt counts | reword tech-debt:17 genealogy | PENDING investigation (trivial) |

## Tasks
| Task | Plan items | Domain | Class | Root cause (1 line) | Write-set | Contract-set | Env-set | Depends on | Conflicts (C#) | Wave | Agent | Status | Code commits | Report |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T-101 | L1 | frontend theme | DEEP | token inversion unproven; palette/toggle/init/probes missing | styles.css, index.html, App.jsx, AuthView.jsx, NewJob:678, theme helpers, tests | data-theme selector; prime_theme; meta color-scheme | jsdom + Chromium probe | spec+planner-review | C1 vs T-102 (lines only) | W2 | TBD | PENDING | — | — |
| T-102 | N1 | RunDetails duration | SURFACE | Math.max clamps negative→0 | RunDetails.jsx, runs.test.jsx | none | jsdom | none | C1 vs T-101 if both touch RunDetails | W1 | TBD | PENDING | — | — |
| T-103 | D1 | docs | SURFACE | dual counts on one line | docs/tech-debt.md | none | none | none | none | W1 | TBD | PENDING | — | — |

## Waves
### Wave 0 (investigation, read-only) — DONE
- W0-INV-01 (INV-light-mode): EXISTS/DEEP, token Census 93 var(--)/94 rgb all token-indirected, 0 hex/dark:, 1 outlier NewJob:678, Option A [data-theme=light] recommended. Confidence high.
- W0-INV-02 (INV-negative-counts): N1 EXISTS (hide-chip 1-line), D1 EXISTS (exact reword proposed). C1 ordered N1 first.
### Wave 1 (parallel, disjoint write-sets) — CLOSED (gate green 119/119)
- T-102 DONE (`ca5d950`+`939fbe4`): hide chip on negative diff + 2 tests. T-103 DONE (`9c73971`+`399c065`): tech-debt:17 genealogy.
- W1-REV-01 APPROVE: 0 B/M/M, NIT-01 mixed-test asymmetry (REJECT — symmetric NaN, no churn), NIT-02 timeAgo clamp (REJECT — correct relative-time semantics).
- W1-TREV-01 APPROVE: 16/16 scoped, diff = 2 files, P3 tests byte-unchanged, reversal genuine.
- Planner-review W1-PLAN-01: APPROVE-WITH-CHANGES, 6 MAJORs folded into spec (P-01..P-10 resolutions committed at `1b8d26a`).
- Gate: gates/gate-w1-1.md GREEN (119/119 + build). Review/improve cycles 0/2.
- Ownership file: ownership/W1.tsv (disjoint, verified).
### Wave 2 (sequential deep)
- T-101: spec docs/plans/2026-11-08-light-mode.md → planner-reviewer → DEEP design → approve → DEEP impl (styles, index.html, App/AuthView toggle, NewJob outlier, theme helpers, tests) → probe (manual Chromium) → tech-debt probe record.
- Pre-mortem (W2): light palette fails contrast without probe; FOUC if init not pre-paint; prime_theme leaks across jsdom tests. Mitigations in spec.

## Deep dives
| Task | Agent | Design approved by | Report | Reviewers |

## Deferred / open items
- Backend pytest + Chromium/SR probes: still manual/NOT-RUN (carried).
- Light-mode design fork (token swap vs full component audit) is resolved at spec stage.

## Out-of-plan discoveries
## Temporary mitigations (user-approved)
## Assumptions → see 00-mission.md
