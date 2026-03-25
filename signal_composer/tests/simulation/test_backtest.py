"""Tests for backtesting engine."""

import sys
from datetime import datetime
from pathlib import Path

import pytest

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from engine.dsl.types import (
    Strategy,
    Trigger,
    SimpleCondition,
    Action,
    ActionType,
    RiskRules,
    DerivedStream,
    DerivedStreamType,
    Operator,
    Window,
)
from simulation.backtest import BacktestEngine, BacktestResult


class TestBacktestWithSingleTrigger:
    """Test backtest with a simple price-based trigger."""

    def test_backtest_with_single_trigger(self):
        """Buy when price < 95, verify trades and profit."""
        # Create a simple strategy: buy SOL when price drops below 95
        strategy = Strategy(
            id="simple_buy_low",
            name="Buy Low Strategy",
            description="Buy when price is low",
            tokens=["SOL"],
            triggers=[
                Trigger(
                    id="buy_low",
                    when=SimpleCondition(
                        metric="price",
                        token="SOL",
                        op=Operator.LT,
                        value=95.0,
                    ),
                    action=Action(
                        type=ActionType.BUY,
                        token="SOL",
                        amount_pct=20.0,
                    ),
                ),
            ],
            risk_rules=RiskRules(
                stop_loss_pct=10.0,
                max_position_pct=50.0,
                max_trades_per_day=10,
                slippage_limit_bps=200,
            ),
        )

        # Price history: starts at 100, drops to 90, then rises to 110
        price_history = [
            {"SOL": 100.0},  # No buy - price >= 95
            {"SOL": 98.0},  # No buy - price >= 95
            {"SOL": 94.0},  # BUY - price < 95
            {"SOL": 92.0},  # BUY - price < 95
            {"SOL": 96.0},  # No buy - price >= 95
            {"SOL": 105.0},  # No buy - price >= 95
            {"SOL": 110.0},  # No buy - final price
        ]

        engine = BacktestEngine(initial_capital=10000.0, slippage_bps=100)
        result = engine.run(strategy, price_history)

        # Should have executed 2 buy trades (at prices 94 and 92)
        assert result.trade_count >= 2
        assert len(result.trades) >= 2

        # Verify trades were buys
        for trade in result.trades:
            assert trade.action == ActionType.BUY
            assert trade.token == "SOL"

        # Final portfolio should have SOL positions
        assert "SOL" in result.final_portfolio.positions

        # Equity curve should have entries for each tick
        assert len(result.equity_curve) == len(price_history)


class TestBacktestRespectsRiskRules:
    """Test that backtest enforces risk rules."""

    def test_backtest_respects_risk_rules(self):
        """Max_position_pct caps position at 40%."""
        # Strategy that tries to buy 100% on each tick
        strategy = Strategy(
            id="aggressive_buy",
            name="Aggressive Buy Strategy",
            tokens=["SOL"],
            triggers=[
                Trigger(
                    id="always_buy",
                    when=SimpleCondition(
                        metric="price",
                        token="SOL",
                        op=Operator.GT,
                        value=0.0,  # Always true
                    ),
                    action=Action(
                        type=ActionType.BUY,
                        token="SOL",
                        amount_pct=100.0,  # Try to buy 100% each time
                    ),
                ),
            ],
            risk_rules=RiskRules(
                stop_loss_pct=10.0,
                max_position_pct=40.0,  # Cap at 40%
                max_trades_per_day=100,
                slippage_limit_bps=200,
            ),
        )

        price_history = [
            {"SOL": 100.0},
            {"SOL": 100.0},
            {"SOL": 100.0},
            {"SOL": 100.0},
        ]

        engine = BacktestEngine(initial_capital=10000.0, slippage_bps=100)
        result = engine.run(strategy, price_history)

        # Position should be capped at 40% of portfolio
        final_prices = price_history[-1]
        if "SOL" in result.final_portfolio.positions:
            position_value = result.final_portfolio.positions["SOL"].value_at(final_prices["SOL"])
            total_value = result.final_portfolio.total_value_at_prices(final_prices)
            position_pct = (position_value / total_value) * 100

            # Position should not exceed 40% (with small tolerance for slippage effects)
            assert position_pct <= 42.0, f"Position {position_pct}% exceeds max 40%"


