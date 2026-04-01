"""Tests for TransactionCoordinator."""

import pytest
from unittest.mock import AsyncMock

from src.live_trading.coordinator import TransactionCoordinator
from src.live_trading.state_machine import Transaction
from src.live_trading.safety.guard import SafetyConfig, SafetyGuard
from src.live_trading.safety.circuit_breaker import CircuitBreaker


class TestTransactionCoordinator:
    """Tests for TransactionCoordinator."""

    @pytest.fixture
    def coordinator(self):
        """Create TransactionCoordinator."""
        return TransactionCoordinator(
            safety_guard=SafetyGuard(SafetyConfig()),
            circuit_breaker=CircuitBreaker(failure_threshold=3),
            rpc_url="https://api.mainnet-beta.solana.com",
        )

    def test_queue_transaction(self, coordinator):
        """Test queuing a transaction."""
        tx = Transaction(
            session_id=1,
            trigger_id="buy_dip",
            action_type="buy",
            token_address="So11111111111111111111111111111111111111112",
            amount_pct=25.0,
        )

        coordinator.queue(tx)

        assert len(coordinator.pending_transactions) == 1
        assert coordinator.pending_transactions[0].id == tx.id

    def test_queue_blocked_by_circuit_breaker(self, coordinator):
        """Test that circuit breaker blocks new transactions."""
        # Trip the breaker
        for _ in range(3):
            coordinator.circuit_breaker.record_failure("test")

        tx = Transaction(
            session_id=1,
            trigger_id="buy_dip",
            action_type="buy",
            token_address="So11111111111111111111111111111111111111112",
            amount_pct=25.0,
        )

        with pytest.raises(RuntimeError, match="Circuit breaker"):
            coordinator.queue(tx)

    def test_get_transaction_by_id(self, coordinator):
        """Test retrieving a transaction by ID."""
        tx = Transaction(
            session_id=1,
            trigger_id="buy_dip",
            action_type="buy",
            token_address="So11111111111111111111111111111111111111112",
            amount_pct=25.0,
        )
        coordinator.queue(tx)

        found = coordinator.get_transaction(tx.id)

        assert found is not None
        assert found.id == tx.id

    def test_get_pending_count(self, coordinator):
        """Test getting count of pending transactions."""
        for i in range(3):
            tx = Transaction(
                session_id=1,
                trigger_id=f"trigger_{i}",
                action_type="buy",
                token_address="So11111111111111111111111111111111111111112",
                amount_pct=10.0,
            )
            coordinator.queue(tx)

        assert coordinator.pending_count == 3

    def test_get_transaction_not_found(self, coordinator):
        """Test retrieving a non-existent transaction returns None."""
        from uuid import uuid4

        found = coordinator.get_transaction(uuid4())

        assert found is None

    def test_get_transaction_from_active(self, coordinator):
        """Test retrieving a transaction from active transactions."""
        tx = Transaction(
            session_id=1,
            trigger_id="buy_dip",
            action_type="buy",
            token_address="So11111111111111111111111111111111111111112",
            amount_pct=25.0,
        )
        # Directly add to active transactions (simulating in-progress tx)
        coordinator.active_transactions[tx.id] = tx

        found = coordinator.get_transaction(tx.id)

        assert found is not None
        assert found.id == tx.id

    def test_set_callbacks(self, coordinator):
        """Test setting callbacks."""

        async def on_confirmed(tx: Transaction):
            pass

        async def on_failed(tx: Transaction):
            pass

        coordinator.set_callbacks(on_confirmed=on_confirmed, on_failed=on_failed)

        assert coordinator._on_confirmed is on_confirmed
        assert coordinator._on_failed is on_failed

    def test_set_callbacks_partial(self, coordinator):
        """Test setting only some callbacks."""

        async def on_confirmed(tx: Transaction):
            pass

        coordinator.set_callbacks(on_confirmed=on_confirmed)

        assert coordinator._on_confirmed is on_confirmed
        assert coordinator._on_failed is None

    @pytest.mark.asyncio
    async def test_close_without_services(self, coordinator):
        """Test closing coordinator when services are not initialized."""
        # Should not raise any errors
        await coordinator.close()

    @pytest.mark.asyncio
    async def test_close_with_services(self, coordinator):
        """Test closing coordinator cleans up services."""
        # Initialize mock services
        mock_swap_service = AsyncMock()
        mock_tx_submitter = AsyncMock()
        mock_confirm_monitor = AsyncMock()

        coordinator._swap_service = mock_swap_service
        coordinator._tx_submitter = mock_tx_submitter
        coordinator._confirm_monitor = mock_confirm_monitor

        await coordinator.close()

        mock_swap_service.close.assert_called_once()
        mock_tx_submitter.close.assert_called_once()
        mock_confirm_monitor.close.assert_called_once()

    def test_queue_multiple_transactions(self, coordinator):
        """Test queuing multiple transactions."""
        tx_ids = []
        for i in range(5):
            tx = Transaction(
                session_id=1,
                trigger_id=f"trigger_{i}",
                action_type="buy" if i % 2 == 0 else "sell",
                token_address="So11111111111111111111111111111111111111112",
                amount_pct=10.0,
            )
            coordinator.queue(tx)
            tx_ids.append(tx.id)

        assert coordinator.pending_count == 5
        # Verify all can be retrieved
        for tx_id in tx_ids:
            assert coordinator.get_transaction(tx_id) is not None

    def test_initial_state(self, coordinator):
        """Test coordinator initializes with empty state."""
        assert coordinator.pending_count == 0
        assert len(coordinator.pending_transactions) == 0
        assert len(coordinator.active_transactions) == 0
        assert len(coordinator.completed_transactions) == 0
        assert coordinator._swap_service is None
        assert coordinator._tx_submitter is None
        assert coordinator._confirm_monitor is None
        assert coordinator._on_confirmed is None
        assert coordinator._on_failed is None
