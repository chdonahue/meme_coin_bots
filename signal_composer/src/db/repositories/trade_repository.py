"""Trade repository."""

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PaperTrade
from .base import BaseRepository


class TradeRepository(BaseRepository[PaperTrade]):
    """Repository for PaperTrade operations."""

    def __init__(self, session: AsyncSession):
        """Initialize with session."""
        super().__init__(session, PaperTrade)

    async def list_by_strategy(
        self, strategy_id: int, limit: int = 100, offset: int = 0
    ) -> list[PaperTrade]:
        """List trades for a strategy, newest first."""
        stmt = (
            select(PaperTrade)
            .where(PaperTrade.strategy_id == strategy_id)
            .order_by(PaperTrade.timestamp.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def bulk_create(self, trades: list[PaperTrade]) -> list[PaperTrade]:
        """Create multiple trades at once."""
        self.session.add_all(trades)
        await self.session.flush()
        for trade in trades:
            await self.session.refresh(trade)
        return trades

    async def count_by_strategy(self, strategy_id: int) -> int:
        """Count trades for a strategy."""
        stmt = (
            select(func.count())
            .select_from(PaperTrade)
            .where(PaperTrade.strategy_id == strategy_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0
