# SUMMARY — 20261109-playwright-verify
Branch: frontend-ui-round2 · Base: `3f5b220` · Head: <post-summary> · Waves: W0 audit + W1 fixes · Agents: 7 · Dates: 2026-11-09

## 1. Outcome in brief
Closed all four gaps. **V-101 rendered re-verify (real Playwright):** Auth CLEAN 1280/390 × dark/light — console 0 errors, overflow 0, contrast ≥6.7, theme+focus clean; both-fields aria recorded as V-103 input. Deferred hypotheses NOT-RENDERABLE (token gate, backend down) — documented, with ResultLine likely misclassified (flex-wrap exists) and Compare title-only has no source basis. **V-103 (`12f46a0`):** status-mapped aria whitelist — 409 username-only via register path, 400 both (guard-rail), all else (403 user-confirmed, 429, network, ≥500, 401, 404/405/422) describedby-only; no string parsing, no dangling describedby. **V-104 (`b86d3a2`):** invite overflow-wrap (`anywhere` + `min-w-0` paired, precedent-consistent) + static pin. Gate 170/170. Final APPROVE. Pushed; PR merge still needs approval.

## 2. Plan coverage
| Item | Status | Commits | Report |
|---|---|---|---|
| V-101 rendered re-verify | DONE | — (evidence) | reports/w0-investigation/INV-rendered-verify.md |
| V-102 aria/wrap audit | DONE | — | reports/w0-investigation/INV-aria-wrap.md |
| V-103 status-mapped aria | DONE | `12f46a0` | reports/w1-impl/W1-IMPL-01-V103.md |
| V-104 invite wrap | DONE (static-only, hostile NOT-RUN) | `b86d3a2` | reports/w1-impl/W1-IMPL-02-V104.md |
| ResultLine/header/Compare | DEFERRED document-only | — | backend-up pass (T-204) |
| Favicon %20 | CLOSED NOT-WORTH-IT | — | rendered console-clean proof |

## 3. Changes by domain
- `frontend/views/AuthView.jsx` + `frontend/tests/auth.test.jsx`: `errorStatus` scalar + first-branch `ariaFor(status)` — whitelist mapping, clear+gate, register-path 409, invariant test (every describedby resolves), old network test inverted in place.
- `frontend/styles.css` + `frontend/AdminScreen.jsx` + `frontend/tests/static.test.js`: `.admin-invite-code-text{min-width:0;overflow-wrap:anywhere}` + wrapper `min-w-0` + pin.

## 4. Verification evidence
Baseline 3f5b220 162/162 + build green (session). W1 gate at HEAD: 170/170 (12.79s) + build green. Scoped 59/59 (TREV). Reversal: discriminating branches fail pre-fix (409-neg, 429, network, 500/502); 400/401 guard-rails pass both ways. Playwright: V-101 7 contact sheets live; V-103 spot + V-104 hostile NOT-RUN (no server/seed; MCP live but no route-mock path; static-only closure per F-04 with named follow-up). Backend pytest NOT-RUN.

## 5. Review outcomes
W1-PLAN-01 APPROVE-WITH-CHANGES (5 MAJOR → whitelist/clear+gate/register-409/F-04 closure/acceptance wording; 403 user-confirmed). W1-REV-01 APPROVE (0 B/M/M, 2 MINOR wording). W1-TREV-01 APPROVE (59/59). FINAL-01 APPROVE, push YES.

## 6. Deferred / open items
- V-104 rendered hostile (64/256-char @390) + V-103 rendered spot: backend-up pass follow-up (owner: future run with backend env).
- ResultLine/header/Compare: still code-only until T-204.
- 400-conflation (short-password vs reserved-name both mark both) accepted without string parsing.

## 7. Agent roster
W0-INV-01 investigator (INV-rendered-verify) · W0-INV-02 investigator (INV-aria-wrap) · W1-PLAN-01 planner-reviewer (PLAN-W1-PLAN-01) · W1-IMPL-01 coder V-103 (12f46a0) · W1-IMPL-02 coder V-104 (b86d3a2) · W1-REV-01 code-reviewer (REV APPROVE) · W1-TREV-01 test-reviewer (TREV APPROVE) · FINAL-01 final reviewer (FINAL APPROVE).
