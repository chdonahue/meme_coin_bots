"""Portfolio management for paper trading."""

from dataclasses import dataclass, field
from typing import Dict


class InsufficientFundsError(Exception):
    """Raised when trying to buy with insufficient cash."""

    pass


class InsufficientPositionError(Exception):
    """Raised when trying to sell more than owned."""

    pass


@dataclass
class Position:
    """A token position in the portfolio."""

    token: str
    quantity: float
    avg_entry_price: float
    total_cost: float = 0.0

    def __post_init__(self):
        if self.total_cost == 0.0:
            self.total_cost = self.quantity * self.avg_entry_price

    def add(self, quantity: float, price: float) -> None:
        """Add to position, updating average entry price."""
        new_cost = quantity * price
        self.total_cost += new_cost
        self.quantity += quantity
        self.avg_entry_price = self.total_cost / self.quantity

    def remove(self, quantity: float) -> float:
        """Remove from position. Returns cost basis of removed shares."""
        if quantity > self.quantity:
            raise InsufficientPositionError(
                f"Cannot sell {quantity} {self.token}, only have {self.quantity}"
            )
        cost_basis = quantity * self.avg_entry_price
        self.quantity -= quantity
        self.total_cost -= cost_basis
        return cost_basis

    def value_at(self, price: float) -> float:
        """Current value at given price."""
        return self.quantity * price

    def unrealized_pnl_at(self, price: float) -> float:
        """Unrealized P&L at given price."""
        return self.value_at(price) - self.total_cost


@dataclass
class Portfolio:
    """Paper trading portfolio tracking positions and cash."""

    initial_balance: float
    cash_balance: float = field(init=False)
    positions: Dict[str, Position] = field(default_factory=dict)
    realized_pnl: float = 0.0

    def __post_init__(self):
        self.cash_balance = self.initial_balance

    @property
    def total_value(self) -> float:
        """Total portfolio value at entry prices (no mark-to-market)."""
        position_value = sum(p.total_cost for p in self.positions.values())
        return self.cash_balance + position_value

    def total_value_at_prices(self, prices: Dict[str, float]) -> float:
        """Total portfolio value at current market prices."""
        position_value = sum(
            p.value_at(prices.get(p.token, p.avg_entry_price)) for p in self.positions.values()
        )
        return self.cash_balance + position_value

    def unrealized_pnl(self, prices: Dict[str, float]) -> float:
        """Total unrealized P&L across all positions."""
        return sum(
            p.unrealized_pnl_at(prices.get(p.token, p.avg_entry_price))
            for p in self.positions.values()
        )

    def position_pct(self, token: str, prices: Dict[str, float]) -> float:
        """Percentage of portfolio in a given token."""
        if token not in self.positions:
            return 0.0
        total = self.total_value_at_prices(prices)
        if total == 0:
            return 0.0
        position_value = self.positions[token].value_at(prices[token])
        return (position_value / total) * 100

    def execute_buy(self, token: str, amount_usd: float, price: float) -> float:
        """
        Buy token with USD amount.

        Returns: quantity purchased
        Raises: InsufficientFundsError if not enough cash
        """
        if amount_usd > self.cash_balance:
            raise InsufficientFundsError(
                f"Cannot buy ${amount_usd}, only have ${self.cash_balance}"
            )

        quantity = amount_usd / price
        self.cash_balance -= amount_usd

        if token in self.positions:
            self.positions[token].add(quantity, price)
        else:
            self.positions[token] = Position(
                token=token,
                quantity=quantity,
                avg_entry_price=price,
            )

        return quantity

    def execute_sell(self, token: str, quantity: float, price: float) -> float:
        """
        Sell specific quantity of token.

        Returns: USD proceeds
        Raises: InsufficientPositionError if not enough tokens
        """
        if token not in self.positions:
            raise InsufficientPositionError(f"No position in {token}")

        position = self.positions[token]
        cost_basis = position.remove(quantity)
        proceeds = quantity * price
        self.cash_balance += proceeds
        self.realized_pnl += proceeds - cost_basis

        # Remove position if fully sold
        if position.quantity <= 0:
            del self.positions[token]

        return proceeds

    def execute_sell_all(self, token: str, price: float) -> float:
        """
        Sell entire position in token.

        Returns: USD proceeds
        """
        if token not in self.positions:
            return 0.0

        quantity = self.positions[token].quantity
        return self.execute_sell(token, quantity, price)
