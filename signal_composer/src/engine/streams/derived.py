"""Derived stream calculations (MA, EMA, RSI, etc.)."""

import statistics
from typing import Sequence

from ..dsl.types import DerivedStream, DerivedStreamType


def moving_average(prices: Sequence[float], window: int) -> float | None:
    """
    Calculate simple moving average.

    Args:
        prices: List of prices (oldest first)
        window: Number of periods to average

    Returns:
        Moving average or None if no data
    """
    if not prices:
        return None

    # Use available data if less than window
    data = prices[-window:] if len(prices) >= window else prices
    return statistics.mean(data)


def ema(prices: Sequence[float], window: int) -> float | None:
    """
    Calculate exponential moving average.

    Args:
        prices: List of prices (oldest first)
        window: Number of periods for EMA

    Returns:
        EMA value or None if no data
    """
    if not prices:
        return None

    multiplier = 2 / (window + 1)
    ema_value = prices[0]

    for price in prices[1:]:
        ema_value = (price * multiplier) + (ema_value * (1 - multiplier))

    return ema_value


def rsi(prices: Sequence[float], periods: int = 14) -> float | None:
    """
    Calculate Relative Strength Index.

    Args:
        prices: List of prices (oldest first)
        periods: RSI period (typically 14)

    Returns:
        RSI value (0-100) or None if insufficient data
    """
    if len(prices) < periods + 1:
        return None

    # Calculate price changes
    changes = [prices[i] - prices[i - 1] for i in range(1, len(prices))]

    # Separate gains and losses
    gains = [max(0, c) for c in changes]
    losses = [abs(min(0, c)) for c in changes]

    # Calculate average gain/loss over period
    avg_gain = statistics.mean(gains[-periods:])
    avg_loss = statistics.mean(losses[-periods:])

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def volatility(prices: Sequence[float]) -> float:
    """
    Calculate price volatility (standard deviation).

    Args:
        prices: List of prices

    Returns:
        Standard deviation of prices
    """
    if len(prices) < 2:
        return 0.0

    return statistics.stdev(prices)


def price_delta(prices: Sequence[float], window: int) -> float | None:
    """
    Calculate price change over window.

    Args:
        prices: List of prices (oldest first)
        window: Number of periods to look back

    Returns:
        Price change (current - past) or None if insufficient data
    """
    if len(prices) < window:
        return None

    return prices[-1] - prices[-window]


class DerivedStreamCalculator:
    """Calculate derived stream values from price data."""

    def calculate(self, stream: DerivedStream, prices: Sequence[float]) -> float | None:
        """
        Calculate a derived stream value.

        Args:
            stream: Derived stream definition
            prices: Historical price data

        Returns:
            Calculated value or None if insufficient data
        """
        window_sizes = {
            "1m": 1,
            "5m": 5,
            "15m": 15,
            "1h": 60,
            "4h": 240,
            "1d": 1440,
        }

        window = window_sizes.get(stream.window.value, 60) if stream.window else 60

        match stream.type:
            case DerivedStreamType.MOVING_AVERAGE:
                return moving_average(prices, window)
            case DerivedStreamType.EMA:
                return ema(prices, window)
            case DerivedStreamType.RSI:
                periods = stream.periods or 14
                return rsi(prices, periods)
            case DerivedStreamType.VOLATILITY:
                return volatility(prices[-window:] if len(prices) >= window else prices)
            case DerivedStreamType.PRICE_DELTA:
                return price_delta(prices, window)
            case _:
                return None
