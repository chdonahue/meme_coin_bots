"""Tests for PriceDataLoader."""

import tempfile
import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.data.loader import PriceDataLoader
from src.data.sources.base import OHLCV


class TestCacheKey:
    """Test cache key generation."""

    def test_cache_key_format(self):
        """Cache key follows {token}_{interval}_{days}d_{date} format."""
        loader = PriceDataLoader()

        with patch("src.data.loader.date") as mock_date:
            mock_date.today.return_value = date(2025, 3, 27)
            key = loader._build_cache_key("SOL", "1H", 30)

        assert key == "SOL_1H_30d_2025-03-27"

    def test_cache_key_different_params(self):
        """Different parameters produce different keys."""
        loader = PriceDataLoader()

        with patch("src.data.loader.date") as mock_date:
            mock_date.today.return_value = date(2025, 3, 27)
            key1 = loader._build_cache_key("SOL", "1H", 30)
            key2 = loader._build_cache_key("SOL", "1H", 7)
            key3 = loader._build_cache_key("USDC", "1H", 30)

        assert key1 != key2
        assert key1 != key3


class TestCacheOperations:
    """Test cache read/write operations."""

    def test_cache_path_created(self):
        """Cache directory is created if missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "new_cache"
            loader = PriceDataLoader(cache_dir=str(cache_dir))
            loader._ensure_cache_dir()
            assert cache_dir.exists()

    def test_write_and_read_cache(self):
        """Data can be written and read from cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = PriceDataLoader(cache_dir=tmpdir)
            test_data = [{"price": 100.0, "timestamp": "2025-03-27T00:00:00Z"}]

            loader._write_cache("test_key", test_data)
            result = loader._read_cache("test_key")

            assert result == test_data

    def test_read_missing_cache_returns_none(self):
        """Reading missing cache file returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = PriceDataLoader(cache_dir=tmpdir)
            result = loader._read_cache("nonexistent_key")
            assert result is None

    def test_read_corrupt_cache_returns_none(self):
        """Reading corrupt cache file returns None and deletes file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = PriceDataLoader(cache_dir=tmpdir)
            cache_file = Path(tmpdir) / "corrupt_key.json"
            cache_file.write_text("not valid json {{{")

            result = loader._read_cache("corrupt_key")

            assert result is None
            assert not cache_file.exists()


class TestDataTransformation:
    """Test OHLCV to backtest format transformation."""

    def test_transform_ohlcv_to_backtest_format(self):
        """OHLCV candles are transformed to backtest format."""
        loader = PriceDataLoader()
        ohlcv_data = [
            OHLCV(
                token="So11111111111111111111111111111111111111112",
                open=180.0,
                high=185.0,
                low=178.0,
                close=183.5,
                volume=1000000,
                timestamp=datetime(2025, 3, 27, 12, 0, tzinfo=timezone.utc),
                source="birdeye",
            ),
            OHLCV(
                token="So11111111111111111111111111111111111111112",
                open=183.5,
                high=190.0,
                low=182.0,
                close=188.0,
                volume=1200000,
                timestamp=datetime(2025, 3, 27, 13, 0, tzinfo=timezone.utc),
                source="birdeye",
            ),
        ]

        result = loader._transform_to_backtest_format(ohlcv_data, "SOL")

        assert len(result) == 2
        assert result[0]["SOL"] == 183.5  # close price
        assert result[0]["timestamp"] == datetime(2025, 3, 27, 12, 0, tzinfo=timezone.utc)
        assert result[1]["SOL"] == 188.0
        assert result[1]["timestamp"] == datetime(2025, 3, 27, 13, 0, tzinfo=timezone.utc)

    def test_transform_empty_list(self):
        """Empty OHLCV list returns empty result."""
        loader = PriceDataLoader()
        result = loader._transform_to_backtest_format([], "SOL")
        assert result == []
