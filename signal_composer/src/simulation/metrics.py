"""Performance metrics calculator for paper trading simulation."""

from dataclasses import dataclass
from typing import Dict, List, Optional

from engine.dsl.types import ActionType
from simulation.executor import TradeRecord


@dataclass
class PerformanceSnapshot:
    """Complete snapshot of performance metrics at a point in time."""

    total_return_pct: float
    sharpe_ratio: Optional[float]
    max_drawdown_pct: float
    win_rate: float
    trade_count: int


@dataclass
class PerformanceCalculator:
    """
    Calculator for portfolio performance metrics.

    Attributes:
        initial_value: Starting portfolio value for calculating returns
    """

    initial_value: float

    def total_return_pct(self, current_value: float) -> float:
        """
        Calculate total percentage return.

        Args:
            current_value: Current portfolio value

        Returns:
            Percentage return (e.g., 20.0 for 20% gain)
        """
        if self.initial_value == 0:
            return 0.0
        return ((current_value - self.initial_value) / self.initial_value) * 100.0

    def sharpe_ratio(
        self,
        daily_returns: List[float],
        risk_free_rate: float = 0.0,
        annualize: bool = True,
    ) -> Optional[float]:
        """
        Calculate Sharpe ratio (risk-adjusted returns).

        Args:
            daily_returns: List of daily returns as decimals (e.g., 0.01 for 1%)
            risk_free_rate: Risk-free rate as decimal (annualized if annualize=True)
            annualize: If True, annualize using sqrt(252)

        Returns:
            Sharpe ratio, or None if insufficient data
        """
        if len(daily_returns) < 2:
            return None

        # Calculate mean daily return
        mean_return = sum(daily_returns) / len(daily_returns)

        # Calculate daily risk-free rate if annualizing
        if annualize:
            daily_rf = risk_free_rate / 252.0
        else:
            daily_rf = risk_free_rate

        # Calculate excess return
        excess_return = mean_return - daily_rf

        # Calculate standard deviation of returns
        variance = sum((r - mean_return) ** 2 for r in daily_returns) / len(daily_returns)
        std_dev = variance**0.5

        if std_dev == 0:
            # No volatility - return large positive value if positive returns
            return float("inf") if excess_return > 0 else 0.0

        # Calculate Sharpe ratio
        sharpe = excess_return / std_dev

        # Annualize if requested
        if annualize:
            sharpe *= 252**0.5

        return sharpe

    def max_drawdown(self, equity_curve: List[float]) -> float:
        """
        Calculate maximum peak-to-trough drawdown.

        Args:
            equity_curve: List of equity values over time

        Returns:
            Maximum drawdown as negative percentage (e.g., -25.0 for 25% drawdown)
        """
        if len(equity_curve) < 2:
            return 0.0

        running_peak = equity_curve[0]
        max_dd = 0.0

        for value in equity_curve:
            if value > running_peak:
                running_peak = value

            if running_peak > 0:
                drawdown = (value - running_peak) / running_peak * 100.0
                if drawdown < max_dd:
                    max_dd = drawdown

        return max_dd

    def win_rate(self, trades: List[TradeRecord]) -> float:
        """
        Calculate percentage of profitable round-trip trades.

        Matches buy/sell pairs by token and compares sell price to average entry price.

        Args:
            trades: List of TradeRecord objects

        Returns:
            Win rate as percentage (e.g., 50.0 for 50%)
        """
        if not trades:
            return 0.0

        # Track positions by token: {token: [(quantity, price), ...]}
        positions: Dict[str, List[tuple]] = {}
        wins = 0
        total_round_trips = 0

        for trade in trades:
            token = trade.token

            if trade.action == ActionType.BUY:
                # Add to position
                if token not in positions:
                    positions[token] = []
                positions[token].append((trade.amount, trade.price_at_exec))

            elif trade.action in (ActionType.SELL, ActionType.SELL_ALL):
                # Calculate round-trip result
                if token not in positions or not positions[token]:
                    continue

                # Calculate average entry price for this token
                total_cost = sum(qty * price for qty, price in positions[token])
                total_qty = sum(qty for qty, _ in positions[token])

                if total_qty == 0:
                    continue

                avg_entry_price = total_cost / total_qty

                # Compare sell price to average entry
                if trade.price_at_exec > avg_entry_price:
                    wins += 1
                total_round_trips += 1

                # Remove sold quantity from position (simplified: remove all for this round-trip)
                sell_qty = trade.amount
                remaining = []
                for qty, price in positions[token]:
                    if sell_qty >= qty:
                        sell_qty -= qty
                    elif sell_qty > 0:
                        remaining.append((qty - sell_qty, price))
                        sell_qty = 0
                    else:
                        remaining.append((qty, price))
                positions[token] = remaining

        if total_round_trips == 0:
            return 0.0

        return (wins / total_round_trips) * 100.0

    def trade_count(self, trades: List[TradeRecord]) -> int:
        """
        Count total number of trades.

        Args:
            trades: List of TradeRecord objects

        Returns:
            Total trade count
        """
        return len(trades)

    def daily_returns_from_equity(self, equity_curve: List[float]) -> List[float]:
        """
        Convert equity curve to daily returns.

        Args:
            equity_curve: List of equity values over time

        Returns:
            List of daily returns as decimals (e.g., 0.05 for 5%)
        """
        if len(equity_curve) < 2:
            return []

        returns = []
        for i in range(1, len(equity_curve)):
            if equity_curve[i - 1] != 0:
                daily_return = (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
                returns.append(daily_return)
            else:
                returns.append(0.0)

        return returns

    def snapshot(
        self,
        current_value: float,
        equity_curve: List[float],
        trades: List[TradeRecord],
        risk_free_rate: float = 0.0,
    ) -> PerformanceSnapshot:
        """
        Generate complete performance snapshot with all metrics.

        Args:
            current_value: Current portfolio value
            equity_curve: List of equity values over time
            trades: List of TradeRecord objects
            risk_free_rate: Risk-free rate for Sharpe calculation (annualized)

        Returns:
            PerformanceSnapshot with all metrics
        """
        daily_returns = self.daily_returns_from_equity(equity_curve)

        return PerformanceSnapshot(
            total_return_pct=self.total_return_pct(current_value),
            sharpe_ratio=self.sharpe_ratio(daily_returns, risk_free_rate, annualize=True),
            max_drawdown_pct=self.max_drawdown(equity_curve),
            win_rate=self.win_rate(trades),
            trade_count=self.trade_count(trades),
        )
