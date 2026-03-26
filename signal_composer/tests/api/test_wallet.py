"""Tests for wallet authentication."""

import pytest
import time
from unittest.mock import patch

from src.api.auth.wallet import (
    generate_challenge,
    verify_signature,
    ChallengeExpiredError,
    InvalidSignatureError,
)


class TestGenerateChallenge:
    """Test challenge generation."""

    def test_generate_challenge_format(self):
        """Challenge has correct format."""
        challenge = generate_challenge("wallet123")

        assert challenge.startswith("signalcomposer:")
        parts = challenge.split(":")
        assert len(parts) == 3

    def test_generate_challenge_stores_nonce(self):
        """Challenge nonce is stored for validation."""
        from src.api.auth.wallet import _challenges

        wallet = "wallet_abc"
        challenge = generate_challenge(wallet)
        nonce = challenge.split(":")[1]

        assert nonce in _challenges


class TestVerifySignature:
    """Test signature verification."""

    def test_verify_expired_challenge_raises(self):
        """Expired challenge raises error."""
        # Create challenge with old timestamp
        old_time = int(time.time()) - 600  # 10 minutes ago
        challenge = f"signalcomposer:nonce123:{old_time}"

        with pytest.raises(ChallengeExpiredError):
            verify_signature("wallet", "signature", challenge)

    def test_verify_invalid_nonce_raises(self):
        """Unknown nonce raises error."""
        current_time = int(time.time())
        challenge = f"signalcomposer:unknown_nonce:{current_time}"

        with pytest.raises(InvalidSignatureError, match="nonce"):
            verify_signature("wallet", "signature", challenge)
