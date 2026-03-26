"""Tests for JWT module."""

import pytest
from datetime import datetime, timezone, timedelta

from src.api.auth.jwt import create_access_token, decode_access_token, JWTError


class TestJWT:
    """Test JWT creation and validation."""

    def test_create_and_decode_token(self):
        """Create token and decode it."""
        token = create_access_token(wallet_address="abc123", user_id=1)

        payload = decode_access_token(token)

        assert payload["sub"] == "abc123"
        assert payload["user_id"] == 1

    def test_decode_expired_token_raises(self):
        """Expired token raises JWTError."""
        token = create_access_token(
            wallet_address="abc123",
            user_id=1,
            expires_delta=timedelta(seconds=-1),
        )

        with pytest.raises(JWTError):
            decode_access_token(token)

    def test_decode_invalid_token_raises(self):
        """Invalid token raises JWTError."""
        with pytest.raises(JWTError):
            decode_access_token("invalid.token.here")
