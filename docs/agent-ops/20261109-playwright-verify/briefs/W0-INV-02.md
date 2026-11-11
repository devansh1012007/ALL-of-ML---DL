# Brief — W0-INV-02 (investigator) · wave 0 · run 20261109-playwright-verify

## 1. Role and mission
READ-ONLY investigator. Mission: audit the code surface for the two DO-LATER fixes (status-mapped aria R-W1-001, invite overflow-wrap R-W1-002) + confirm the favicon NOT-WORTH-IT close. No source edits. Write ONLY docs/agent-ops/20261109-playwright-verify/reports/w0-investigation/INV-aria-wrap.md.
Branch frontend-ui-round2, Dir D:\dev work\coding\Projects\ALL-of-ML---DL.

## 2. Required reading (in order)
1. docs/agent-ops/20261109-playwright-verify/templates/STANDING-ORDERS.md (binding)
2. docs/agent-ops/20261109-playwright-verify/00-mission.md, 01-work-ledger.md, COMMS.md
3. docs/agent-ops/20261109-playwright-verify/templates/report-investigation.md (ORCH-DIGEST first)
4. frontend/views/AuthView.jsx (handleSubmit, error state, status availability — can we map by status without parsing strings?), frontend/tests/auth.test.jsx (current both-fields tests + harness), frontend/App.jsx (apiFetch/login error shape if used)
5. frontend/styles.css:310 (.admin-invite-code) + frontend/AdminScreen.jsx:554-556 (code text element), frontend/tests/static.test.js (wrap pin), docs/agent-ops/20261109-playwright-verify/reports/w1-review/REV-W1-IMPL-01.md R-W1-001/R-W1-002 + docs/plans/2026-11-09-playwright-fine-tune.md

## 3. Task and acceptance criteria
Task V-102.
- **Aria mapping:** trace how errors reach AuthView state (HTTP status vs message string). Is `status` (409/429/401) available without parsing message text? What does the reviewer recommendation (409→username-only, 429/network→describedby-no-invalid, credentials→both) require in code? [RAN grep status|setError|error] + path:line. Define the exact state shape (e.g. `error` + `invalidField`?) and test additions per branch. Flag any branch where mapping is impossible without API contract change → ESCALATE, don't guess.
- **Overflow-wrap:** which element to wrap (code text vs row)? `overflow-wrap:anywhere` vs `word-break:break-all` — which breaks base32-ish codes without ugly splits? Check the invite-code generation shape (length/charset) from backend code if visible, else mark [UNKNOWN] + safe default. Define static pin + Playwright hostile check (32+ char code at 390).
- **Favicon:** confirm inline data-URI valid as-is (spaces OK); close as NOT-WORTH-IT, no churn.
Deliverable: exact fix map (files, hunks, tests, acceptance per branch) + SURFACE/DEEP classification. Long-run test per fix.

## 4. Ownership
READ-ONLY except report. No commits. Scoped greps only; never full suite.

## 5. Deliverables
Report first (append; ORCH-DIGEST first). Final ≤8 lines: STATUS | agent | report path | proposals count | top risk | blockers.
