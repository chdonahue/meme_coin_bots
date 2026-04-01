"""Tests for PaperTradingSession."""

from datetime import datetime, timezone

import pytest

from src.engine.dsl.parser import parse_strategy
from src.paper_trading.session import (
    PaperTradingSession,
    LivePosition,
    LiveTrade,
)


class TestLivePosition:
    """Tests for LivePosition."""

    def test_create_position(self):
        """Test creating a position."""
        pos = LivePosition(
            token="SOL",
            quantity=10.0,
            avg_entry_price=100.0,
        )
        assert pos.quantity == 10.0
        assert pos.avg_entry_price == 100.0
        assert pos.total_cost == 1000.0

    def test_add_to_position(self):
        """Test adding to an existing position."""
        pos = LivePosition(token="SOL", quantity=10.0, avg_entry_price=100.0)

        # Add more at higher price
        pos.add(quantity=10.0, price=120.0)

        assert pos.quantity == 20.0
        assert pos.total_cost == 2200.0  # 1000 + 1200
        assert pos.avg_entry_price == 110.0  # 2200 / 20

    def test_remove_from_position(self):
        """Test selling part of a position."""
        pos = LivePosition(token="SOL", quantity=20.0, avg_entry_price=100.0)

        cost_basis = pos.remove(quantity=5.0)

        assert cost_basis == 500.0  # 5 * 100
        assert pos.quantity == 15.0
        assert pos.total_cost == 1500.0
        assert pos.avg_entry_price == 100.0  # Unchanged

    def test_value_at_price(self):
        """Test position valuation."""
        pos = LivePosition(token="SOL", quantity=10.0, avg_entry_price=100.0)

        assert pos.value_at(150.0) == 1500.0
        assert pos.value_at(50.0) == 500.0

    def test_pnl_percentage(self):
        """Test P&L calculation."""
        pos = LivePosition(token="SOL", quantity=10.0, avg_entry_price=100.0)

        assert pos.pnl_pct(100.0) == 0.0  # Breakeven
        assert pos.pnl_pct(150.0) == 50.0  # 50% gain
        assert pos.pnl_pct(80.0) == -20.0  # 20% loss


