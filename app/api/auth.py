"""
API authentication — Bearer token verification.

Why this exists:
  Without authentication, anyone who finds your API URL gets free
  Claude calls on your dime.  This module enforces that every request
  to /api/v1/* carries a valid bearer token in the Authorization header.

How it works:
  1. Each beta tester is given a unique key from API_KEYS env var
  2. Client sends:  Authorization: Bearer dl_test_abc123
  3. The dependency extracts the token, looks it up in the allowed list
  4. Valid token → request proceeds, key is attached to request state
  5. Invalid token → 401 Unauthorized

Why bearer tokens (not basic auth):
  - Industry standard
  - Easy to rotate per user (just regenerate one key)
  - Easy to attribute usage (logs include the key prefix)
  - No password to leak

Future upgrades:
  - Move keys to a database (when you have >50 users)
  - Add per-key rate limits and quotas
  - Add expiry dates per key
  - Add scopes (read-only vs full access)
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import API_KEYS, REQUIRE_API_KEY


# auto_error=False so we can return our own error messages
_bearer_scheme = HTTPBearer(auto_error=False)


def verify_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """FastAPI dependency that verifies the Authorization: Bearer header.

    Returns:
        The validated API key (stored on request.state.api_key for logging)

    Raises:
        HTTPException 401 if the key is missing or invalid
    """
    # Bypass auth in dev mode (REQUIRE_API_KEY=false)
    if not REQUIRE_API_KEY:
        request.state.api_key = "dev-bypass"
        return "dev-bypass"

    # Check header is present
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Send: Authorization: Bearer <api_key>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check scheme is Bearer
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid auth scheme '{credentials.scheme}'. Use: Bearer <api_key>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # No keys configured = misconfiguration, fail closed
    if not API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is not configured on the server.",
        )

    # Check token is in allow-list
    token = credentials.credentials
    if token not in API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Attach to request state so logging middleware can record it
    # (we only log the prefix, never the full key)
    request.state.api_key = token
    return token


def get_key_prefix(api_key: str) -> str:
    """Return a safe-to-log prefix of the API key.

    Example: "dl_test_abc123xyz" -> "dl_test_abc..."
    """
    if not api_key or len(api_key) < 8:
        return "***"
    return api_key[:10] + "..."
