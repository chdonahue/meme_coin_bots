"""Performance repository."""

from datetime import datetime, timedelta, timezone
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import StrategyPerformance
from .base import BaseRepository


class PerformanceRepository(BaseRepository[StrategyPerformance]):
    """Repository for StrategyPerformance operations."""

    def __init__(self, session: AsyncSession):
        """Initialize with session."""
        super().__init__(session, StrategyPerformance)

    async def get_latest(self, strategy_id: int) -> StrategyPerformance | None:
        """Get most recent performance snapshot."""
        stmt = (
            select(StrategyPerformance)
            .where(StrategyPerformance.strategy_id == strategy_id)
            .order_by(StrategyPerformance.date.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_history(self, strategy_id: int, days: int = 30) -> list[StrategyPerformance]:
        """Get performance history for last N days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(StrategyPerformance)
            .where(StrategyPerformance.strategy_id == strategy_id)
            .where(StrategyPerformance.date >= cutoff)
            .order_by(StrategyPerformance.date.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_daily(
        self,
        strategy_id: int,
        date: datetime,
        total_return_pct: float,
        sharpe_ratio: float | None = None,
        max_drawdown_pct: float | None = None,
        trade_count: int = 0,
        win_rate: float | None = None,
    ) -> StrategyPerformance:
        """Insert or update daily performance snapshot."""
        # Normalize date to start of day
        normalized_date = date.replace(hour=0, minute=0, second=0, microsecond=0)

        # Check if exists
        stmt = select(StrategyPerformance).where(
            and_(
                StrategyPerformance.strategy_id == strategy_id,
                StrategyPerformance.date == normalized_date,
            )
        )
        result = await self.session.execute(stmt)
        perf = result.scalar_one_or_none()

        if perf:
            # Update existing
            perf.total_return_pct = total_return_pct
            perf.sharpe_ratio = sharpe_ratio
            perf.max_drawdown_pct = max_drawdown_pct
            perf.trade_count = trade_count
            perf.win_rate = win_rate
        else:
            # Create new
            perf = StrategyPerformance(
                strategy_id=strategy_id,
                date=normalized_date,
                total_return_pct=total_return_pct,
                sharpe_ratio=sharpe_ratio,
                max_drawdown_pct=max_drawdown_pct,
                trade_count=trade_count,
                win_rate=win_rate,
            )
            self.session.add(perf)

        await self.session.flush()
        await self.session.refresh(perf)
        return perf
