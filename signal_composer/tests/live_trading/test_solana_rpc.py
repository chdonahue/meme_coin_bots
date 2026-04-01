"""Tests for Solana RPC services."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from src.live_trading.services.solana_rpc import TxSubmitter, ConfirmMonitor, TxStatus, SubmitResult


class TestTxStatus:
    """Tests for TxStatus enum."""

    def test_all_status_values_exist(self):
        """Verify all expected status values exist."""
        assert TxStatus.NOT_FOUND.value == "not_found"
        assert TxStatus.PROCESSING.value == "processing"
        assert TxStatus.CONFIRMED.value == "confirmed"
        assert TxStatus.FINALIZED.value == "finalized"
        assert TxStatus.FAILED.value == "failed"


class TestSubmitResult:
    """Tests for SubmitResult dataclass."""

    def test_submit_result_success(self):
        """Test successful submit result."""
        result = SubmitResult(
            success=True,
            signature="5VERv8NMvzbJMEkV8xnrLkEaWRtSz9CosKDYjCJjBRnbJLgp8uirBgmQpjKhoR4tjF3ZpRzrFmBV6UjKdiSZkQUW",
        )
        assert result.success
        assert result.signature is not None
        assert result.error is None

    def test_submit_result_failure(self):
        """Test failed submit result."""
        result = SubmitResult(
            success=False,
            error="Transaction failed",
        )
        assert not result.success
        assert result.signature is None
        assert result.error == "Transaction failed"


class TestTxSubmitter:
    """Tests for TxSubmitter."""

    @pytest.fixture
    def submitter(self):
        """Create TxSubmitter."""
        return TxSubmitter(rpc_url="https://api.mainnet-beta.solana.com")

    @pytest.mark.asyncio
    async def test_submit_transaction_success(self, submitter):
        """Test successful transaction submission."""
        mock_signature = "5VERv8NMvzbJMEkV8xnrLkEaWRtSz9CosKDYjCJjBRnbJLgp8uirBgmQpjKhoR4tjF3ZpRzrFmBV6UjKdiSZkQUW"

        with patch.object(submitter, "_send_transaction", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = mock_signature

            result = await submitter.submit(signed_tx_base64="signed_transaction_base64")

            assert result.signature == mock_signature
            assert result.success

    @pytest.mark.asyncio
    async def test_submit_transaction_failure(self, submitter):
        """Test failed transaction submission."""
        with patch.object(submitter, "_send_transaction", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = None

            result = await submitter.submit(signed_tx_base64="invalid_transaction")

            assert not result.success
            assert result.signature is None

    @pytest.mark.asyncio
    async def test_send_transaction_rpc_success(self, submitter):
        """Test _send_transaction with successful RPC response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": "5VERv8NMvzbJMEkV8xnrLkEaWRtSz9CosKDYjCJjBRnbJLgp8uirBgmQpjKhoR4tjF3ZpRzrFmBV6UjKdiSZkQUW",
        }

        with patch.object(submitter, "_get_client", new_callable=AsyncMock) as mock_client_getter:
            mock_client = AsyncMock()
            mock_client_getter.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await submitter._send_transaction("signed_tx_base64")

            assert (
                result
                == "5VERv8NMvzbJMEkV8xnrLkEaWRtSz9CosKDYjCJjBRnbJLgp8uirBgmQpjKhoR4tjF3ZpRzrFmBV6UjKdiSZkQUW"
            )

    @pytest.mark.asyncio
    async def test_send_transaction_rpc_error(self, submitter):
        """Test _send_transaction with RPC error response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32600, "message": "Invalid Request"},
        }

        with patch.object(submitter, "_get_client", new_callable=AsyncMock) as mock_client_getter:
            mock_client = AsyncMock()
            mock_client_getter.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await submitter._send_transaction("invalid_tx")

            assert result is None

    @pytest.mark.asyncio
    async def test_send_transaction_request_error(self, submitter):
        """Test _send_transaction handles request errors."""
        with patch.object(submitter, "_get_client", new_callable=AsyncMock) as mock_client_getter:
            mock_client = AsyncMock()
            mock_client_getter.return_value = mock_client
            mock_client.post.side_effect = httpx.RequestError("Connection failed")

            result = await submitter._send_transaction("signed_tx_base64")

            assert result is None

    @pytest.mark.asyncio
    async def test_send_transaction_json_decode_error(self, submitter):
        """Test _send_transaction handles JSON decode errors."""
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")

        with patch.object(submitter, "_get_client", new_callable=AsyncMock) as mock_client_getter:
            mock_client = AsyncMock()
            mock_client_getter.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await submitter._send_transaction("signed_tx_base64")

            assert result is None

    @pytest.mark.asyncio
    async def test_close_client(self, submitter):
        """Test closing the HTTP client."""
        # First create a client
        await submitter._get_client()
        assert submitter._client is not None

        # Close it
        await submitter.close()
        assert submitter._client is None


class TestConfirmMonitor:
    """Tests for ConfirmMonitor."""

    @pytest.fixture
    def monitor(self):
        """Create ConfirmMonitor."""
        return ConfirmMonitor(rpc_url="https://api.mainnet-beta.solana.com")

    @pytest.mark.asyncio
    async def test_check_status_confirmed(self, monitor):
        """Test checking confirmed transaction."""
        signature = "5VERv8NMvzbJMEkV8xnrLkEaWRtSz9CosKDYjCJjBRnbJLgp8uirBgmQpjKhoR4tjF3ZpRzrFmBV6UjKdiSZkQUW"

        with patch.object(monitor, "_get_signature_status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = {
                "confirmationStatus": "confirmed",
                "err": None,
            }

            status = await monitor.check_status(signature)

            assert status == TxStatus.CONFIRMED

    @pytest.mark.asyncio
    async def test_check_status_finalized(self, monitor):
        """Test checking finalized transaction."""
        signature = "5VERv8NMvzbJMEkV8xnrLkEaWRtSz9CosKDYjCJjBRnbJLgp8uirBgmQpjKhoR4tjF3ZpRzrFmBV6UjKdiSZkQUW"

        with patch.object(monitor, "_get_signature_status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = {
                "confirmationStatus": "finalized",
                "err": None,
            }

            status = await monitor.check_status(signature)

            assert status == TxStatus.FINALIZED

    @pytest.mark.asyncio
    async def test_check_status_processing(self, monitor):
        """Test checking processing transaction."""
        signature = "5VERv8NMvzbJMEkV8xnrLkEaWRtSz9CosKDYjCJjBRnbJLgp8uirBgmQpjKhoR4tjF3ZpRzrFmBV6UjKdiSZkQUW"

        with patch.object(monitor, "_get_signature_status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = {
                "confirmationStatus": "processed",
                "err": None,
            }

            status = await monitor.check_status(signature)

            assert status == TxStatus.PROCESSING

    @pytest.mark.asyncio
    async def test_check_status_not_found(self, monitor):
        """Test checking non-existent transaction."""
        signature = "invalid_signature"

        with patch.object(monitor, "_get_signature_status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = None

            status = await monitor.check_status(signature)

            assert status == TxStatus.NOT_FOUND

    @pytest.mark.asyncio
    async def test_check_status_failed(self, monitor):
        """Test checking failed transaction."""
        signature = "5VERv8NMvzbJMEkV8xnrLkEaWRtSz9CosKDYjCJjBRnbJLgp8uirBgmQpjKhoR4tjF3ZpRzrFmBV6UjKdiSZkQUW"

        with patch.object(monitor, "_get_signature_status", new_callable=AsyncMock) as mock_status:
            mock_status.return_value = {
                "confirmationStatus": "confirmed",
                "err": {"InstructionError": [0, "Custom"]},
            }

            status = await monitor.check_status(signature)

            assert status == TxStatus.FAILED

    @pytest.mark.asyncio
    async def test_get_signature_status_success(self, monitor):
        """Test _get_signature_status with successful RPC response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "context": {"slot": 123456},
                "value": [
                    {
                        "confirmationStatus": "confirmed",
                        "err": None,
                    }
                ],
            },
        }

        with patch.object(monitor, "_get_client", new_callable=AsyncMock) as mock_client_getter:
            mock_client = AsyncMock()
            mock_client_getter.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await monitor._get_signature_status("some_signature")

            assert result == {"confirmationStatus": "confirmed", "err": None}

    @pytest.mark.asyncio
    async def test_get_signature_status_not_found(self, monitor):
        """Test _get_signature_status when transaction not found."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "context": {"slot": 123456},
                "value": [None],
            },
        }

        with patch.object(monitor, "_get_client", new_callable=AsyncMock) as mock_client_getter:
            mock_client = AsyncMock()
            mock_client_getter.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await monitor._get_signature_status("nonexistent_signature")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_signature_status_request_error(self, monitor):
        """Test _get_signature_status handles request errors."""
        with patch.object(monitor, "_get_client", new_callable=AsyncMock) as mock_client_getter:
            mock_client = AsyncMock()
            mock_client_getter.return_value = mock_client
            mock_client.post.side_effect = httpx.RequestError("Connection failed")

            result = await monitor._get_signature_status("some_signature")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_signature_status_json_decode_error(self, monitor):
        """Test _get_signature_status handles JSON decode errors."""
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")

        with patch.object(monitor, "_get_client", new_callable=AsyncMock) as mock_client_getter:
            mock_client = AsyncMock()
            mock_client_getter.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await monitor._get_signature_status("some_signature")

            assert result is None

    @pytest.mark.asyncio
    async def test_close_client(self, monitor):
        """Test closing the HTTP client."""
        # First create a client
        await monitor._get_client()
        assert monitor._client is not None

        # Close it
        await monitor.close()
        assert monitor._client is None

    @pytest.mark.asyncio
    async def test_get_signature_status_empty_value_list(self, monitor):
        """Test _get_signature_status with empty value list."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "context": {"slot": 123456},
                "value": [],
            },
        }

        with patch.object(monitor, "_get_client", new_callable=AsyncMock) as mock_client_getter:
            mock_client = AsyncMock()
            mock_client_getter.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = await monitor._get_signature_status("some_signature")

            assert result is None
