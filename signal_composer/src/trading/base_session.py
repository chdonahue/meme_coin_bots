"""Base trading session with shared logic for paper and live trading."""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from ..engine.dsl.types import Strategy, Action
from ..engine.dsl.executor import StrategyExecutor
from ..engine.streams.derived import DerivedStreamCalculator

logger = logging.getLogger(__name__)


class BaseTradingSession(ABC):
    """
    Abstract base class for trading sessions.

    This class provides shared logic for both paper trading and live trading:
    - Price buffer management
    - Derived stream computation
    - Trigger evaluation with cooldown
    - Market data construction

    Subclasses must implement:
    - _check_stop_losses: Check and execute stop-loss orders
    - _execute_trade: Execute a trade action
    """

    def __init__(self, session_id: int, strategy: Strategy):
        """
        Initialize a trading session.

        Args:
            session_id: Unique identifier for this session
            strategy: Strategy to execute
        """
        self.session_id = session_id
        self.strategy = strategy

        # Price tracking
        self.price_buffers: dict[str, list[float]] = {}
        self.derived_values: dict[str, dict[str, float]] = {}

        # Trigger state tracking (for cooldown)
        self._trigger_states: dict[str, bool] = {}

        # Internal components
        self._executor = StrategyExecutor(strategy)
        self._derived_calculator = DerivedStreamCalculator()

        # Initialize price buffers for each token
        for token in strategy.tokens:
            self.price_buffers[token] = []

        # Initialize trigger states (all start as False)
        for trigger in strategy.triggers:
            self._trigger_states[trigger.id] = False

    def process_tick(
        self, prices: dict[str, float], timestamp: datetime | None = None
    ) -> list[Any]:
        """
        Process a price tick: update buffers, evaluate triggers, execute trades.

        Args:
            prices: Current prices for each token
            timestamp: Timestamp for this tick (defaults to now)

        Returns:
            List of trades executed during this tick
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        executed_trades: list[Any] = []

        # Update price buffers
        for token in self.strategy.tokens:
            if token in prices:
                self.price_buffers[token].append(prices[token])
                # Keep buffer size reasonable (last 1000 ticks)
                if len(self.price_buffers[token]) > 1000:
                    self.price_buffers[token] = self.price_buffers[token][-1000:]

        # Compute derived streams
        self.derived_values = self._compute_derived_streams()

        # Check stop-losses first
        stop_loss_trades = self._check_stop_losses(prices, timestamp)
        executed_trades.extend(stop_loss_trades)

        # Build market data for executor
        market_data = self._build_market_data(prices)

        # Evaluate strategy triggers
        triggered_actions = self._executor.evaluate(market_data)
        triggered_ids = {t.trigger_id for t in triggered_actions}

        # Execute triggered actions (only on FALSE -> TRUE transition)
        for triggered in triggered_actions:
            was_active = self._trigger_states.get(triggered.trigger_id, False)

            if was_active:
                # Trigger was already active - skip to prevent repeated signals
                logger.debug(f"Trigger '{triggered.trigger_id}' skipped: already active (cooldown)")
                continue

            trade = self._execute_trade(
                action=triggered.action,
                prices=prices,
                trigger_id=triggered.trigger_id,
                timestamp=timestamp,
            )
            if trade is not None:
                executed_trades.append(trade)

        # Update trigger states for next tick
        for trigger in self.strategy.triggers:
            self._trigger_states[trigger.id] = trigger.id in triggered_ids

        return executed_trades

    def _compute_derived_streams(self) -> dict[str, dict[str, float]]:
        """Compute derived stream values from price buffers."""
        result: dict[str, dict[str, float]] = {}

        for stream in self.strategy.derived_streams:
            prices = self.price_buffers.get(stream.token, [])
            if not prices:
                continue

            current_value = self._derived_calculator.calculate(stream, prices)
            if current_value is not None:
                previous = self.derived_values.get(stream.id, {}).get("current")
                result[stream.id] = {
                    "current": current_value,
                    "previous": previous if previous is not None else current_value,
                }

        return result

    def _build_market_data(self, prices: dict[str, float]) -> dict[str, Any]:
        """Build market data dict for strategy executor."""
        market_data: dict[str, Any] = {}

        for token, price in prices.items():
            market_data[token] = {"price": price}

        if self.derived_values:
            market_data["_derived"] = self.derived_values

        return market_data

    @abstractmethod
    def _check_stop_losses(self, prices: dict[str, float], timestamp: datetime) -> list[Any]:
        """
        Check all positions for stop-loss conditions.

        Args:
            prices: Current prices for each token
            timestamp: Current timestamp

        Returns:
            List of stop-loss trades executed
        """
        pass

    @abstractmethod
    def _execute_trade(
        self,
        action: Action,
        prices: dict[str, float],
        trigger_id: str,
        timestamp: datetime,
    ) -> Any | None:
        """
        Execute a trade action.

        Args:
            action: Action to execute
            prices: Current prices for each token
            trigger_id: ID of the trigger that fired
            timestamp: Current timestamp

        Returns:
            Trade record if executed, None if skipped
        """
        pass