class TestPaperTradingSession:
    """Tests for PaperTradingSession."""

    @pytest.fixture
    def strategy_json(self):
        """Strategy with simple buy trigger."""
        return {
            "id": "paper_test",
            "name": "Paper Test",
            "description": "Test",
            "version": 1,
            "tokens": ["SOL"],
            "derived_streams": [],
            "triggers": [
                {
                    "id": "buy_dip",
                    "when": {
                        "metric": "price_change_pct",
                        "token": "SOL",
                        "window": "15m",
                        "op": "<",
                        "value": -5,
                    },
                    "action": {"type": "buy", "token": "SOL", "amount_pct": 25},
                }
            ],
            "risk_rules": {
                "stop_loss_pct": -10,
                "max_position_pct": 50,
                "max_trades_per_day": 10,
                "slippage_limit_bps": 200,
            },
        }

    @pytest.fixture
    def session(self, strategy_json):
        """Create a test session."""
        strategy = parse_strategy(strategy_json)
        return PaperTradingSession(
            session_id=1,
            strategy=strategy,
            initial_capital=10000.0,
            slippage_bps=100,
        )

    def test_initial_state(self, session):
        """Test initial session state."""
        assert session.cash_balance == 10000.0
        assert session.initial_capital == 10000.0
        assert len(session.positions) == 0
        assert len(session.trades) == 0

    def test_total_value_no_positions(self, session):
        """Test total value with only cash."""
        assert session.total_value == 10000.0

    def test_process_tick_no_trigger(self, session):
        """Test processing tick without triggering a trade."""
        prices = {"SOL": 100.0}
        timestamp = datetime.now(timezone.utc)

        trades = session.process_tick(prices, timestamp)

        assert len(trades) == 0
        assert session.cash_balance == 10000.0
        assert len(session.positions) == 0

    def test_process_tick_updates_price_buffer(self, session):
        """Test that price buffer is updated on each tick."""
        session.process_tick({"SOL": 100.0})
        session.process_tick({"SOL": 101.0})
        session.process_tick({"SOL": 99.0})

        assert len(session.price_buffers["SOL"]) == 3
        assert session.price_buffers["SOL"] == [100.0, 101.0, 99.0]

    def test_stop_loss_triggers(self, session):
        """Test stop-loss triggers when position drops."""
        # Manually create a position (simulating a previous buy)
        session.positions["SOL"] = LivePosition(
            token="SOL",
            quantity=10.0,
            avg_entry_price=100.0,
        )
        session.cash_balance = 9000.0  # After buying

        # Price drops 15% - should trigger stop-loss (threshold is -10%)
        prices = {"SOL": 85.0}
        trades = session.process_tick(prices)

        # Stop-loss should have triggered
        assert len(trades) == 1
        assert trades[0].trigger_id == "stop_loss"
        assert trades[0].action == "sell_all"
        assert "SOL" not in session.positions

        # Cash should be restored (with slippage)
        # Sell at 85 * (1 - 0.01) = 84.15
        expected_proceeds = 10 * 84.15
        assert session.cash_balance == pytest.approx(9000.0 + expected_proceeds, rel=0.01)

    def test_max_position_limit(self, session):
        """Test that max_position_pct is enforced."""
        # Strategy has max_position_pct of 50%
        # Buy trigger requests 25% of portfolio

        # Create a position that's already at 40%
        session.positions["SOL"] = LivePosition(
            token="SOL",
            quantity=40.0,
            avg_entry_price=100.0,
        )
        session.cash_balance = 6000.0

        # Try to execute a buy - should be limited
        # Directly call _calculate_buy_quantity to test the limit
        from src.engine.dsl.types import Action, ActionType

        action = Action(type=ActionType.BUY, token="SOL", amount_pct=25)
        prices = {"SOL": 100.0}
        exec_price = 101.0  # With slippage

        quantity, skip_reason = session._calculate_buy_quantity(action, prices, exec_price)

        # Max is 50% of 10000 = 5000 USD
        # Current position is 4000 USD
        # Can only buy 1000 / 101 = ~9.9 more
        assert quantity < 10.0
        assert quantity > 0
        assert skip_reason == ""

    def test_daily_trade_limit(self, session):
        """Test daily trade limit is enforced."""
        # Strategy allows 10 trades per day
        from src.engine.dsl.types import Action, ActionType

        action = Action(type=ActionType.BUY, token="SOL", amount_pct=5)
        prices = {"SOL": 100.0}
        timestamp = datetime.now(timezone.utc)

        # Execute 10 trades
        for i in range(10):
            trade = session._execute_action(action, prices, f"trigger_{i}", timestamp)
            assert trade is not None

        # 11th trade should be blocked
        trade = session._execute_action(action, prices, "trigger_10", timestamp)
        assert trade is None

    def test_get_status(self, session):
        """Test getting session status."""
        session.positions["SOL"] = LivePosition(
            token="SOL",
            quantity=10.0,
            avg_entry_price=100.0,
        )
        session.cash_balance = 9000.0

        prices = {"SOL": 120.0}
        status = session.get_status(prices)

        assert status["session_id"] == 1
        assert status["initial_capital"] == 10000.0
        assert status["cash_balance"] == 9000.0
        assert status["total_value"] == 10200.0  # 9000 + (10 * 120)
        assert status["pnl_pct"] == pytest.approx(2.0, rel=0.01)
        assert "SOL" in status["positions"]
        assert status["positions"]["SOL"]["pnl_pct"] == pytest.approx(20.0, rel=0.01)


