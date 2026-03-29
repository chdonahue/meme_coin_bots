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
