"""Wallet signature authentication."""

import os
import time
import uuid

from solders.pubkey import Pubkey
from solders.signature import Signature


class ChallengeExpiredError(Exception):
    """Challenge has expired."""

    pass


class InvalidSignatureError(Exception):
    """Signature verification failed."""

    pass


# In-memory challenge storage (use Redis in production)
_challenges: dict[str, str] = {}  # nonce -> wallet_address


def _get_ttl_minutes() -> int:
    """Get challenge TTL from environment."""
    return int(os.getenv("CHALLENGE_TTL_MINUTES", "5"))


def generate_challenge(wallet_address: str) -> str:
    """Generate a challenge string for wallet to sign."""
    nonce = str(uuid.uuid4())
    timestamp = int(time.time())

    # Store nonce for validation
    _challenges[nonce] = wallet_address

    return f"signalcomposer:{nonce}:{timestamp}"


def verify_signature(wallet_address: str, signature: str, challenge: str) -> bool:
    """
    Verify a signed challenge.

    Raises:
        ChallengeExpiredError: If challenge is too old
        InvalidSignatureError: If signature is invalid or nonce unknown
    """
    # Parse challenge
    parts = challenge.split(":")
    if len(parts) != 3 or parts[0] != "signalcomposer":
        raise InvalidSignatureError("Invalid challenge format")

    nonce = parts[1]
    timestamp = int(parts[2])

    # Check expiry
    ttl_seconds = _get_ttl_minutes() * 60
    if time.time() - timestamp > ttl_seconds:
        raise ChallengeExpiredError("Challenge has expired")

    # Check nonce exists and matches wallet
    if nonce not in _challenges:
        raise InvalidSignatureError("Invalid or already used nonce")

    if _challenges[nonce] != wallet_address:
        raise InvalidSignatureError("Challenge was issued to different wallet")

    # Remove nonce (single use)
    del _challenges[nonce]

    # Verify Ed25519 signature
    try:
        pubkey = Pubkey.from_string(wallet_address)
        sig = Signature.from_string(signature)
        message = challenge.encode("utf-8")

        if not sig.verify(pubkey, message):
            raise InvalidSignatureError("Signature verification failed")

    except Exception as e:
        if isinstance(e, (ChallengeExpiredError, InvalidSignatureError)):
            raise
        raise InvalidSignatureError(f"Signature verification failed: {e}") from e

    return True


def clear_challenges() -> None:
    """Clear all stored challenges (for testing)."""
    _challenges.clear()
