<!-- PROPOSED pull request template. To activate, move to .github/pull_request_template.md. -->

## What changed

<!-- One paragraph. Why, not only what. -->

## How it was tested

- [ ] `pytest backend/tests` (or not affected)
- [ ] `alembic check` if models or migrations changed
- [ ] `npm test` and `npm run build` in `frontend/` (or not affected)
- [ ] For UI changes: a screenshot or a note on the widths and themes checked

## Risk and rollback

<!-- What could go wrong after deployment, and how to get back to the previous version.
     Does this change add a migration? Is it additive (expand and contract)? -->

## Checklist

- [ ] No `.env`, keys, models, or uploads in the diff
- [ ] Documentation updated where behaviour or configuration changed
- [ ] If this belongs to a numbered wave in `docs/agent-ops/`, its report is linked below

<!-- Link: -->
