"""Tests for performance metrics calculator."""

import sys
from datetime import datetime
from pathlib import Path

import pytest

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from engine.dsl.types import ActionType
from simulation.executor import TradeRecord
from simulation.metrics import PerformanceCalculator, PerformanceSnapshot


class TestPerformanceCalculator:
    """Test performance metrics calculations."""

    def test_total_return_pct_gain(self):
        """20% gain returns 20%."""
        calculator = PerformanceCalculator(initial_value=10000.0)
        result = calculator.total_return_pct(current_value=12000.0)
        assert result == pytest.approx(20.0)

    def test_total_return_pct_loss(self):
        """20% loss returns -20%."""
        calculator = PerformanceCalculator(initial_value=10000.0)
        result = calculator.total_return_pct(current_value=8000.0)
        assert result == pytest.approx(-20.0)

    def test_total_return_pct_no_change(self):
        """0% change returns 0%."""
        calculator = PerformanceCalculator(initial_value=10000.0)
        result = calculator.total_return_pct(current_value=10000.0)
        assert result == pytest.approx(0.0)

    def test_sharpe_ratio_consistent_returns(self):
        """Consistent positive returns have high Sharpe ratio."""
        calculator = PerformanceCalculator(initial_value=10000.0)
        # Consistent 1% daily returns
        daily_returns = [0.01] * 30
        sharpe = calculator.sharpe_ratio(daily_returns, risk_free_rate=0.0, annualize=True)
        # Very consistent returns should have high Sharpe (low std dev)
        assert sharpe > 10.0  # High Sharpe for no volatility

    def test_sharpe_ratio_volatile_returns(self):
        """Volatile returns have lower Sharpe ratio."""
        calculator = PerformanceCalculator(initial_value=10000.0)
        # Volatile returns: alternating +5% and -5%
        daily_returns = [0.05, -0.05] * 15
        sharpe = calculator.sharpe_ratio(daily_returns, risk_free_rate=0.0, annualize=True)
        # Average return near 0 with high volatility = low Sharpe
        assert sharpe == pytest.approx(0.0, abs=0.1)

    def test_max_drawdown(self):
        """12000->9000 peak-to-trough = -25% drawdown."""
        calculator = PerformanceCalculator(initial_value=10000.0)
        # Equity curve: rises to 12000, then falls to 9000
        equity_curve = [10000.0, 11000.0, 12000.0, 10500.0, 9000.0, 9500.0]
        drawdown = calculator.max_drawdown(equity_curve)
        # From peak 12000 to trough 9000 = -25%
        assert drawdown == pytest.approx(-25.0)

    def test_win_rate_half(self):
        """50% win rate from 1 win, 1 loss."""
        calculator = PerformanceCalculator(initial_value=10000.0)
        timestamp = datetime(2024, 1, 15, 10, 30, 0)
        trades = [
            # First round-trip: buy at 100, sell at 120 (profit)
            TradeRecord(
                action=ActionType.BUY,
                token="SOL",
                amount=10.0,
                price_at_exec=100.0,
                timestamp=timestamp,
                trigger_id="trigger1",
                slippage_bps=100,
            ),
            TradeRecord(
                action=ActionType.SELL,
                token="SOL",
                amount=10.0,
                price_at_exec=120.0,
                timestamp=timestamp,
                trigger_id="trigger2",
                slippage_bps=100,
            ),
            # Second round-trip: buy at 100, sell at 80 (loss)
            TradeRecord(
                action=ActionType.BUY,
                token="ETH",
                amount=5.0,
                price_at_exec=100.0,
                timestamp=timestamp,
                trigger_id="trigger3",
                slippage_bps=100,
            ),
            TradeRecord(
                action=ActionType.SELL,
                token="ETH",
                amount=5.0,
                price_at_exec=80.0,
                timestamp=timestamp,
                trigger_id="trigger4",
                slippage_bps=100,
            ),
        ]
        win_rate = calculator.win_rate(trades)
        assert win_rate == pytest.approx(50.0)

    def test_trade_count(self):
        """Count 3 trades."""
        calculator = PerformanceCalculator(initial_value=10000.0)
        timestamp = datetime(2024, 1, 15, 10, 30, 0)
        trades = [
            TradeRecord(
                action=ActionType.BUY,
                token="SOL",
                amount=10.0,
                price_at_exec=100.0,
                timestamp=timestamp,
                trigger_id="trigger1",
                slippage_bps=100,
            ),
            TradeRecord(
                action=ActionType.SELL,
                token="SOL",
                amount=10.0,
                price_at_exec=120.0,
                timestamp=timestamp,
                trigger_id="trigger2",
                slippage_bps=100,
            ),
            TradeRecord(
                action=ActionType.BUY,
                token="ETH",
                amount=5.0,
                price_at_exec=100.0,
                timestamp=timestamp,
                trigger_id="trigger3",
                slippage_bps=100,
            ),
        ]
        count = calculator.trade_count(trades)
        assert count == 3

    def test_daily_returns_from_equity(self):
        """Calculate daily returns from equity curve."""
        calculator = PerformanceCalculator(initial_value=10000.0)
        # 10000 -> 10500 (5%), 10500 -> 10290 (-2%), 10290 -> 11319 (10%)
        equity_curve = [10000.0, 10500.0, 10290.0, 11319.0]
        returns = calculator.daily_returns_from_equity(equity_curve)
        assert len(returns) == 3
        assert returns[0] == pytest.approx(0.05)
        assert returns[1] == pytest.approx(-0.02)
        assert returns[2] == pytest.approx(0.10)

    def test_performance_snapshot(self):
        """Complete snapshot with all metrics."""
        calculator = PerformanceCalculator(initial_value=10000.0)
        timestamp = datetime(2024, 1, 15, 10, 30, 0)

        # Equity curve with 20% gain
        equity_curve = [10000.0, 10500.0, 11000.0, 12000.0]

        # One winning trade
        trades = [
            TradeRecord(
                action=ActionType.BUY,
                token="SOL",
                amount=10.0,
                price_at_exec=100.0,
                timestamp=timestamp,
                trigger_id="trigger1",
                slippage_bps=100,
            ),
            TradeRecord(
                action=ActionType.SELL,
                token="SOL",
                amount=10.0,
                price_at_exec=120.0,
                timestamp=timestamp,
                trigger_id="trigger2",
                slippage_bps=100,
            ),
        ]

        snapshot = calculator.snapshot(
            current_value=12000.0,
            equity_curve=equity_curve,
            trades=trades,
            risk_free_rate=0.0,
        )

        assert isinstance(snapshot, PerformanceSnapshot)
        assert snapshot.total_return_pct == pytest.approx(20.0)
        assert snapshot.trade_count == 2
        assert snapshot.win_rate == pytest.approx(100.0)  # 1 winning round-trip
        assert snapshot.max_drawdown_pct <= 0  # Should be negative or zero
        assert snapshot.sharpe_ratio is not None
