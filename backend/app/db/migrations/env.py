"""
Alembic env.py — supports both sync (offline) and async (online) migration modes.

Key behaviours:
1. DATABASE_URL env var overrides alembic.ini's sqlalchemy.url.
2. Online mode uses async_engine_from_config (asyncpg / aiosqlite).
3. compare_type=True ensures column type changes are detected on autogenerate.
4. render_as_batch=True is required for SQLite ALTER TABLE emulation.
5. include_schemas=False — single-schema deployment; adjust for multi-schema.

PostgreSQL production tips (applied in migration files, not here):
- Add postgresql_where on partial indexes for soft-delete patterns.
- Use postgresql_using="gin" on JSONB columns for GIN indexes.
- Declare audit_logs as PARTITION BY RANGE (created_at).
"""
from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ---------------------------------------------------------------------------
# Load all models so autogenerate can see every table
# ---------------------------------------------------------------------------
from app.db.models import Base  # noqa: F401 — registers all metadata

# ---------------------------------------------------------------------------
# Alembic Config object — gives access to alembic.ini values
# ---------------------------------------------------------------------------
config = context.config

# Wire up Python logging from the config file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate comparison
target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Override DATABASE_URL from environment (never commit credentials to ini)
# ---------------------------------------------------------------------------
_db_url = os.environ.get("DATABASE_URL")
if _db_url:
    config.set_main_option("sqlalchemy.url", _db_url)


# ---------------------------------------------------------------------------
# Offline mode — generate SQL scripts without a live connection
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    """
    Emit migration SQL to stdout.
    Useful for: reviewing changes, DBAs applying migrations manually.

    Usage:
        DATABASE_URL=postgresql+asyncpg://... alembic upgrade head --sql
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_as_batch=True,  # required for SQLite
        include_schemas=False,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode — connect and run migrations
# ---------------------------------------------------------------------------
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        render_as_batch=True,  # required for SQLite; harmless on PostgreSQL
        include_schemas=False,
        # Exclude Alembic's own version table from autogenerate diff
        include_object=_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def _include_object(
    obj: object, name: str, type_: str, reflected: bool, compare_to: object
) -> bool:
    """
    Filter objects for autogenerate.

    Excludes:
    - temp_ prefixed tables (scratch tables)
    - alembic_version itself
    """
    if type_ == "table":
        if name.startswith("temp_"):
            return False
        if name == "alembic_version":
            return False
    return True


async def run_async_migrations() -> None:
    """
    Create an async engine and run migrations inside a sync shim.

    async_engine_from_config reads sqlalchemy.url from alembic config
    (which may have been overridden by DATABASE_URL above).
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # NullPool: no persistent connections in migration runner
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
