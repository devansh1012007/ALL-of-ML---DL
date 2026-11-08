# SUMMARY — 20261108-light-negative
Branch: frontend-ui-round2 · Base: `85acdda` · Head: <post-summary> · Waves: 2 (W0 investigation, W1 surface, W2 deep) · Agents: 12 (2 investigators + 2 coders + planner-reviewer + 2 code/test reviewers + deep designer + coder + 3 reviewers + final reviewer) · Dates: 2026-11-08

## 1. Outcome in brief
All three user-directed fixes closed end-to-end. T-102: negative-diff durations now hide the chip (was false "Took 0 s") + 2 tests. T-103: tech-debt:17 counts genealogy made explicit (115/115 at 2502fd9 → 117/117 at gate). T-101 (DEEP): light mode shipped via the spec — 14-token `[data-theme="light"]` inversion (dark :root byte-identical), pre-paint init, App-level toggles in both shells, NewJob tokenized, 27-pair contrast table (26 pass, 1 documented exception), ratio guards, production-build probe recorded. Final full gate GREEN: 154/154 tests + build. Final integration review APPROVE (push YES). Branch pushed; PR #2 description updated. Still manual: backend pytest, SR pass. PR #2 merge needs your explicit approval.

## 2. Plan coverage
| Plan item | Task | Status | Commits | Report |
|---|---|---|---|---|
| N1 negative-diff (P3 follow-up) | T-102 | DONE | `ca5d950` | reports/w1-impl/W1-IMPL-01-T-102.md |
| D1 tech-debt counts | T-103 | DONE | `9c73971` | reports/w1-impl/W1-IMPL-02-T-103.md |
| L1 light mode | T-101 spec → design → impl | DONE | `21f65c13` + `94963e6` | reports/w0-investigation/INV-light-mode.md, w2-impl/W2-DEEP-01-T-101.md, w2-impl/W2-IMPL-01-T-101.md, w2-impl/W2-IMPR-01-T-101.md |
| Spec docs/plans/2026-11-08-light-mode.md | T-101 spec | DONE (planner-reviewed, 6 MAJORs folded at `1b8d26a`) | — | reports/w1-review/PLAN-W1-PLAN-01.md |

## 3. Changes by domain
- RunDetails.jsx: `durationMs < 0 → null` (hide chip; Math.max kept as defense-in-depth) + invariant comment. runs.test.jsx +2 (negative, mixed).
- docs/tech-debt.md: line 17 genealogy (one hunk; 18-22 byte-identical); +1 light-mode probe line (additive, history preserved).
- Light mode: styles.css `[data-theme="light"]` 14 triples + color-scheme light; index.html head init script (try/catch, single resolution, dual write); components/theme.jsx (resolveTheme/applyTheme/toggleTheme/ThemeToggle, App-level state, both shells, "Switch to light/dark mode"); NewJob:678 text-orange-400 → text-warn; tests/theme.test.jsx (23) + static ratio/structure/dark-invariance/init-parity guards (37 total in file). tailwind.config.js untouched (no contract change). RunDetails untouched by light mode (C1 honored).

## 4. Deep-Dive Spotlight (T-101)
Problem: light mode deferred as spirit — token inversion was unproven hypothesis, no palette/toggle/init/probes. Decision: Option A (data-theme variable inversion) over B (dark: variants; ~119-site churn), C (system-only; no user control), D (stylesheet swap; FOUC). Deep designer computed 14 light triples from WCAG 2.x luminance against every pinned pair (26/27 pass; raised/canvas 1.18 non-text accepted as fill-vs-boundary with rule/canvas 3.36 contract). Key findings: accent-ink must be WHITE in light (empty-interval proof — spec amended); warn darkened 228 185 95 → 165 73 10 (1.84:1 → 5.64:1); no warn-strong needed. Rollout: additive; revert = remove 3 mechanisms → identical dark (inert storage keys). Design → impl → delta-review sequence; all reviewers approved. Reports: reports/w2-impl/W2-DEEP-01-T-101.md (binding table), PLAN-W1-PLAN-01.md, REV-W2-IMPL-01.md, TREV-W2-IMPL-01.md, REV-W2-DELTA.md.

## 5. Verification evidence
Baseline 85acdda: 117/117 + build green (ORCH). W1 gate: 119/119. W2 gate at HEAD: 154/154 (11 files) + build 1670. Probe: vite preview, 7 views + Admin, 390px + desktop, both themes, focus 2px, stored/system first-paint — recorded described-only in tech-debt (no screenshots persisted; accepted MINOR R-W2-001). Ratio guards execute WCAG math on shipped CSS (recomputed independently by TREV + FINAL). Reversal: init guard/NewJob/count demonstrated on mutations (IMPR); toggle/hostile traced (TREV). Backend pytest NOT-RUN (frontend-only diff). SR pass NOT-RUN (jsdom limits; carried).

