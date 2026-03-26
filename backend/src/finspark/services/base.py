"""Generic async repository / service base."""

from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finspark.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseService(Generic[ModelT]):
    """Thin async CRUD wrapper around a SQLAlchemy model."""

    model: type[ModelT]

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, record_id: str) -> ModelT | None:
        return await self.db.get(self.model, record_id)

    async def list(self, *, limit: int = 50, offset: int = 0) -> list[ModelT]:
        result = await self.db.execute(
            select(self.model).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def create(self, **kwargs: Any) -> ModelT:
        instance = self.model(**kwargs)
        self.db.add(instance)
        await self.db.flush()
        await self.db.refresh(instance)
        return instance

    async def delete(self, record_id: str) -> bool:
        instance = await self.get(record_id)
        if instance is None:
            return False
        await self.db.delete(instance)
        await self.db.flush()
        return True
