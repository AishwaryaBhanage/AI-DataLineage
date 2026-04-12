"""
Repository layer — all database read/write operations.

Why this pattern:
  Routes should never contain raw SQL.  They call repository functions
  which handle the DB details.  This gives us:
    - One place to optimize a query
    - Easier testing (mock the repository, not the DB)
    - Clean migration path to a different DB engine

Every function takes an AsyncSession as its first argument.  Callers
get the session from the get_session FastAPI dependency.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job, JobMode, JobStatus, UsageLog, CacheEntry, _utcnow


# ─────────────────────────────────────────────────────────────────────────────
# JOBS
# ─────────────────────────────────────────────────────────────────────────────

async def create_job(
    session: AsyncSession,
    api_key_prefix: str,
    mode: JobMode,
    request_body: dict,
    cache_key: str | None = None,
) -> Job:
    """Create a new job with status=queued."""
    job = Job(
        api_key_prefix=api_key_prefix,
        mode=mode,
        status=JobStatus.QUEUED,
        request=request_body,
        cache_key=cache_key,
    )
    session.add(job)
    await session.flush()  # populates job.id without committing
    return job


async def get_job(session: AsyncSession, job_id: str) -> Job | None:
    """Fetch one job by ID."""
    result = await session.execute(select(Job).where(Job.id == job_id))
    return result.scalar_one_or_none()


async def list_jobs_for_key(
    session: AsyncSession,
    api_key_prefix: str,
    limit: int = 50,
) -> list[Job]:
    """List recent jobs for a specific API key, newest first."""
    result = await session.execute(
        select(Job)
        .where(Job.api_key_prefix == api_key_prefix)
        .order_by(Job.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def mark_job_running(session: AsyncSession, job_id: str) -> None:
    """Mark a job as running (called when worker picks it up)."""
    await session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(status=JobStatus.RUNNING, started_at=_utcnow())
    )


async def mark_job_completed(
    session: AsyncSession,
    job_id: str,
    result: dict,
    broken_model: str | None = None,
) -> None:
    """Mark a job as completed and store its result."""
    now = _utcnow()

    # Fetch to compute duration
    job = await get_job(session, job_id)
    duration_ms = None
    if job and job.started_at:
        delta = now - job.started_at
        duration_ms = int(delta.total_seconds() * 1000)

    await session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(
            status=JobStatus.COMPLETED,
            result=result,
            broken_model=broken_model,
            completed_at=now,
            duration_ms=duration_ms,
        )
    )


async def mark_job_failed(
    session: AsyncSession,
    job_id: str,
    error: str,
) -> None:
    """Mark a job as failed with an error message."""
    now = _utcnow()

    job = await get_job(session, job_id)
    duration_ms = None
    if job and job.started_at:
        delta = now - job.started_at
        duration_ms = int(delta.total_seconds() * 1000)

    await session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(
            status=JobStatus.FAILED,
            error=error[:2000],  # cap to prevent huge error dumps
            completed_at=now,
            duration_ms=duration_ms,
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
# USAGE LOG
# ─────────────────────────────────────────────────────────────────────────────

async def log_request(
    session: AsyncSession,
    api_key_prefix: str,
    endpoint: str,
    method: str,
    status_code: int,
    duration_ms: int,
    job_id: str | None = None,
) -> None:
    """Record an API request in the usage log."""
    entry = UsageLog(
        api_key_prefix=api_key_prefix,
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        duration_ms=duration_ms,
        job_id=job_id,
    )
    session.add(entry)


async def get_usage_stats(
    session: AsyncSession,
    api_key_prefix: str,
    days: int = 7,
) -> dict:
    """Aggregate truthful usage stats for a specific key over the last N days.

    Returns two categories of numbers:
      1. debug_runs — 1 entry per actual analysis (from jobs table)
      2. http_requests — 1 entry per HTTP call (from usage_log, includes polls)

    Use debug_runs for "how much has this user actually analyzed".
    Use http_requests for debugging request volume or detecting abuse.
    """
    since = _utcnow() - timedelta(days=days)

    # ── Debug runs (from jobs table — 1 row per actual analysis) ─────
    # Total debug runs
    total_runs = (await session.execute(
        select(func.count(Job.id)).where(
            Job.api_key_prefix == api_key_prefix,
            Job.created_at >= since,
        )
    )).scalar() or 0

    # Fast vs agentic breakdown
    fast_runs = (await session.execute(
        select(func.count(Job.id)).where(
            Job.api_key_prefix == api_key_prefix,
            Job.created_at >= since,
            Job.mode == JobMode.FAST,
        )
    )).scalar() or 0

    agentic_runs = (await session.execute(
        select(func.count(Job.id)).where(
            Job.api_key_prefix == api_key_prefix,
            Job.created_at >= since,
            Job.mode == JobMode.AGENTIC,
        )
    )).scalar() or 0

    # Status breakdown
    completed_runs = (await session.execute(
        select(func.count(Job.id)).where(
            Job.api_key_prefix == api_key_prefix,
            Job.created_at >= since,
            Job.status == JobStatus.COMPLETED,
        )
    )).scalar() or 0

    failed_runs = (await session.execute(
        select(func.count(Job.id)).where(
            Job.api_key_prefix == api_key_prefix,
            Job.created_at >= since,
            Job.status == JobStatus.FAILED,
        )
    )).scalar() or 0

    # Average duration by mode
    fast_avg_ms = (await session.execute(
        select(func.avg(Job.duration_ms)).where(
            Job.api_key_prefix == api_key_prefix,
            Job.created_at >= since,
            Job.mode == JobMode.FAST,
            Job.duration_ms.isnot(None),
        )
    )).scalar() or 0

    agentic_avg_ms = (await session.execute(
        select(func.avg(Job.duration_ms)).where(
            Job.api_key_prefix == api_key_prefix,
            Job.created_at >= since,
            Job.mode == JobMode.AGENTIC,
            Job.duration_ms.isnot(None),
        )
    )).scalar() or 0

    # Unique broken models debugged (gives a sense of "distinct problems analyzed")
    unique_models = (await session.execute(
        select(func.count(func.distinct(Job.broken_model))).where(
            Job.api_key_prefix == api_key_prefix,
            Job.created_at >= since,
            Job.broken_model.isnot(None),
        )
    )).scalar() or 0

    # Cache hits — jobs with a cache_key that was shared across runs
    # (a rough approximation — real cache hits are tracked in CacheEntry.hit_count)
    cache_entries = (await session.execute(
        select(func.coalesce(func.sum(CacheEntry.hit_count), 0)).select_from(CacheEntry)
    )).scalar() or 0

    # ── Raw HTTP requests (from usage_log — includes polling noise) ──
    total_http = (await session.execute(
        select(func.count(UsageLog.id)).where(
            UsageLog.api_key_prefix == api_key_prefix,
            UsageLog.timestamp >= since,
        )
    )).scalar() or 0

    by_endpoint_rows = (await session.execute(
        select(UsageLog.endpoint, func.count(UsageLog.id).label("count"))
        .where(
            UsageLog.api_key_prefix == api_key_prefix,
            UsageLog.timestamp >= since,
        )
        .group_by(UsageLog.endpoint)
    )).all()
    by_endpoint = {row.endpoint: row.count for row in by_endpoint_rows}

    by_status_rows = (await session.execute(
        select(UsageLog.status_code, func.count(UsageLog.id).label("count"))
        .where(
            UsageLog.api_key_prefix == api_key_prefix,
            UsageLog.timestamp >= since,
        )
        .group_by(UsageLog.status_code)
    )).all()
    by_status = {row.status_code: row.count for row in by_status_rows}

    avg_http_ms = (await session.execute(
        select(func.avg(UsageLog.duration_ms)).where(
            UsageLog.api_key_prefix == api_key_prefix,
            UsageLog.timestamp >= since,
        )
    )).scalar() or 0

    # ── Estimate LLM calls ───────────────────────────────────────────
    # Fast runs: the LLM is called 0 or 1 times per run depending on
    # rule confidence.  We don't currently log whether it was actually
    # called, so we approximate: if a fast run has an llm_result in its
    # serialized response, it used the LLM.  For simplicity, we count
    # fast runs as calling the LLM 0 times (most are rule-only) and
    # agentic runs as calling the LLM ~7 times average (per typical
    # ReAct trace in this project).
    estimated_llm_calls = agentic_runs * 7

    return {
        "api_key_prefix": api_key_prefix,
        "period_days": days,

        # NEW: truthful debug-run metrics
        "debug_runs": {
            "total": total_runs,
            "fast": fast_runs,
            "agentic": agentic_runs,
            "completed": completed_runs,
            "failed": failed_runs,
            "unique_models": unique_models,
            "fast_avg_ms": int(fast_avg_ms),
            "agentic_avg_ms": int(agentic_avg_ms),
        },

        # Estimated LLM / cost signals
        "llm_calls_estimated": estimated_llm_calls,
        "cache_hits": int(cache_entries),

        # Raw HTTP traffic (includes polls, health checks, etc.)
        "http_requests": {
            "total": total_http,
            "avg_duration_ms": int(avg_http_ms),
            "by_endpoint": by_endpoint,
            "by_status_code": by_status,
        },

        # ── Legacy fields (kept for backward compat) ─────────────────
        "total_requests": total_http,
        "avg_duration_ms": int(avg_http_ms),
        "by_endpoint": by_endpoint,
        "by_status_code": by_status,
    }


async def count_recent_requests(
    session: AsyncSession,
    api_key_prefix: str,
    since: datetime,
) -> int:
    """Count requests for a key since a given time.

    Used by daily quota enforcement.
    """
    q = select(func.count(UsageLog.id)).where(
        UsageLog.api_key_prefix == api_key_prefix,
        UsageLog.timestamp >= since,
    )
    return (await session.execute(q)).scalar() or 0


# ─────────────────────────────────────────────────────────────────────────────
# CACHE
# ─────────────────────────────────────────────────────────────────────────────

def compute_cache_key(
    manifest_path: str,
    run_results_path: str,
    model_name: str | None,
    mode: str,
) -> str:
    """Compute a deterministic cache key for a debug request.

    Why include the paths and not their contents:
      Hashing file contents would be more accurate but more expensive.
      For beta use, path+model+mode is good enough — if a user re-runs
      the exact same debug within the TTL, they get the cached answer.
    """
    payload = f"{manifest_path}|{run_results_path}|{model_name or ''}|{mode}"
    return hashlib.sha256(payload.encode()).hexdigest()


async def get_cached_result(
    session: AsyncSession,
    cache_key: str,
    ttl_seconds: int = 3600,
) -> dict | None:
    """Fetch a cached result if it exists and hasn't expired.

    Returns None if missing or expired.  Increments hit_count on hit.
    """
    cutoff = _utcnow() - timedelta(seconds=ttl_seconds)

    result = await session.execute(
        select(CacheEntry).where(
            CacheEntry.cache_key == cache_key,
            CacheEntry.created_at >= cutoff,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return None

    # Increment hit counter
    await session.execute(
        update(CacheEntry)
        .where(CacheEntry.cache_key == cache_key)
        .values(hit_count=CacheEntry.hit_count + 1)
    )

    return entry.result


async def set_cached_result(
    session: AsyncSession,
    cache_key: str,
    mode: JobMode,
    result: dict,
) -> None:
    """Store a result in the cache (overwrites any existing entry)."""
    # Upsert pattern: check if exists, update or insert
    existing = await session.execute(
        select(CacheEntry).where(CacheEntry.cache_key == cache_key)
    )
    entry = existing.scalar_one_or_none()

    if entry:
        await session.execute(
            update(CacheEntry)
            .where(CacheEntry.cache_key == cache_key)
            .values(result=result, created_at=_utcnow(), hit_count=0)
        )
    else:
        session.add(CacheEntry(
            cache_key=cache_key,
            mode=mode,
            result=result,
        ))
