import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
import os

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from data.sources.birdeye import BirdeyeDataSource

SOL_MINT = "So11111111111111111111111111111111111111112"


class TestBirdeyeDataSource:
    @pytest.fixture
    def birdeye_source(self):
        # Use test API key
        return BirdeyeDataSource(api_key="test_key")

    def test_source_name(self, birdeye_source):
        assert birdeye_source.name == "birdeye"

    @pytest.mark.asyncio
    async def test_get_price_returns_tick(self, birdeye_source):
        mock_response = {
            "success": True,
            "data": {
                "value": 150.50,
                "updateUnixTime": 1700000000,
            },
        }

        with patch.object(birdeye_source, "_fetch_price", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_response

            tick = await birdeye_source.get_price(SOL_MINT)

            assert tick is not None
            assert tick.price == 150.50
            assert tick.source == "birdeye"

    @pytest.mark.asyncio
    async def test_get_ohlcv(self, birdeye_source):
        from data.sources.base import OHLCV

        mock_response = {
            "success": True,
            "data": {
                "items": [
                    {
                        "o": 100.0,
                        "h": 110.0,
                        "l": 95.0,
                        "c": 105.0,
                        "v": 1000000,
                        "unixTime": 1700000000,
                    }
                ]
            },
        }

        with patch.object(birdeye_source, "_fetch_ohlcv", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_response

            candles = await birdeye_source.get_ohlcv(SOL_MINT, interval="1m", limit=1)

            assert len(candles) == 1
            assert candles[0].open == 100.0
            assert candles[0].close == 105.0

    @pytest.mark.asyncio
    async def test_api_failure_returns_empty(self, birdeye_source):
        with patch.object(birdeye_source, "_fetch_price", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = Exception("API Error")

            tick = await birdeye_source.get_price(SOL_MINT)

            assert tick is None
