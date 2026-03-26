"""
Async database session factory.

Supports both SQLite (hackathon demo) and PostgreSQL (production) via a
single DATABASE_URL environment variable.  No code changes required when
switching dialects — only the URL prefix changes.

SQLite  : sqlite+aiosqlite:///./finspark_demo.db
Postgres: postgresql+asyncpg://user:pass@host/dbname

Session usage (FastAPI dependency):
    async def endpoint(db: AsyncSession = Depends(get_db)):
        result = await db.execute(select(Tenant))
        ...
"""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool

from app.db.models.base import Base  # noqa: F401 — ensures metadata is populated


def _build_engine_kwargs(database_url: str) -> dict[str, Any]:
    """
    Return engine kwargs tuned for the target dialect.

    SQLite quirks that must be handled:
    - StaticPool + check_same_thread=False for single-file in-process use
    - PRAGMA foreign_keys=ON (disabled by default in SQLite)
    - WAL mode for concurrent reads during tests
    """
    if database_url.startswith("sqlite"):
        return {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
    # PostgreSQL / asyncpg
    return {
        "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }


def create_engine(database_url: str | None = None) -> AsyncEngine:
    url = database_url or os.environ.get(
        "DATABASE_URL", "sqlite+aiosqlite:///./finspark_demo.db"
    )
    kwargs = _build_engine_kwargs(url)
    engine = create_async_engine(url, echo=os.getenv("DB_ECHO", "0") == "1", **kwargs)

    # Enable SQLite foreign keys and WAL mode on every new connection
    if url.startswith("sqlite"):
        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragmas(dbapi_conn: Any, _conn_record: Any) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


# Module-level singletons — re-used across the process lifetime
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a session and commits/rolls back."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all_tables() -> None:
    """
    Dev/test utility: create all tables directly from ORM metadata.
    Do NOT call this in production — use Alembic migrations.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_all_tables() -> None:
    """Wipe all tables — test teardown only."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
