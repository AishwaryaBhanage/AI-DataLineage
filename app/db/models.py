"""
SQLAlchemy ORM models.

Design notes:
  - All timestamps use UTC (naive datetime in SQLite, timestamptz in Postgres)
  - JSON columns use SQLAlchemy's JSON type — maps to TEXT on SQLite,
    JSONB on Postgres automatically
  - String UUIDs (not native UUID) because SQLite has no UUID type;
    Postgres will still accept them
  - Indexes on columns we query by: api_key_prefix, status, created_at
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
)

from app.db.base import Base


# ── Enums ────────────────────────────────────────────────────────────────────

class JobStatus(str, PyEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobMode(str, PyEnum):
    FAST = "fast"
    AGENTIC = "agentic"


# ── Helper ───────────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    """Return current UTC time as a naive datetime.

    Naive because SQLite has no tz support; we store everything as UTC
    and convert in the API layer if the client cares about tz.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _new_job_id() -> str:
    """Generate a short, URL-safe job ID.

    Example: "job_7c9a3e2f4b1d"
    """
    return f"job_{uuid.uuid4().hex[:12]}"


# ── Jobs table ───────────────────────────────────────────────────────────────

class Job(Base):
    """One debug run.

    Jobs in fast mode complete synchronously but are still logged here
    for usage tracking and history.

    Jobs in agentic mode are async: the API creates the row with
    status=queued, returns the job_id to the client, and a background
    task updates the row as it runs.
    """
    __tablename__ = "jobs"

    # Primary key — string UUID for Postgres/SQLite portability
    id = Column(String(32), primary_key=True, default=_new_job_id)

    # Who: first 10 chars of the API key (never the full key)
    api_key_prefix = Column(String(32), nullable=False, index=True)

    # What: fast or agentic
    mode = Column(Enum(JobMode), nullable=False, index=True)

    # Status: queued → running → completed/failed
    status = Column(
        Enum(JobStatus),
        nullable=False,
        default=JobStatus.QUEUED,
        index=True,
    )

    # Request body (for reproducibility — don't store anything secret)
    # Contains: source, manifest_path, run_results_path, model_name, etc.
    request = Column(JSON, nullable=False, default=dict)

    # Result: populated when status=completed
    # Contains: broken_model, rule_hits, corrected_sql, llm_result, etc.
    result = Column(JSON, nullable=True)

    # Error message if status=failed
    error = Column(Text, nullable=True)

    # Broken model name (pulled out for quick filtering)
    broken_model = Column(String(255), nullable=True, index=True)

    # Cache key (hash of input) — for dedup / caching hits
    cache_key = Column(String(64), nullable=True, index=True)

    # Timings
    created_at = Column(DateTime, nullable=False, default=_utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # Compound indexes for common queries
    __table_args__ = (
        Index("ix_jobs_key_created", "api_key_prefix", "created_at"),
        Index("ix_jobs_status_created", "status", "created_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status.value if self.status else None,
            "mode": self.mode.value if self.mode else None,
            "broken_model": self.broken_model,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "duration_ms": self.duration_ms,
        }


# ── Usage log table ──────────────────────────────────────────────────────────

class UsageLog(Base):
    """One row per API request.

    Used for:
      - Per-key usage stats (for the /api/v1/usage endpoint)
      - Rate limit auditing
      - Finding abusive or slow requests
      - Billing (when you monetize later)
    """
    __tablename__ = "usage_log"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Who
    api_key_prefix = Column(String(32), nullable=False, index=True)

    # What
    endpoint = Column(String(255), nullable=False, index=True)
    method = Column(String(10), nullable=False)
    status_code = Column(Integer, nullable=False)

    # How long
    duration_ms = Column(Integer, nullable=False)

    # When
    timestamp = Column(DateTime, nullable=False, default=_utcnow, index=True)

    # Optional: job ID if this request created a job
    job_id = Column(String(32), nullable=True)

    __table_args__ = (
        Index("ix_usage_key_ts", "api_key_prefix", "timestamp"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "api_key_prefix": self.api_key_prefix,
            "endpoint": self.endpoint,
            "method": self.method,
            "status_code": self.status_code,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "job_id": self.job_id,
        }


# ── Cache table ──────────────────────────────────────────────────────────────

class CacheEntry(Base):
    """Cached debug results keyed by content hash.

    Why:
      If two users debug the same broken model with the same manifest,
      there's no point calling Claude twice.  We cache the result for
      1 hour by default.

    The cache_key is sha256(manifest_path + run_results_path + model_name + mode).
    """
    __tablename__ = "cache_entries"

    cache_key = Column(String(64), primary_key=True)
    mode = Column(Enum(JobMode), nullable=False)
    result = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False, default=_utcnow, index=True)
    hit_count = Column(Integer, nullable=False, default=0)

    def to_dict(self) -> dict:
        return {
            "cache_key": self.cache_key,
            "mode": self.mode.value if self.mode else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "hit_count": self.hit_count,
        }
