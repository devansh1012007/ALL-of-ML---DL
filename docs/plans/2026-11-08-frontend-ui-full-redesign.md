# Plan: Frontend UI/UX Full Redesign (Round 2 — visual system + shell + views)

Status: In progress — planner-reviewer APPROVE WITH CHANGES folded in 2026-11-08 (see §6); implementing R1→R6
Baseline: branch `frontend-ui-round1` @ `0c1b7ed` (clean tree; `npm test` 39/39, `npm run build` green — verified by orchestrator). PR #1 (round-1) MERGED 2026-11-08T04:21:02Z; `origin/main` @ `7e40830` = merge of `0c1b7ed`. Round-2 work branches as `frontend-ui-round2` from `origin/main` @ `7e40830`.
Prior round: `docs/plans/2026-11-08-frontend-ui-round1-revised.md` (P1 harness + P2 truthful states + P3 a11y/mobile, merged via PR #1)
Decisions carried forward: D3 keep "PrimeTrade AutoML" name, D4 keep token in `localStorage`, D5 touch targets 24px AA minimum (Playwright deferred), D6 admin shared-classes before `App.jsx` split. No backend API changes.

## 1. Problem, goal, non-goals, acceptance

Problem: Round-1 fixed truth/a11y but the UI still reads as an unmined prototype: dark-only tokens with inconsistent spacing, negative-margin headers (`-mt-5`) compensating for shell spacing, bespoke Admin controls diverging from shared `.btn/.field/.th/.td`, duplicated formatters, a top-nav shell with cramped admin/compare tables, and a 2.4k-line `App.jsx` that makes every visual change risky.

Goal: A full, coherent redesign of the frontend SPA — design tokens, app shell, all views (Auth, ModelsCatalog, RunsDashboard, RunDetails, CompareRuns, PredictPanel, NewJob) and AdminScreen — delivered as small, independently verifiable phases, each leaving the system working and all 39 existing behaviour tests green except where a test pins visual copy that is intentionally changed (with justification).

Non-goals: backend API/schema changes, model catalog changes, router/state-library migration, product rename, env-based `API_BASE`, light-theme parity in this round (dark-first polish; light tokens only if cheap via token inversion), Playwright/CI, training-flow behaviour changes (layout only).

Acceptance:
- `npm test` green, `npm run build` green after every phase; `git diff` per phase stays reviewable (no 1-commit rewrite).
- No regression to invariants: `apiFetch` throw contract + 401 logout + `/artifact` blob, runs `{items}`/bare-array parse, polling cadences (5s/2s/1.5s), auth/register flow, predict request shapes (rows/texts/prompt/window_rows/node_ids/state/image).
- `role="alert"`/`role="status"` single-announcement behaviour preserved (C2), best-bar text cue, visible Compare header, scoped D1/D2 fixes not regressed.
- Visual: one palette/typography/spacing system consumed via tokens only (no ad-hoc hex), no layout negative margins, 44px not required but no interactive target <24px, `prefers-reduced-motion` and focus-visible preserved, mobile usable at 390px (DOM + static guards; browser probe recorded separately).

## 2. Facts vs assumptions

Facts [investigator + orchestrator baseline, all `file:line` in investigation report]:
- Palette tokens `styles.css:15-30` (`--canvas/surface/raised/rule/strong/ink/muted/faint/accent/.../ok/warn/bad`), `color-scheme:dark`, IBM Plex Sans 15px/Mono, `maxWidth:page:68rem/prose:42rem` (`tailwind.config.js:29`). Components: `.panel` hairline-only (`styles.css:73`), `.field` (`:74-85`), `.btn*` (`:86-97`), `.notice*` (`:100-102`), `.th/.td` (`:104-105`), `.dot` (`:103`). Dark-only, no `[data-theme]`. Focus-visible 2px (`styles.css:53`), reduced-motion kill-switch (`:118-120`).
- Tailwind content = `./index.html,./App.jsx,./AdminScreen.jsx,./main.jsx` only (`tailwind.config.js:6`) — any new `.jsx/.js` file needs a content entry or its classes vanish.
- Shell: header + `main` both `max-w-page px-5 md:px-8`, main `py-8 md:py-10` (`App.jsx:2594,2625`); nav `-mx-2` (`:2596`). Negative margins: `-mt-5` RunDetails header (`:1606`) + CompareRuns header (`:1286`), `-mx-2` catalog summary (`:459`) + nav.
- Views: `AuthView` (`:252`), `ModelsCatalog` (`:371`, `space-y-8`, search `field max-w-xs`), `RunsDashboard` (`:508`), `RunDetails` (`:1477`, `space-y-10`, ResultLine `text-5xl` at `:740`, "How it was trained" `grid-[10rem_1fr]` `:1683`), `CompareRuns` (`:1240`), `PredictPanel` (`:955`, segmented One/Several rows `:1092-1099`), `NewJob` (`:1706`, `max-w-6xl`, Model Intelligence gradient `:2341`, preset cards `:2305-2310`, labels without `htmlFor` at 8 sites). `MainApp` (`:2523`), `ErrorBoundary key=currentView:activeParams` (`:2627`).
- Admin bespoke: `AdminTab` (`AdminScreen.jsx:59-67`), tables `px-4 py-3 bg-surface divide-rule rounded-md border` (`:109-111`), inputs `bg-raised border-rule rounded-md px-2 py-1` (`:289,309,490`), saves `bg-accent hover:bg-accent-hover` (`:315,468,552`), vs shared `.field/.btn/.th/.td`.
- Duplicated formatters: `formatBytes` `App.jsx:2581` vs `AdminScreen.jsx:9-15` (different precision), `timeAgo` `App.jsx:74-85` vs `formatWhen` `AdminScreen.jsx:17-21`. P2a unknown handling depends on null→"—" semantics (must preserve true-zero vs unknown).
- Tests pin copy/labels/titles: headings (`admin` heading, auth labels), `getByTitle('Approve the pending account')`, `columnheader Compare`, `Select run 7…`, `0.900 best`, strings "No runs yet", "2 of 2 can run on this server.", "Session expired…", "Saved. The limits apply…", "Usage could not be loaded.", alert/status roles. Class-only changes are mostly safe; copy changes break suites.
- Invariants: `apiFetch` (`:173-239`) Bearer + FormData + 401 logout/throw `.status=401` + friendly network/non-JSON + `/artifact→blob` (`:236`); runs parse bare/`{items}` (`:526-531`); Compare per-run GET (not `/compare`); predict shapes rows/texts/prompt/window_rows/node_ids/state/image; poll cadences above.

Assumptions (verify in R1):
- Dark-first polish is sufficient for "full redesign" in this round; light mode can follow via token inversion without structural change (to be proven by token-only theming, phase R1).
- Copy pinned by tests can mostly be preserved verbatim; only shell/navigation headings may change, with test updates justified per case.
- `App.jsx` split is enabling but not prerequisite for visual redesign — shell/views can be redesigned in place, split afterwards (D6 order preserved).

## 3. Candidate approaches

A. **Incremental redesign in place, token-first (chosen).** R1 foundation (tokens, shell spacing, format helpers `E3`, negative-margin removal `E2`) → R2 shell/nav → R3 views → R4 admin (`E1`) → R5 mobile/a11y → R6 split. Correctness: each phase is a small diff with existing tests as guardrails; blast radius is one surface per phase; fully reversible per commit; consistency rises because every phase converges on shared tokens/classes. Cost: more phases, needs discipline.
B. **Big-bang rewrite** (new component tree + router + state library in one branch). Rejected: blast radius is the whole SPA, tests pinning copy/roles would all need rewrite, polling/401/blob regressions likely, unreviewable diff, violates atomic-phase rule and "smallest correct change".
C. **Light-theme-first redesign.** Rejected for this round: inverts the token risk (dark tokens are proven with contrast/focus/reduced-motion), doubles visual verification, no user ask for light. Token structure stays light-ready.
D. **Copy/layout redesign with behaviour changes** (new training flow, pagination, env config) bundled in. Rejected: mixes product decisions (pagination, env, router) into a visual round; those remain separate specs. Layout-only.

## 4. Atomic phases (sequential — shared `App.jsx`/`styles.css`, no parallel file ownership)

- **R1 Foundation.** Files: `frontend/styles.css`, `frontend/tailwind.config.js` (add `./views/**/*.jsx` + `./components/**/*.jsx` globs up front, even though dirs land in R6), new `frontend/format.js`, `frontend/App.jsx` (shell spacing only), `frontend/AdminScreen.jsx` (imports only), `frontend/tests/format.test.js` (new) + `frontend/tests/static.test.js` (extend). Work: polish tokens (contrast, spacing scale), page-shell rhythm so `-mt-5`/`-mx-2`/`-mx-3` layout hacks deleted (E2; guard covers ALL layout negative margins with allow-list for intentional `-translate-x-1/2`), consolidate formatters (E3) per contract table below, header spacing fix in shell. Formatter contract (resolve BEFORE extraction, F2): canonical `formatBytes(null/undefined)→"—"`, `0→"0 B"` (Admin semantics, preserves P2a true-zero), `formatWhen(null)→"—"`; App callers at `:630,1612` that today render `"0 KB"`/`""` must be updated to canonical and their tests adjusted with justification; failing unit tests first for null/0/undefined/large/date-edges. Preserves: every public component signature, polling, apiFetch. Tests: unit tests per helper; static guard: no layout negative margins remain. Done: suite+build green, no visual regression in test copy. Browser probe for shell/header spacing recorded per phase in tech-debt (jsdom cannot measure).
- **R2 App shell + navigation.** Files: `frontend/App.jsx` (MainApp shell, header/nav, breadcrumbs, ErrorBoundary untouched), `frontend/styles.css` (shell classes only), `frontend/tests/smoke.test.jsx` (extend nav cases). Work: redesigned header/nav (active states, mobile wrapping), breadcrumb component, page-header pattern (title + actions, no negative margins), empty/loading skeleton consistency. Preserves: hash routes `#/view/params`, `navigate()`, auth gate, roles/headings copy unless intentionally changed (justified + test updated). Tests: nav renders all destinations, active item marked, breadcrumb links navigate, 401 still logs out. Done: suite+build green.
- **R3 Views redesign (split for atomicity, F3).** R3a Files: `App.jsx`, `styles.css`, `runs.test.jsx`/`models.test.jsx` — AuthView, ModelsCatalog cards/search/disclosure, RunsDashboard table + Compare selection. R3b Files: `App.jsx`, `styles.css`, `compare.test.jsx`/`predict.test.jsx` — RunDetails (ResultLine, Evaluation, ConfusionMatrix, PreprocessingReport, PredictPanel incl. explicit predict-shape regression test rows/texts/prompt/window_rows/node_ids/state/image), "How it was trained", CompareRuns chart/table. R3c Files: `App.jsx`, `styles.css`, `smoke.test.jsx` — NewJob sections/preset cards/label `htmlFor` fixes. Preserves: data fetching, polling, predict shapes, alert/status semantics, best-bar cue. Done per sub-phase: suite+build green.
- **R4 Admin migration (E1).** Files: `frontend/AdminScreen.jsx`, `frontend/styles.css` (additive only), `frontend/tests/admin.test.jsx` + `static.test.js`. Work: replace bespoke inputs/buttons/tables with shared `.field/.btn*/.th/.td/.notice`, icons keep `lucide-react`, `UsageBar/StatusBadge/SummaryCard` restyled, no copy change except class-only. Preserves: all mutation alert/unknown semantics from P2a (queue action/load error split). Tests: existing 15 admin tests still green; static guard: no `bg-raised border border-rule` input strings remain. Done: suite+build green.
- **R5 Mobile + a11y hardening.** Files: `frontend/App.jsx`, `frontend/AdminScreen.jsx`, `frontend/styles.css`, `frontend/tests/static.test.js` + runs/predict cases. Work: 390px layout (tables scroll, grids collapse, no interactive target <24px, focus-visible audit, `label htmlFor` on NewJob, disclosure/aria polish). Preserves: C2 status dedup, C3 cue, C4 visible header. Tests: static guards + DOM order/focus checks. Note: 24px height cannot be proven by string scan (F7) — guards are indicative only; definitive check is manual 390px probe + tech-debt. Done: suite+build green; browser/SR probe queued in tech-debt (not claimed).
- **R6 Split (F1, enabling).** Files: new `frontend/views/*.jsx` / `frontend/components/*.jsx` (wired in `tailwind.config.js` in R1), `frontend/App.jsx` re-exports, `frontend/tests/static.test.js` UPDATED FIRST to scan `App.jsx+views/**+AdminScreen.jsx` (F1 — static guards read source directly, not black-box), other `frontend/tests/` unchanged. Work: move views/components verbatim out of `App.jsx` (no behaviour change; imports only). Preserves: every export contract + fetch behaviour. Tests: full suite green with zero copy changes; static guard: `App.jsx` shrinks, no duplicate definitions. Done: suite+build green. If split proves higher-risk than value in R6 brief, it may be deferred with ADR — recorded as decision, not silent.

Dependency graph: R1 → R2 → R3 → R4 → R5 → R6 (strictly sequential: shared `App.jsx`/`styles.css`; R4 needs R1 tokens; R6 needs R3–R5 stable). Checkpoint after each: `npm test` + `npm run build` + independent code-review + test-review.

## 5. Blast radius, rollback, risks, second-order effects

Blast radius: frontend only (`frontend/`); no backend, migration, API, or config change. Shared touchpoints: `.panel/.field/.btn/.th/.td/.notice` tokens, `MainApp` shell, `apiFetch`. Rollback: revert phase commit on branch `frontend-ui-round2` (branched from `origin/main` @ `7e40830`, the merged PR #1 result; round-1 branch `frontend-ui-round1` is closed).

Risks: (1) copy/label/title changes breaking test-suite pins — mitigate by preserving test-pinned strings or updating tests with explicit justification; (2) new files without Tailwind content entry → unstyled UI — mitigate via R1 wiring + build check; (3) shell spacing change exposing `-mt-5` compensation elsewhere — mitigate by deleting hacks and re-checking Compare/RunDetails headers in R1–R2; (4) token polish breaking contrast/focus — mitigate via token-only diff + focus-visible/reduced-motion tests; (5) split introducing import cycles — mitigate via R6 no-behaviour-change rule.

Second-order: tokens make future light mode cheap; shared classes lower Admin/App divergence; split lowers the cost of the next view change. Test suite becomes the design contract — future copy edits must update tests deliberately.

Open questions (non-blocking): exact light-mode timing (deferred, token-ready as hypothesis only — inversion may need component fixes, no parity claim), pagination/env/router (out of scope, separate specs), browser/SR probe scheduling (tech-debt).

## 6. Planner-reviewer objections → resolutions (2026-11-08)

- F1 major, R6 tests-unchanged false (`static.test.js` source-based) → R6 updates `static.test.js` FIRST to scan `App.jsx+views/**+AdminScreen.jsx`.
- F2 major, E3 semantics ambiguous (App `0→"0 KB"` no-null vs Admin `0→"0 B"` null→"—") → R1 contract table: canonical null→"—", `0→"0 B"`, `formatWhen(null)→"—"`; App callers updated with test justification; failing tests first.
- F3 major, R3 too large → split R3a/R3b/R3c (Auth/Catalog/Runs, RunDetails/Compare/Predict, NewJob), each independently verifiable.
- F4 major, `-mt-5` guard too narrow + jsdom can't measure → guard ALL layout negative margins with allow-list for `-translate-x-1/2`; browser probe per phase in tech-debt.
- F5 major, rollback stale (PR #1 MERGED) → branch `frontend-ui-round2` from `origin/main` @ `7e40830`; round-1 branch closed.
- F6 minor, Tailwind glob vague → R1 adds `./views/**/*.jsx` + `./components/**/*.jsx` up front with build check.
- F7 minor, 24px string guard unreliable → indicative only; manual probe in tech-debt.
- F8 minor, light-inversion unproven → marked hypothesis, no parity claim.
