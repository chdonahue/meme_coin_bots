"""Abstract base class for data sources."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class PriceTick:
    """A single price data point."""

    token: str
    price: float
    volume: float | None
    timestamp: datetime
    source: str


@dataclass
class OHLCV:
    """OHLCV candle data."""

    token: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: datetime
    source: str


class DataSource(ABC):
    """Abstract base class for market data sources."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of this data source."""
        ...

    @abstractmethod
    async def get_price(self, token: str) -> PriceTick | None:
        """
        Get current price for a token.

        Args:
            token: Token symbol (e.g., "SOL") or mint address

        Returns:
            PriceTick or None if unavailable
        """
        ...

    @abstractmethod
    async def get_prices(self, tokens: list[str]) -> dict[str, PriceTick]:
        """
        Get current prices for multiple tokens.

        Args:
            tokens: List of token symbols or mint addresses

        Returns:
            Dict mapping token to PriceTick
        """
        ...

    async def health_check(self) -> bool:
        """Check if data source is available."""
        return True
