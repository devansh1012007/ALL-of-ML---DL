from sqlalchemy import Column, Index, Integer, String, ForeignKey, DateTime, JSON, Text, Boolean, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="user")
    # The lifecycle state of the account (plan A1): "pending" waits for an
    # approval, "active" is a normal account, "suspended" cannot log in and
    # its tokens stop working at the next request (the row is re-read every
    # time, so a status change applies at once).
    status = Column(String, nullable=False, default="active", server_default="active")
    # The revocation counter (plan A2): any change that must end sessions
    # (password change, suspension, an admin action) increments it, and the
    # token carries the version it was minted with.
    token_version = Column(Integer, nullable=False, default=0, server_default="0")
    email = Column(String, nullable=True)
    # No database-level foreign key: the column was added to an existing
    # table (SQLite cannot ALTER in a constraint), and the profile of a user
    # is resolved through the queries.
    quota_profile_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    training_runs = relationship("TrainingRun", back_populates="owner", cascade="all, delete-orphan")

class Dataset(Base):
    """A dataset the application can train on.

    A dataset is a row, not a path: the client refers to it by its id, and
    only the server turns a row into a path. The path itself is relative to
    the datasets root, so a dataset can never point outside of it.

    ``owner_id`` is NULL for the datasets that ship with the repository: they
    belong to everybody. An uploaded dataset belongs to the user who uploaded
    it.
    """

    __tablename__ = "datasets"
    __table_args__ = (
        # The path of a dataset is unique: it is what identifies the file.
        Index("ix_datasets_storage_path", "storage_path", unique=True),
        # A name is unique inside an owner, and the listing is always "the
        # datasets of this owner, by name": the same index serves both.
        Index("uq_datasets_owner_id_name", "owner_id", "name", unique=True),
        # The datasets of the repository have no owner, and a NULL is not a
        # value that a unique index compares: their names need an index of
        # their own.
        Index(
            "uq_datasets_builtin_name",
            "name",
            unique=True,
            sqlite_where=text("owner_id IS NULL"),
            postgresql_where=text("owner_id IS NULL"),
        ),
    )
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    name = Column(String, nullable=False)
    # The path of the file, relative to the datasets root.
    storage_path = Column(String, nullable=False)
    # "builtin" (a file of the repository), "upload" (a file of a user) or
    # "folder" (a directory of class subfolders, for the vision models).
    source = Column(String, nullable=False, default="upload")
    # The kind of data the file holds (plan F1): tabular, timeseries, graph,
    # text, text_pairs or image_folder. It decides which model family can
    # train on it and how the upload is validated.
    kind = Column(String, nullable=False, default="tabular", server_default="tabular")
    # The content hash of the file: it identifies the data itself (two names
    # for one file are one dataset), and the comparison guard of plan E4
    # compares runs by it.
    content_sha256 = Column(String, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    row_count = Column(Integer, nullable=True)
    # The columns of the file: a list of {"name": ..., "dtype": ...}.
    columns = Column(JSON, nullable=True)
    # The label column the registry suggests for this dataset.
    label_column = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    owner = relationship("User")


class TrainingRun(Base):
    __tablename__ = "training_runs"
    __table_args__ = (
        # The listing of the runs of one owner is ordered by date (plan E5).
        Index("ix_training_runs_owner_created", "owner_id", "created_at"),
    )
    id = Column(Integer, primary_key=True, index=True)
    # Indexed because every read of the run history filters on the owner.
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    model_name = Column(String, nullable=False)
    dataset_source = Column(String, nullable=False)
    dataset_tag = Column(String, nullable=False)
    # The dataset row of the training (plan E4): the comparison guard
    # compares runs by dataset id and content hash. No database-level
    # foreign key: the column was added to an existing table.
    dataset_id = Column(Integer, nullable=True, index=True)
    hf_dataset_url = Column(String, nullable=True)
    mode = Column(String, nullable=False, default="manual")
    env_id = Column(String, nullable=True)
    optimize_metric = Column(String, nullable=True)
    model_candidates = Column(JSON, nullable=True)
    hyperparameters = Column(JSON, nullable=False)
    metrics = Column(JSON, nullable=True)
    # The heavy chart data of plan E1: written at the end of the training,
    # returned by GET /runs/{id}/charts, never by the run list.
    charts = Column(JSON, nullable=True)
    artifact_path = Column(String, nullable=True)
    # The integrity record of the artifact (plan C1): the sha256 of the
    # manifest, verified before every load.
    artifact_sha256 = Column(String, nullable=True)
    artifact_bytes = Column(Integer, nullable=True)
    # The moment the artifact was removed while the run stayed (plan H1): a
    # retention rule or the janitor dropped the file, the metrics stay. NULL
    # means the artifact (or the lack of one) is exactly as it was written.
    artifact_removed_at = Column(DateTime(timezone=True), nullable=True)
    # "train" (a training) or "predict" (a queued batch prediction, plan D3).
    job_kind = Column(String, nullable=False, default="train", server_default="train")
    # The fair share and the routing of the execution layer (plans B5-B7):
    # the claim prefers the owners with the fewest running runs, then the
    # highest priority, then the oldest; ``requirements`` records what the
    # model needs (gpu, memory) so a worker that cannot satisfy it does not
    # take it, and ``max_attempts`` bounds the retries of an infrastructure
    # death (B6).
    priority = Column(Integer, nullable=False, default=0, server_default="0")
    requirements = Column(JSON, nullable=True)
    max_attempts = Column(Integer, nullable=False, default=2, server_default="2")
    # queued -> running -> completed | failed | cancelled. Indexed: the worker
    # asks for the oldest queued run.
    status = Column(String, nullable=False, default="pending", index=True)
    # The editable memory of a run (plan E5): tags and a note, the lightweight
    # equivalent of what a notebook gets from its cells.
    tags = Column(JSON, nullable=True)
    note = Column(Text, nullable=True)
    # The usage accounting of plan A5, filled when the run finishes.
    wall_seconds = Column(Integer, nullable=True)
    cpu_seconds = Column(Integer, nullable=True)
    peak_rss_bytes = Column(Integer, nullable=True)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    # Everything a worker needs to run the training: the request, the resolved
    # path of the dataset and its name. The row is the queue, so a queued run
    # survives a restart and any process can pick it up.
    request_payload = Column(JSON, nullable=True)
    # Who runs the run, since when, and the last time it said it was alive. A
    # running run whose heartbeat stopped is failed; one with a fresh heartbeat
    # belongs to a live worker and is never touched.
    worker_id = Column(String, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    owner = relationship("User", back_populates="training_runs")


class QuotaProfile(Base):
    """A named bundle of limits (plan A3).

    Every limit column is nullable and NULL means unlimited, which is how the
    ``unlimited`` profile for the admins is simply the absence of numbers.
    The limits are data an admin edits, not constants in the code.
    """

    __tablename__ = "quota_profiles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    max_concurrent_runs = Column(Integer, nullable=True)
    max_queued_runs = Column(Integer, nullable=True)
    max_runs_per_day = Column(Integer, nullable=True)
    max_run_seconds = Column(Integer, nullable=True)
    max_run_memory_mb = Column(Integer, nullable=True)
    max_cpu_seconds_per_month = Column(Integer, nullable=True)
    max_storage_bytes = Column(Integer, nullable=True)
    max_datasets = Column(Integer, nullable=True)
    max_upload_bytes = Column(Integer, nullable=True)
    max_rows = Column(Integer, nullable=True)
    max_predict_rows_per_request = Column(Integer, nullable=True)
    max_predict_requests_per_minute = Column(Integer, nullable=True)
    # A JSON list of the categories this profile may train (plan A3): the
    # compute-heavy families default to off until an admin enables them.
    allowed_categories = Column(JSON, nullable=True)
    gpu_allowed = Column(Boolean, nullable=True)
    # The retention of the artifacts (plan H1): the artifacts of the runs that
    # fall out of either rule are removed while the run keeps its metrics and
    # shows ``artifact_removed``. NULL on both means "keep everything".
    artifact_keep_runs = Column(Integer, nullable=True)
    artifact_keep_days = Column(Integer, nullable=True)


class UserQuotaOverride(Base):
    """The per-user exceptions to a quota profile (plan A3).

    A non-null value overrides the profile for that user; the profile is one
    decision per user, the overrides keep the exceptions out of it.
    """

    __tablename__ = "user_quota_overrides"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)
    max_concurrent_runs = Column(Integer, nullable=True)
    max_queued_runs = Column(Integer, nullable=True)
    max_runs_per_day = Column(Integer, nullable=True)
    max_run_seconds = Column(Integer, nullable=True)
    max_run_memory_mb = Column(Integer, nullable=True)
    max_cpu_seconds_per_month = Column(Integer, nullable=True)
    max_storage_bytes = Column(Integer, nullable=True)
    max_datasets = Column(Integer, nullable=True)
    max_upload_bytes = Column(Integer, nullable=True)
    max_rows = Column(Integer, nullable=True)
    max_predict_rows_per_request = Column(Integer, nullable=True)
    max_predict_requests_per_minute = Column(Integer, nullable=True)
    allowed_categories = Column(JSON, nullable=True)
    gpu_allowed = Column(Boolean, nullable=True)
    # The retention of the artifacts (plan H1): the artifacts of the runs that
    # fall out of either rule are removed while the run keeps its metrics and
    # shows ``artifact_removed``. NULL on both means "keep everything".
    artifact_keep_runs = Column(Integer, nullable=True)
    artifact_keep_days = Column(Integer, nullable=True)


class Invite(Base):
    """A one-time registration code (plan A1, registration mode "invite").

    The code is stored hashed, expires, and is counted: the same code can be
    handed to a class of twenty with ``max_uses``.
    """

    __tablename__ = "invites"
    id = Column(Integer, primary_key=True, index=True)
    code_hash = Column(String, nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    max_uses = Column(Integer, nullable=False, default=1)
    use_count = Column(Integer, nullable=False, default=0, server_default="0")
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    """Who did what, and when (plan A9).

    The moment there is an admin who can change another person's limits,
    someone will ask who did it.
    """

    __tablename__ = "audit_events"
    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    action = Column(String, nullable=False, index=True)
    target_type = Column(String, nullable=True)
    target_id = Column(String, nullable=True)
    detail = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class Deployment(Base):
    """A stable name for a model (plan D1).

    A run is an experiment and never changes; a service needs an address that
    survives retraining. Pointing the name at another run is one transaction,
    and the events table keeps the history a rollback needs.
    """

    __tablename__ = "deployments"
    __table_args__ = (
        # A name is unique per owner: two users may both have "production".
        Index("uq_deployments_owner_name", "owner_id", "name", unique=True),
    )
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    run_id = Column(Integer, ForeignKey("training_runs.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DeploymentEvent(Base):
    """Who pointed a deployment name at which run, and when (plan D1)."""

    __tablename__ = "deployment_events"
    id = Column(Integer, primary_key=True, index=True)
    deployment_id = Column(Integer, ForeignKey("deployments.id"), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    from_run_id = Column(Integer, nullable=True)
    to_run_id = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ApiKey(Base):
    """An API key for programs (plan D2).

    The key is 32 random bytes shown once and stored only as a hash: a
    database leak does not leak working keys. A key has the ``predict`` scope
    only - it cannot train, delete or read the owner's data - and it counts
    against the owner's quota.
    """

    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    prefix = Column(String, nullable=False, index=True)
    key_hash = Column(String, nullable=False, unique=True, index=True)
    scopes = Column(JSON, nullable=False, default=list)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DeploymentStat(Base):
    """The hourly counters of a deployment (plan D6).

    The first question after deploying is "does it still work?" - these
    counters answer it without a monitoring system, and they double as the
    usage numbers the quota UI shows. The drift flag compares the prediction
    distribution of the hour with the stored histogram (a population
    stability index above 0.2).
    """

    __tablename__ = "deployment_stats"
    id = Column(Integer, primary_key=True, index=True)
    deployment_id = Column(Integer, ForeignKey("deployments.id"), nullable=False, index=True)
    # The hour the counters belong to, as UTC ISO (truncated to the hour).
    hour = Column(String, nullable=False, index=True)
    requests = Column(Integer, nullable=False, default=0, server_default="0")
    rows = Column(Integer, nullable=False, default=0, server_default="0")
    errors = Column(Integer, nullable=False, default=0, server_default="0")
    out_of_range = Column(Integer, nullable=False, default=0, server_default="0")
    # The histogram of the predictions of this hour (a JSON list of counts)
    # and the reference the drift flag is computed against.
    prediction_histogram = Column(JSON, nullable=True)
    drift_flag = Column(Boolean, nullable=False, default=False, server_default="false")


class RefreshToken(Base):
    """A refresh token of a browser session (plan A2).

    The long-lived credential never travels in the response body of a browser
    login: it goes into an httpOnly cookie. The row stores the *hash* of the
    token, so a stolen database does not hold a usable session.

    Rotation with reuse detection: refreshing marks the row revoked and names
    its replacement (``replaced_by``). Presenting a token that was already
    rotated means the family leaked, and every member of the family
    (``family_id``) is revoked at once - the attacker's copy included.
    """

    __tablename__ = "refresh_tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # sha256 hex of the raw token. Unique: one row per issued token.
    token_hash = Column(String, nullable=False, unique=True, index=True)
    # All tokens of one login chain share the family id; a reuse revokes it.
    family_id = Column(String, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    replaced_by = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RateEvent(Base):
    """One counted attempt of the rate limiter (plan A8).

    The limiter used to live in the memory of one process, which made it a
    lie the moment a second worker started: every process had its own budget.
    The events live in the database now, so the budget is shared by every
    worker, and a fixed-window (sliding, in fact) count in SQL is enough at
    this scale. A purge in the maintenance loop keeps the table small.
    """

    __tablename__ = "rate_events"
    id = Column(Integer, primary_key=True, index=True)
    # The limiter key: "login:1.2.3.4", "login:1.2.3.4:alice",
    # "register:1.2.3.4", "upload:user:17", "predict:user:17".
    key = Column(String, nullable=False, index=True)
    at = Column(DateTime(timezone=True), nullable=False, index=True)


class RunEvent(Base):
    """One progress event of a run (plan B4).

    A run that trains for ten minutes must be able to say what it is doing:
    the phase it entered, the epoch it finished, the metric it just measured,
    the log line worth keeping. The child process writes the events as JSON
    lines on its standard output and the parent batches them into this table
    once a second; the thread executor writes them directly.

    The table is capped per run: the last ``MAX_EVENTS_PER_RUN`` events stay,
    the older ones are deleted as new ones arrive, so a chatty trainer cannot
    fill the disk with progress.
    """

    __tablename__ = "run_events"
    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("training_runs.id"), nullable=False, index=True)
    # The position of the event in the run's stream: the client asks for
    # everything after the seq it has seen (plan B4).
    seq = Column(Integer, nullable=False, index=True)
    ts = Column(DateTime(timezone=True), server_default=func.now())
    # phase | epoch | step | metric | log | result
    kind = Column(String, nullable=False)
    payload = Column(JSON, nullable=True)


class Worker(Base):
    """A process that claims runs, with what it can do (plan B7).

    Every worker registers itself in the maintenance loop: its id, the
    capabilities of the machine (a GPU? how much memory?), and the last
    seen time. The claim of a run checks the run's ``requirements`` against
    the claiming worker's capabilities - a GPU model never waits silently on
    a machine that cannot run it, and the submit answers 409 when no online
    worker could.
    """

    __tablename__ = "workers"
    # The id the worker writes into ``training_runs.worker_id``.
    id = Column(String, primary_key=True)
    capabilities = Column(JSON, nullable=False, default=dict)
    memory_mb = Column(Integer, nullable=True)
    last_seen = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
