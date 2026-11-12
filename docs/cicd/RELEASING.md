# Releasing

How a version is cut, published and rolled back. Companion to `docs/cicd/SPEC.md`. Some steps
depend on decisions and blockers listed there; the status column of section 5 says which.

## Versions

- Semantic versioning: `MAJOR.MINOR.PATCH`, tagged `vMAJOR.MINOR.PATCH` (for example `v0.1.0`).
- Start at `0.1.0`. A `0.x` series may change the API and the schema between minors; say so in the
  release notes.
- A tag is never moved or reused. A bad release gets a new patch version.

## What a release is

A tag on a commit of `main` whose CI passed. The tag triggers the release workflow, proposed as
`docs/cicd/proposed/release.yml` and adopted in SPEC phase P4. That workflow:

1. runs the reusable CI on the tagged commit;
2. builds the backend image and pushes `ghcr.io/<owner>/allml-backend:X.Y.Z`, `:X.Y` and `:<sha>`;
3. builds the frontend and attaches `frontend-<tag>.tgz` to a GitHub Release with generated notes.

A release deploys nothing. Deployment is a separate, manual step (section "Deploying").

## Cutting a release

1. Confirm `main` is green in the two required checks.
2. Confirm the migrations of this release follow the rules in section "Migrations".
3. Update `CHANGELOG.md` with the changes since the last tag (by hand until release automation is
   adopted, SPEC REL-4).
4. Tag the commit and push the tag:

       git switch main && git pull --ff-only
       git tag -a v0.1.0 -m "v0.1.0"
       git push origin v0.1.0

5. Wait for the release workflow. Check that the three image tags exist and that the GitHub
   Release has the archive.

## Deploying

Always deploy to staging first, then production, with the same image tag.

1. Run `deploy.yml` (manual) with `environment: staging`, the new `image_tag`, and the previous
   tag as `previous_tag`.
2. Check the health endpoint and one feature by hand.
3. Run `deploy.yml` with `environment: production`. The production environment needs an approval
   from a required reviewer (SPEC SET-8).
4. Check the health endpoint again and watch the logs for ten minutes.

`deploy.yml` backs up the database to `backups/pre-<tag>.sql.gz` on the host before it migrates.
Keep that file until the next release is verified.

## Migrations

- Every change to a model comes with an Alembic migration. `alembic check` must pass in CI, so a
  forgotten migration fails the build.
- Never edit a migration that has been applied anywhere, including staging.
- Use expand and contract. Each release either adds (new tables, new nullable columns, new
  indexes) or completes a change whose first half is already deployed. A release that renames or
  drops a column is two releases: one that stops using the old name, and a later one that removes
  it.
- Under this rule the previous application image works against the new schema, so a rollback of
  the application is always safe.
- Down-migrations are not used in production. A destructive change is undone from a backup, not
  from a script.

## Rolling back

Application rollback (the normal case):

    ALLML_IMAGE=ghcr.io/<owner>/allml-backend:<previous tag> docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d api worker

Run it on the host in the deployment directory. The `-f docker-compose.prod.yml` file is the one
blocker B6 asks for; it does not exist yet. `deploy.yml` prints the same command when its health
check fails. Then confirm `/healthz`.

Schema rollback (only when a migration itself is wrong and the application cannot work with it):

1. Stop `api` and `worker`.
2. Restore `backups/pre-<tag>.sql.gz` into an empty database. Every write made after the backup is
   lost.
3. Start the previous image, then `/healthz`.
4. Record what was lost, and why, in the incident note.

This is a decision for a person. No workflow does it automatically.

## Hotfixes

A fix for the current release branches from the tag, not from `main`, when `main` contains
unreleased work. Use `fix/<name>`, merge it into `main` as well, and tag a patch version. Keep the
hotfix to the one change.

## After a release

- The release notes say what changed for operators (configuration, migrations, required backups),
  not only what changed in the code.
- Note the image tag and the backup name in the deployment log.
