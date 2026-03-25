"""Tests for TradeRepository."""

from datetime import datetime, timezone

import pytest
from src.db.models import PaperTrade
from src.db.repositories.trade_repository import TradeRepository


class TestTradeRepository:
    """Test trade repository operations."""

    @pytest.mark.asyncio
    async def test_list_by_strategy(self, db_session, sample_strategy):
        """List trades by strategy."""
        repo = TradeRepository(db_session)

        # Create some trades
        trade = PaperTrade(
            strategy_id=sample_strategy.id,
            trigger_id="buy_trigger",
            token="SOL",
            action="buy",
            amount=10.0,
            price_at_exec=100.0,
            timestamp=datetime.now(timezone.utc),
        )
        db_session.add(trade)
        await db_session.flush()

        result = await repo.list_by_strategy(sample_strategy.id)

        assert len(result) == 1
        assert result[0].token == "SOL"

    @pytest.mark.asyncio
    async def test_bulk_create(self, db_session, sample_strategy):
        """Bulk create trades."""
        repo = TradeRepository(db_session)

        trades = [
            PaperTrade(
                strategy_id=sample_strategy.id,
                trigger_id="trigger_1",
                token="SOL",
                action="buy",
                amount=10.0,
                price_at_exec=100.0,
                timestamp=datetime.now(timezone.utc),
            ),
            PaperTrade(
                strategy_id=sample_strategy.id,
                trigger_id="trigger_2",
                token="SOL",
                action="sell",
                amount=5.0,
                price_at_exec=110.0,
                timestamp=datetime.now(timezone.utc),
            ),
        ]

        result = await repo.bulk_create(trades)

        assert len(result) == 2
        assert all(t.id is not None for t in result)

    @pytest.mark.asyncio
    async def test_count_by_strategy(self, db_session, sample_strategy):
        """Count trades for a strategy."""
        repo = TradeRepository(db_session)

        # Create trades
        for i in range(3):
            trade = PaperTrade(
                strategy_id=sample_strategy.id,
                trigger_id=f"trigger_{i}",
                token="SOL",
                action="buy",
                amount=10.0,
                price_at_exec=100.0,
                timestamp=datetime.now(timezone.utc),
            )
            db_session.add(trade)
        await db_session.flush()

        result = await repo.count_by_strategy(sample_strategy.id)

        assert result == 3
