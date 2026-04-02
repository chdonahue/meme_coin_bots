"""Tests for wallet encryption."""

import pytest
from src.wallets.encryption import encrypt_private_key, decrypt_private_key


def test_encrypt_decrypt_roundtrip():
    """Encrypted key can be decrypted back to original."""
    original = "4wBqpZM9k1Sz2LvXbhA9wJrMcPz5mZvNq3aJyR9Kx"
    encrypted = encrypt_private_key(original)
    decrypted = decrypt_private_key(encrypted)
    assert decrypted == original


def test_encrypted_differs_from_original():
    """Encrypted value should not equal original."""
    original = "4wBqpZM9k1Sz2LvXbhA9wJrMcPz5mZvNq3aJyR9Kx"
    encrypted = encrypt_private_key(original)
    assert encrypted != original.encode()


def test_decrypt_invalid_raises():
    """Decrypting invalid data raises error."""
    with pytest.raises(Exception):
        decrypt_private_key(b"invalid-encrypted-data")
