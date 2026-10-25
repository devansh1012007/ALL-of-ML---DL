from sqlalchemy import Column, Index, Integer, String, ForeignKey, DateTime, JSON, Text, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="user")
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
    id = Column(Integer, primary_key=True, index=True)
    # Indexed because every read of the run history filters on the owner.
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    model_name = Column(String, nullable=False)
    dataset_source = Column(String, nullable=False)
    dataset_tag = Column(String, nullable=False)
    hf_dataset_url = Column(String, nullable=True)
    mode = Column(String, nullable=False, default="manual")
    env_id = Column(String, nullable=True)
    optimize_metric = Column(String, nullable=True)
    model_candidates = Column(JSON, nullable=True)
    hyperparameters = Column(JSON, nullable=False)
    metrics = Column(JSON, nullable=True)
    artifact_path = Column(String, nullable=True)
    # queued -> running -> completed | failed | cancelled. Indexed: the worker
    # asks for the oldest queued run.
    status = Column(String, nullable=False, default="pending", index=True)
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
