<!-- ORCH-DIGEST:START -->
agent: W1-PLAN-01 | domain: planner-review-V103-V104 | status: DONE
verdict: APPROVE-WITH-CHANGES | findings: 0 BLOCKER / 5 MAJOR / 5 MINOR
items: SUPPORTED 8 areas (V-101 baseline, err.status contract, A-over-B/C, wrap pair, doc-only closures) / UNSUPPORTED 4 (403->both, unknown->both default, "each branch fails pre-fix", static-only V-104 acceptance) / MISSING 5 (errorStatus clear/gate, 404/405/422 rows, register-path 409, dangling-invariant test, Playwright NOT-RUN decision rule)
top_risks: invite-policy 403 + unknown statuses mislabel fields via else-both; stale errorStatus can leave dangling aria-describedby; V-104 passable by regex without layout proof
cross_domain_conflicts: none | confidence: high read-only, code-verified
<!-- ORCH-DIGEST:END -->

# Plan review — W1-PLAN-01 — V-103/V-104 verify/fix plan

Verdict: APPROVE-WITH-CHANGES. Approach A + wrap pair sound; gaps are targeted plan-text fixes. (Full verbatim output captured in subagent result; key findings F-01..F-10 folded below.)

## Resolutions folded into plan (2026-11-09)
- F-01 MAJOR inverse default → whitelist: 409→username-only; 400→both; all else→describedby-only. User-confirmed 403→describedby-only.
- F-02 dangling invariant → initial null, clear both, attrs gated on error, invariant test.
- F-03 wrong-endpoint 409 → register-mode test.
- F-04 V-104 static-only risk → attempt Playwright route-mock hostile; if NOT-RUN, static-only + follow-up owner (not rendered-verified).
- F-05 acceptance contradiction → discriminating vs guard-rail wording; edit :201-232 in place preserving guard.
- F-06 401 defensive-describedby-only; F-08 ariaFor inside AuthView test-through-DOM + omission semantics; F-09 400-conflation known; F-10 helpers untouched.
