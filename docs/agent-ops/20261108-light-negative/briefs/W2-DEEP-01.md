# Brief — W2-DEEP-01 (deep-dive design) · wave 2 · run 20261108-light-negative

## 1. Role and mission
Mission: produce the T-101 light-mode DESIGN RECORD (no source edits yet): the 14-token light palette with computed contrast for every pinned pair, the alpha-wash inventory with composited ratios, the exact toggle label, and the final acceptance checklist that the implementation will be judged against. This is the evidence half of the "separate spec" — implementation (W2-IMPL-01) will execute it mechanically after ORCH approves your digest. Failure mode to avoid: inventing a palette by eyeball or mechanical invert without the math, or guessing at pairs the spec didn't pin.
Your role: deep-dive design agent (READ-ONLY on source during design; your only write is your report). Branch: frontend-ui-round2. Working dir: D:\dev work\coding\Projects\ALL-of-ML---DL.

## 2. Required reading (in this order)
1. docs/agent-ops/20261108-light-negative/templates/STANDING-ORDERS.md (binding)
2. docs/plans/2026-11-08-light-mode.md (THE spec — §§1-7; it pins thresholds, pair inventory, wash inventory, contracts; you pin VALUES)
3. docs/agent-ops/20261108-light-negative/reports/w0-investigation/INV-light-mode.md (§1 census + §4-5)
4. docs/agent-ops/20261108-light-negative/reports/w1-review/PLAN-W1-PLAN-01.md (§§3.3,3.5,5 P-04/P-05 — what the reviewer could NOT verify without your table)
5. docs/agent-ops/20261108-light-negative/templates/report-implementation.md plus report-deepdive-addendum.md (D1-D7 sections; your design record is D1-D6 + acceptance)
6. frontend/styles.css (all 323 lines — the 14 dark tokens + every component rule using them; esp. :51 ::selection, :85 field focus, :94-95 btn-primary hover, :298-301 admin badges, :258-262 newjob-tag)
7. frontend/components/metrics.jsx (ResultLine :161-179, Bar :231-240, ConfusionMatrix :270 — the alpha math)
8. COMMS.md

## 3. Task and acceptance criteria
Task T-101-design (D1-D7). You compute — you do NOT implement:
- **D1 (design decision record):** restate the decision (Option A `[data-theme="light"]` inversion + App-level state + header/AuthView toggles + head init script) and the invariants that must hold (dark :root triples byte-unchanged; toggle label action-describing; prime_theme never cleared on sign-out; attribute/meta/storage always agree).
- **D2 (failure-mode table, per spec §4.9 inventory):** one row per pinned pair (body tokens × surfaces, accent ink dual, ok/warn/bad, rule/raised vs canvas, focus outline) with the COMPUTED light value (RGB triple) + source of derivation (which constraint forced it, e.g. "warn darkened to meet 4.5:1 on canvas #FFFFFF"). Show the relative-luminance arithmetic explicitly (WCAG formula). The reviewer must be able to recompute every number from your table.
- **D3 (load):** pure client theme; one localStorage key; StrictMode/HMR idempotent; no render cost. Confirm `applyTheme()` is a pure DOM write.
- **D4 (security):** prime_theme hostile values (XSS/10KB/unicode) — allow-list only touches `dataset.theme`; prove the write paths never reach `innerHTML`. Plus `matchMedia` absent in jsdom, localStorage throws (private mode) — exact guards + fall-through.
- **D5 (rollout/rollback):** revert = remove light block + init script + toggle (dark identical). Ordering: tokens → init → toggle → tests. Flag the `--warn-strong` conditional (§4.8) — DECIDE: does light `--warn` alone reach 4.5:1 on canvas, or is warn-strong needed? (Your decision is binding on W2-IMPL-01.)
- **D6 (observability):** `document.documentElement.dataset.theme` + meta color-scheme inspectable; static test ratio guards optional-but-recommended with exact assertions your implementation must satisfy.
- **D7 (open risks/follow-ups):** anything the design could not pin (incl. the ring-canvas cosmetic note).
- Plus: **the toggle's exact accessible label** (fits "Runs"/"Models"/"New run"/"Admin", describes the action — e.g. "Switch to light mode"), and the **exact 14 light triples** in one table.
Acceptance (measurable): every pinned pair has a number; nothing is eyeballed; the impl agent could implement from your report with zero design freedom left.
Commands: read-only greps/`git show` only. Do NOT run vitest/build here (implementation stage owns execution). Do NOT edit source. Start the report NOW; append as you work.

## 4. Ownership
WRITE-SET: only docs/agent-ops/20261108-light-negative/reports/w2-impl/W2-DEEP-01-T-101.md. Everything else READ-ONLY (incl. the spec — the spec is ORCH-owned; if the spec needs amendment, propose it in your report as a NEED, don't edit it).

## 5. Parallel siblings this wave
None (design phase is solo). W2-IMPL-01 runs only after your design is approved.

## 6. Skip list and known traps
- Do NOT produce code. Design only. (One quick node/python contrast-math script is allowed as computation — it is not a source edit; describe it in D2.)
- Don't re-derive the whole census; INV §1 already proved it. Doubt-check ONLY the components your palette touches (badge washes, confusion alpha).
- known: jsdom `test.css: false` (no computed colors); helpers wipe localStorage per test (theme tests must afterEach-remove prime_theme).

## 7. Deliverables
Report: docs/agent-ops/20261108-light-negative/reports/w2-impl/W2-DEEP-01-T-101.md (ORCH-DIGEST first, then D1-D7 + the two pinned tables). No source commit (you're design-only; ORCH commits the report at wave close).
Final message ≤8 lines: STATUS | W2-DEEP-01 | T-101-design | report path | palette complete? Y/N | warn-strong needed? Y/N | blockers.
