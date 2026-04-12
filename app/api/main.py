"""
DataLineage AI — FastAPI application entry point.

Wires together:
  - v1 router (authenticated endpoints under /api/v1/*)
  - public router (/api/v1/health — no auth)
  - Root /health endpoint for load balancers
  - CORS middleware (locked down via env var in prod)
  - Rate limiting (slowapi)
  - Structured logging middleware
  - Global exception handler
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import (
    CORS_ORIGINS,
    ENVIRONMENT,
    MAX_REQUEST_SIZE_MB,
)
from app.core.logging import configure_logging, get_logger
from app.api.v1 import router as v1_router, public_router as v1_public_router
from app.api.rate_limit import limiter, _rate_limit_exceeded_handler

# Configure structured logging once on startup
configure_logging()
log = get_logger(__name__)

app = FastAPI(
    title="DataLineage AI",
    version="1.0.0",
    description="AI-powered dbt/SQL pipeline debugger",
    docs_url="/docs" if ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if ENVIRONMENT != "production" else None,
)

# ── Rate limiting (slowapi) ──────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(429, _rate_limit_exceeded_handler)

# ── CORS ─────────────────────────────────────────────────────────────────────
# In dev: CORS_ORIGINS=*  (matches everything)
# In prod: CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=False,
)


# ── Request size limit middleware ────────────────────────────────────────────
@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    """Reject requests larger than MAX_REQUEST_SIZE_MB.

    Why: stops malicious or buggy clients from uploading 500MB manifests
    that would OOM the worker.
    """
    max_bytes = MAX_REQUEST_SIZE_MB * 1024 * 1024
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > max_bytes:
        return JSONResponse(
            status_code=413,
            content={
                "error": "request_too_large",
                "detail": f"Request body exceeds {MAX_REQUEST_SIZE_MB}MB limit",
            },
        )
    return await call_next(request)


# ── Request logging middleware ───────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every request with a unique ID, status code, and duration.

    Also writes a row to the usage_log table for authenticated requests
    so we can show per-key usage stats later.
    """
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    start = time.time()

    log.info(
        "request_start",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        client=request.client.host if request.client else "unknown",
    )

    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = int((time.time() - start) * 1000)
        log.error(
            "request_failed",
            request_id=request_id,
            duration_ms=duration_ms,
            error=str(exc),
            exc_info=True,
        )
        raise

    duration_ms = int((time.time() - start) * 1000)
    api_key = getattr(request.state, "api_key", None)
    from app.api.auth import get_key_prefix
    key_prefix = get_key_prefix(api_key) if api_key else None

    log.info(
        "request_end",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
        api_key=key_prefix,
    )

    # Persist to usage_log for authenticated requests to v1 endpoints.
    # Fire and forget — never let DB errors kill a response.
    if api_key and api_key != "dev-bypass" and request.url.path.startswith("/api/v1/"):
        try:
            from app.db.base import async_session_maker
            from app.db import repository as repo
            async with async_session_maker() as log_session:
                await repo.log_request(
                    session=log_session,
                    api_key_prefix=key_prefix,
                    endpoint=request.url.path,
                    method=request.method,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )
                await log_session.commit()
        except Exception as db_exc:
            log.warning("usage_log_failed", error=str(db_exc))

    response.headers["X-Request-ID"] = request_id
    return response


# ── Global exception handler ─────────────────────────────────────────────────
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all for unexpected errors.

    Why: a bare exception traceback is a security issue (leaks file paths,
    library versions, internal logic).  We log the full trace internally
    and return a safe generic message.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    log.error(
        "unhandled_exception",
        request_id=request_id,
        path=request.url.path,
        error=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "detail": "An unexpected error occurred. Please try again.",
            "request_id": request_id,
        },
    )


# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(v1_public_router)   # /api/v1/health (no auth)
app.include_router(v1_router)           # /api/v1/* (auth required)


# ── Root health endpoint (unauthenticated, for load balancers) ──────────────

@app.get("/health")
def root_health():
    """Simple health endpoint at the root path for monitoring tools.

    The full health check with dependency verification is at /api/v1/health.
    """
    return {"status": "ok", "version": "1.0.0", "environment": ENVIRONMENT}


@app.on_event("startup")
async def startup():
    from app.db import init_db
    await init_db()
    log.info(
        "api_startup",
        environment=ENVIRONMENT,
        cors_origins=CORS_ORIGINS,
        version="1.0.0",
    )


@app.on_event("shutdown")
async def shutdown():
    from app.db.base import close_db
    await close_db()
    log.info("api_shutdown")


# ─────────────────────────────────────────────────────────────────────────────
# Serve the React frontend (must be LAST so API routes above win)
# ─────────────────────────────────────────────────────────────────────────────
#
# When the Docker image is built, the frontend-builder stage produces
# frontend/dist/.  In production this directory exists and we serve it.
# In local dev, the frontend is served by Vite on port 5173 instead,
# so this code path is skipped.

_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.exists():
    log.info("mounting_frontend", path=str(_FRONTEND_DIST))

    # Serve static assets (JS, CSS, images, etc.) from /assets
    app.mount(
        "/assets",
        StaticFiles(directory=_FRONTEND_DIST / "assets"),
        name="assets",
    )

    # Specific static files at root
    @app.get("/favicon.svg", include_in_schema=False)
    async def favicon():
        return FileResponse(_FRONTEND_DIST / "favicon.svg")

    # SPA catch-all: any non-API route falls through to index.html so
    # React Router can handle client-side routing (/, /jobs, /settings, etc.)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # Don't intercept API routes — they're registered above and should
        # have matched already if they exist.  But as a safety net:
        if full_path.startswith("api/") or full_path.startswith("health"):
            return JSONResponse(
                status_code=404,
                content={"error": "not_found", "detail": f"/{full_path} not found"},
            )
        # Everything else → index.html (React handles the route)
        return FileResponse(_FRONTEND_DIST / "index.html")
else:
    log.info("frontend_dist_not_found", path=str(_FRONTEND_DIST),
             note="Running backend-only mode (dev). Frontend will run separately.")
