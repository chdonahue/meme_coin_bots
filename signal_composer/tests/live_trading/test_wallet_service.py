"""Tests for WalletService."""

import pytest
from unittest.mock import MagicMock
from src.live_trading.services.wallet import WalletService


class TestWalletService:
    """Tests for WalletService."""

    def test_sign_transaction(self):
        """Test signing a transaction."""
        # Using a test keypair (DO NOT use in production)
        test_keypair_bytes = bytes(
            [
                174,
                47,
                154,
                16,
                202,
                193,
                206,
                113,
                199,
                190,
                53,
                133,
                169,
                175,
                31,
                56,
                222,
                53,
                138,
                189,
                224,
                216,
                117,
                173,
                10,
                149,
                53,
                45,
                73,
                251,
                237,
                246,
                15,
                23,
                189,
                78,
                100,
                132,
                190,
                231,
                63,
                64,
                195,
                57,
                48,
                63,
                154,
                79,
                180,
                237,
                64,
                21,
                3,
                15,
                176,
                128,
                196,
                75,
                92,
                35,
                220,
                131,
                189,
                83,
            ]
        )

        service = WalletService()
        service.load_keypair(test_keypair_bytes)

        assert service.public_key is not None
        assert len(service.public_key) == 44  # Base58 encoded

    def test_no_keypair_loaded(self):
        """Test error when no keypair loaded."""
        service = WalletService()

        with pytest.raises(ValueError, match="No keypair loaded"):
            service.sign_message(b"test")

    def test_invalid_keypair_length(self):
        """Test error with invalid keypair length."""
        service = WalletService()

        with pytest.raises(ValueError, match="Keypair must be 64 bytes"):
            service.load_keypair(b"too_short")

    def test_sign_message(self):
        """Test signing a message returns valid signature."""
        test_keypair_bytes = bytes(
            [
                174,
                47,
                154,
                16,
                202,
                193,
                206,
                113,
                199,
                190,
                53,
                133,
                169,
                175,
                31,
                56,
                222,
                53,
                138,
                189,
                224,
                216,
                117,
                173,
                10,
                149,
                53,
                45,
                73,
                251,
                237,
                246,
                15,
                23,
                189,
                78,
                100,
                132,
                190,
                231,
                63,
                64,
                195,
                57,
                48,
                63,
                154,
                79,
                180,
                237,
                64,
                21,
                3,
                15,
                176,
                128,
                196,
                75,
                92,
                35,
                220,
                131,
                189,
                83,
            ]
        )

        service = WalletService()
        service.load_keypair(test_keypair_bytes)

        message = b"test message"
        signature = service.sign_message(message)

        # Ed25519 signatures are 64 bytes
        assert len(signature) == 64

    def test_encrypt_decrypt_round_trip(self):
        """Test encrypting and decrypting keypair."""
        test_keypair_bytes = bytes(
            [
                174,
                47,
                154,
                16,
                202,
                193,
                206,
                113,
                199,
                190,
                53,
                133,
                169,
                175,
                31,
                56,
                222,
                53,
                138,
                189,
                224,
                216,
                117,
                173,
                10,
                149,
                53,
                45,
                73,
                251,
                237,
                246,
                15,
                23,
                189,
                78,
                100,
                132,
                190,
                231,
                63,
                64,
                195,
                57,
                48,
                63,
                154,
                79,
                180,
                237,
                64,
                21,
                3,
                15,
                176,
                128,
                196,
                75,
                92,
                35,
                220,
                131,
                189,
                83,
            ]
        )

        password = "test_password_123"

        encrypted, salt = WalletService.encrypt_keypair(test_keypair_bytes, password)
        decrypted = WalletService.decrypt_keypair(encrypted, salt, password)

        assert decrypted == test_keypair_bytes

    def test_decrypt_wrong_password(self):
        """Test decryption with wrong password fails."""
        test_keypair_bytes = bytes(
            [
                174,
                47,
                154,
                16,
                202,
                193,
                206,
                113,
                199,
                190,
                53,
                133,
                169,
                175,
                31,
                56,
                222,
                53,
                138,
                189,
                224,
                216,
                117,
                173,
                10,
                149,
                53,
                45,
                73,
                251,
                237,
                246,
                15,
                23,
                189,
                78,
                100,
                132,
                190,
                231,
                63,
                64,
                195,
                57,
                48,
                63,
                154,
                79,
                180,
                237,
                64,
                21,
                3,
                15,
                176,
                128,
                196,
                75,
                92,
                35,
                220,
                131,
                189,
                83,
            ]
        )

        password = "correct_password"
        wrong_password = "wrong_password"

        encrypted, salt = WalletService.encrypt_keypair(test_keypair_bytes, password)

        # Decrypting with wrong password should raise an error
        from cryptography.fernet import InvalidToken

        with pytest.raises(InvalidToken):
            WalletService.decrypt_keypair(encrypted, salt, wrong_password)

    def test_public_key_none_initially(self):
        """Test public_key is None before loading keypair."""
        service = WalletService()
        assert service.public_key is None

    def test_signature_verification(self):
        """Test that signature can be verified with public key."""
        # Generate a valid keypair where public key matches secret key
        from nacl.signing import SigningKey

        sk = SigningKey.generate()
        # Create 64-byte keypair: 32 secret + 32 public
        valid_keypair_bytes = bytes(sk) + bytes(sk.verify_key)

        service = WalletService()
        service.load_keypair(valid_keypair_bytes)

        message = b"verify this message"
        signature = service.sign_message(message)

        # Verify the signature using nacl
        from nacl.signing import VerifyKey

        public_key_bytes = valid_keypair_bytes[32:]
        verify_key = VerifyKey(public_key_bytes)

        # Should not raise an exception
        verify_key.verify(message, signature)
