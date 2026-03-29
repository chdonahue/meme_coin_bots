"""Price data loader with caching."""

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

from src.data.sources.base import OHLCV
from src.data.sources.birdeye import BirdeyeDataSource
from src.data.tokens import get_mint_address


class PriceDataLoader:
    """Load price data with file-based caching."""

    def __init__(self, cache_dir: str = ".cache/ohlcv"):
        self.cache_dir = Path(cache_dir)
        self._birdeye: BirdeyeDataSource | None = None

    def _build_cache_key(self, token: str, interval: str, days: int) -> str:
        """Build cache key from parameters."""
        today = date.today().isoformat()
        return f"{token}_{interval}_{days}d_{today}"

    def _ensure_cache_dir(self) -> None:
        """Create cache directory if it doesn't exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, key: str) -> Path:
        """Get file path for cache key."""
        return self.cache_dir / f"{key}.json"

    def _read_cache(self, key: str) -> list[dict] | None:
        """Read data from cache file."""
        path = self._cache_path(key)
        if not path.exists():
            return None

        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            # Corrupt file - delete and return None
            path.unlink(missing_ok=True)
            return None

    def _write_cache(self, key: str, data: list[dict]) -> None:
        """Write data to cache file."""
        self._ensure_cache_dir()
        path = self._cache_path(key)
        with open(path, "w") as f:
            json.dump(data, f)

    def _transform_to_backtest_format(
        self, ohlcv_data: list[OHLCV], token_symbol: str
    ) -> list[dict]:
        """
        Transform OHLCV candles to backtest engine format.

        Args:
            ohlcv_data: List of OHLCV candles from Birdeye
            token_symbol: Token symbol (e.g., "SOL")

        Returns:
            List of dicts with {token_symbol: close_price, timestamp: datetime}
        """
        return [
            {
                token_symbol: candle.close,
                "timestamp": candle.timestamp,
            }
            for candle in ohlcv_data
        ]

    def _get_birdeye(self) -> BirdeyeDataSource:
        """Get or create Birdeye data source."""
        if self._birdeye is None:
            self._birdeye = BirdeyeDataSource()
        return self._birdeye

    def _serialize_for_cache(self, data: list[dict]) -> list[dict]:
        """Serialize data for JSON cache (convert datetime to ISO string)."""
        result = []
        for item in data:
            serialized = {}
            for key, value in item.items():
                if isinstance(value, datetime):
                    serialized[key] = value.isoformat()
                else:
                    serialized[key] = value
            result.append(serialized)
        return result

    def _deserialize_from_cache(self, data: list[dict]) -> list[dict]:
        """Deserialize data from JSON cache (convert ISO string to datetime)."""
        result = []
        for item in data:
            deserialized = {}
            for key, value in item.items():
                if key == "timestamp" and isinstance(value, str):
                    deserialized[key] = datetime.fromisoformat(value)
                else:
                    deserialized[key] = value
            result.append(deserialized)
        return result

    async def load_price_history(
        self,
        token_symbol: str,
        interval: str = "1H",
        days: int = 30,
    ) -> tuple[list[dict], str]:
        """
        Load price history for a token.

        Args:
            token_symbol: Token symbol (e.g., "SOL")
            interval: Candle interval (1H, 4H, 1D)
            days: Number of days of history

        Returns:
            Tuple of (price_history, data_source)
            - price_history: List of {token: price, timestamp: datetime}
            - data_source: "cache" or "birdeye"

        Raises:
            ValueError: If token unknown or no data available
        """
        # Resolve token symbol to mint address
        mint_address = get_mint_address(token_symbol)
        if mint_address is None:
            raise ValueError(f"Unknown token: {token_symbol}")

        # Check cache first
        cache_key = self._build_cache_key(token_symbol, interval, days)
        cached_data = self._read_cache(cache_key)
        if cached_data is not None:
            return self._deserialize_from_cache(cached_data), "cache"

        # Fetch from Birdeye
        birdeye = self._get_birdeye()
        # Calculate limit: candles per day depends on interval
        candles_per_day = {"1H": 24, "4H": 6, "1D": 1}.get(interval, 24)
        limit = days * candles_per_day

        ohlcv_data = await birdeye.get_ohlcv(mint_address, interval, limit)

        if not ohlcv_data:
            raise ValueError(f"No price data available for {token_symbol}")

        # Transform to backtest format
        price_history = self._transform_to_backtest_format(ohlcv_data, token_symbol)

        # Cache the result
        self._write_cache(cache_key, self._serialize_for_cache(price_history))

        return price_history, "birdeye"

    async def close(self) -> None:
        """Close any open connections."""
        if self._birdeye is not None:
            await self._birdeye.close()
            self._birdeye = None
