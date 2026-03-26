"""Authentication schemas."""

from pydantic import BaseModel


class ChallengeRequest(BaseModel):
    """Request a challenge to sign."""

    wallet_address: str


class ChallengeResponse(BaseModel):
    """Challenge for wallet to sign."""

    challenge: str


class VerifyRequest(BaseModel):
    """Verify signed challenge."""

    wallet_address: str
    signature: str
    challenge: str


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str
    token_type: str = "bearer"
