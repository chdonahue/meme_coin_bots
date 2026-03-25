"""Paper trade executor with slippage and risk rules."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

from engine.dsl.types import Action, ActionType, RiskRules
from simulation.portfolio import Portfolio


@dataclass
class TradeRecord:
    """Record of an executed trade."""

    action: ActionType
    token: str
    amount: float
    price_at_exec: float
    timestamp: datetime
    trigger_id: str
    slippage_bps: int


@dataclass
class PaperTradeExecutor:
    """
    Executes paper trades with slippage simulation and risk rule enforcement.

    Attributes:
        portfolio: The portfolio to execute trades on
        slippage_bps: Slippage in basis points (100 = 1%)
        risk_rules: Optional risk management rules
    """

    portfolio: Portfolio
    slippage_bps: int = 100
    risk_rules: Optional[RiskRules] = None
    _daily_trade_counts: Dict[str, int] = field(default_factory=dict)

    def _apply_slippage(self, price: float, is_buy: bool) -> float:
        """
        Apply slippage to price.

        For buys: price increases (worse execution)
        For sells: price decreases (worse execution)
        """
        slippage_multiplier = self.slippage_bps / 10000.0
        if is_buy:
            return price * (1 + slippage_multiplier)
        else:
            return price * (1 - slippage_multiplier)

    def _check_slippage_limit(self) -> bool:
        """
        Check if executor's slippage is within risk rule limits.

        Returns True if slippage is acceptable, False otherwise.
        """
        if self.risk_rules is None:
            return True
        return self.slippage_bps <= self.risk_rules.slippage_limit_bps

    def _get_date_key(self, timestamp: datetime) -> str:
        """Get date string key for tracking daily trades."""
        return timestamp.strftime("%Y-%m-%d")

    def _check_daily_limit(self, timestamp: datetime) -> bool:
        """
        Check if we've exceeded daily trade limit.

        Returns True if trade is allowed, False if limit exceeded.
        """
        if self.risk_rules is None:
            return True

        date_key = self._get_date_key(timestamp)
        current_count = self._daily_trade_counts.get(date_key, 0)
        return current_count < self.risk_rules.max_trades_per_day

    def _increment_daily_count(self, timestamp: datetime) -> None:
        """Increment the trade count for the given day."""
        date_key = self._get_date_key(timestamp)
        self._daily_trade_counts[date_key] = self._daily_trade_counts.get(date_key, 0) + 1

    def _calculate_buy_amount(
        self, action: Action, prices: Dict[str, float], exec_price: float
    ) -> float:
        """
        Calculate the USD amount to buy, respecting max_position_pct.

        Returns the quantity of tokens to purchase.
        """
        # Determine requested amount in USD
        if action.amount_pct is not None:
            requested_usd = self.portfolio.total_value_at_prices(prices) * (
                action.amount_pct / 100.0
            )
        elif action.amount_fixed is not None:
            requested_usd = action.amount_fixed
        else:
            # Default to 0 if no amount specified
            return 0.0

        # Apply max_position_pct limit if risk rules exist
        if self.risk_rules is not None:
            max_position_usd = self.portfolio.total_value_at_prices(prices) * (
                self.risk_rules.max_position_pct / 100.0
            )
            # Check current position value
            current_position_usd = 0.0
            if action.token in self.portfolio.positions:
                current_position_usd = self.portfolio.positions[action.token].value_at(
                    prices[action.token]
                )
            # Cap at remaining room to max position
            max_additional_usd = max_position_usd - current_position_usd
            requested_usd = min(requested_usd, max_additional_usd)

        # Cap at available cash
        requested_usd = min(requested_usd, self.portfolio.cash_balance)

        # Don't allow negative amounts
        if requested_usd <= 0:
            return 0.0

        # Return quantity of tokens at execution price
        return requested_usd / exec_price

    def _calculate_sell_quantity(self, action: Action) -> float:
        """
        Calculate quantity of tokens to sell.

        For SELL: uses amount_pct of current position
        For SELL_ALL: sells entire position
        """
        if action.token not in self.portfolio.positions:
            return 0.0

        position = self.portfolio.positions[action.token]

        if action.type == ActionType.SELL_ALL:
            return position.quantity

        if action.amount_pct is not None:
            return position.quantity * (action.amount_pct / 100.0)
        elif action.amount_fixed is not None:
            # Fixed amount means fixed quantity of tokens
            return min(action.amount_fixed, position.quantity)

        return 0.0

    def execute(
        self,
        action: Action,
        prices: Dict[str, float],
        trigger_id: str,
        timestamp: datetime,
    ) -> Optional[TradeRecord]:
        """
        Execute a trade action with slippage and risk rule checks.

        Args:
            action: The Action to execute (buy/sell/sell_all)
            prices: Current token prices
            trigger_id: ID of the trigger that fired this action
            timestamp: Execution timestamp

        Returns:
            TradeRecord if trade executed, None if skipped due to risk rules
        """
        # Check slippage limit
        if not self._check_slippage_limit():
            return None

        # Check daily trade limit
        if not self._check_daily_limit(timestamp):
            return None

        # Determine if this is a buy or sell
        is_buy = action.type == ActionType.BUY

        # Get token price and apply slippage
        if action.token not in prices:
            return None
        base_price = prices[action.token]
        exec_price = self._apply_slippage(base_price, is_buy)

        # Calculate trade amount
        if is_buy:
            quantity = self._calculate_buy_amount(action, prices, exec_price)
            if quantity <= 0:
                return None
            # Execute the buy
            amount_usd = quantity * exec_price
            self.portfolio.execute_buy(token=action.token, amount_usd=amount_usd, price=exec_price)
        else:
            # Sell or Sell_all
            quantity = self._calculate_sell_quantity(action)
            if quantity <= 0:
                return None
            # Execute the sell
            self.portfolio.execute_sell(token=action.token, quantity=quantity, price=exec_price)

        # Increment daily trade count
        self._increment_daily_count(timestamp)

        return TradeRecord(
            action=action.type,
            token=action.token,
            amount=quantity,
            price_at_exec=exec_price,
            timestamp=timestamp,
            trigger_id=trigger_id,
            slippage_bps=self.slippage_bps,
        )
