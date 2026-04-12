"""
API v1 routes — the public interface for DataLineage AI.

Endpoints:
  GET  /api/v1/health          Health check + capabilities (PUBLIC)
  POST /api/v1/debug           Main debug endpoint
                               - fast mode: runs inline, returns full result
                               - agentic mode: returns 202 + job_id (poll /jobs/{id})
  POST /api/v1/debug/cloud     Convenience: debug from dbt Cloud artifacts
  GET  /api/v1/models          List all models in a manifest
  GET  /api/v1/jobs/{job_id}   Poll status of an agentic job
  GET  /api/v1/jobs            List recent jobs for the caller's API key
  GET  /api/v1/usage           Usage stats for the caller's API key
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    DebugRequest,
    DebugMode,
    ArtifactSource,
    HealthResponse,
    FastDebugResponse,
    AgenticDebugResponse,
    AnalyzerResultResponse,
    ParsedSQLResponse,
    ParsedErrorResponse,
    ErrorResponse,
)
from app.api.auth import verify_api_key, get_key_prefix
from app.api.rate_limit import limiter, LIMIT_FAST, LIMIT_AGENTIC
from app.api.jobs import run_fast_job, run_agentic_job
from app.core.config import (
    MANIFEST_PATH,
    DBT_CLOUD_API_TOKEN,
    DBT_CLOUD_ACCOUNT_ID,
    DBT_CLOUD_BASE_URL,
    CACHE_TTL_SECONDS,
    DAILY_QUOTA_PER_KEY,
)
from app.core.logging import get_logger
from app.db import get_session
from app.db import repository as repo
from app.db.models import JobMode, JobStatus

log = get_logger(__name__)

# All endpoints under this router require a valid API key.
router = APIRouter(
    prefix="/api/v1",
    tags=["v1"],
    dependencies=[Depends(verify_api_key)],
)

# Public router for endpoints that should NOT require auth (just /health).
public_router = APIRouter(prefix="/api/v1", tags=["v1-public"])


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/health  (PUBLIC)
# ─────────────────────────────────────────────────────────────────────────────

@public_router.get("/health", response_model=HealthResponse)
def health():
    """Health check with dependency verification.

    Verifies:
      - Anthropic API key is configured
      - File system writable
      - Core modules importable

    Intentionally unauthenticated for load balancers and monitoring.
    """
    from app.core.config import ANTHROPIC_API_KEY, ENVIRONMENT
    import tempfile

    checks = {}
    checks["anthropic_key_configured"] = bool(
        ANTHROPIC_API_KEY and ANTHROPIC_API_KEY != "your_api_key_here"
    )

    try:
        with tempfile.NamedTemporaryFile(delete=True) as f:
            f.write(b"healthcheck")
        checks["filesystem_writable"] = True
    except Exception:
        checks["filesystem_writable"] = False

    try:
        import sqlglot, networkx, anthropic, langgraph  # noqa
        checks["core_modules_loaded"] = True
    except ImportError:
        checks["core_modules_loaded"] = False

    overall = "ok" if all(checks.values()) else "degraded"

    return HealthResponse(
        status=overall,
        environment=ENVIRONMENT,
        checks=checks,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/debug
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/debug")
@limiter.limit(LIMIT_FAST)
async def debug(
    request: Request,
    req: DebugRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Main debug endpoint.

    - **fast mode**: runs inline (~1-3s), returns full result immediately.
      Cached by (manifest + run_results + model + mode) hash for 1 hour.
    - **agentic mode**: creates a job, returns 202 + job_id. Poll
      GET /api/v1/jobs/{job_id} to retrieve the result. Typical duration
      is 15-30 seconds.

    Rate limits: 10/min fast, 3/min agentic (per API key).
    Daily quota: if DAILY_QUOTA_PER_KEY is set, enforced per key.
    """
    api_key = request.state.api_key
    prefix = get_key_prefix(api_key)

    log.info(
        "debug_request",
        request_id=getattr(request.state, "request_id", None),
        api_key=prefix,
        mode=req.mode.value,
        source=req.source.value,
        model_name=req.model_name,
    )

    # ── Daily quota check ────────────────────────────────────────────
    if DAILY_QUOTA_PER_KEY > 0:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        count = await repo.count_recent_requests(session, prefix, since)
        if count >= DAILY_QUOTA_PER_KEY:
            raise HTTPException(
                429,
                f"Daily quota exceeded ({DAILY_QUOTA_PER_KEY} requests/day). "
                "Try again tomorrow or contact support for a higher limit.",
            )

    # ── Resolve artifact paths ───────────────────────────────────────
    manifest_path, run_results_path = _resolve_artifacts(req)

    # ── Check cache ──────────────────────────────────────────────────
    cache_key = repo.compute_cache_key(
        manifest_path=manifest_path,
        run_results_path=run_results_path,
        model_name=req.model_name,
        mode=req.mode.value,
    )

    cached = await repo.get_cached_result(
        session, cache_key, ttl_seconds=CACHE_TTL_SECONDS
    )
    if cached is not None:
        log.info("cache_hit", api_key=prefix, cache_key=cache_key[:16])
        return {
            **cached,
            "cached": True,
        }

    # ── Route to the right pipeline ──────────────────────────────────
    request_data = {
        "manifest_path": manifest_path,
        "run_results_path": run_results_path,
        "model_name": req.model_name,
        "use_llm": req.use_llm,
        "error_message": req.error_message,
    }

    if req.mode == DebugMode.FAST:
        return await _handle_fast(
            req, request_data, cache_key, prefix, session
        )
    else:
        return await _handle_agentic(
            req, request_data, cache_key, prefix, session, background_tasks
        )


