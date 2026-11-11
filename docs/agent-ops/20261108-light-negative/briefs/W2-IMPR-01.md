# Brief — W2-IMPR-01 (coder) · wave 2 improvement · run 20261108-light-negative

## 1. Role and mission
Mission: close the test-side findings from W2 reviews (test additions only; NO production code change). The reviewers' verdict is APPROVE-WITH-CHANGES with 0 BLOCKERs but 1 MAJOR init-parity coverage gap + 3 MINORs + 2 NITs — your job is to add the pinned tests so the central invariants are actually regression-guarded. Failure mode to avoid: touching any production file, "improving" test style, or re-opening settled palette/design questions.
Your role: coder (test-only improvement). Branch: frontend-ui-round2. Working dir: D:\dev work\coding\Projects\ALL-of-ML---DL.

## 2. Required reading
1. docs/agent-ops/20261108-light-negative/templates/STANDING-ORDERS.md (binding)
2. docs/agent-ops/20261108-light-negative/briefs/W2-IMPL-01.md (§3 test requirements — scope ceiling)
3. The findings: docs/agent-ops/20261108-light-negative/reports/w2-review/TREV-W2-IMPL-01.md (§§5-6: R-W2-01..06)
4. docs/agent-ops/20261108-light-negative/templates/report-improvement.md (your report template — ORCH-DIGEST first)
5. frontend/tests/theme.test.jsx, frontend/tests/static.test.js, frontend/index.html (init script under pin), frontend/views/NewJob.jsx:678 area

## 3. Task and acceptance criteria
Address finding-by-finding (each ends FIXED in your report):
- R-W2-01 [MAJOR] (static.test.js): ADD a guard that reads `frontend/index.html` and asserts: init script appears in `<head>` BEFORE the module entry script; script text references `prime_theme`; contains an allow-list check (`=== "light"`/`=== "dark"`-style guard); contains a `typeof window.matchMedia` guard; sets `dataset.theme` AND meta content from ONE resolved variable; has a try/catch. AND assert `frontend/views/NewJob.jsx` contains `text-warn` and does NOT contain `text-orange-400`.
- R-W2-02 [MINOR] (theme.test.jsx): ADD matchMedia-THROWS test: `window.matchMedia = () => { throw new Error() }`, absent storage → dark + not.toThrow.
- R-W2-03 [MINOR] (theme.test.jsx hostile matrix): ADD `['padded light',' light ']` and `['string null','null']` entries with the same fall-through asserts.
- R-W2-04 [MINOR] (theme.test.jsx): ADD ONE raw-applyTheme test: `applyTheme('"><script>…')` (the hostile literal) → dataset `dark`, no new script element.
- R-W2-05 [NIT] (static.test.js): ADD exactly-14 `--*:` count assertion per block (:root and light).
- R-W2-06 [NIT] (static.test.js): ADD one-line comment at the ratio section documenting raised/canvas exclusion (design D2 §2.4a exception).
Acceptance:
- All 6 findings FIXED (additive-only tests/comments). No production file changed (`git diff <wave-base> -- <prod files>` empty).
- Scoped: `cd frontend; npx vitest run tests/theme.test.jsx tests/static.test.js` green (count grows accordingly); then `cd frontend; npm test` full green ONCE at the end (single-writer; no parallelism).
- Regression proof: each new guard must be shown to FAIL on the unpinned state where cheap (e.g. static init guard vs missing `prime_theme` string — reason or demonstrate; record evidence; do not actually break production files).
- Do NOT run build here (ORCH gate runs it) — actually you MAY run `npm run build` once for confidence; record it either way.

## 4. Ownership
WRITE-SET: exactly frontend/tests/theme.test.jsx, frontend/tests/static.test.js, and your report docs/agent-ops/20261108-light-negative/reports/w2-impl/W2-IMPR-01-T-101.md. (Ownership table W2.tsv lists these files under W2-IMPL-01 — you are the wave's improvement agent and own them this wave per ORCH; do not modify W2.tsv.)
READ-ONLY: everything else. FORBIDDEN: every production file. Need something outside? NEED + DEFERRED-DEPENDENCY.

## 5. Parallel siblings
None running in parallel (improvement is the wave's last change — reviewers are read-only).

## 6. Skip list and known traps
- Do NOT touch: palette values, theme logic, guards already green, thresholds, dark literals, R-W2-001 probe (ORCH disposition: described-only accepted, no re-run).
- jsdom has no matchMedia: stub per-test; afterEach already cleans. New tests must follow the existing beforeEach/afterEach hygiene (localStorage.clear, dataset.theme delete, unstubAllGlobals).
- Known flake: runs.test.jsx Progress-poll (pre-existing).

## 7. Environment and tests
Scoped vitest (the two files) then ONE full `npm test` at end (single-writer). Kill processes. No containers/ports.

## 8. Deliverables
Report: docs/agent-ops/20261108-light-negative/reports/w2-impl/W2-IMPR-01-T-101.md (start NOW; ORCH-DIGEST first). Commits (verify branch first, explicit paths only): 1) test-fix commit (2 test files) with trailers Task/Agent/Wave/Report; 2) separate docs-only report commit listing the code SHA.
Final message ≤8 lines: STATUS | W2-IMPR-01 | T-101-improve | report path | commit SHAs | blockers.