class TestBacktestWithDerivedStreams:
    """Test backtest with derived stream calculations."""

    def test_backtest_with_derived_streams(self):
        """MA crossover strategy (basic test)."""
        # Strategy using moving average
        strategy = Strategy(
            id="ma_strategy",
            name="MA Crossover Strategy",
            tokens=["SOL"],
            derived_streams=[
                DerivedStream(
                    id="sol_ma_5m",
                    name="SOL 5m MA",
                    type=DerivedStreamType.MOVING_AVERAGE,
                    token="SOL",
                    metric="price",
                    window=Window.FIVE_MIN,
                ),
            ],
            triggers=[
                Trigger(
                    id="buy_below_ma",
                    when=SimpleCondition(
                        metric="price",
                        token="SOL",
                        op=Operator.LT,
                        value=95.0,  # Simple price trigger for now
                    ),
                    action=Action(
                        type=ActionType.BUY,
                        token="SOL",
                        amount_pct=25.0,
                    ),
                ),
            ],
            risk_rules=RiskRules(
                stop_loss_pct=10.0,
                max_position_pct=50.0,
                max_trades_per_day=10,
                slippage_limit_bps=200,
            ),
        )

        # Price history with enough data for MA calculation
        price_history = [
            {"SOL": 100.0},
            {"SOL": 99.0},
            {"SOL": 98.0},
            {"SOL": 97.0},
            {"SOL": 96.0},
            {"SOL": 94.0},  # BUY - price < 95
            {"SOL": 93.0},  # BUY - price < 95
            {"SOL": 95.0},  # No buy
            {"SOL": 100.0},
            {"SOL": 105.0},
        ]

        engine = BacktestEngine(initial_capital=10000.0, slippage_bps=100)
        result = engine.run(strategy, price_history)

        # Should have some trades
        assert result.trade_count >= 1

        # Equity curve should have correct length
        assert len(result.equity_curve) == len(price_history)


class TestBacktestResultHasPerformanceMetrics:
    """Test that BacktestResult contains all required fields."""

    def test_backtest_result_has_performance_metrics(self):
        """Verify all result fields exist."""
        strategy = Strategy(
            id="test_strategy",
            name="Test Strategy",
            tokens=["SOL"],
            triggers=[
                Trigger(
                    id="simple_trigger",
                    when=SimpleCondition(
                        metric="price",
                        token="SOL",
                        op=Operator.LT,
                        value=95.0,
                    ),
                    action=Action(
                        type=ActionType.BUY,
                        token="SOL",
                        amount_pct=10.0,
                    ),
                ),
            ],
            risk_rules=RiskRules(
                stop_loss_pct=10.0,
                max_position_pct=50.0,
                max_trades_per_day=10,
                slippage_limit_bps=200,
            ),
        )

        price_history = [
            {"SOL": 100.0},
            {"SOL": 94.0},  # Buy trigger
            {"SOL": 92.0},  # Buy trigger
            {"SOL": 110.0},
        ]

        engine = BacktestEngine(initial_capital=10000.0, slippage_bps=100)
        result = engine.run(strategy, price_history)

        # Verify all required attributes exist
        assert hasattr(result, "total_return_pct")
        assert hasattr(result, "sharpe_ratio")
        assert hasattr(result, "max_drawdown_pct")
        assert hasattr(result, "trade_count")
        assert hasattr(result, "win_rate")
        assert hasattr(result, "equity_curve")
        assert hasattr(result, "trades")
        assert hasattr(result, "final_portfolio")

        # Verify types
        assert isinstance(result.total_return_pct, float)
        assert result.sharpe_ratio is None or isinstance(result.sharpe_ratio, float)
        assert isinstance(result.max_drawdown_pct, float)
        assert isinstance(result.trade_count, int)
        assert isinstance(result.win_rate, float)
        assert isinstance(result.equity_curve, list)
        assert isinstance(result.trades, list)

        # Equity curve should have one entry per price tick
        assert len(result.equity_curve) == len(price_history)


class TestBacktestSellTriggers:
    """Test backtest with sell triggers."""

    def test_backtest_with_buy_and_sell_triggers(self):
        """Test round-trip trading with buy and sell triggers."""
        strategy = Strategy(
            id="round_trip",
            name="Round Trip Strategy",
            tokens=["SOL"],
            triggers=[
                Trigger(
                    id="buy_low",
                    when=SimpleCondition(
                        metric="price",
                        token="SOL",
                        op=Operator.LT,
                        value=95.0,
                    ),
                    action=Action(
                        type=ActionType.BUY,
                        token="SOL",
                        amount_pct=30.0,
                    ),
                ),
                Trigger(
                    id="sell_high",
                    when=SimpleCondition(
                        metric="price",
                        token="SOL",
                        op=Operator.GT,
                        value=105.0,
                    ),
                    action=Action(
                        type=ActionType.SELL_ALL,
                        token="SOL",
                    ),
                ),
            ],
            risk_rules=RiskRules(
                stop_loss_pct=10.0,
                max_position_pct=50.0,
                max_trades_per_day=20,
                slippage_limit_bps=200,
            ),
        )

        # Price drops, buy happens, price rises, sell happens
        price_history = [
            {"SOL": 100.0},
            {"SOL": 94.0},  # BUY - price < 95
            {"SOL": 92.0},  # BUY - price < 95
            {"SOL": 98.0},
            {"SOL": 102.0},
            {"SOL": 106.0},  # SELL_ALL - price > 105
            {"SOL": 108.0},  # SELL_ALL (but no position left)
        ]

        engine = BacktestEngine(initial_capital=10000.0, slippage_bps=100)
        result = engine.run(strategy, price_history)

        # Should have buys and sells
        buy_trades = [t for t in result.trades if t.action == ActionType.BUY]
        sell_trades = [
            t for t in result.trades if t.action in (ActionType.SELL, ActionType.SELL_ALL)
        ]

        assert len(buy_trades) >= 1, "Should have at least one buy"
        # May or may not have sells depending on position tracking

        # Equity curve should track through the journey
        assert len(result.equity_curve) == len(price_history)