class TestTriggerCooldown:
    """Tests for trigger cooldown mechanism."""

    @pytest.fixture
    def strategy_with_simple_trigger(self):
        """Strategy with a simple > comparison that could fire repeatedly."""
        return {
            "id": "cooldown_test",
            "name": "Cooldown Test",
            "description": "Test",
            "version": 1,
            "tokens": ["SOL"],
            "derived_streams": [
                {"id": "ma_fast", "type": "moving_average", "token": "SOL", "window": "5m"},
            ],
            "triggers": [
                {
                    "id": "buy_when_ma_high",
                    "when": {
                        "metric": "ma_fast",
                        "op": ">",
                        "value": 100,
                    },
                    "action": {"type": "buy", "token": "SOL", "amount_pct": 10},
                }
            ],
            "risk_rules": {
                "stop_loss_pct": -10,
                "max_position_pct": 100,
                "max_trades_per_day": 100,
                "slippage_limit_bps": 200,
            },
        }

    def test_trigger_only_fires_once(self, strategy_with_simple_trigger):
        """Test that a trigger only fires on FALSE->TRUE transition."""
        strategy = parse_strategy(strategy_with_simple_trigger)
        session = PaperTradingSession(
            session_id=1,
            strategy=strategy,
            initial_capital=10000.0,
            slippage_bps=100,
        )

        # Build up price history below threshold (MA < 100)
        for price in [90.0, 92.0, 94.0, 96.0, 98.0]:
            trades = session.process_tick({"SOL": price})
            assert len(trades) == 0

        # Push MA above 100 with high prices
        # Keep adding until we get a trade (MA needs to cross above 100)
        first_trade_tick = None
        for i, price in enumerate([110.0, 120.0, 130.0, 140.0]):
            trades = session.process_tick({"SOL": price})
            if trades and first_trade_tick is None:
                first_trade_tick = i
                break

        # Should have triggered at some point
        assert first_trade_tick is not None, "Trigger should have fired"
        assert len(session.trades) == 1, "Should have exactly one trade"

        # Now continue with high prices - should NOT trigger again
        for price in [150.0, 160.0, 170.0]:
            trades = session.process_tick({"SOL": price})
            assert len(trades) == 0, f"Should not fire again at {price} - cooldown active"

        # Verify still only 1 trade
        assert len(session.trades) == 1, "Should still have exactly one trade"

        # Drop MA below threshold with many low prices
        for price in [50.0] * 10:
            session.process_tick({"SOL": price})

        # MA should now be well below 100, trigger state should reset
        # Push back above threshold - should trigger again
        for price in [150.0, 200.0, 250.0]:
            trades = session.process_tick({"SOL": price})
            if trades:
                break

        # Should now have 3 trades total:
        # 1. First buy (trigger fired)
        # 2. Stop-loss sell (when price dropped to 50)
        # 3. Second buy (after cooldown reset)
        assert len(session.trades) == 3, "Should have 3 trades: buy, stop-loss, buy"
        assert session.trades[0].trigger_id == "buy_when_ma_high"
        assert session.trades[1].trigger_id == "stop_loss"
        assert session.trades[2].trigger_id == "buy_when_ma_high"


class TestDerivedStreams:
    """Tests for derived stream calculation in paper trading."""

    @pytest.fixture
    def strategy_with_ma(self):
        """Strategy using moving average."""
        return {
            "id": "ma_test",
            "name": "MA Test",
            "description": "Test",
            "version": 1,
            "tokens": ["SOL"],
            "derived_streams": [
                {"id": "ma_fast", "type": "moving_average", "token": "SOL", "window": "5m"},
                {"id": "ma_slow", "type": "moving_average", "token": "SOL", "window": "15m"},
            ],
            "triggers": [
                {
                    "id": "golden_cross",
                    "when": {
                        "metric": "ma_fast",
                        "op": "crosses_above",
                        "compare_to": "ma_slow",
                    },
                    "action": {"type": "buy", "token": "SOL", "amount_pct": 50},
                }
            ],
            "risk_rules": {
                "stop_loss_pct": -10,
                "max_position_pct": 100,
                "max_trades_per_day": 10,
                "slippage_limit_bps": 200,
            },
        }

    def test_derived_streams_computed(self, strategy_with_ma):
        """Test that derived streams are computed from price buffer."""
        strategy = parse_strategy(strategy_with_ma)
        session = PaperTradingSession(
            session_id=1,
            strategy=strategy,
            initial_capital=10000.0,
            slippage_bps=100,
        )

        # Add enough prices for MA calculation
        prices = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110]
        for price in prices:
            session.process_tick({"SOL": float(price)})

        # MA values should be computed
        assert "ma_fast" in session.derived_values
        assert "ma_slow" in session.derived_values
