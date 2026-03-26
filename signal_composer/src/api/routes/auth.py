"""Authentication routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories import UserRepository
from src.api.dependencies import get_db_session
from src.api.schemas.auth import (
    ChallengeRequest,
    ChallengeResponse,
    VerifyRequest,
    TokenResponse,
)
from src.api.auth.wallet import (
    generate_challenge,
    verify_signature,
    ChallengeExpiredError,
    InvalidSignatureError,
)
from src.api.auth.jwt import create_access_token


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/challenge", response_model=ChallengeResponse)
async def request_challenge(request: ChallengeRequest) -> ChallengeResponse:
    """Generate a challenge for the wallet to sign."""
    challenge = generate_challenge(request.wallet_address)
    return ChallengeResponse(challenge=challenge)


@router.post("/verify", response_model=TokenResponse)
async def verify_and_get_token(
    request: VerifyRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    """Verify signed challenge and return JWT token."""
    try:
        verify_signature(
            wallet_address=request.wallet_address,
            signature=request.signature,
            challenge=request.challenge,
        )
    except ChallengeExpiredError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Challenge has expired",
        )
    except InvalidSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Get or create user
    repo = UserRepository(session)
    user = await repo.get_or_create(request.wallet_address)
    await session.commit()

    # Create JWT
    token = create_access_token(
        wallet_address=user.wallet_address,
        user_id=user.id,
    )

    return TokenResponse(access_token=token)
