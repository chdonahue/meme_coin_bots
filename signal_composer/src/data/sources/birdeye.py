"""Birdeye API data source."""

import os
from datetime import datetime, timezone
from typing import Any

import httpx

from .base import DataSource, PriceTick, OHLCV


class BirdeyeDataSource(DataSource):
    """Fetch price and OHLCV data from Birdeye API."""

    BASE_URL = "https://public-api.birdeye.so"

    def __init__(self, api_key: str | None = None, timeout: float = 10.0):
        self.api_key = api_key or os.getenv("BIRDEYE_API_KEY", "")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "birdeye"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"X-API-KEY": self.api_key} if self.api_key else {}
            self._client = httpx.AsyncClient(timeout=self.timeout, headers=headers)
        return self._client

    async def _fetch_price(self, token: str) -> dict[str, Any]:
        """Fetch price from Birdeye API."""
        client = await self._get_client()
        response = await client.get(f"{self.BASE_URL}/defi/price", params={"address": token})
        response.raise_for_status()
        return response.json()

    async def _fetch_ohlcv(self, token: str, interval: str, limit: int) -> dict[str, Any]:
        """Fetch OHLCV from Birdeye API."""
        client = await self._get_client()
        response = await client.get(
            f"{self.BASE_URL}/defi/ohlcv",
            params={
                "address": token,
                "type": interval,
                "limit": limit,
            },
        )
        response.raise_for_status()
        return response.json()

    async def get_price(self, token: str) -> PriceTick | None:
        """Get current price for a token."""
        try:
            data = await self._fetch_price(token)
            if not data.get("success") or not data.get("data"):
                return None

            price_data = data["data"]
            return PriceTick(
                token=token,
                price=float(price_data["value"]),
                volume=None,
                timestamp=datetime.fromtimestamp(
                    price_data.get("updateUnixTime", datetime.now(timezone.utc).timestamp()),
                    tz=timezone.utc,
                ),
                source=self.name,
            )
        except Exception:
            return None

    async def get_prices(self, tokens: list[str]) -> dict[str, PriceTick]:
        """Get current prices for multiple tokens."""
        result = {}
        for token in tokens:
            tick = await self.get_price(token)
            if tick:
                result[token] = tick
        return result

    async def get_ohlcv(self, token: str, interval: str = "1m", limit: int = 100) -> list[OHLCV]:
        """
        Get OHLCV candle data.

        Args:
            token: Token mint address
            interval: Candle interval (1m, 5m, 15m, 1H, 4H, 1D)
            limit: Number of candles to fetch

        Returns:
            List of OHLCV candles
        """
        try:
            data = await self._fetch_ohlcv(token, interval, limit)
            if not data.get("success") or not data.get("data"):
                return []

            items = data["data"].get("items", [])
            return [
                OHLCV(
                    token=token,
                    open=float(item["o"]),
                    high=float(item["h"]),
                    low=float(item["l"]),
                    close=float(item["c"]),
                    volume=float(item["v"]),
                    timestamp=datetime.fromtimestamp(item["unixTime"], tz=timezone.utc),
                    source=self.name,
                )
                for item in items
            ]
        except Exception:
            return []

    async def health_check(self) -> bool:
        """Check if Birdeye API is available."""
        try:
            tick = await self.get_price("So11111111111111111111111111111111111111112")
            return tick is not None
        except Exception:
            return False

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
