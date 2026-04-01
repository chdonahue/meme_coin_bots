"""Solana RPC services for transaction submission and monitoring."""

import httpx
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TxStatus(Enum):
    """Transaction confirmation status."""

    NOT_FOUND = "not_found"
    PROCESSING = "processing"
    CONFIRMED = "confirmed"
    FINALIZED = "finalized"
    FAILED = "failed"


@dataclass
class SubmitResult:
    """Result of transaction submission."""

    success: bool
    signature: str | None = None
    error: str | None = None


class TxSubmitter:
    """Submits transactions to Solana RPC."""

    def __init__(self, rpc_url: str, timeout: float = 30.0):
        self.rpc_url = rpc_url
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

    async def _send_transaction(self, tx_base64: str) -> str | None:
        """Send transaction to Solana RPC.

        Args:
            tx_base64: Base64 encoded signed transaction.

        Returns:
            Transaction signature if successful, None otherwise.
        """
        client = await self._get_client()
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sendTransaction",
            "params": [tx_base64, {"encoding": "base64", "skipPreflight": False}],
        }
        try:
            response = await client.post(self.rpc_url, json=payload)
            data = response.json()
            if "result" in data:
                return data["result"]
            if "error" in data:
                logger.error(f"RPC error: {data['error']}")
            return None
        except httpx.RequestError as e:
            logger.error(f"RPC request error: {e}")
            return None
        except ValueError as e:  # Includes JSONDecodeError
            logger.error(f"RPC JSON decode error: {e}")
            return None

    async def submit(self, signed_tx_base64: str) -> SubmitResult:
        """Submit a signed transaction to Solana.

        Args:
            signed_tx_base64: Base64 encoded signed transaction.

        Returns:
            SubmitResult with success status and signature or error.
        """
        signature = await self._send_transaction(signed_tx_base64)
        if signature:
            return SubmitResult(success=True, signature=signature)
        return SubmitResult(success=False, error="Failed to submit transaction")


class ConfirmMonitor:
    """Monitors transaction confirmation status."""

    def __init__(self, rpc_url: str, timeout: float = 10.0):
        self.rpc_url = rpc_url
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

    async def _get_signature_status(self, signature: str) -> dict[str, Any] | None:
        """Get signature status from Solana RPC.

        Args:
            signature: Transaction signature to check.

        Returns:
            Status dict if found, None otherwise.
        """
        client = await self._get_client()
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignatureStatuses",
            "params": [[signature]],
        }
        try:
            response = await client.post(self.rpc_url, json=payload)
            data = response.json()
            if "result" in data and data["result"]["value"]:
                value = data["result"]["value"][0]
                if value is not None:
                    return value
            return None
        except httpx.RequestError as e:
            logger.error(f"RPC request error: {e}")
            return None
        except ValueError as e:  # Includes JSONDecodeError
            logger.error(f"RPC JSON decode error: {e}")
            return None

    async def check_status(self, signature: str) -> TxStatus:
        """Check the confirmation status of a transaction.

        Args:
            signature: Transaction signature to check.

        Returns:
            TxStatus indicating the confirmation state.
        """
        status_data = await self._get_signature_status(signature)

        if status_data is None:
            return TxStatus.NOT_FOUND

        if status_data.get("err"):
            return TxStatus.FAILED

        confirmation = status_data.get("confirmationStatus")
        if confirmation == "finalized":
            return TxStatus.FINALIZED
        elif confirmation == "confirmed":
            return TxStatus.CONFIRMED
        elif confirmation == "processed":
            return TxStatus.PROCESSING

        return TxStatus.NOT_FOUND
