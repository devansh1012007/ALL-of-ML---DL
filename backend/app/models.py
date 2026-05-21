from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="user")
    training_runs = relationship("TrainingRun", back_populates="owner", cascade="all, delete-orphan")

class TrainingRun(Base):
    __tablename__ = "training_runs"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
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
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    owner = relationship("User", back_populates="training_runs")
