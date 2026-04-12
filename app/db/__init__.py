"""
Database module — SQLAlchemy async layer.

Exports:
  - engine        : AsyncEngine singleton
  - get_session   : FastAPI dependency yielding a session
  - init_db       : Called on app startup to create tables

Usage in a route:
    @app.get("/things")
    async def list_things(session: AsyncSession = Depends(get_session)):
        return await repository.list_things(session)
"""

from app.db.base import engine, get_session, init_db, Base

__all__ = ["engine", "get_session", "init_db", "Base"]
