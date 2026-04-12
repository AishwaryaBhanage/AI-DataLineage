"""
Rate limiting via slowapi.

Why per-API-key (not per-IP):
  - Multiple users behind a corporate NAT share one IP — per-IP would
    over-block legitimate users
  - The whole point of issuing API keys is so we can attribute usage

Limits (configurable in config.py):
  - Fast mode:    10 requests/min  (cheap, deterministic)
  - Agentic mode:  3 requests/min  (expensive, calls Claude many times)
  - Anonymous:     5 requests/min  (when REQUIRE_API_KEY=false in dev)

How it works:
  - Key function returns the API key (or IP if no key) for tracking
  - @limiter.limit("X/minute") decorator applies the limit
  - On exceed: 429 Too Many Requests with Retry-After header

In production behind a load balancer, slowapi reads X-Forwarded-For
to get the real client IP.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import RATE_LIMIT_FAST, RATE_LIMIT_AGENTIC


def _key_func(request: Request) -> str:
    """Identify the client for rate limiting.

    Prefers the API key (set by verify_api_key dependency), falls back
    to IP address if no key was provided.
    """
    api_key = getattr(request.state, "api_key", None)
    if api_key and api_key != "dev-bypass":
        return f"key:{api_key}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=_key_func, default_limits=["60/minute"])


def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom 429 response with a clear error message."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "detail": f"Too many requests. Limit: {exc.detail}. Try again shortly.",
        },
        headers={"Retry-After": "60"},
    )


# Limit decorator strings (used in v1.py)
LIMIT_FAST = RATE_LIMIT_FAST
LIMIT_AGENTIC = RATE_LIMIT_AGENTIC
