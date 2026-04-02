"""Tests for keypair derivation from encrypted storage."""

import pytest
from base58 import b58encode
from solders.keypair import Keypair

from src.wallets.keypair import get_keypair
from src.wallets.encryption import encrypt_private_key


def test_get_keypair_from_seed():
    """Get keypair from 32-byte seed (from_seed path)."""
    # Generate a test keypair and get its seed
    original = Keypair()
    seed_bytes = bytes(original)[:32]
    seed_b58 = b58encode(seed_bytes).decode()

    # Encrypt and recover
    encrypted = encrypt_private_key(seed_b58)
    recovered = get_keypair(encrypted)

    assert str(recovered.pubkey()) == str(original.pubkey())


def test_get_keypair_from_full_bytes():
    """Get keypair from 64-byte full key (from_bytes path)."""
    original = Keypair()
    full_bytes = bytes(original)
    full_b58 = b58encode(full_bytes).decode()

    encrypted = encrypt_private_key(full_b58)
    recovered = get_keypair(encrypted)

    assert str(recovered.pubkey()) == str(original.pubkey())
