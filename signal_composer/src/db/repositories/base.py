"""Base repository with common CRUD operations."""

from typing import TypeVar, Generic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """Generic repository with common CRUD operations."""

    def __init__(self, session: AsyncSession, model_class: type[T]):
        """Initialize repository with session and model class."""
        self.session = session
        self.model_class = model_class

    async def create(self, obj: T) -> T:
        """Create a new entity."""
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def get_by_id(self, id: int) -> T | None:
        """Get entity by ID."""
        return await self.session.get(self.model_class, id)

    async def delete(self, id: int) -> bool:
        """Delete entity by ID. Returns True if deleted."""
        obj = await self.get_by_id(id)
        if obj:
            await self.session.delete(obj)
            await self.session.flush()
            return True
        return False

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[T]:
        """List all entities with pagination."""
        stmt = select(self.model_class).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
