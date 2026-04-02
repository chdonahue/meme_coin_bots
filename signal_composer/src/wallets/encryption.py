"""Encryption utilities for wallet private keys."""

import os
from cryptography.fernet import Fernet


def _get_fernet() -> Fernet:
    """Get Fernet instance with platform key."""
    key = os.getenv("WALLET_ENCRYPTION_KEY")
    if not key:
        raise ValueError("WALLET_ENCRYPTION_KEY environment variable not set")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_private_key(private_key_b58: str) -> bytes:
    """Encrypt a base58-encoded private key."""
    return _get_fernet().encrypt(private_key_b58.encode())


def decrypt_private_key(encrypted: bytes) -> str:
    """Decrypt to base58-encoded private key."""
    return _get_fernet().decrypt(encrypted).decode()
