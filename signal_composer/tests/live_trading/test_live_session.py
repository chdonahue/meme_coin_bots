"""Tests for LiveTradingSession."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from src.live_trading.session import LiveTradingSession, LivePosition
from src.live_trading.coordinator import TransactionCoordinator
from src.live_trading.safety.guard import SafetyConfig, SafetyGuard
from src.live_trading.safety.circuit_breaker import CircuitBreaker
from src.engine.dsl.parser import parse_strategy


class TestLivePosition:
    """Tests for LivePosition dataclass."""

    def test_pnl_pct_positive(self):
        """Test positive PnL calculation."""
        position = LivePosition(
            token="SOL",
            quantity=10.0,
            avg_entry_price=100.0,
        )
        # Price went up 10%
        pnl = position.pnl_pct(110.0)
        assert pnl == 10.0

    def test_pnl_pct_negative(self):
        """Test negative PnL calculation."""
        position = LivePosition(
            token="SOL",
            quantity=10.0,
            avg_entry_price=100.0,
        )
        # Price went down 15%
        pnl = position.pnl_pct(85.0)
        assert pnl == -15.0

    def test_pnl_pct_zero(self):
        """Test zero PnL when price unchanged."""
        position = LivePosition(
            token="SOL",
            quantity=10.0,
            avg_entry_price=100.0,
        )
        pnl = position.pnl_pct(100.0)
        assert pnl == 0.0

    def test_position_value(self):
        """Test calculating position value."""
        position = LivePosition(
            token="SOL",
            quantity=5.0,
            avg_entry_price=100.0,
        )
        value = position.value_at(150.0)
        assert value == 750.0


class TestLiveTradingSession:
    """Tests for LiveTradingSession."""

    @pytest.fixture
    def strategy_json(self):
        """Simple strategy for testing."""
        return {
            "id": "live_test",
            "name": "Live Test",
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

    @pytest.fixture
    def coordinator(self):
        """Create TransactionCoordinator."""
        return TransactionCoordinator(
            safety_guard=SafetyGuard(SafetyConfig()),
            circuit_breaker=CircuitBreaker(failure_threshold=3),
            rpc_url="https://api.mainnet-beta.solana.com",
        )

    @pytest.fixture
    def session(self, strategy_json, coordinator):
        """Create LiveTradingSession."""
        strategy = parse_strategy(strategy_json)
        return LiveTradingSession(
            session_id=1,
            strategy=strategy,
            coordinator=coordinator,
            wallet_address="7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        )

    def test_initial_state(self, session):
        """Test initial session state."""
        assert session.session_id == 1
        assert session.wallet_address is not None
        assert len(session.positions) == 0

    def test_initial_counters(self, session):
        """Test initial counters are zero."""
        assert session.daily_volume_usd == 0.0
        assert session.daily_pnl_usd == 0.0
        assert len(session.trades) == 0

    def test_process_tick_updates_buffers(self, session):
        """Test that price buffers are updated."""
        session.process_tick({"SOL": 100.0})
        session.process_tick({"SOL": 101.0})

        assert len(session.price_buffers["SOL"]) == 2

    def test_process_tick_updates_multiple_tokens(self, strategy_json, coordinator):
        """Test tick updates for multiple tokens."""
        strategy_json["tokens"] = ["SOL", "BTC"]
        strategy = parse_strategy(strategy_json)
        session = LiveTradingSession(
            session_id=1,
            strategy=strategy,
            coordinator=coordinator,
            wallet_address="7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        )

        session.process_tick({"SOL": 100.0, "BTC": 50000.0})

        assert len(session.price_buffers["SOL"]) == 1
        assert len(session.price_buffers["BTC"]) == 1


class TestLiveSessionStopLoss:
    """Tests for stop-loss functionality."""

    @pytest.fixture
    def strategy_json(self):
        """Strategy with stop-loss."""
        return {
            "id": "stop_loss_test",
            "name": "Stop Loss Test",
            "description": "Test",
            "version": 1,
            "tokens": ["SOL"],
            "derived_streams": [],
            "triggers": [],
            "risk_rules": {
                "stop_loss_pct": -10,
                "max_position_pct": 50,
                "max_trades_per_day": 10,
                "slippage_limit_bps": 200,
            },
        }

    @pytest.fixture
    def coordinator(self):
        """Create TransactionCoordinator."""
        return TransactionCoordinator(
            safety_guard=SafetyGuard(SafetyConfig()),
            circuit_breaker=CircuitBreaker(failure_threshold=3),
            rpc_url="https://api.mainnet-beta.solana.com",
        )

    @pytest.fixture
    def session(self, strategy_json, coordinator):
        """Create LiveTradingSession."""
        strategy = parse_strategy(strategy_json)
        return LiveTradingSession(
            session_id=1,
            strategy=strategy,
            coordinator=coordinator,
            wallet_address="7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        )

    def test_stop_loss_triggered(self, session, coordinator):
        """Test that stop-loss is triggered when position drops below threshold."""
        # Add a position at $100
        session.positions["SOL"] = LivePosition(
            token="SOL",
            quantity=10.0,
            avg_entry_price=100.0,
        )

        # Price drops 12%, should trigger stop-loss at -10%
        session.process_tick({"SOL": 88.0})

        # Should have queued a sell transaction
        assert coordinator.pending_count == 1
        tx = coordinator.pending_transactions[0]
        assert tx.action_type == "sell_all"
        assert tx.token_address == "SOL"

    def test_stop_loss_not_triggered_above_threshold(self, session, coordinator):
        """Test that stop-loss is not triggered above threshold."""
        # Add a position at $100
        session.positions["SOL"] = LivePosition(
            token="SOL",
            quantity=10.0,
            avg_entry_price=100.0,
        )

        # Price drops only 5%, under the -10% threshold
        session.process_tick({"SOL": 95.0})

        # Should NOT have queued a transaction
        assert coordinator.pending_count == 0

    def test_stop_loss_only_triggers_once(self, session, coordinator):
        """Test that stop-loss only triggers once per position."""
        # Add a position at $100
        session.positions["SOL"] = LivePosition(
            token="SOL",
            quantity=10.0,
            avg_entry_price=100.0,
        )

        # Price drops 12%
        session.process_tick({"SOL": 88.0})
        session.process_tick({"SOL": 87.0})  # Further drop

        # Should only have queued ONE sell transaction
        assert coordinator.pending_count == 1


class TestLiveSessionTradeExecution:
    """Tests for trade execution."""

    @pytest.fixture
    def strategy_json(self):
        """Strategy with a buy trigger."""
        return {
            "id": "trade_test",
            "name": "Trade Test",
            "description": "Test",
            "version": 1,
            "tokens": ["SOL"],
            "derived_streams": [],
            "triggers": [],
            "risk_rules": {
                "stop_loss_pct": -10,
                "max_position_pct": 50,
                "max_trades_per_day": 10,
                "slippage_limit_bps": 200,
            },
        }

    @pytest.fixture
    def coordinator(self):
        """Create TransactionCoordinator."""
        return TransactionCoordinator(
            safety_guard=SafetyGuard(SafetyConfig()),
            circuit_breaker=CircuitBreaker(failure_threshold=3),
            rpc_url="https://api.mainnet-beta.solana.com",
        )

    @pytest.fixture
    def session(self, strategy_json, coordinator):
        """Create LiveTradingSession."""
        strategy = parse_strategy(strategy_json)
        return LiveTradingSession(
            session_id=1,
            strategy=strategy,
            coordinator=coordinator,
            wallet_address="7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        )

    def test_execute_trade_queues_transaction(self, session, coordinator):
        """Test that _execute_trade queues a transaction."""
        from src.engine.dsl.types import Action, ActionType

        action = Action(type=ActionType.BUY, token="SOL", amount_pct=25.0)
        prices = {"SOL": 100.0}
        timestamp = datetime.now(timezone.utc)

        trade = session._execute_trade(
            action=action,
            prices=prices,
            trigger_id="test_trigger",
            timestamp=timestamp,
        )

        assert trade is not None
        assert coordinator.pending_count == 1
        tx = coordinator.pending_transactions[0]
        assert tx.action_type == "buy"
        assert tx.token_address == "SOL"
        assert tx.amount_pct == 25.0

    def test_execute_trade_records_in_trades_list(self, session, coordinator):
        """Test that trades are recorded."""
        from src.engine.dsl.types import Action, ActionType

        action = Action(type=ActionType.BUY, token="SOL", amount_pct=25.0)
        prices = {"SOL": 100.0}
        timestamp = datetime.now(timezone.utc)

        session._execute_trade(
            action=action,
            prices=prices,
            trigger_id="test_trigger",
            timestamp=timestamp,
        )

        assert len(session.trades) == 1


class TestLiveSessionGetStatus:
    """Tests for get_status method."""

    @pytest.fixture
    def strategy_json(self):
        """Simple strategy for testing."""
        return {
            "id": "status_test",
            "name": "Status Test",
            "description": "Test",
            "version": 1,
            "tokens": ["SOL"],
            "derived_streams": [],
            "triggers": [],
            "risk_rules": {
                "stop_loss_pct": -10,
                "max_position_pct": 50,
                "max_trades_per_day": 10,
                "slippage_limit_bps": 200,
            },
        }

    @pytest.fixture
    def coordinator(self):
        """Create TransactionCoordinator."""
        return TransactionCoordinator(
            safety_guard=SafetyGuard(SafetyConfig()),
            circuit_breaker=CircuitBreaker(failure_threshold=3),
            rpc_url="https://api.mainnet-beta.solana.com",
        )

    @pytest.fixture
    def session(self, strategy_json, coordinator):
        """Create LiveTradingSession."""
        strategy = parse_strategy(strategy_json)
        return LiveTradingSession(
            session_id=1,
            strategy=strategy,
            coordinator=coordinator,
            wallet_address="7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        )

    def test_get_status_returns_dict(self, session):
        """Test that get_status returns a dict."""
        status = session.get_status()

        assert isinstance(status, dict)

    def test_get_status_contains_session_info(self, session):
        """Test that get_status contains session info."""
        status = session.get_status()

        assert status["session_id"] == 1
        assert status["wallet_address"] == "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"

    def test_get_status_contains_positions(self, session):
        """Test that get_status contains positions."""
        session.positions["SOL"] = LivePosition(
            token="SOL",
            quantity=10.0,
            avg_entry_price=100.0,
        )

        status = session.get_status()

        assert "positions" in status
        assert len(status["positions"]) == 1

    def test_get_status_contains_counters(self, session):
        """Test that get_status contains daily counters."""
        session.daily_volume_usd = 1000.0
        session.daily_pnl_usd = 50.0

        status = session.get_status()

        assert status["daily_volume_usd"] == 1000.0
        assert status["daily_pnl_usd"] == 50.0

    def test_get_status_contains_pending_tx_count(self, session, coordinator):
        """Test that get_status contains pending transaction count."""
        # Queue a transaction
        from src.live_trading.state_machine import Transaction

        tx = Transaction(
            session_id=1,
            trigger_id="test",
            action_type="buy",
            token_address="SOL",
            amount_pct=25.0,
        )
        coordinator.queue(tx)

        status = session.get_status()

        assert status["pending_transactions"] == 1

    def test_get_status_contains_trade_count(self, session):
        """Test that get_status contains trade count."""
        # Simulate some trades
        session.trades.append({"trigger_id": "test1"})
        session.trades.append({"trigger_id": "test2"})

        status = session.get_status()

        assert status["trade_count"] == 2
