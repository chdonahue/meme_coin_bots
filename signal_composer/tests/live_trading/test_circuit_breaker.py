"""Tests for CircuitBreaker."""

import pytest
from datetime import datetime, timezone
from src.live_trading.safety.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    @pytest.fixture
    def breaker(self):
        """Create a CircuitBreaker with threshold of 3."""
        return CircuitBreaker(failure_threshold=3)

    def test_initial_state_closed(self, breaker):
        """Circuit should start closed (allowing trades)."""
        assert breaker.state == CircuitState.CLOSED
        assert breaker.allows_trade()

    def test_single_failure_stays_closed(self, breaker):
        """Single failure should not trip breaker."""
        breaker.record_failure("tx_dropped")
        assert breaker.state == CircuitState.CLOSED
        assert breaker.allows_trade()

    def test_consecutive_failures_trips_breaker(self, breaker):
        """3 consecutive failures should trip breaker."""
        breaker.record_failure("tx_dropped")
        breaker.record_failure("tx_timeout")
        breaker.record_failure("slippage_exceeded")

        assert breaker.state == CircuitState.OPEN
        assert not breaker.allows_trade()
        assert breaker.tripped_at is not None

    def test_success_resets_failure_count(self, breaker):
        """Success should reset consecutive failure count."""
        breaker.record_failure("tx_dropped")
        breaker.record_failure("tx_timeout")
        breaker.record_success()
        breaker.record_failure("tx_dropped")

        assert breaker.state == CircuitState.CLOSED
        assert breaker.consecutive_failures == 1

    def test_manual_reset(self, breaker):
        """Manual reset should close the circuit."""
        breaker.record_failure("tx_dropped")
        breaker.record_failure("tx_timeout")
        breaker.record_failure("slippage_exceeded")
        assert breaker.state == CircuitState.OPEN

        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.allows_trade()
        assert breaker.consecutive_failures == 0
