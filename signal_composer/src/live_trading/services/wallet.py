"""Wallet and keypair management."""

import base64
import os

import base58
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


class WalletService:
    """Manages wallet keypairs for signing transactions."""

    def __init__(self):
        self._keypair: bytes | None = None
        self._public_key: str | None = None

    @property
    def public_key(self) -> str | None:
        """Get the public key as base58 string."""
        return self._public_key

    def load_keypair(self, keypair_bytes: bytes) -> None:
        """Load a keypair from raw bytes (64 bytes: 32 secret + 32 public)."""
        if len(keypair_bytes) != 64:
            raise ValueError("Keypair must be 64 bytes")

        self._keypair = keypair_bytes
        # Public key is the last 32 bytes
        public_key_bytes = keypair_bytes[32:]
        self._public_key = base58.b58encode(public_key_bytes).decode("utf-8")

    def sign_message(self, message: bytes) -> bytes:
        """Sign a message with the loaded keypair."""
        if self._keypair is None:
            raise ValueError("No keypair loaded")

        # Import nacl for signing (Ed25519)
        try:
            from nacl.signing import SigningKey
        except ImportError:
            raise ImportError("PyNaCl required for signing: pip install pynacl")

        # First 32 bytes are the secret key
        secret_key = self._keypair[:32]
        signing_key = SigningKey(secret_key)
        signed = signing_key.sign(message)
        return signed.signature

    @staticmethod
    def encrypt_keypair(keypair_bytes: bytes, password: str) -> tuple[bytes, bytes]:
        """Encrypt a keypair with a password. Returns (encrypted_data, salt)."""
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        fernet = Fernet(key)
        encrypted = fernet.encrypt(keypair_bytes)
        return encrypted, salt

    @staticmethod
    def decrypt_keypair(encrypted_data: bytes, salt: bytes, password: str) -> bytes:
        """Decrypt a keypair with password."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        fernet = Fernet(key)
        return fernet.decrypt(encrypted_data)
