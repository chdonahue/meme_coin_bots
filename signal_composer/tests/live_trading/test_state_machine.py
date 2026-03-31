"""Tests for transaction state machine."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from src.live_trading.state_machine import (
    TransactionState,
    VALID_TRANSITIONS,
    can_transition,
    Transaction,
)


class TestTransactionState:
    """Tests for TransactionState enum."""

    def test_all_states_defined(self):
        """Verify all expected states exist."""
        expected = [
            "PENDING",
            "QUOTING",
            "SIGNING",
            "SUBMITTED",
            "CONFIRMING",
            "CONFIRMED",
            "DROPPED",
            "TIMEOUT",
            "QUOTE_FAILED",
            "QUOTE_EXPIRED",
            "RETRY_CHECK",
            "TRADE_STALE",
            "MAX_RETRY",
        ]
        actual = [s.name for s in TransactionState]
        assert set(expected) == set(actual)

    def test_terminal_states(self):
        """Terminal states should be identified."""
        terminal = [
            TransactionState.CONFIRMED,
            TransactionState.QUOTE_FAILED,
            TransactionState.TRADE_STALE,
            TransactionState.MAX_RETRY,
        ]
        for state in terminal:
            assert state.is_terminal

    def test_non_terminal_states(self):
        """Non-terminal states should not be marked terminal."""
        non_terminal = [
            TransactionState.PENDING,
            TransactionState.QUOTING,
            TransactionState.SUBMITTED,
        ]
        for state in non_terminal:
            assert not state.is_terminal


class TestTransitions:
    """Tests for state transitions."""

    def test_pending_to_quoting_valid(self):
        """PENDING -> QUOTING is valid."""
        assert can_transition(TransactionState.PENDING, TransactionState.QUOTING)

    def test_quoting_to_signing_valid(self):
        """QUOTING -> SIGNING is valid."""
        assert can_transition(TransactionState.QUOTING, TransactionState.SIGNING)

    def test_quoting_to_quote_failed_valid(self):
        """QUOTING -> QUOTE_FAILED is valid."""
        assert can_transition(TransactionState.QUOTING, TransactionState.QUOTE_FAILED)

    def test_submitted_to_confirming_valid(self):
        """SUBMITTED -> CONFIRMING is valid."""
        assert can_transition(TransactionState.SUBMITTED, TransactionState.CONFIRMING)

    def test_invalid_transition_fails(self):
        """Invalid transitions should return False."""
        assert not can_transition(TransactionState.PENDING, TransactionState.CONFIRMED)
        assert not can_transition(TransactionState.CONFIRMED, TransactionState.PENDING)

    def test_terminal_state_has_no_transitions(self):
        """Terminal states have no valid outgoing transitions."""
        for state in [TransactionState.CONFIRMED, TransactionState.MAX_RETRY]:
            assert state not in VALID_TRANSITIONS or len(VALID_TRANSITIONS[state]) == 0


class TestTransaction:
    """Tests for Transaction class."""

    def test_create_transaction(self):
        """Test creating a new transaction."""
        tx = Transaction(
            session_id=1,
            trigger_id="buy_dip",
            action_type="buy",
            token_address="So11111111111111111111111111111111111111112",
            amount_pct=25.0,
        )
        assert tx.state == TransactionState.PENDING
        assert tx.retry_count == 0
        assert tx.id is not None

    def test_transition_updates_state(self):
        """Test that transition updates state and history."""
        tx = Transaction(
            session_id=1,
            trigger_id="buy_dip",
            action_type="buy",
            token_address="So11111111111111111111111111111111111111112",
            amount_pct=25.0,
        )

        tx.transition_to(TransactionState.QUOTING)
        assert tx.state == TransactionState.QUOTING
        assert len(tx.state_history) == 1
        assert tx.state_history[0]["from"] == "PENDING"
        assert tx.state_history[0]["to"] == "QUOTING"

    def test_invalid_transition_raises(self):
        """Invalid transition should raise ValueError."""
        tx = Transaction(
            session_id=1,
            trigger_id="buy_dip",
            action_type="buy",
            token_address="So11111111111111111111111111111111111111112",
            amount_pct=25.0,
        )

        with pytest.raises(ValueError, match="Invalid transition"):
            tx.transition_to(TransactionState.CONFIRMED)
