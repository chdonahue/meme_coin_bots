"""JWT token handling."""

import os
from datetime import datetime, timezone, timedelta

from jose import jwt, JWTError as JoseJWTError


class JWTError(Exception):
    """JWT validation error."""

    pass


def _get_secret() -> str:
    """Get JWT secret from environment."""
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise ValueError("JWT_SECRET environment variable must be set")
    return secret


def _get_expiry_hours() -> int:
    """Get JWT expiry hours from environment."""
    return int(os.getenv("JWT_EXPIRY_HOURS", "24"))


ALGORITHM = "HS256"


def create_access_token(
    wallet_address: str,
    user_id: int,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token."""
    if expires_delta is None:
        expires_delta = timedelta(hours=_get_expiry_hours())

    expire = datetime.now(timezone.utc) + expires_delta

    payload = {
        "sub": wallet_address,
        "user_id": user_id,
        "exp": expire,
    }

    return jwt.encode(payload, _get_secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=[ALGORITHM])
        return payload
    except JoseJWTError as e:
        raise JWTError(str(e)) from e
