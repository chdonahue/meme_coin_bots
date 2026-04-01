"""Paper trading session with real-time execution."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..engine.dsl.types import Strategy, Action, ActionType
from ..trading.base_session import BaseTradingSession

logger = logging.getLogger(__name__)


@dataclass
class LivePosition:
    """A position in a paper trading session."""

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
        self.avg_entry_price = self.total_cost / self.quantity if self.quantity > 0 else 0

    def remove(self, quantity: float) -> float:
        """Remove from position. Returns cost basis of removed shares."""
        cost_basis = quantity * self.avg_entry_price
        self.quantity -= quantity
        self.total_cost -= cost_basis
        return cost_basis

    def value_at(self, price: float) -> float:
        """Current value at given price."""
        return self.quantity * price

    def pnl_pct(self, price: float) -> float:
        """Current P&L percentage."""
        if self.avg_entry_price == 0:
            return 0.0
        return ((price - self.avg_entry_price) / self.avg_entry_price) * 100


@dataclass
class LiveTrade:
    """A trade executed in a paper trading session."""

    trigger_id: str
    token: str
    action: str
    quantity: float
    price_at_exec: float
    timestamp: datetime


class PaperTradingSession(BaseTradingSession):
    """
    In-memory paper trading session that tracks positions and executes trades.

    This class handles the business logic for paper trading:
    - Maintaining positions and cash balance
    - Evaluating strategy triggers against price data
    - Executing trades with slippage
    - Enforcing risk rules (stop-loss, max position, daily limits)
    """

    def __init__(
        self,
        session_id: int,
        strategy: Strategy,
        initial_capital: float = 10000.0,
        slippage_bps: int = 100,
    ):
        """
        Initialize a paper trading session.

        Args:
            session_id: Unique identifier for this session
            strategy: Strategy to execute
            initial_capital: Starting cash balance
            slippage_bps: Slippage in basis points
        """
        super().__init__(session_id=session_id, strategy=strategy)

        self.initial_capital = initial_capital
        self.slippage_bps = slippage_bps

        # State
        self.cash_balance = initial_capital
        self.positions: dict[str, LivePosition] = {}
        self.trades: list[LiveTrade] = []

        # Internal
        self._daily_trade_counts: dict[str, int] = {}

    @property
    def total_value(self) -> float:
        """Total portfolio value at entry prices."""
        position_value = sum(p.total_cost for p in self.positions.values())
        return self.cash_balance + position_value

    def total_value_at_prices(self, prices: dict[str, float]) -> float:
        """Total portfolio value at current market prices."""
        position_value = sum(
            p.value_at(prices.get(p.token, p.avg_entry_price)) for p in self.positions.values()
        )
        return self.cash_balance + position_value

    def _check_stop_losses(self, prices: dict[str, float], timestamp: datetime) -> list[LiveTrade]:
        """Check all positions for stop-loss conditions."""
        trades: list[LiveTrade] = []
        stop_loss_pct = self.strategy.risk_rules.stop_loss_pct

        for token, position in list(self.positions.items()):
            if token not in prices:
                continue

            current_price = prices[token]
            pnl_pct = position.pnl_pct(current_price)

            if pnl_pct <= stop_loss_pct:
                # Execute stop-loss sell
                quantity = position.quantity
                exec_price = current_price * (1 - self.slippage_bps / 10000.0)

                # Update cash and remove position
                proceeds = quantity * exec_price
                self.cash_balance += proceeds
                del self.positions[token]

                trade = LiveTrade(
                    trigger_id="stop_loss",
                    token=token,
                    action="sell_all",
                    quantity=quantity,
                    price_at_exec=exec_price,
                    timestamp=timestamp,
                )
                self.trades.append(trade)
                trades.append(trade)

        return trades

    def _execute_trade(
        self,
        action: Action,
        prices: dict[str, float],
        trigger_id: str,
        timestamp: datetime,
    ) -> LiveTrade | None:
        """Execute a trade action."""
        return self._execute_action(action, prices, trigger_id, timestamp)

    def _execute_action(
        self,
        action: Action,
        prices: dict[str, float],
        trigger_id: str,
        timestamp: datetime,
    ) -> LiveTrade | None:
        """Execute a trade action."""
        action_type = action.type.value

        # Check daily trade limit
        date_key = timestamp.strftime("%Y-%m-%d")
        daily_count = self._daily_trade_counts.get(date_key, 0)
        if daily_count >= self.strategy.risk_rules.max_trades_per_day:
            logger.info(
                f"Trade SKIPPED [{trigger_id}]: daily limit reached "
                f"({daily_count}/{self.strategy.risk_rules.max_trades_per_day})"
            )
            return None

        # Check slippage limit
        if self.slippage_bps > self.strategy.risk_rules.slippage_limit_bps:
            logger.info(
                f"Trade SKIPPED [{trigger_id}]: slippage too high "
                f"({self.slippage_bps} > {self.strategy.risk_rules.slippage_limit_bps} bps)"
            )
            return None

        if action.token not in prices:
            logger.info(f"Trade SKIPPED [{trigger_id}]: no price data for {action.token}")
            return None

        is_buy = action.type == ActionType.BUY
        base_price = prices[action.token]

        # Apply slippage
        if is_buy:
            exec_price = base_price * (1 + self.slippage_bps / 10000.0)
        else:
            exec_price = base_price * (1 - self.slippage_bps / 10000.0)

        if is_buy:
            quantity, skip_reason = self._calculate_buy_quantity(action, prices, exec_price)
            if quantity <= 0:
                logger.info(
                    f"Trade SKIPPED [{trigger_id}]: {action_type} {action.token} - {skip_reason}"
                )
                return None

            # Execute buy
            amount_usd = quantity * exec_price
            self.cash_balance -= amount_usd

            if action.token in self.positions:
                self.positions[action.token].add(quantity, exec_price)
            else:
                self.positions[action.token] = LivePosition(
                    token=action.token,
                    quantity=quantity,
                    avg_entry_price=exec_price,
                )
        else:
            # Sell or sell_all
            quantity, skip_reason = self._calculate_sell_quantity(action)
            if quantity <= 0:
                logger.info(
                    f"Trade SKIPPED [{trigger_id}]: {action_type} {action.token} - {skip_reason}"
                )
                return None

            # Execute sell
            position = self.positions[action.token]
            position.remove(quantity)
            proceeds = quantity * exec_price
            self.cash_balance += proceeds

            # Remove position if fully sold
            if position.quantity <= 0:
                del self.positions[action.token]

        # Record trade
        trade = LiveTrade(
            trigger_id=trigger_id,
            token=action.token,
            action=action.type.value,
            quantity=quantity,
            price_at_exec=exec_price,
            timestamp=timestamp,
        )
        self.trades.append(trade)
        self._daily_trade_counts[date_key] = daily_count + 1

        return trade

    def _calculate_buy_quantity(
        self, action: Action, prices: dict[str, float], exec_price: float
    ) -> tuple[float, str]:
        """Calculate quantity to buy, respecting risk rules. Returns (quantity, skip_reason)."""
        total_value = self.total_value_at_prices(prices)

        # Determine requested amount
        if action.amount_pct is not None:
            requested_usd = total_value * (action.amount_pct / 100.0)
        elif action.amount_fixed is not None:
            requested_usd = action.amount_fixed
        else:
            return 0.0, "no amount specified"

        original_requested = requested_usd

        # Apply max_position_pct limit
        max_position_usd = total_value * (self.strategy.risk_rules.max_position_pct / 100.0)
        current_position_usd = 0.0
        if action.token in self.positions:
            current_position_usd = self.positions[action.token].value_at(prices[action.token])
        max_additional_usd = max_position_usd - current_position_usd

        if max_additional_usd <= 0:
            return 0.0, f"max position limit reached ({self.strategy.risk_rules.max_position_pct}%)"

        requested_usd = min(requested_usd, max_additional_usd)

        # Cap at available cash
        if self.cash_balance <= 0:
            return 0.0, "no cash available"

        requested_usd = min(requested_usd, self.cash_balance)

        if requested_usd <= 0:
            return 0.0, "insufficient funds after limits applied"

        return requested_usd / exec_price, ""

    def _calculate_sell_quantity(self, action: Action) -> tuple[float, str]:
        """Calculate quantity to sell. Returns (quantity, skip_reason)."""
        if action.token not in self.positions:
            return 0.0, "no position to sell"

        position = self.positions[action.token]

        if action.type == ActionType.SELL_ALL:
            return position.quantity, ""

        if action.amount_pct is not None:
            return position.quantity * (action.amount_pct / 100.0), ""
        elif action.amount_fixed is not None:
            return min(action.amount_fixed, position.quantity), ""

        return 0.0, "no amount specified"

    def get_status(self, prices: dict[str, float]) -> dict[str, Any]:
        """Get current session status."""
        total_value = self.total_value_at_prices(prices)
        return {
            "session_id": self.session_id,
            "initial_capital": self.initial_capital,
            "cash_balance": self.cash_balance,
            "total_value": total_value,
            "pnl_pct": ((total_value - self.initial_capital) / self.initial_capital) * 100,
            "positions": {
                token: {
                    "quantity": pos.quantity,
                    "avg_entry_price": pos.avg_entry_price,
                    "current_value": pos.value_at(prices.get(token, pos.avg_entry_price)),
                    "pnl_pct": pos.pnl_pct(prices.get(token, pos.avg_entry_price)),
                }
                for token, pos in self.positions.items()
            },
            "trade_count": len(self.trades),
        }
