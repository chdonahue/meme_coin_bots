"""Persistence service for simulation results."""

from datetime import datetime, timezone

from ..db.models import PaperTrade
from ..db.repositories.trade_repository import TradeRepository
from ..db.repositories.performance_repository import PerformanceRepository
from .backtest import BacktestResult


class SimulationPersistence:
    """Bridges simulation engine with database storage."""

    def __init__(
        self,
        trade_repo: TradeRepository,
        performance_repo: PerformanceRepository,
    ):
        """Initialize with repositories."""
        self.trade_repo = trade_repo
        self.performance_repo = performance_repo

    async def save_backtest_result(
        self,
        strategy_id: int,
        result: BacktestResult,
    ) -> None:
        """
        Save complete backtest results to database.

        Converts TradeRecord objects to PaperTrade models and
        creates a performance snapshot from metrics.
        """
        # Save trades (if any)
        if result.trades:
            paper_trades = [
                PaperTrade(
                    strategy_id=strategy_id,
                    trigger_id=trade.trigger_id,
                    token=trade.token,
                    action=trade.action.value,
                    amount=trade.amount,
                    price_at_exec=trade.price_at_exec,
                    timestamp=trade.timestamp,
                )
                for trade in result.trades
            ]
            await self.trade_repo.bulk_create(paper_trades)

        # Save performance snapshot
        await self.performance_repo.upsert_daily(
            strategy_id=strategy_id,
            date=datetime.now(timezone.utc),
            total_return_pct=result.total_return_pct,
            sharpe_ratio=result.sharpe_ratio,
            max_drawdown_pct=result.max_drawdown_pct,
            trade_count=result.trade_count,
            win_rate=result.win_rate,
        )
