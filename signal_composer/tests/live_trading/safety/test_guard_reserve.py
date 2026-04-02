"""Tests for reserve protection in SafetyGuard."""

from decimal import Decimal
import pytest

from src.live_trading.safety.guard import SafetyGuard, SafetyConfig


def test_check_reserve_allowed():
    """Trade is allowed when balance covers trade + reserve."""
    guard = SafetyGuard(SafetyConfig())
    result = guard.check_reserve_balance(
        wallet_balance_sol=Decimal("1.000"),
        trade_amount_sol=Decimal("0.500"),
    )
    assert result.allowed is True


def test_check_reserve_reduced():
    """Trade amount is capped when it would dip into reserve."""
    guard = SafetyGuard(SafetyConfig())
    result = guard.check_reserve_balance(
        wallet_balance_sol=Decimal("0.010"),
        trade_amount_sol=Decimal("0.010"),
    )
    # Should succeed but with reduced amount
    assert result.allowed is True
    # The method returns suggested_amount in reason if reduced
    assert "0.008" in result.reason  # Available after reserve


def test_check_reserve_blocked():
    """Trade blocked when balance below reserve."""
    guard = SafetyGuard(SafetyConfig())
    result = guard.check_reserve_balance(
        wallet_balance_sol=Decimal("0.001"),
        trade_amount_sol=Decimal("0.001"),
    )
    assert result.allowed is False
    assert "reserve" in result.reason.lower()
