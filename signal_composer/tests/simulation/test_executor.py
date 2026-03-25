"""Tests for paper trade executor."""

import sys
from datetime import datetime
from pathlib import Path

import pytest

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from engine.dsl.types import Action, ActionType, RiskRules
from simulation.portfolio import Portfolio
from simulation.executor import PaperTradeExecutor, TradeRecord


class TestPaperTradeExecutor:
    """Test paper trade executor with slippage and risk rules."""

    def test_execute_buy_action(self):
        """Buy action applies slippage (higher price)."""
        portfolio = Portfolio(initial_balance=10000.0)
        executor = PaperTradeExecutor(portfolio=portfolio, slippage_bps=100)  # 1% slippage

        action = Action(type=ActionType.BUY, token="SOL", amount_pct=10.0)
        prices = {"SOL": 100.0}
        timestamp = datetime(2024, 1, 15, 10, 30, 0)

        record = executor.execute(action, prices, trigger_id="test_trigger", timestamp=timestamp)

        assert record is not None
        assert record.action == ActionType.BUY
        assert record.token == "SOL"
        # Slippage increases buy price: 100 * 1.01 = 101
        assert record.price_at_exec == pytest.approx(101.0)
        assert record.slippage_bps == 100
        # 10% of 10000 = 1000 USD, at price 101 = ~9.9 tokens
        assert record.amount == pytest.approx(1000.0 / 101.0, rel=0.01)

    def test_execute_sell_action(self):
        """Sell action applies slippage (lower price)."""
        portfolio = Portfolio(initial_balance=10000.0)
        # First buy some tokens
        portfolio.execute_buy(token="SOL", amount_usd=2000.0, price=100.0)  # 20 SOL

        executor = PaperTradeExecutor(portfolio=portfolio, slippage_bps=100)  # 1% slippage

        action = Action(type=ActionType.SELL, token="SOL", amount_pct=50.0)  # Sell 50% of position
        prices = {"SOL": 100.0}
        timestamp = datetime(2024, 1, 15, 10, 30, 0)

        record = executor.execute(action, prices, trigger_id="test_trigger", timestamp=timestamp)

        assert record is not None
        assert record.action == ActionType.SELL
        assert record.token == "SOL"
        # Slippage decreases sell price: 100 * 0.99 = 99
        assert record.price_at_exec == pytest.approx(99.0)
        assert record.slippage_bps == 100
        # 50% of 20 SOL = 10 SOL
        assert record.amount == pytest.approx(10.0)

    def test_execute_sell_all_action(self):
        """Sell all removes entire position."""
        portfolio = Portfolio(initial_balance=10000.0)
        # First buy some tokens
        portfolio.execute_buy(token="SOL", amount_usd=1500.0, price=100.0)  # 15 SOL

        executor = PaperTradeExecutor(portfolio=portfolio, slippage_bps=100)

        action = Action(type=ActionType.SELL_ALL, token="SOL")
        prices = {"SOL": 120.0}
        timestamp = datetime(2024, 1, 15, 10, 30, 0)

        record = executor.execute(action, prices, trigger_id="test_trigger", timestamp=timestamp)

        assert record is not None
        assert record.action == ActionType.SELL_ALL
        assert record.token == "SOL"
        # Slippage decreases sell price: 120 * 0.99 = 118.8
        assert record.price_at_exec == pytest.approx(118.8)
        # Should sell all 15 SOL
        assert record.amount == pytest.approx(15.0)
        # Position should be removed
        assert "SOL" not in portfolio.positions

    def test_respects_max_position_pct(self):
        """Buy is capped at max_position_pct from risk rules."""
        portfolio = Portfolio(initial_balance=10000.0)
        risk_rules = RiskRules(
            stop_loss_pct=5.0,
            max_position_pct=30.0,  # Max 30% in any one position
            max_trades_per_day=10,
            slippage_limit_bps=200,
        )
        executor = PaperTradeExecutor(portfolio=portfolio, slippage_bps=100, risk_rules=risk_rules)

        # Try to buy 50% but should be capped at 30%
        action = Action(type=ActionType.BUY, token="SOL", amount_pct=50.0)
        prices = {"SOL": 100.0}
        timestamp = datetime(2024, 1, 15, 10, 30, 0)

        record = executor.execute(action, prices, trigger_id="test_trigger", timestamp=timestamp)

        assert record is not None
        # 30% of 10000 = 3000 USD, at slippage-adjusted price 101 = ~29.7 tokens
        expected_amount = 3000.0 / 101.0
        assert record.amount == pytest.approx(expected_amount, rel=0.01)

    def test_skip_if_slippage_exceeds_limit(self):
        """Trade skipped if slippage exceeds risk rule limit."""
        portfolio = Portfolio(initial_balance=10000.0)
        risk_rules = RiskRules(
            stop_loss_pct=5.0,
            max_position_pct=30.0,
            max_trades_per_day=10,
            slippage_limit_bps=50,  # Only allow 0.5% slippage
        )
        # Executor has 100bps (1%) slippage, exceeds 50bps limit
        executor = PaperTradeExecutor(portfolio=portfolio, slippage_bps=100, risk_rules=risk_rules)

        action = Action(type=ActionType.BUY, token="SOL", amount_pct=10.0)
        prices = {"SOL": 100.0}
        timestamp = datetime(2024, 1, 15, 10, 30, 0)

        record = executor.execute(action, prices, trigger_id="test_trigger", timestamp=timestamp)

        # Should return None - trade skipped
        assert record is None

    def test_daily_trade_limit(self):
        """Third trade is blocked after 2 allowed."""
        portfolio = Portfolio(initial_balance=10000.0)
        risk_rules = RiskRules(
            stop_loss_pct=5.0,
            max_position_pct=50.0,
            max_trades_per_day=2,  # Only 2 trades per day
            slippage_limit_bps=200,
        )
        executor = PaperTradeExecutor(portfolio=portfolio, slippage_bps=100, risk_rules=risk_rules)

        prices = {"SOL": 100.0}
        timestamp = datetime(2024, 1, 15, 10, 30, 0)

        # First trade - should succeed
        action1 = Action(type=ActionType.BUY, token="SOL", amount_pct=10.0)
        record1 = executor.execute(action1, prices, trigger_id="trigger1", timestamp=timestamp)
        assert record1 is not None

        # Second trade - should succeed
        action2 = Action(type=ActionType.BUY, token="SOL", amount_pct=10.0)
        record2 = executor.execute(action2, prices, trigger_id="trigger2", timestamp=timestamp)
        assert record2 is not None

        # Third trade - should be blocked
        action3 = Action(type=ActionType.BUY, token="SOL", amount_pct=10.0)
        record3 = executor.execute(action3, prices, trigger_id="trigger3", timestamp=timestamp)
        assert record3 is None

    def test_trade_record_has_timestamp(self):
        """TradeRecord includes execution timestamp."""
        portfolio = Portfolio(initial_balance=10000.0)
        executor = PaperTradeExecutor(portfolio=portfolio, slippage_bps=100)

        action = Action(type=ActionType.BUY, token="SOL", amount_pct=10.0)
        prices = {"SOL": 100.0}
        timestamp = datetime(2024, 1, 15, 10, 30, 0)

        record = executor.execute(action, prices, trigger_id="test_trigger", timestamp=timestamp)

        assert record is not None
        assert record.timestamp == timestamp
        assert record.trigger_id == "test_trigger"
