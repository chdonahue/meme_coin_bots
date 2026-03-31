"""Tests for Jupiter SwapService."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

from src.live_trading.services.jupiter import SwapQuote, SwapService


class TestSwapQuote:
    """Tests for SwapQuote dataclass."""

    def test_quote_not_expired(self):
        """Fresh quote should not be expired."""
        quote = SwapQuote(
            input_mint="So11111111111111111111111111111111111111112",
            output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            in_amount=1_000_000_000,
            out_amount=100_000_000,
            price_impact_pct=0.1,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
            route_plan=[],
            swap_transaction="base64_tx_data",
        )
        assert not quote.is_expired

    def test_quote_expired(self):
        """Old quote should be expired."""
        quote = SwapQuote(
            input_mint="So11111111111111111111111111111111111111112",
            output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            in_amount=1_000_000_000,
            out_amount=100_000_000,
            price_impact_pct=0.1,
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),
            route_plan=[],
            swap_transaction="base64_tx_data",
        )
        assert quote.is_expired


class TestSwapService:
    """Tests for SwapService."""

    @pytest.fixture
    def service(self):
        """Create SwapService."""
        return SwapService()

    @pytest.mark.asyncio
    async def test_get_quote_success(self, service):
        """Test getting a quote from Jupiter."""
        mock_response = {
            "inputMint": "So11111111111111111111111111111111111111112",
            "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "inAmount": "1000000000",
            "outAmount": "100000000",
            "priceImpactPct": "0.1",
            "routePlan": [],
        }

        mock_swap_response = {
            "swapTransaction": "base64_encoded_transaction_data",
        }

        with patch.object(service, "_fetch_quote", new_callable=AsyncMock) as mock_quote:
            with patch.object(service, "_fetch_swap_tx", new_callable=AsyncMock) as mock_swap:
                mock_quote.return_value = mock_response
                mock_swap.return_value = mock_swap_response

                quote = await service.get_quote(
                    input_mint="So11111111111111111111111111111111111111112",
                    output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    amount=1_000_000_000,
                    slippage_bps=100,
                )

                assert quote is not None
                assert quote.in_amount == 1_000_000_000
                assert quote.out_amount == 100_000_000
                assert not quote.is_expired

    @pytest.mark.asyncio
    async def test_get_quote_no_route(self, service):
        """Test handling no route found."""
        with patch.object(service, "_fetch_quote", new_callable=AsyncMock) as mock_quote:
            mock_quote.return_value = None

            quote = await service.get_quote(
                input_mint="invalid_mint",
                output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                amount=1_000_000_000,
                slippage_bps=100,
            )

            assert quote is None

    @pytest.mark.asyncio
    async def test_get_quote_with_user_public_key(self, service):
        """Test getting a quote with user public key includes swap transaction."""
        mock_response = {
            "inputMint": "So11111111111111111111111111111111111111112",
            "outputMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            "inAmount": "1000000000",
            "outAmount": "100000000",
            "priceImpactPct": "0.1",
            "routePlan": [],
        }

        mock_swap_response = {
            "swapTransaction": "base64_encoded_transaction_data",
        }

        with patch.object(service, "_fetch_quote", new_callable=AsyncMock) as mock_quote:
            with patch.object(service, "_fetch_swap_tx", new_callable=AsyncMock) as mock_swap:
                mock_quote.return_value = mock_response
                mock_swap.return_value = mock_swap_response

                quote = await service.get_quote(
                    input_mint="So11111111111111111111111111111111111111112",
                    output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    amount=1_000_000_000,
                    slippage_bps=100,
                    user_public_key="TestPublicKey123",
                )

                assert quote is not None
                assert quote.swap_transaction == "base64_encoded_transaction_data"
                mock_swap.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_client(self, service):
        """Test closing the HTTP client."""
        # First create a client
        await service._get_client()
        assert service._client is not None

        # Close it
        await service.close()
        assert service._client is None
