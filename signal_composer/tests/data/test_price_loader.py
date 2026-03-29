"""Tests for PriceDataLoader."""

import tempfile
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

from src.data.loader import PriceDataLoader


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
