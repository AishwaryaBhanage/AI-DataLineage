"""
SQLAlchemy async engine and session management.

Why async:
  FastAPI is async. Sync SQL calls block the event loop and kill
  throughput. aiosqlite (dev) and asyncpg (prod) are both async drivers.

Why one global engine:
  SQLAlchemy's AsyncEngine manages a connection pool internally.
  Creating one per request would defeat the pool. One singleton,
  many sessions.

Why a session factory:
  Each request gets its own session via the get_session dependency.
  Sessions are cheap; connections are reused from the pool.

Migrating SQLite → Postgres later:
  Change DATABASE_URL in config.py from
    sqlite+aiosqlite:///./datalineage.db
  to
    postgresql+asyncpg://user:pass@host:5432/datalineage
  Install asyncpg in requirements.txt.  That's it.
"""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import DATABASE_URL, ENVIRONMENT
from app.core.logging import get_logger

log = get_logger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


# ── Engine (singleton) ───────────────────────────────────────────────────────

# echo=True in development prints every SQL query to stdout — useful for
# debugging but noisy in production.
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=(ENVIRONMENT == "development" and False),  # flip to True to debug
    pool_pre_ping=True,  # verify connections before using (handles stale conns)
    future=True,
)


# ── Session factory ──────────────────────────────────────────────────────────

# expire_on_commit=False keeps ORM objects usable after commit.
# Without it, accessing attributes after commit re-queries the DB.
async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a database session.

    Usage:
        @app.get("/things")
        async def list_things(session: AsyncSession = Depends(get_session)):
            result = await session.execute(select(Thing))
            return result.scalars().all()

    The session is closed automatically when the request finishes.
    On exception, the transaction is rolled back.
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Schema initialization ────────────────────────────────────────────────────

async def init_db() -> None:
    """Create all tables on startup.

    For a beta, create_all is fine.  For production later, use Alembic
    migrations so you can alter tables without losing data.
    """
    # Import models so their tables register with Base.metadata
    from app.db import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    log.info("db_initialized", url=DATABASE_URL)


async def close_db() -> None:
    """Dispose of the engine on shutdown.

    Without this, the event loop may warn about pending connections.
    """
    await engine.dispose()
    log.info("db_closed")
