"""Tests for SimulationPersistence service."""

from datetime import datetime, timezone

import pytest
from src.db.models import PaperTrade, StrategyPerformance
from src.db.repositories.trade_repository import TradeRepository
from src.db.repositories.performance_repository import PerformanceRepository
from src.simulation.persistence import SimulationPersistence
from src.simulation.executor import TradeRecord
from src.simulation.backtest import BacktestResult
from src.simulation.portfolio import Portfolio
from src.engine.dsl.types import ActionType


class TestSimulationPersistence:
    """Test simulation persistence service."""

    @pytest.mark.asyncio
    async def test_save_backtest_result(self, db_session, sample_strategy):
        """Save complete backtest result to database."""
        trade_repo = TradeRepository(db_session)
        perf_repo = PerformanceRepository(db_session)
        persistence = SimulationPersistence(trade_repo, perf_repo)

        # Create a backtest result
        trades = [
            TradeRecord(
                action=ActionType.BUY,
                token="SOL",
                amount=10.0,
                price_at_exec=100.0,
                timestamp=datetime.now(timezone.utc),
                trigger_id="buy_trigger",
                slippage_bps=100,
            ),
            TradeRecord(
                action=ActionType.SELL,
                token="SOL",
                amount=10.0,
                price_at_exec=110.0,
                timestamp=datetime.now(timezone.utc),
                trigger_id="sell_trigger",
                slippage_bps=100,
            ),
        ]

        result = BacktestResult(
            total_return_pct=10.0,
            sharpe_ratio=1.5,
            max_drawdown_pct=-5.0,
            trade_count=2,
            win_rate=100.0,
            equity_curve=[10000.0, 10500.0, 11000.0],
            trades=trades,
            final_portfolio=Portfolio(initial_balance=11000.0),
        )

        await persistence.save_backtest_result(sample_strategy.id, result)

        # Verify trades saved
        saved_trades = await trade_repo.list_by_strategy(sample_strategy.id)
        assert len(saved_trades) == 2

        # Verify performance saved
        perf = await perf_repo.get_latest(sample_strategy.id)
        assert perf is not None
        assert perf.total_return_pct == 10.0
        assert perf.sharpe_ratio == 1.5

    @pytest.mark.asyncio
    async def test_save_backtest_empty_trades(self, db_session, sample_strategy):
        """Save backtest with no trades."""
        trade_repo = TradeRepository(db_session)
        perf_repo = PerformanceRepository(db_session)
        persistence = SimulationPersistence(trade_repo, perf_repo)

        result = BacktestResult(
            total_return_pct=0.0,
            sharpe_ratio=None,
            max_drawdown_pct=0.0,
            trade_count=0,
            win_rate=0.0,
            equity_curve=[10000.0],
            trades=[],
            final_portfolio=Portfolio(initial_balance=10000.0),
        )

        await persistence.save_backtest_result(sample_strategy.id, result)

        # Verify no trades saved
        saved_trades = await trade_repo.list_by_strategy(sample_strategy.id)
        assert len(saved_trades) == 0

        # Verify performance still saved
        perf = await perf_repo.get_latest(sample_strategy.id)
        assert perf is not None
        assert perf.trade_count == 0