async def _handle_fast(
    req: DebugRequest,
    request_data: dict,
    cache_key: str,
    api_key_prefix: str,
    session: AsyncSession,
) -> dict:
    """Run fast-mode debug inline, cache the result."""
    import asyncio
    from app.api.jobs import _execute_fast_sync

    # Create a job row for audit/history (even for sync runs)
    job = await repo.create_job(
        session=session,
        api_key_prefix=api_key_prefix,
        mode=JobMode.FAST,
        request_body=request_data,
        cache_key=cache_key,
    )
    job_id = job.id

    await repo.mark_job_running(session, job_id)

    try:
        # Run in a thread to keep the event loop responsive
        result = await asyncio.to_thread(_execute_fast_sync, request_data)
    except Exception as exc:
        await repo.mark_job_failed(session, job_id, str(exc))
        log.error("fast_job_failed", job_id=job_id, error=str(exc))
        raise HTTPException(500, f"Debug pipeline error: {exc}")

    await repo.mark_job_completed(
        session,
        job_id,
        result=result,
        broken_model=result.get("broken_model"),
    )

    # Cache the result
    await repo.set_cached_result(session, cache_key, JobMode.FAST, result)

    return {
        **result,
        "job_id": job_id,
        "cached": False,
    }


async def _handle_agentic(
    req: DebugRequest,
    request_data: dict,
    cache_key: str,
    api_key_prefix: str,
    session: AsyncSession,
    background_tasks: BackgroundTasks,
) -> dict:
    """Queue an agentic job and return 202 + job_id."""
    job = await repo.create_job(
        session=session,
        api_key_prefix=api_key_prefix,
        mode=JobMode.AGENTIC,
        request_body=request_data,
        cache_key=cache_key,
    )
    job_id = job.id

    # Commit immediately so the background task can read it
    await session.commit()

    # Schedule the background task to run after the response is sent
    background_tasks.add_task(run_agentic_job, job_id, request_data)

    log.info("agentic_job_queued", job_id=job_id, api_key=api_key_prefix)

    return {
        "status": "accepted",
        "job_id": job_id,
        "mode": "agentic",
        "poll_url": f"/api/v1/jobs/{job_id}",
        "message": (
            "Agentic mode runs asynchronously. Poll the poll_url to check "
            "status. Typical completion time: 15-30 seconds."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/jobs/{job_id}
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}")
async def get_job_status(
    request: Request,
    job_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Poll the status of a job.

    Callers can only access jobs created with their own API key.
    """
    api_key = request.state.api_key
    prefix = get_key_prefix(api_key)

    job = await repo.get_job(session, job_id)
    if job is None:
        raise HTTPException(404, f"Job {job_id} not found")

    # Ownership check: prevent one user from reading another user's job
    if job.api_key_prefix != prefix:
        raise HTTPException(404, f"Job {job_id} not found")

    return job.to_dict()


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/jobs
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/jobs")
@limiter.limit("30/minute")
async def list_jobs(
    request: Request,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
):
    """List recent jobs for the caller's API key.  Most recent first."""
    api_key = request.state.api_key
    prefix = get_key_prefix(api_key)

    limit = min(max(1, limit), 100)
    jobs = await repo.list_jobs_for_key(session, prefix, limit=limit)

    return {
        "count": len(jobs),
        "jobs": [j.to_dict() for j in jobs],
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/usage
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/usage")
@limiter.limit("30/minute")
async def get_usage(
    request: Request,
    days: int = 7,
    session: AsyncSession = Depends(get_session),
):
    """Usage statistics for the caller's API key over the last N days."""
    api_key = request.state.api_key
    prefix = get_key_prefix(api_key)

    days = min(max(1, days), 90)
    stats = await repo.get_usage_stats(session, prefix, days=days)

    if DAILY_QUOTA_PER_KEY > 0:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        today_count = await repo.count_recent_requests(session, prefix, since)
        stats["daily_quota"] = DAILY_QUOTA_PER_KEY
        stats["requests_today"] = today_count
        stats["quota_remaining"] = max(0, DAILY_QUOTA_PER_KEY - today_count)

    return stats


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/debug/cloud
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/debug/cloud")
@limiter.limit(LIMIT_FAST)
async def debug_cloud(
    request: Request,
    background_tasks: BackgroundTasks,
    run_id: str = "",
    job_id: str = "",
    model_name: str | None = None,
    mode: DebugMode = DebugMode.FAST,
    session: AsyncSession = Depends(get_session),
):
    """Convenience endpoint: debug directly from dbt Cloud.

    Uses server-configured dbt Cloud credentials from .env.
    """
    if not run_id and not job_id:
        raise HTTPException(400, "Provide either run_id or job_id")

    req = DebugRequest(
        source=ArtifactSource.CLOUD,
        dbt_cloud_token=DBT_CLOUD_API_TOKEN,
        dbt_cloud_account_id=DBT_CLOUD_ACCOUNT_ID,
        dbt_cloud_run_id=run_id or None,
        dbt_cloud_job_id=job_id or None,
        model_name=model_name,
        mode=mode,
    )

    # Delegate to the main debug handler
    return await debug(request, req, background_tasks, session)


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/v1/models
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/models")
@limiter.limit("30/minute")
def list_models(request: Request, manifest_path: str = ""):
    """List all models in a dbt project."""
    path = manifest_path or MANIFEST_PATH
    try:
        from app.dbt.manifest_loader import load_manifest
        manifest = load_manifest(path)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(400, str(e))

    models = []
    for name in manifest.all_model_names():
        m = manifest.get_model(name)
        models.append({
            "name": m.name,
            "file_path": m.file_path,
            "materialized": m.materialized,
            "upstream": manifest.get_upstream(name),
            "downstream": manifest.get_downstream(name),
        })

    return {
        "project": manifest.metadata.project_name,
        "adapter": manifest.metadata.adapter_type,
        "total_models": len(models),
        "models": models,
    }


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/v1/upload
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/upload")
@limiter.limit("10/minute")
async def upload_artifacts(
    request: Request,
    manifest: UploadFile = File(..., description="dbt manifest.json"),
    run_results: Optional[UploadFile] = File(
        None, description="dbt run_results.json (optional)"
    ),
):
    """Upload dbt artifacts from the user's local machine.

    Saves the uploaded files to a temp directory and returns the paths.
    The client then passes these paths to POST /api/v1/debug.

    Why not combine upload + debug into one endpoint?
      - Keeps the multipart upload separate from the JSON debug request
      - Lets users retry the debug without re-uploading
      - The backend can cache / reuse uploads by filename hash
    """
    import os
    import tempfile
    import json as _json

    # Basic validation — manifest.json must be valid JSON
    manifest_bytes = await manifest.read()
    if not manifest_bytes:
        raise HTTPException(400, "manifest file is empty")
    try:
        _json.loads(manifest_bytes)
    except _json.JSONDecodeError as e:
        raise HTTPException(400, f"manifest.json is not valid JSON: {e}")

    # Create a unique temp dir per upload.  We don't clean these up
    # automatically — OS handles it on reboot.  For long-running prod
    # we'd add a cron to clean old entries.
    tmp_dir = tempfile.mkdtemp(prefix="dl_upload_")
    manifest_path = os.path.join(tmp_dir, "manifest.json")
    with open(manifest_path, "wb") as f:
        f.write(manifest_bytes)

    run_results_path: str | None = None
    if run_results is not None:
        rr_bytes = await run_results.read()
        if rr_bytes:
            try:
                _json.loads(rr_bytes)
            except _json.JSONDecodeError as e:
                raise HTTPException(
                    400, f"run_results.json is not valid JSON: {e}"
                )
            run_results_path = os.path.join(tmp_dir, "run_results.json")
            with open(run_results_path, "wb") as f:
                f.write(rr_bytes)

    log.info(
        "files_uploaded",
        request_id=getattr(request.state, "request_id", None),
        tmp_dir=tmp_dir,
        manifest_bytes=len(manifest_bytes),
        has_run_results=run_results_path is not None,
    )

    return {
        "upload_id": os.path.basename(tmp_dir),
        "manifest_path": manifest_path,
        "run_results_path": run_results_path or "",
        "bytes": {
            "manifest": len(manifest_bytes),
            "run_results": len(rr_bytes) if run_results is not None else 0,
        },
    }


# ── Private helpers ──────────────────────────────────────────────────────────

def _resolve_artifacts(req: DebugRequest) -> tuple[str, str]:
    """Resolve manifest/run_results paths from either local files or dbt Cloud."""

    if req.source == ArtifactSource.LOCAL:
        manifest_path = req.manifest_path or MANIFEST_PATH
        run_results_path = req.run_results_path or ""
        return manifest_path, run_results_path

    # ── dbt Cloud ────────────────────────────────────────────────────
    from app.dbt.cloud_client import DbtCloudClient

    token = req.dbt_cloud_token or DBT_CLOUD_API_TOKEN
    account_id = req.dbt_cloud_account_id or DBT_CLOUD_ACCOUNT_ID

    if not token or not account_id:
        raise HTTPException(
            400,
            "dbt Cloud credentials required. Provide dbt_cloud_token and "
            "dbt_cloud_account_id in the request, or set DBT_CLOUD_API_TOKEN "
            "and DBT_CLOUD_ACCOUNT_ID in .env",
        )

    client = None
    try:
        client = DbtCloudClient(
            api_token=token,
            account_id=account_id,
            base_url=DBT_CLOUD_BASE_URL,
        )

        if req.dbt_cloud_run_id:
            paths = client.fetch_artifacts(run_id=req.dbt_cloud_run_id)
        elif req.dbt_cloud_job_id:
            paths = client.fetch_latest_artifacts(job_id=req.dbt_cloud_job_id)
        else:
            raise HTTPException(400, "Provide either dbt_cloud_run_id or dbt_cloud_job_id")

        return paths.manifest_path, paths.run_results_path
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"dbt Cloud API error: {e}")
    finally:
        if client:
            client.close()
