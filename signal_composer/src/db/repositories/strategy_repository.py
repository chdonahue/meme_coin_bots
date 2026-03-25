"""Strategy repository."""

from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Strategy
from .base import BaseRepository


class StrategyRepository(BaseRepository[Strategy]):
    """Repository for Strategy operations."""

    def __init__(self, session: AsyncSession):
        """Initialize with session."""
        super().__init__(session, Strategy)

    async def get_by_external_id(self, external_id: str) -> Strategy | None:
        """Get strategy by external ID."""
        stmt = select(Strategy).where(Strategy.external_id == external_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: int, limit: int = 100, offset: int = 0) -> list[Strategy]:
        """List strategies created by a user."""
        stmt = (
            select(Strategy)
            .where(Strategy.creator_id == user_id)
            .order_by(Strategy.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_public(self, limit: int = 100, offset: int = 0) -> list[Strategy]:
        """List public strategies."""
        stmt = (
            select(Strategy)
            .where(Strategy.is_public == True)
            .where(Strategy.status == "active")
            .order_by(Strategy.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def save_dsl(self, strategy_id: int, dsl_json: dict[str, Any]) -> Strategy:
        """Update strategy DSL JSON."""
        strategy = await self.get_by_id(strategy_id)
        if not strategy:
            raise ValueError(f"Strategy {strategy_id} not found")

        strategy.dsl_json = dsl_json
        await self.session.flush()
        await self.session.refresh(strategy)
        return strategy
