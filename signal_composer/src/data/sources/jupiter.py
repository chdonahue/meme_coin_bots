"""Jupiter API data source."""

from datetime import datetime, timezone
from typing import Any

import httpx

from .base import DataSource, PriceTick


class JupiterDataSource(DataSource):
    """Fetch price data from Jupiter API."""

    BASE_URL = "https://api.jup.ag/price/v2"

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "jupiter"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def _fetch_prices(self, tokens: list[str]) -> dict[str, Any]:
        """Fetch prices from Jupiter API."""
        client = await self._get_client()
        ids = ",".join(tokens)
        response = await client.get(f"{self.BASE_URL}?ids={ids}")
        response.raise_for_status()
        return response.json()

    async def get_price(self, token: str) -> PriceTick | None:
        """Get current price for a token."""
        prices = await self.get_prices([token])
        return prices.get(token)

    async def get_prices(self, tokens: list[str]) -> dict[str, PriceTick]:
        """Get current prices for multiple tokens."""
        if not tokens:
            return {}

        try:
            data = await self._fetch_prices(tokens)
        except httpx.HTTPError:
            return {}

        result = {}
        price_data = data.get("data", {})

        for token in tokens:
            if token in price_data and price_data[token]:
                price_str = price_data[token].get("price")
                if price_str:
                    result[token] = PriceTick(
                        token=token,
                        price=float(price_str),
                        volume=None,  # Jupiter doesn't provide volume
                        timestamp=datetime.now(timezone.utc),
                        source=self.name,
                    )

        return result

    async def health_check(self) -> bool:
        """Check if Jupiter API is available."""
        try:
            client = await self._get_client()
            # Use SOL as test token
            response = await client.get(
                f"{self.BASE_URL}?ids=So11111111111111111111111111111111111111112"
            )
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
