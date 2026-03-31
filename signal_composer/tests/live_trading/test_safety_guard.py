"""Tests for SafetyGuard."""

import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from src.live_trading.safety.guard import SafetyConfig, SafetyGuard


class TestSafetyConfig:
    """Tests for SafetyConfig."""

    def test_default_config(self):
        """Test default safety configuration."""
        config = SafetyConfig()
        assert config.max_trade_usd == Decimal("500")
        assert config.max_daily_usd == Decimal("2000")
        assert config.max_daily_loss_usd == Decimal("500")
        assert config.min_trade_interval_sec == 30
        assert config.max_concurrent_txs == 3


class TestSafetyGuard:
    """Tests for SafetyGuard."""

    @pytest.fixture
    def guard(self):
        """Create a SafetyGuard with default config."""
        return SafetyGuard(SafetyConfig())

    def test_check_trade_size_within_limit(self, guard):
        """Trade within limit should pass."""
        result = guard.check_trade_size(Decimal("100"))
        assert result.allowed
        assert result.reason == ""

    def test_check_trade_size_exceeds_limit(self, guard):
        """Trade exceeding limit should fail."""
        result = guard.check_trade_size(Decimal("600"))
        assert not result.allowed
        assert "exceeds max" in result.reason.lower()

    def test_check_daily_volume_within_limit(self, guard):
        """Daily volume within limit should pass."""
        result = guard.check_daily_volume(
            current_daily_usd=Decimal("1000"),
            proposed_trade_usd=Decimal("500"),
        )
        assert result.allowed

    def test_check_daily_volume_exceeds_limit(self, guard):
        """Daily volume exceeding limit should fail."""
        result = guard.check_daily_volume(
            current_daily_usd=Decimal("1800"),
            proposed_trade_usd=Decimal("500"),
        )
        assert not result.allowed
        assert "daily limit" in result.reason.lower()

    def test_check_daily_loss_within_limit(self, guard):
        """Daily loss within limit should pass."""
        result = guard.check_daily_loss(current_daily_loss_usd=Decimal("400"))
        assert result.allowed

    def test_check_daily_loss_exceeds_limit(self, guard):
        """Daily loss exceeding limit should fail."""
        result = guard.check_daily_loss(current_daily_loss_usd=Decimal("600"))
        assert not result.allowed
        assert "daily loss" in result.reason.lower()

    def test_check_trade_interval_ok(self, guard):
        """Trade after minimum interval should pass."""
        last_trade = datetime.now(timezone.utc) - timedelta(seconds=60)
        result = guard.check_trade_interval(last_trade)
        assert result.allowed

    def test_check_trade_interval_too_soon(self, guard):
        """Trade before minimum interval should fail."""
        last_trade = datetime.now(timezone.utc)
        result = guard.check_trade_interval(last_trade)
        assert not result.allowed
        assert "interval" in result.reason.lower()

    def test_check_concurrent_txs_within_limit(self, guard):
        """Concurrent txs within limit should pass."""
        result = guard.check_concurrent_txs(current_count=2)
        assert result.allowed

    def test_check_concurrent_txs_at_limit(self, guard):
        """Concurrent txs at limit should fail."""
        result = guard.check_concurrent_txs(current_count=3)
        assert not result.allowed
        assert "concurrent" in result.reason.lower()
