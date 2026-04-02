"""Tests for reserve protection logic."""

from decimal import Decimal
import pytest

from src.wallets.reserve import RESERVE_SOL, get_available_capital


def test_reserve_constant():
    """Reserve is 0.002 SOL."""
    assert RESERVE_SOL == Decimal("0.002")


def test_available_capital_normal():
    """Available capital is balance minus reserve."""
    balance = Decimal("1.500")
    available = get_available_capital(balance)
    assert available == Decimal("1.498")


def test_available_capital_exact_reserve():
    """Balance equals reserve means zero available."""
    balance = Decimal("0.002")
    available = get_available_capital(balance)
    assert available == Decimal("0")


def test_available_capital_below_reserve():
    """Balance below reserve returns zero, not negative."""
    balance = Decimal("0.001")
    available = get_available_capital(balance)
    assert available == Decimal("0")


def test_available_capital_zero_balance():
    """Zero balance returns zero available."""
    balance = Decimal("0")
    available = get_available_capital(balance)
    assert available == Decimal("0")
