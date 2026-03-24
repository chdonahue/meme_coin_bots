"""Tests for Jupiter data source."""

import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from data.sources.jupiter import JupiterDataSource

# Well-known Solana token addresses
SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


class TestJupiterDataSource:
    @pytest.fixture
    def jupiter_source(self):
        return JupiterDataSource()

    def test_source_name(self, jupiter_source):
        assert jupiter_source.name == "jupiter"

    @pytest.mark.asyncio
    async def test_get_price_returns_tick(self, jupiter_source):
        # Mock the HTTP response
        mock_response = {"data": {SOL_MINT: {"id": SOL_MINT, "price": "150.50"}}}

        with patch.object(jupiter_source, "_fetch_prices", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_response

            tick = await jupiter_source.get_price(SOL_MINT)

            assert tick is not None
            assert tick.token == SOL_MINT
            assert tick.price == 150.50
            assert tick.source == "jupiter"

    @pytest.mark.asyncio
    async def test_get_prices_multiple_tokens(self, jupiter_source):
        mock_response = {
            "data": {
                SOL_MINT: {"id": SOL_MINT, "price": "150.50"},
                USDC_MINT: {"id": USDC_MINT, "price": "1.00"},
            }
        }

        with patch.object(jupiter_source, "_fetch_prices", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_response

            prices = await jupiter_source.get_prices([SOL_MINT, USDC_MINT])

            assert len(prices) == 2
            assert prices[SOL_MINT].price == 150.50
            assert prices[USDC_MINT].price == 1.00

    @pytest.mark.asyncio
    async def test_get_price_not_found(self, jupiter_source):
        mock_response = {"data": {}}

        with patch.object(jupiter_source, "_fetch_prices", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_response

            tick = await jupiter_source.get_price("UNKNOWN_TOKEN")

            assert tick is None
