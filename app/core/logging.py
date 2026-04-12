"""
Structured logging configuration.

Why structlog instead of plain logging:
  - Every log line is a structured key/value pair (rendered as JSON in prod)
  - You can attach context to a logger and it stays attached for nested calls
  - CloudWatch / Datadog / Grafana can index the structured fields
  - Easier to search ("find all 500 errors for user X yesterday")

Format depends on environment:
  - development: human-readable, color-coded console output
  - production:  one-line JSON per event for log aggregators

Usage:
    from app.core.logging import get_logger
    log = get_logger(__name__)

    log.info("user_action", user_id=123, action="debug", duration_ms=47)
    log.error("api_call_failed", endpoint="/debug", error=str(exc), exc_info=True)
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import ENVIRONMENT, LOG_LEVEL


def configure_logging() -> None:
    """Configure structlog and stdlib logging.

    Call once at application startup (in main.py).
    """
    log_level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)

    # Configure stdlib logging — structlog routes through this
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Tame noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)

    # Choose renderer based on environment
    if ENVIRONMENT == "production":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Get a structured logger.

    Args:
        name: Logger name (typically __name__)
    """
    return structlog.get_logger(name)
