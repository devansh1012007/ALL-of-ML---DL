# Operating this application

The audience of this page is the person who runs the deployment. The user's
manual lives in `docs/USER_GUIDE.md`; the model catalogue's honesty rules
live in `docs/MODEL_TIERS.md`; the first-week checkpoint in
`docs/CHECKPOINT.md`.

## The three processes

* **the api** - serves the HTTP endpoints, enqueues runs. With
  `TRAINING_IN_API=0` it never trains (what `docker-compose.yml` sets).
* **the worker** - `python -m backend.app.worker`: claims queued runs from
  the database and trains them. One worker per machine; scale by adding
  machines, not by editing code.
* **postgres** - the database is the queue, the registry and the ledger.
  SQLite works for one user on one box; Postgres is the tested target
  (see `.github/workflows/ci-postgres.yml`).

## The start of a deployment

    cp .env.example .env          # then edit the values
    docker compose up -d
    docker compose exec api alembic upgrade head
    docker compose exec api python -m backend.app.admin create-admin <username>

The startup validates every environment variable (plan H4) and prints the
effective non-secret configuration; a nonsense value is refused with the
variable's name in the message.

## What to watch

* `GET /healthz` - the process is up and the database answers.
* `GET /readyz` - the schema is at the revision the code expects. A 503
  here means "run the migrations", nothing else.
* `GET /metrics` - the queue depth by status, the run durations, the
  failures by model, the predict latency, the live workers (plan H3).

## The limits and the fairness

Every limit is a row in `quota_profiles` (or `user_quota_overrides`), not a
constant: edit them in the admin screen. The claim gives the turn to the
owner with the fewest running runs (plan B5), so one full queue cannot
starve the others. A run whose worker died is retried while it has attempts
left (plan B6); a model that needs a GPU is only claimed by a worker that
has one (plan B7).

## The executor

`TRAINING_EXECUTOR=thread` (default) runs trainings in the worker's own
process: fine for tests and for a trusted single user, but a cancel frees
the slot only when the training ends. `TRAINING_EXECUTOR=subprocess` starts
one interpreter per training: a cancel kills it, the wall-clock and memory
limits of the quota profile are enforced, and a segfault in a booster takes
down one child and not the worker. The subprocess executor is the
production default; the thread one is the tests' default.

## Backups and upgrades

* the database holds the state: back it up before every migration
  (`pg_dump`; the sqlite file is backed up by copying it while the
  processes are stopped).
* the artifacts live under `backend/models/`, the uploads under
  `uploads/` - both on volumes the API and the workers share.
* to upgrade: pull, `alembic upgrade head`, restart the processes. The
  retention rules and the janitor (plan H1) keep the disk from filling
  between upgrades.
