"""
Async job execution — background task runners.

How this works:
  1. POST /api/v1/debug with mode=agentic creates a Job row (queued)
     and calls background_tasks.add_task(run_agentic_job, job_id)
  2. FastAPI sends the 202 response with the job_id
  3. AFTER the response is sent, FastAPI runs run_agentic_job in the
     background of the same worker process
  4. The background task uses its own DB session, fetches the job,
     runs the agent, writes the result back
  5. Client polls GET /api/v1/jobs/{id} to check status

Why a separate function (not inline in the route):
  - Route has access to Request/session but those scopes end when the
    response is sent.  Background tasks need their own.
  - Easier to test in isolation.
  - Cleaner error handling per job.

Production upgrade path:
  When you outgrow BackgroundTasks (multi-worker, multi-pod), swap this
  file for a Celery worker or SQS consumer.  The route code doesn't change.
"""

from __future__ import annotations

import asyncio
import traceback
from typing import Any

from app.core.logging import get_logger
from app.db.base import async_session_maker
from app.db import repository as repo
from app.db.models import JobMode

log = get_logger(__name__)


async def run_fast_job(job_id: str, request_data: dict) -> None:
    """Execute a fast-mode debug run and update the job row.

    Runs the LangGraph pipeline (sync code) inside a thread pool
    so the event loop stays responsive.
    """
    async with async_session_maker() as session:
        try:
            await repo.mark_job_running(session, job_id)
            await session.commit()

            # Run the sync pipeline in a worker thread
            result = await asyncio.to_thread(_execute_fast_sync, request_data)

            await repo.mark_job_completed(
                session,
                job_id,
                result=result,
                broken_model=result.get("broken_model"),
            )
            await session.commit()
            log.info("job_completed", job_id=job_id, mode="fast")

        except Exception as exc:
            tb = traceback.format_exc()
            log.error("job_failed", job_id=job_id, error=str(exc), traceback=tb)
            await repo.mark_job_failed(session, job_id, f"{exc}\n{tb[:1000]}")
            await session.commit()


async def run_agentic_job(job_id: str, request_data: dict) -> None:
    """Execute an agentic debug run and update the job row.

    The agent may take 15-30 seconds.  This function runs in the
    background (after the HTTP response is already sent), so the
    duration doesn't block the API.
    """
    async with async_session_maker() as session:
        try:
            await repo.mark_job_running(session, job_id)
            await session.commit()

            # Run the agent in a worker thread (sync code using Claude SDK)
            result = await asyncio.to_thread(_execute_agentic_sync, request_data)

            await repo.mark_job_completed(
                session,
                job_id,
                result=result,
                broken_model=_extract_broken_model(result),
            )
            await session.commit()
            log.info("job_completed", job_id=job_id, mode="agentic")

        except Exception as exc:
            tb = traceback.format_exc()
            log.error("job_failed", job_id=job_id, error=str(exc), traceback=tb)
            await repo.mark_job_failed(session, job_id, f"{exc}\n{tb[:1000]}")
            await session.commit()


# ── Sync executors (run inside asyncio.to_thread) ───────────────────────────

def _execute_fast_sync(request_data: dict) -> dict:
    """Run the fast LangGraph pipeline and return a JSON-safe result."""
    from app.graph.pipeline import run_graph

    state = run_graph(
        manifest_path=request_data["manifest_path"],
        run_results_path=request_data.get("run_results_path", ""),
        model_name=request_data.get("model_name"),
        use_llm=request_data.get("use_llm", True),
    )

    return _serialize_fast_state(state)


def _execute_agentic_sync(request_data: dict) -> dict:
    """Run the agentic pipeline and return a JSON-safe result.

    Also loads the failure context separately so we can return the
    raw broken SQL for the side-by-side diff in the UI.  The agent
    itself doesn't expose the raw SQL in its output.
    """
    from app.graph.agent import run_agent
    from app.dbt.manifest_loader import load_manifest
    from app.dbt.run_results_loader import load_run_results
    from app.dbt.model_resolver import resolve_model, resolve_failures

    result = run_agent(
        manifest_path=request_data["manifest_path"],
        run_results_path=request_data.get("run_results_path", ""),
        model_name=request_data.get("model_name"),
        extra_context=request_data.get("error_message", ""),
    )

    # Get the raw SQL for display purposes
    raw_sql = ""
    broken_model = request_data.get("model_name") or ""
    file_path = ""
    try:
        manifest = load_manifest(request_data["manifest_path"])
        ctx = None
        if request_data.get("run_results_path"):
            run_results = load_run_results(request_data["run_results_path"])
            if broken_model:
                ctx = resolve_model(manifest, run_results, broken_model)
            else:
                failures = resolve_failures(manifest, run_results)
                if failures:
                    ctx = failures[0]
                    broken_model = ctx.failed_model
        if ctx:
            raw_sql = ctx.raw_sql
            file_path = ctx.file_path
    except Exception:
        # Non-fatal — agent result is still useful without raw SQL
        pass

    return {
        "mode": "agentic",
        "broken_model": broken_model,
        "file_path": file_path,
        "raw_sql": raw_sql,
        "diagnosis": result["diagnosis"],
        "tools_used": result["tool_calls"],
        "errors": [],
    }


def _serialize_fast_state(state: dict) -> dict:
    """Convert a PipelineState (which contains dataclass objects) to JSON.

    The new LLM-first response includes analyzer_result as the primary
    diagnosis source.  rule_hits and llm_result are gone.
    """
    parsed_sql = state.get("parsed_sql")
    parsed_error = state.get("parsed_error")
    analyzer_result = state.get("analyzer_result")
    ctx = state.get("failure_context")

    raw_sql = ctx.raw_sql if ctx else ""
    compiled_sql = ctx.compiled_sql if ctx else None
    file_path = ctx.file_path if ctx else ""

    return {
        "mode": "fast",
        "broken_model": state.get("broken_model", "unknown"),
        "file_path": file_path,
        "raw_sql": raw_sql,
        "compiled_sql": compiled_sql,
        "parsed_sql": parsed_sql.to_dict() if parsed_sql else None,
        "parsed_error": parsed_error.to_dict() if parsed_error else None,
        "lineage": state.get("lineage", {}),
        "lineage_ascii": state.get("lineage_ascii", ""),
        "upstream_columns": state.get("upstream_columns", {}),
        "query_is_valid": state.get("query_is_valid", False),
        "corrected_sql": state.get("corrected_sql"),
        "analyzer_result": analyzer_result.to_dict() if analyzer_result else None,
        "errors": state.get("errors", []),
    }


def _extract_broken_model(agentic_result: dict) -> str | None:
    """Extract the broken model name from an agentic result for indexing."""
    # We now store broken_model directly in _execute_agentic_sync
    return agentic_result.get("broken_model") or None
