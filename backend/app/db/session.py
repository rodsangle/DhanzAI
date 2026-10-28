from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def make_engine(database_url: str) -> AsyncEngine:
    kwargs: dict = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
    engine = create_async_engine(database_url, **kwargs)
    if database_url.startswith("sqlite"):
        # SQLite ignores ON DELETE CASCADE unless foreign keys are switched on per connection.
        @event.listens_for(engine.sync_engine, "connect")
        def _fk_on(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
