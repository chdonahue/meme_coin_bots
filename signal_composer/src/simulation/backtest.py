"""Backtesting engine for strategy simulation."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from engine.dsl.types import Strategy, DerivedStream
from engine.dsl.executor import StrategyExecutor
from engine.streams.derived import DerivedStreamCalculator
from simulation.portfolio import Portfolio
from simulation.executor import PaperTradeExecutor, TradeRecord
from simulation.metrics import PerformanceCalculator


# Window to ticks mapping for derived stream calculations
WINDOW_TO_TICKS = {
    "1m": 2,
    "5m": 10,
    "15m": 30,
    "1h": 120,
    "4h": 480,
    "1d": 2880,
}


@dataclass
class BacktestResult:
    """Results from a backtest run."""

    total_return_pct: float
    sharpe_ratio: Optional[float]
    max_drawdown_pct: float
    trade_count: int
    win_rate: float
    equity_curve: List[float]
    trades: List[TradeRecord]
    final_portfolio: Portfolio


@dataclass
class BacktestEngine:
    """
    Backtesting engine that replays price history through a strategy.

    Attributes:
        initial_capital: Starting capital for the simulation
        slippage_bps: Slippage in basis points (100 = 1%)
    """

    initial_capital: float = 10000.0
    slippage_bps: int = 100

    def run(self, strategy: Strategy, price_history: List[Dict[str, float]]) -> BacktestResult:
        """
        Run a backtest simulation.

        Args:
            strategy: Strategy to test
            price_history: List of price snapshots, each a dict mapping token to price

        Returns:
            BacktestResult with performance metrics and trade history
        """
        # Initialize portfolio and executor
        portfolio = Portfolio(initial_balance=self.initial_capital)
        executor = PaperTradeExecutor(
            portfolio=portfolio,
            slippage_bps=self.slippage_bps,
            risk_rules=strategy.risk_rules,
        )
        strategy_executor = StrategyExecutor(strategy)
        derived_calculator = DerivedStreamCalculator()

        # Track state
        trades: List[TradeRecord] = []
        equity_curve: List[float] = []
        price_buffers: Dict[str, List[float]] = {token: [] for token in strategy.tokens}
        derived_values: Dict[str, Dict[str, float]] = (
            {}
        )  # {stream_id: {"current": x, "previous": y}}

        # Base timestamp for simulation
        base_timestamp = datetime(2024, 1, 1, 0, 0, 0)

        # Process each price tick
        for tick_idx, prices in enumerate(price_history):
            timestamp = base_timestamp + timedelta(minutes=tick_idx)

            # Update price buffers for each token
            for token in strategy.tokens:
                if token in prices:
                    price_buffers[token].append(prices[token])

            # Compute derived streams
            derived_values = self._compute_derived_streams(
                strategy.derived_streams,
                price_buffers,
                derived_values,
                derived_calculator,
            )

            # Build market data for executor
            market_data = self._build_market_data(prices, derived_values)

            # Evaluate strategy triggers
            triggered_actions = strategy_executor.evaluate(market_data)

            # Execute triggered actions
            for triggered in triggered_actions:
                trade = executor.execute(
                    action=triggered.action,
                    prices=prices,
                    trigger_id=triggered.trigger_id,
                    timestamp=timestamp,
                )
                if trade is not None:
                    trades.append(trade)

            # Record equity at current prices
            equity = portfolio.total_value_at_prices(prices)
            equity_curve.append(equity)

        # Compute performance metrics
        performance = self._compute_performance(
            portfolio=portfolio,
            equity_curve=equity_curve,
            trades=trades,
            final_prices=price_history[-1] if price_history else {},
        )

        return BacktestResult(
            total_return_pct=performance["total_return_pct"],
            sharpe_ratio=performance["sharpe_ratio"],
            max_drawdown_pct=performance["max_drawdown_pct"],
            trade_count=performance["trade_count"],
            win_rate=performance["win_rate"],
            equity_curve=equity_curve,
            trades=trades,
            final_portfolio=portfolio,
        )

    def _compute_derived_streams(
        self,
        derived_streams: List[DerivedStream],
        price_buffers: Dict[str, List[float]],
        previous_values: Dict[str, Dict[str, float]],
        calculator: DerivedStreamCalculator,
    ) -> Dict[str, Dict[str, float]]:
        """
        Compute derived stream values on-the-fly.

        Args:
            derived_streams: List of derived stream definitions
            price_buffers: Historical prices for each token
            previous_values: Previous derived values (for crossover detection)
            calculator: DerivedStreamCalculator instance

        Returns:
            Dict mapping stream_id to {"current": value, "previous": value}
        """
        result: Dict[str, Dict[str, float]] = {}

        for stream in derived_streams:
            # Get price buffer for this token
            prices = price_buffers.get(stream.token, [])

            if not prices:
                continue

            # Calculate current value
            current_value = calculator.calculate(stream, prices)

            if current_value is not None:
                # Get previous value if available
                previous = previous_values.get(stream.id, {}).get("current")

                result[stream.id] = {
                    "current": current_value,
                    "previous": previous if previous is not None else current_value,
                }

        return result

    def _build_market_data(
        self,
        prices: Dict[str, float],
        derived_values: Dict[str, Dict[str, float]],
    ) -> Dict[str, Any]:
        """
        Build market data dict for strategy executor.

        Args:
            prices: Current token prices
            derived_values: Computed derived stream values

        Returns:
            Market data dict in format expected by ConditionEvaluator
        """
        market_data: Dict[str, Any] = {}

        # Add token prices
        for token, price in prices.items():
            market_data[token] = {
                "price": price,
            }

        # Add derived streams
        if derived_values:
            market_data["_derived"] = derived_values

        return market_data

    def _compute_performance(
        self,
        portfolio: Portfolio,
        equity_curve: List[float],
        trades: List[TradeRecord],
        final_prices: Dict[str, float],
    ) -> Dict[str, Any]:
        """
        Compute performance metrics from backtest results.

        Args:
            portfolio: Final portfolio state
            equity_curve: Equity values over time
            trades: List of executed trades
            final_prices: Final price snapshot

        Returns:
            Dict with performance metrics
        """
        calc = PerformanceCalculator(initial_value=self.initial_capital)

        # Get final value
        final_value = (
            portfolio.total_value_at_prices(final_prices) if final_prices else portfolio.total_value
        )

        # Compute daily returns for Sharpe ratio
        daily_returns = calc.daily_returns_from_equity(equity_curve)

        return {
            "total_return_pct": calc.total_return_pct(final_value),
            "sharpe_ratio": calc.sharpe_ratio(daily_returns) if len(daily_returns) >= 2 else None,
            "max_drawdown_pct": calc.max_drawdown(equity_curve),
            "trade_count": calc.trade_count(trades),
            "win_rate": calc.win_rate(trades),
        }
