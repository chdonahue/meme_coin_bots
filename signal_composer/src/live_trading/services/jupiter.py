"""Jupiter Aggregator integration for swaps."""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any
import httpx
import logging

logger = logging.getLogger(__name__)

JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_URL = "https://quote-api.jup.ag/v6/swap"
QUOTE_TTL_SECONDS = 30


@dataclass
class SwapQuote:
    """Quote from Jupiter for a swap."""

    input_mint: str
    output_mint: str
    in_amount: int
    out_amount: int
    price_impact_pct: float
    expires_at: datetime
    route_plan: list[dict[str, Any]]
    swap_transaction: str

    @property
    def is_expired(self) -> bool:
        """Check if quote has expired."""
        return datetime.now(timezone.utc) > self.expires_at


class SwapService:
    """Jupiter Aggregator swap service."""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _fetch_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int,
    ) -> dict[str, Any] | None:
        """Fetch quote from Jupiter API."""
        client = await self._get_client()
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": str(amount),
            "slippageBps": slippage_bps,
        }
        try:
            response = await client.get(JUPITER_QUOTE_URL, params=params)
            if response.status_code == 200:
                return response.json()
            logger.warning(f"Jupiter quote failed: {response.status_code}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Jupiter quote request error: {e}")
            return None
        except ValueError as e:  # Includes JSONDecodeError
            logger.error(f"Jupiter quote JSON decode error: {e}")
            return None

    async def _fetch_swap_tx(
        self,
        quote_response: dict[str, Any],
        user_public_key: str,
    ) -> dict[str, Any] | None:
        """Fetch swap transaction from Jupiter API."""
        client = await self._get_client()
        payload = {
            "quoteResponse": quote_response,
            "userPublicKey": user_public_key,
            "wrapAndUnwrapSol": True,
        }
        try:
            response = await client.post(JUPITER_SWAP_URL, json=payload)
            if response.status_code == 200:
                return response.json()
            logger.warning(f"Jupiter swap tx failed: {response.status_code}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Jupiter swap request error: {e}")
            return None
        except ValueError as e:  # Includes JSONDecodeError
            logger.error(f"Jupiter swap JSON decode error: {e}")
            return None

    async def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int,
        user_public_key: str = "",
    ) -> SwapQuote | None:
        """Get a swap quote from Jupiter."""
        quote_data = await self._fetch_quote(input_mint, output_mint, amount, slippage_bps)
        if quote_data is None:
            return None

        swap_tx = ""
        if user_public_key:
            swap_response = await self._fetch_swap_tx(quote_data, user_public_key)
            if swap_response:
                swap_tx = swap_response.get("swapTransaction", "")

        return SwapQuote(
            input_mint=quote_data["inputMint"],
            output_mint=quote_data["outputMint"],
            in_amount=int(quote_data["inAmount"]),
            out_amount=int(quote_data["outAmount"]),
            price_impact_pct=float(quote_data.get("priceImpactPct", 0)),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=QUOTE_TTL_SECONDS),
            route_plan=quote_data.get("routePlan", []),
            swap_transaction=swap_tx,
        )
