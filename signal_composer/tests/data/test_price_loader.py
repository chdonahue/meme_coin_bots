"""Tests for PriceDataLoader."""

from datetime import date
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
