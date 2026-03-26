"""
Shared base classes, mixins, and the JSON/JSONB type shim.

Design choices:
- JSONBType: uses JSONB on PostgreSQL, JSON on SQLite/others. Single
  import throughout models — no dialect switching at callsites.
- TimestampMixin: server-side defaults so they survive bulk INSERTs that
  bypass the ORM.
- SoftDeleteMixin: adds deleted_at + is_deleted; never hard-deletes rows.
  Callers must filter on is_deleted=False; a SessionFactory wrapper can
  inject this automatically via query events.
- UUIDPk: UUIDs as primary keys for tenant-safe portability. SQLite stores
  them as 36-char strings; PostgreSQL uses the native UUID type.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedColumn, mapped_column
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.types import JSON, TypeDecorator


# ---------------------------------------------------------------------------
# Dialect-adaptive JSONB shim
# ---------------------------------------------------------------------------

class JSONBType(TypeDecorator[dict[str, Any]]):
    """
    Uses PostgreSQL JSONB when the dialect supports it, falls back to JSON
    (SQLite, MySQL).  JSONB gives GIN-indexable, operator-rich storage in
    production; JSON is structurally equivalent for the hackathon demo.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        return value

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        return value


# ---------------------------------------------------------------------------
# Declarative base with async attributes
# ---------------------------------------------------------------------------

class Base(AsyncAttrs, DeclarativeBase):
    """
    Project-wide declarative base.

    AsyncAttrs enables `await obj.awaitable_attrs.<relationship>` without
    explicit selectinload on every query.
    """

    # Annotated type → Column type registry (used by mapped_column inference)
    type_annotation_map: dict[Any, Any] = {
        dict[str, Any]: JSONBType(),
    }


# ---------------------------------------------------------------------------
# Reusable mixins
# ---------------------------------------------------------------------------

class TimestampMixin:
    """Adds created_at / updated_at with server-side defaults."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """
    Soft-delete pattern.

    deleted_at is the canonical source of truth; is_deleted is a
    generated-looking boolean kept in sync by ORM events for index
    friendliness (partial indexes in PostgreSQL, plain index in SQLite).
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        index=True,
    )

    def soft_delete(self) -> None:
        self.deleted_at = datetime.utcnow()
        self.is_deleted = True

    def restore(self) -> None:
        self.deleted_at = None
        self.is_deleted = False


# ---------------------------------------------------------------------------
# Primary key helper
# ---------------------------------------------------------------------------

def uuid_pk() -> MappedColumn[str]:
    """
    32-char hex UUID primary key.

    Stored as VARCHAR(32) (no hyphens) for efficient indexing on both
    SQLite and PostgreSQL.  Swap to sa.UUID(as_uuid=True) if you move
    to PostgreSQL-only and want the native type.
    """
    return mapped_column(
        String(32),
        primary_key=True,
        default=lambda: uuid.uuid4().hex,
        nullable=False,
    )
