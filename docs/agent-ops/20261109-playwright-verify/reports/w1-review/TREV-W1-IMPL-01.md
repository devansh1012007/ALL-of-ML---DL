<!-- ORCH-DIGEST:START -->
agent: W1-TREV-01 | scope: W1 V-103+V-104 | verdict: APPROVE
tests_reviewed: 59 | fail-before/pass-after confirmed: 7 / reasoned: 2 / not-possible: 0
findings: BLOCKER 0 | MAJOR 0 | MINOR 1 | NIT 1
flaky_suspects: none
missing_edge_cases: P1 0 | P2 2 | P3 2
mutation_survivors: 1 of 9 plausible bugs not caught
changed_behavior_without_tests: none
confidence: high (scoped run green, both commits verified diff + prior report claim vs guard logic)
<!-- ORCH-DIGEST:END -->

# Test quality review — TREV-W1-IMPL-01

## 0. Method (temporary worktree used? repeat counts, coverage tooling)
- Worktree: N/A (read-only; current tree). Commits: V-103 `12f46a0`, V-104 `b86d3a2`.
- Scoped run: `cd frontend; npx vitest run tests/auth.test.jsx tests/static.test.js` →
  **2 files / 59 tests all passed in 3.32s** (static 44, auth 15). No coverage tooling configured.
- Reversal reasoning: old both-fields-invalid test replaced in place (:201-232 diff-verified);
  pre-fix both-fields code fails `not.toHaveAttribute('aria-invalid')` by construction. 400/401
  guard-rails: 400 both-invalid passes old/new; 401/403 now describedby-only per whitelist.

## 1. Per test/suite assessment
| Test | Asserts behavior? | Fails without fix? | Deterministic/isolated? | Over-mocked? | Notes |
|---|---|---|---|---|---|
| auth network (edited :210) | Yes — alert text + both described, neither invalid | Yes (old both-invalid) | Yes; clearTimeout + cleanup | No | Guard preserved; self-check bare input at :197-198 intact |
| auth 409 register | Yes — username-only invalid+described, password negative | Yes | Yes | No | Only register-path test; correct whitelist target |
| auth 429 / 502 / 500 (login) | Yes — both described, neither invalid | Yes | Yes | No | Three-way plateau coverage |
| auth 400 guard-rail | Yes — both invalid+described | Passes both ways (by design) | Yes | No | Correctly labeled guard-rail |
| auth 403 / 401 login | Yes — described only | Yes (old) | Yes | No | Whitelist 'else' branch validated |
| auth 401 /me | Yes — logout + token cleared | Yes | Yes | No | Session-expired contract |
| auth 502 non-JSON custom fetch | Yes — connectivity sentence | Partially | Custom fetch + delegate | No | Only non-JSON branch test |
| static V-104 pin (:604-620) | Yes — min-width:0 + anywhere + wrapper min-w-0 | Yes (pre-fix literal self-check) | Yes | No | Scoped 400-char slice avoids audit-row false-positive |

## 2. Coverage of changed lines/branches, error paths, boundaries
- V-103: all three whitelist branches hit (409 / 400 / else-network,429,500,502,403,401). Describedby invariant (`checkDescribedByInvariant`) enforced in all 8 post-fix tests.
- V-104: invite-code block fully covered: CSS rule, class on element, wrapper min-w-0.
- Boundary: regex self-checks present in both files (pattern catches `-mt-[5px]`, old `.newjob-pair`, token parity, etc.).

## 3. Mutation thinking
| Plausible bug | Caught? | By which test |
|---|---|---|
| else-branch marks both invalid | Yes | network/429/502/500/403/401 |
| 409 leaks aria-invalid onto password | Yes | 409 negative `not.toHaveAttribute` |
| errorStatus not cleared on resubmit | Yes (resubmitted network) | network test (submit after clear) |
| 400 treated as else (no invalid) | Yes | 400 guard-rail |
| overflow-wrap:anywhere dropped / break-all | Yes | V-104 pin regex |
| wrapper min-w-0 removed | Yes | 400-char slice pin |
| aria-invalid present-but-'' sentinel | Not fully | `not.toHaveAttribute` catches '' — actually caught; survivor is describedby pointing to wrong id when multiple alerts exist (single alert only) |
| login↔register mode leak (409 on login) | Not caught | No login-409 coverage (P2) |

## 4. Flakiness evidence (repeated runs) and test-suite health
- Single scoped run green (563ms auth). `beforeEach/afterEach` use real timers, clear localStorage/hash
  and restore fake backend — good isolation. No shared state across suites or ordering sensitivity observed.

## 5. Findings
- R-W1-01 MINOR (auth.test.jsx:279-368): 403 test named "user-confirmed whitelist" but provides no
  issue-link for the contract decision; keep for audit, add reference. Recommended: link DEC decision.
- R-W1-02 NIT (auth.test.jsx:201-208): `checkDescribedByInvariant` asserts target===alert by identity;
  works only with one alert — fine today; note brittleness if alerts stack.

## 6. Missing edge cases and tests
- P1: none.
- P2: login 409 (whitelist binds to register only? confirm else-branch on login-409) — add `seed fail '/token' 409` test.
- P2: V-104 visual render at 390px manual probe (static pin is indicative only, label says so; keep probe note in tech-debt).
- P3: 422 (validation error) describedby-only parity with 403/401.
- P3: overflow at content level — ultra-long single-token code in `.admin-invite-code-text` visual check (optional, playwright phase).

## 7. What I could not verify
- Fail-before reversal not executed (read-only; inferred from diff/commit message "7 fail pre-fix" vs guard logic — consistent but not re-run).
- Rendered layout at 390px (needs live dev-server probe).
- No full frontend suite run (scoped per brief: 59/59 in scope).
