"""Tests for PerformanceRepository."""

from datetime import datetime, timezone, timedelta

import pytest
from src.db.models import StrategyPerformance
from src.db.repositories.performance_repository import PerformanceRepository


class TestPerformanceRepository:
    """Test performance repository operations."""

    @pytest.mark.asyncio
    async def test_get_latest(self, db_session, sample_strategy):
        """Get latest performance snapshot."""
        repo = PerformanceRepository(db_session)

        # Create performance records
        perf = StrategyPerformance(
            strategy_id=sample_strategy.id,
            date=datetime.now(timezone.utc),
            total_return_pct=10.5,
            sharpe_ratio=1.2,
            max_drawdown_pct=-5.0,
            trade_count=15,
            win_rate=60.0,
        )
        db_session.add(perf)
        await db_session.flush()

        result = await repo.get_latest(sample_strategy.id)

        assert result is not None
        assert result.total_return_pct == 10.5

    @pytest.mark.asyncio
    async def test_get_latest_none(self, db_session, sample_strategy):
        """Get latest returns None when no records."""
        repo = PerformanceRepository(db_session)

        result = await repo.get_latest(sample_strategy.id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_history(self, db_session, sample_strategy):
        """Get performance history."""
        repo = PerformanceRepository(db_session)

        # Create historical records
        now = datetime.now(timezone.utc)
        for i in range(5):
            perf = StrategyPerformance(
                strategy_id=sample_strategy.id,
                date=now - timedelta(days=i),
                total_return_pct=float(i),
                trade_count=i,
            )
            db_session.add(perf)
        await db_session.flush()

        result = await repo.get_history(sample_strategy.id, days=3)

        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_upsert_daily_creates(self, db_session, sample_strategy):
        """Upsert creates new record."""
        repo = PerformanceRepository(db_session)
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        result = await repo.upsert_daily(
            strategy_id=sample_strategy.id,
            date=today,
            total_return_pct=5.5,
            sharpe_ratio=0.8,
            max_drawdown_pct=-3.0,
            trade_count=10,
            win_rate=55.0,
        )

        assert result.id is not None
        assert result.total_return_pct == 5.5

    @pytest.mark.asyncio
    async def test_upsert_daily_updates(self, db_session, sample_strategy):
        """Upsert updates existing record."""
        repo = PerformanceRepository(db_session)
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        # Create initial
        await repo.upsert_daily(
            strategy_id=sample_strategy.id,
            date=today,
            total_return_pct=5.0,
            trade_count=10,
        )

        # Update
        result = await repo.upsert_daily(
            strategy_id=sample_strategy.id,
            date=today,
            total_return_pct=7.5,
            trade_count=12,
        )

        assert result.total_return_pct == 7.5
        assert result.trade_count == 12