## 6. Review outcomes
- W1: W1-REV-01 APPROVE (0 B/M/M, NITs rejected), W1-TREV-01 APPROVE (16/16, reversal genuine).
- W1 planner-review: APPROVE-WITH-CHANGES, 6 MAJORs folded into spec.
- W2: W2-REV-01 APPROVE-WITH-CHANGES (0 B/M; MINOR probe evidence accepted; NITs not-worth-it), W2-TREV-01 APPROVE-WITH-CHANGES (1 MAJOR init-parity + 3 MINOR + 2 NIT, all FIXED by IMPR), W2-DELTA-01 APPROVE (closure verified).
- FINAL-01 (combined 85acdda..HEAD): APPROVE, BLOCKER 0 MAJOR 0 MINOR 1, push YES.
- Improvement cycles: W1 0/2, W2 1/2.

## 7. Deferred / open items
- Backend pytest + SR/NVDA pass: manual/NOT-RUN, accepted, carried in tech-debt.
- Probe screenshots described-only (no artifacts persisted): accept or re-run with screenshots on request.
- min-α confusion distinguishability by hue (16,0,25) + digit/labels — probe should eyeball at 390px (recorded).
- timeAgo "just now" future clamp: correct relative-time semantics, out of scope (not a lie like the chip).

## 8. Out-of-plan discoveries
- AGENTS.md single-file-SPA description still stale vs views/ split (carried).
- timeAgo clamp noted above (not a defect).

## 9. Temporary mitigations
None.

## 10. Risks, rollout and operational notes
- Migrations/config/env: none (one localStorage key prime_theme; no API/schema change). Stored key absent = system default. Rollback: revert 21f65c13 elements or full revert; keys inert.
- PR #2 merge still separately approved only.

## 11. Assumptions made
- A-010: negative-diff remedy = hide chip (default chosen; warn-chip rejected as over-engineering; wall_seconds product decision).
- A-011: toggle+system theme default — pinned and implemented.

## 12. How to review this branch
`git diff 85acdda..HEAD -- . ':!docs/agent-ops'`: RunDetails.jsx, runs.test.jsx, tech-debt.md, styles.css, index.html, components/theme.jsx (new), App.jsx, AuthView.jsx, NewJob.jsx, tests/theme.test.jsx (new), tests/static.test.js. Test counts: 117 → 119 → 154 (all gates green).

## 13. Agent roster
| Agent | Role | Task | Report | Commits |
|---|---|---|---|---|
| W0-INV-01 | investigator | L1 | reports/w0-investigation/INV-light-mode.md | — |
| W0-INV-02 | investigator | N1+D1 | reports/w0-investigation/INV-negative-counts.md | — |
| W1-IMPL-01 | coder | T-102 | reports/w1-impl/W1-IMPL-01-T-102.md | ca5d950 |
| W1-IMPL-02 | coder | T-103 | reports/w1-impl/W1-IMPL-02-T-103.md | 9c73971 |
| W1-PLAN-01 | planner-reviewer | T-101 spec | reports/w1-review/PLAN-W1-PLAN-01.md | — |
| W1-REV-01 | code reviewer | W1 | reports/w1-review/REV-W1-IMPL-01.md | — |
| W1-TREV-01 | test reviewer | W1 | reports/w1-review/TREV-W1-IMPL-01.md | — |
| W2-DEEP-01 | deep designer | T-101 D1-D7 | reports/w2-impl/W2-DEEP-01-T-101.md | — |
| W2-IMPL-01 | coder | T-101-impl | reports/w2-impl/W2-IMPL-01-T-101.md | 21f65c13 |
| W2-IMPR-01 | coder | T-101-improve | reports/w2-impl/W2-IMPR-01-T-101.md | 94963e6 |
| W2-REV-01 | code reviewer | W2 | reports/w2-review/REV-W2-IMPL-01.md | — |
| W2-TREV-01 | test reviewer | W2 | reports/w2-review/TREV-W2-IMPL-01.md | — |
| W2-DELTA-01 | delta reviewer | W2-impr | reports/w2-review/REV-W2-DELTA.md | — |
| FINAL-01 | final reviewer | combined | reports/final/FINAL-01.md | — |

## 14. Residual risk and unverified claims
- Probe evidence described-only (no screenshots in repo) — accepted by REV as non-blocking.
- Backend pytest + SR pass: NOT-RUN (explicit).
- Contrast proof is computed (WCAG luminance on shipped triples), not rendered-pixel sampled — probe confirmed visibility, ratio guards keep it guarded.
