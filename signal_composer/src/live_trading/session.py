"""Live trading session implementation."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..trading.base_session import BaseTradingSession
from ..engine.dsl.types import Strategy, Action
from .coordinator import TransactionCoordinator
from .state_machine import Transaction

logger = logging.getLogger(__name__)


@dataclass
class LivePosition:
    """A position held in live trading."""

    token: str
    quantity: float
    avg_entry_price: float
    stop_loss_pending: bool = False

    def pnl_pct(self, current_price: float) -> float:
        """
        Calculate percentage PnL for this position.

        Args:
            current_price: Current price of the token

        Returns:
            Percentage change from entry price
        """
        return ((current_price - self.avg_entry_price) / self.avg_entry_price) * 100

    def value_at(self, current_price: float) -> float:
        """
        Calculate current value of the position.

        Args:
            current_price: Current price of the token

        Returns:
            Current value (quantity * current_price)
        """
        return self.quantity * current_price


class LiveTradingSession(BaseTradingSession):
    """
    Live trading session that executes real trades via TransactionCoordinator.

    Extends BaseTradingSession with:
    - Position tracking
    - Stop-loss enforcement
    - Trade execution via coordinator
    - Daily volume and PnL tracking
    """

    def __init__(
        self,
        session_id: int,
        strategy: Strategy,
        coordinator: TransactionCoordinator,
        wallet_address: str,
    ):
        """
        Initialize a live trading session.

        Args:
            session_id: Unique identifier for this session
            strategy: Strategy to execute
            coordinator: TransactionCoordinator for executing trades
            wallet_address: Wallet address for this session
        """
        super().__init__(session_id, strategy)

        self.coordinator = coordinator
        self.wallet_address = wallet_address

        # Position tracking
        self.positions: dict[str, LivePosition] = {}

        # Daily counters (reset at UTC midnight)
        self.daily_volume_usd: float = 0.0
        self.daily_pnl_usd: float = 0.0

        # Trade history
        self.trades: list[dict[str, Any]] = []

    def _check_stop_losses(self, prices: dict[str, float], timestamp: datetime) -> list[Any]:
        """
        Check all positions for stop-loss conditions.

        Args:
            prices: Current prices for each token
            timestamp: Current timestamp

        Returns:
            List of stop-loss trades queued
        """
        stop_loss_trades: list[dict[str, Any]] = []
        stop_loss_pct = self.strategy.risk_rules.stop_loss_pct

        for token, position in self.positions.items():
            if token not in prices:
                continue

            # Skip if stop-loss already pending
            if position.stop_loss_pending:
                continue

            current_price = prices[token]
            pnl_pct = position.pnl_pct(current_price)

            # Check if stop-loss should trigger
            if pnl_pct <= stop_loss_pct:
                logger.warning(
                    f"Stop-loss triggered for {token}: {pnl_pct:.2f}% " f"<= {stop_loss_pct}%"
                )

                # Queue a sell_all transaction
                tx = Transaction(
                    session_id=self.session_id,
                    trigger_id=f"stop_loss_{token}",
                    action_type="sell_all",
                    token_address=token,
                    amount_pct=100.0,
                )

                try:
                    self.coordinator.queue(tx)
                    position.stop_loss_pending = True

                    trade_record = {
                        "trigger_id": f"stop_loss_{token}",
                        "action_type": "sell_all",
                        "token": token,
                        "price": current_price,
                        "pnl_pct": pnl_pct,
                        "timestamp": timestamp.isoformat(),
                        "transaction_id": str(tx.id),
                    }
                    self.trades.append(trade_record)
                    stop_loss_trades.append(trade_record)
                except RuntimeError as e:
                    logger.error(f"Failed to queue stop-loss: {e}")

        return stop_loss_trades

    def _execute_trade(
        self,
        action: Action,
        prices: dict[str, float],
        trigger_id: str,
        timestamp: datetime,
    ) -> dict[str, Any] | None:
        """
        Execute a trade action via the coordinator.

        Args:
            action: Action to execute
            prices: Current prices for each token
            trigger_id: ID of the trigger that fired
            timestamp: Current timestamp

        Returns:
            Trade record if queued, None if skipped
        """
        # Build the transaction
        tx = Transaction(
            session_id=self.session_id,
            trigger_id=trigger_id,
            action_type=action.type.value,
            token_address=action.token,
            amount_pct=action.amount_pct or 100.0,
        )

        try:
            self.coordinator.queue(tx)
        except RuntimeError as e:
            logger.error(f"Failed to queue trade: {e}")
            return None

        # Record the trade
        current_price = prices.get(action.token, 0.0)
        trade_record = {
            "trigger_id": trigger_id,
            "action_type": action.type.value,
            "token": action.token,
            "amount_pct": action.amount_pct,
            "price": current_price,
            "timestamp": timestamp.isoformat(),
            "transaction_id": str(tx.id),
        }
        self.trades.append(trade_record)

        logger.info(
            f"Queued trade: {action.type.value} {action.token} "
            f"({action.amount_pct}%) at ${current_price}"
        )

        return trade_record

    def get_status(self) -> dict[str, Any]:
        """
        Get current session status.

        Returns:
            Dict containing session status information
        """
        # Build positions info
        positions_info = []
        for token, position in self.positions.items():
            positions_info.append(
                {
                    "token": position.token,
                    "quantity": position.quantity,
                    "avg_entry_price": position.avg_entry_price,
                    "stop_loss_pending": position.stop_loss_pending,
                }
            )

        return {
            "session_id": self.session_id,
            "wallet_address": self.wallet_address,
            "strategy_id": self.strategy.id,
            "positions": positions_info,
            "daily_volume_usd": self.daily_volume_usd,
            "daily_pnl_usd": self.daily_pnl_usd,
            "trade_count": len(self.trades),
            "pending_transactions": self.coordinator.pending_count,
        }
