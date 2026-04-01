"""Tests for BaseTradingSession."""

import pytest
from datetime import datetime, timezone
from src.trading.base_session import BaseTradingSession
from src.engine.dsl.parser import parse_strategy


class ConcreteSession(BaseTradingSession):
    """Concrete implementation for testing."""

    def __init__(self, strategy, **kwargs):
        super().__init__(session_id=1, strategy=strategy)
        self.executed_trades = []

    def _check_stop_losses(self, prices, timestamp):
        """No stop-loss checks in test implementation."""
        return []

    def _execute_trade(self, action, prices, trigger_id, timestamp):
        """Record trade for testing."""
        self.executed_trades.append(
            {
                "action": action,
                "prices": prices,
                "trigger_id": trigger_id,
            }
        )
        return {"executed": True}


class TestBaseTradingSession:
    """Tests for BaseTradingSession."""

    @pytest.fixture
    def strategy_json(self):
        """Simple strategy for testing."""
        return {
            "id": "test",
            "name": "Test",
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
                        "window": "5m",
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

    def test_process_tick_updates_price_buffer(self, strategy_json):
        """Test that price buffer is updated."""
        strategy = parse_strategy(strategy_json)
        session = ConcreteSession(strategy)

        session.process_tick({"SOL": 100.0})
        session.process_tick({"SOL": 101.0})

        assert len(session.price_buffers["SOL"]) == 2
        assert session.price_buffers["SOL"] == [100.0, 101.0]

    def test_trigger_cooldown(self, strategy_json):
        """Test trigger cooldown mechanism."""
        strategy = parse_strategy(strategy_json)
        session = ConcreteSession(strategy)

        # First trigger should not be active
        assert session._trigger_states.get("buy_dip", False) is False

    def test_derived_streams_initialized(self, strategy_json):
        """Test derived values dict is initialized."""
        strategy = parse_strategy(strategy_json)
        session = ConcreteSession(strategy)

        assert session.derived_values == {}

    def test_price_buffers_initialized_for_tokens(self, strategy_json):
        """Test price buffers are created for strategy tokens."""
        strategy = parse_strategy(strategy_json)
        session = ConcreteSession(strategy)

        assert "SOL" in session.price_buffers
        assert session.price_buffers["SOL"] == []

    def test_session_id_stored(self, strategy_json):
        """Test session_id is stored."""
        strategy = parse_strategy(strategy_json)
        session = ConcreteSession(strategy)

        assert session.session_id == 1

    def test_strategy_stored(self, strategy_json):
        """Test strategy is stored."""
        strategy = parse_strategy(strategy_json)
        session = ConcreteSession(strategy)

        assert session.strategy == strategy

    def test_price_buffer_limited_to_1000(self, strategy_json):
        """Test price buffer does not exceed 1000 entries."""
        strategy = parse_strategy(strategy_json)
        session = ConcreteSession(strategy)

        # Add 1100 prices
        for i in range(1100):
            session.process_tick({"SOL": 100.0 + i * 0.01})

        # Buffer should be limited to 1000
        assert len(session.price_buffers["SOL"]) == 1000
        # Should contain most recent 1000 prices
        assert session.price_buffers["SOL"][0] == pytest.approx(101.0, rel=0.01)


class TestBaseTradingSessionWithDerivedStreams:
    """Tests for BaseTradingSession with derived streams."""

    @pytest.fixture
    def strategy_with_ma(self):
        """Strategy with moving average."""
        return {
            "id": "ma_test",
            "name": "MA Test",
            "description": "Test",
            "version": 1,
            "tokens": ["SOL"],
            "derived_streams": [
                {"id": "ma_fast", "type": "moving_average", "token": "SOL", "window": "5m"},
            ],
            "triggers": [
                {
                    "id": "buy_ma_cross",
                    "when": {
                        "metric": "ma_fast",
                        "op": ">",
                        "value": 100,
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

    def test_derived_streams_computed(self, strategy_with_ma):
        """Test derived streams are computed from price buffers."""
        strategy = parse_strategy(strategy_with_ma)
        session = ConcreteSession(strategy)

        # Add enough prices for MA calculation
        for price in [100, 101, 102, 103, 104, 105]:
            session.process_tick({"SOL": float(price)})

        # MA values should be computed
        assert "ma_fast" in session.derived_values
        assert "current" in session.derived_values["ma_fast"]
