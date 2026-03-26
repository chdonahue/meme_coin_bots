"""Tests for auth routes."""

import pytest
from unittest.mock import patch


class TestAuthChallenge:
    """Test /auth/challenge endpoint."""

    def test_challenge_returns_challenge_string(self, client):
        """Challenge endpoint returns challenge."""
        response = client.post(
            "/auth/challenge",
            json={"wallet_address": "SomeWallet123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "challenge" in data
        assert data["challenge"].startswith("signalcomposer:")


class TestAuthVerify:
    """Test /auth/verify endpoint."""

    def test_verify_with_invalid_signature_returns_400(self, client):
        """Invalid signature returns 400."""
        # First get a challenge
        challenge_resp = client.post(
            "/auth/challenge",
            json={"wallet_address": "SomeWallet123"},
        )
        challenge = challenge_resp.json()["challenge"]

        # Try to verify with invalid signature
        response = client.post(
            "/auth/verify",
            json={
                "wallet_address": "SomeWallet123",
                "signature": "invalid_signature",
                "challenge": challenge,
            },
        )

        assert response.status_code == 400

    def test_verify_with_expired_challenge_returns_400(self, client):
        """Expired challenge returns 400."""
        import time

        old_challenge = f"signalcomposer:old_nonce:{int(time.time()) - 600}"

        response = client.post(
            "/auth/verify",
            json={
                "wallet_address": "SomeWallet123",
                "signature": "some_sig",
                "challenge": old_challenge,
            },
        )

        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()
