# Brief — W1-PLAN-01 (planner-reviewer) · wave 1 · run 20261108-light-negative

## 1. Role and mission
You CRITIQUE the light-mode spec (T-101, DEEP) before any implementation. Your job is to break the plan against the actual code: is Option A (data-theme variable inversion) really the right call, are the unresolvable questions actually resolvable, and is the wave plan safe? You are read-only; you never edit the spec. Failure mode to hunt: a confident plan that silently requires touching RunDetails.jsx classes (C1), misses the FOUC/init detail, or leaves the palette to the implementer without acceptance math.

## 2. Required reading
1. docs/agent-ops/20261108-light-negative/templates/STANDING-ORDERS.md (binding)
2. docs/plans/2026-11-08-light-mode.md (THE spec under review — read in full)
3. docs/agent-ops/20261108-light-negative/reports/w0-investigation/INV-light-mode.md (evidence base for the spec)
4. frontend/index.html, frontend/vite.config.js (verify §4.4 init-script + §10 static-test claims against reality)
5. frontend/App.jsx:1-200 and frontend/components/shared.jsx:150-200 (verify toggle-placement + storage claims, cross-check AuthView.jsx)

## 3. Task and acceptance criteria
For each spec section, classify as SUPPORTED (code confirms), UNSUPPORTED (code contradicts), or MISSING (real question the spec should pin but doesn't). Attack surface you MUST cover:
1. Is the inline-init-script-in-index.html actually pre-paint in this Vite setup? What else could FOUC (StrictMode double-render, HMR)?
2. Toggle-in-both-shells vs header-only vs AuthView-only — which does the spec pin? Is requiring BOTH shells over-engineering? What's the minimal-risk placement?
3. Does any component break if the token VALUES change even though class names stay? (e.g. ConfusionMatrix inline alpha, Bar/ResultLine, badges with /0.1-/0.5 washes compositing over white — spot-check metrics.jsx:270.)
4. Is `text-orange-400` the ONLY hardcoded outlier, or did the census miss Tailwind-palette or arbitrary-value usages (e.g. `bg-[#...]`, `text-[...]`, `shadow-*`)?
5. The light palette is left to the design record — is that acceptable, or must the spec carry the 14 values + contrast math NOW so implementation is mechanical? What evidence will prove the palette is right without a browser?
6. Static-test strategy: does pinning "selector exists + 14 tokens + color-scheme" actually prevent regression, or does it test implementation detail?
Acceptance: objections with severity (BLOCKER = must fix before impl; MAJOR = fix or explicitly accept; MINOR = note) + a final APPROVE / APPROVE-WITH-CHANGES / REJECT verdict on the spec. Record each objection's resolution requirement.
Write to: docs/agent-ops/20261108-light-negative/reports/w1-review/PLAN-W1-PLAN-01.md (use templates/review-code.md structure adapted for a planner review — start with ORCH-DIGEST).

## 4. Ownership
READ-ONLY on source AND on the spec. Write ONLY your report file. Do NOT commit.

## 5. Deliverables
Report first (ORCH-DIGEST first). Final message ≤8 lines: STATUS | agent | report path | verdict | BLOCKER/MAJOR counts | blockers. Scoped greps/reads only; never full suite/build (coder agents own those).
