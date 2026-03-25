"""Tests for portfolio management."""

import sys
from pathlib import Path

import pytest

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from simulation.portfolio import Portfolio, InsufficientFundsError, InsufficientPositionError


class TestPortfolio:
    """Test portfolio state management."""

    def test_initial_balance(self):
        """Portfolio starts with initial cash balance."""
        portfolio = Portfolio(initial_balance=10000.0)

        assert portfolio.cash_balance == 10000.0
        assert portfolio.positions == {}
        assert portfolio.total_value == 10000.0

    def test_buy_creates_position(self):
        """Buying creates a new position."""
        portfolio = Portfolio(initial_balance=10000.0)
        portfolio.execute_buy(token="SOL", amount_usd=1000.0, price=150.0)

        assert "SOL" in portfolio.positions
        assert portfolio.positions["SOL"].quantity == pytest.approx(6.6666, rel=0.01)
        assert portfolio.positions["SOL"].avg_entry_price == 150.0
        assert portfolio.cash_balance == 9000.0

    def test_buy_adds_to_existing_position(self):
        """Buying more of same token updates average entry price."""
        portfolio = Portfolio(initial_balance=10000.0)
        portfolio.execute_buy(token="SOL", amount_usd=1000.0, price=100.0)  # 10 SOL
        portfolio.execute_buy(token="SOL", amount_usd=1000.0, price=200.0)  # 5 SOL

        # 15 SOL total, avg price = (1000 + 1000) / 15 = 133.33
        assert portfolio.positions["SOL"].quantity == pytest.approx(15.0, rel=0.01)
        assert portfolio.positions["SOL"].avg_entry_price == pytest.approx(133.33, rel=0.01)
        assert portfolio.cash_balance == 8000.0

    def test_sell_reduces_position(self):
        """Selling reduces position quantity."""
        portfolio = Portfolio(initial_balance=10000.0)
        portfolio.execute_buy(token="SOL", amount_usd=1500.0, price=150.0)  # 10 SOL
        portfolio.execute_sell(token="SOL", quantity=5.0, price=160.0)  # Sell 5 SOL

        assert portfolio.positions["SOL"].quantity == pytest.approx(5.0)
        assert portfolio.cash_balance == pytest.approx(8500.0 + 800.0)  # 8500 + 5*160

    def test_sell_all_removes_position(self):
        """Selling all removes position from portfolio."""
        portfolio = Portfolio(initial_balance=10000.0)
        portfolio.execute_buy(token="SOL", amount_usd=1000.0, price=100.0)  # 10 SOL
        portfolio.execute_sell_all(token="SOL", price=120.0)  # Sell all at profit

        assert "SOL" not in portfolio.positions
        assert portfolio.cash_balance == pytest.approx(9000.0 + 1200.0)  # Profit!

    def test_total_value_includes_positions(self):
        """Total value = cash + sum of position values."""
        portfolio = Portfolio(initial_balance=10000.0)
        portfolio.execute_buy(token="SOL", amount_usd=3000.0, price=150.0)  # 20 SOL

        # At current price $150: value = 7000 cash + 20*150 = 10000
        assert portfolio.total_value_at_prices({"SOL": 150.0}) == pytest.approx(10000.0)
        # Price goes up to $200: value = 7000 + 20*200 = 11000
        assert portfolio.total_value_at_prices({"SOL": 200.0}) == pytest.approx(11000.0)

    def test_unrealized_pnl(self):
        """Calculate unrealized P&L on positions."""
        portfolio = Portfolio(initial_balance=10000.0)
        portfolio.execute_buy(token="SOL", amount_usd=1000.0, price=100.0)  # 10 SOL

        # Price up 20%
        pnl = portfolio.unrealized_pnl({"SOL": 120.0})
        assert pnl == pytest.approx(200.0)  # 10 * (120 - 100) = 200

    def test_cannot_buy_more_than_cash(self):
        """Cannot buy more than available cash."""
        portfolio = Portfolio(initial_balance=1000.0)

        with pytest.raises(InsufficientFundsError):
            portfolio.execute_buy(token="SOL", amount_usd=2000.0, price=100.0)

    def test_cannot_sell_more_than_owned(self):
        """Cannot sell more than position size."""
        portfolio = Portfolio(initial_balance=10000.0)
        portfolio.execute_buy(token="SOL", amount_usd=1000.0, price=100.0)  # 10 SOL

        with pytest.raises(InsufficientPositionError):
            portfolio.execute_sell(token="SOL", quantity=20.0, price=100.0)

    def test_position_pct(self):
        """Calculate what percentage of portfolio a position represents."""
        portfolio = Portfolio(initial_balance=10000.0)
        portfolio.execute_buy(token="SOL", amount_usd=4000.0, price=100.0)  # 40 SOL

        # At $100, position = 4000, total = 10000, pct = 40%
        assert portfolio.position_pct("SOL", {"SOL": 100.0}) == pytest.approx(40.0)
