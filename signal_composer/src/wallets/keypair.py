"""Keypair utilities for wallet management."""

from base58 import b58decode
from solders.keypair import Keypair

from .encryption import decrypt_private_key


def get_keypair(encrypted: bytes) -> Keypair:
    """Get usable Keypair from encrypted storage.

    Handles both 32-byte seeds and 64-byte full keypairs.
    """
    private_key_b58 = decrypt_private_key(encrypted)
    key_bytes = b58decode(private_key_b58)

    if len(key_bytes) == 32:
        return Keypair.from_seed(key_bytes)
    elif len(key_bytes) == 64:
        return Keypair.from_bytes(key_bytes)
    else:
        raise ValueError(f"Invalid key length: {len(key_bytes)} bytes (expected 32 or 64)")
