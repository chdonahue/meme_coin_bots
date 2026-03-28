"""Price data loader with caching."""

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

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
