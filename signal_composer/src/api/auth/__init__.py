"""Authentication module."""

from .jwt import create_access_token, decode_access_token
from .wallet import generate_challenge, verify_signature

__all__ = ["create_access_token", "decode_access_token", "generate_challenge", "verify_signature"]
